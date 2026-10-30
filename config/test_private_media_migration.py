import copy
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from cloudinary.exceptions import NotFound
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from config.private_media_migration import MigrationConflict, check_exposed_urls, inventory, migrate_record


def record(resource='raw', namespace='verification_documents/', delivery='upload'):
    return dict(asset_id='immutable-asset', public_id='media/' + namespace + 'proof',
                resource_type=resource, bytes=128, etag='original-checksum', delivery_type=delivery, state='planned')


class Provider:
    def __init__(self, row):
        self.assets = {(row['resource_type'], row['delivery_type'], row['public_id']): copy.deepcopy(row)}
        self.rename = Mock(side_effect=self.move)

    def resource(self, public_id, resource_type, type):
        key = resource_type, type, public_id
        if key not in self.assets:
            raise NotFound('fixture missing')
        return self.assets[key]

    def move(self, source, target, **options):
        assert source == target
        key = options['resource_type'], options['type'], source
        asset = self.assets.pop(key)
        self.assets[(options['resource_type'], options['to_type'], target)] = asset
        return copy.deepcopy(asset)


class PrivateMediaMigrationTests(SimpleTestCase):
    def test_in_place_move_preserves_identity_bytes_names_and_invalidates_all_resources(self):
        for resource in ('raw', 'image', 'video'):
            for source_type in ('upload', 'private'):
                with self.subTest(resource=resource, type=source_type):
                    row = record(resource, delivery=source_type); provider = Provider(row); checkpoints = []
                    migrate_record(provider, provider, row, 'media', lambda: checkpoints.append(row['state']))
                    self.assertEqual(checkpoints, ['moving', 'origin_private_cdn_pending'])
                    provider.rename.assert_called_once_with(row['public_id'], row['public_id'], resource_type=resource,
                        type=source_type, to_type='authenticated', overwrite=False, invalidate=True)
                    self.assertEqual(provider.resource(row['public_id'], resource, 'authenticated')['etag'], 'original-checksum')
                    with self.assertRaises(NotFound):
                        provider.resource(row['public_id'], resource, source_type)

    def test_all_private_namespaces_are_eligible_and_public_profiles_are_never_moved(self):
        from config.media_storage import PlaybackMediaStorage
        for namespace in PlaybackMediaStorage.PRIVATE_PREFIXES:
            row = record(namespace=namespace); provider = Provider(row)
            migrate_record(provider, provider, row, 'media', lambda: None)
            self.assertEqual(row['state'], 'origin_private_cdn_pending')
        for namespace in ('organizations/logos/', 'profiles/', 'verification_documents/../profiles/'):
            row = record(namespace=namespace); provider = Provider(row)
            with self.assertRaises(MigrationConflict):
                migrate_record(provider, provider, row, 'media', lambda: None)
            provider.rename.assert_not_called()

    def test_changed_source_and_existing_destination_refuse_overwrite(self):
        for conflict in ('source', 'target'):
            row = record(); provider = Provider(row)
            if conflict == 'source':
                next(iter(provider.assets.values()))['etag'] = 'different-bytes'
            else:
                provider.assets[('raw', 'authenticated', row['public_id'])] = {**row, 'asset_id': 'other-file'}
            with self.assertRaises(MigrationConflict):
                migrate_record(provider, provider, row, 'media', lambda: None)
            provider.rename.assert_not_called()

    def test_resume_after_provider_success_and_lost_reply_never_moves_twice(self):
        row = record(); provider = Provider(row)
        def lost_reply(*args, **kwargs):
            provider.move(*args, **kwargs)
            raise TimeoutError('lost reply')
        provider.rename.side_effect = lost_reply
        with self.assertRaises(TimeoutError):
            migrate_record(provider, provider, row, 'media', lambda: None)
        self.assertEqual(row['state'], 'moving')
        migrate_record(provider, provider, row, 'media', lambda: None)
        self.assertEqual(row['state'], 'origin_private_cdn_pending')
        self.assertEqual(provider.rename.call_count, 1)

    def test_wrong_identity_after_move_stops_without_deleting_either_file(self):
        row = record(); provider = Provider(row)
        def corrupt_metadata(*args, **kwargs):
            provider.move(*args, **kwargs)
            next(iter(provider.assets.values()))['bytes'] = 1
        provider.rename.side_effect = corrupt_metadata
        with self.assertRaises(MigrationConflict):
            migrate_record(provider, provider, row, 'media', lambda: None)
        self.assertEqual(len(provider.assets), 1)
        self.assertEqual(row['state'], 'moving')

    def test_checkpoint_failure_prevents_provider_mutation(self):
        row = record(); provider = Provider(row)
        with self.assertRaises(OSError):
            migrate_record(provider, provider, row, 'media', Mock(side_effect=OSError('disk full')))
        provider.rename.assert_not_called()

    def test_inventory_paginates_both_legacy_types_and_includes_orphans(self):
        api = Mock()
        first = record(); second = {**first, 'public_id': first['public_id'] + '2', 'asset_id': 'orphan'}
        def pages(**options):
            if options['resource_type'] == 'raw' and options['type'] == 'upload':
                return {'resources': [{**second, 'type': 'upload'}]} if options.get('next_cursor') else {
                    'resources': [{**first, 'type': 'upload'}], 'next_cursor': 'next'}
            return {'resources': []}
        api.resources.side_effect = pages
        rows = list(inventory(api, 'media', ['verification_documents/']))
        self.assertEqual([row['asset_id'] for row in rows], ['immutable-asset', 'orphan'])
        self.assertTrue(any(call.kwargs['type'] == 'private' for call in api.resources.call_args_list))

    def test_inventory_missing_checksum_and_scope_escape_fail_closed(self):
        for value in ({**record(), 'etag': None}, record(namespace='profiles/')):
            api = Mock(); api.resources.return_value = {'resources': [{**value, 'type': 'upload'}]}
            with self.assertRaises(MigrationConflict):
                list(inventory(api, 'media', ['verification_documents/']))

    def test_provider_errors_are_not_treated_as_absent_files(self):
        row = record(); provider = Mock(); provider.resource.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            migrate_record(provider, provider, row, 'media', lambda: None)
        provider.rename.assert_not_called()

    def test_exposed_url_checks_detect_cached_bytes_and_never_follow_redirects(self):
        row = record(); provider = Provider(row)
        migrate_record(provider, provider, row, 'media', lambda: None)
        session = Mock()
        responses = [Mock(status_code=value) for value in (200, 206, 302, 500, 404, 403)]
        session.get.side_effect = responses
        url = 'https://res.cloudinary.com/fixture-cloud/raw/upload/v123/' + row['public_id']
        checks = check_exposed_urls(provider, session, [row], 'fixture-cloud', [url] * 6)
        self.assertEqual([value['denied'] for value in checks], [False, False, False, False, True, True])
        for call in session.get.call_args_list:
            self.assertFalse(call.kwargs['allow_redirects'])
            self.assertNotIn('Authorization', call.kwargs['headers'])
        for response in responses:
            response.close.assert_called_once()

    def test_cdn_checks_validate_entire_list_before_network_and_reject_ssrf_or_unrelated_assets(self):
        row = {**record(), 'state': 'origin_private_cdn_pending'}
        good = 'https://res.cloudinary.com/fixture-cloud/raw/upload/' + row['public_id']
        for url in ('https://localhost/private', good.replace('https:', 'http:'),
                    good.replace('fixture-cloud', 'other-cloud'), good.replace('/proof', '/different'),
                    good.replace('res.cloudinary.com', 'user:password@res.cloudinary.com'),
                    good.replace('res.cloudinary.com', 'res.cloudinary.com:8443')):
            api, session = Mock(), Mock()
            with self.assertRaises(MigrationConflict):
                check_exposed_urls(api, session, [row], 'fixture-cloud', [good, url])
            api.resource.assert_not_called(); session.get.assert_not_called()

    def test_cdn_checks_accept_original_and_transformed_versioned_image_urls(self):
        row = record('image'); provider = Provider(row)
        migrate_record(provider, provider, row, 'media', lambda: None)
        session = Mock(); session.get.return_value.status_code = 404
        urls = ['https://res.cloudinary.com/fixture-cloud/image/upload/' + value + row['public_id'] + '.jpg'
                for value in ('', 'v123/', 'c_fill,w_100/v123/')]
        self.assertTrue(all(value['denied'] for value in check_exposed_urls(provider, session, [row], 'fixture-cloud', urls)))

    def test_cdn_check_stops_if_original_is_republished(self):
        row = record(); provider = Provider(row)
        migrate_record(provider, provider, row, 'media', lambda: None)
        provider.assets[('raw', 'upload', row['public_id'])] = dict(row)
        session = Mock()
        with self.assertRaises(MigrationConflict):
            check_exposed_urls(provider, session, [row], 'fixture-cloud',
                ['https://res.cloudinary.com/fixture-cloud/raw/upload/' + row['public_id']])
        session.get.assert_not_called()

    def test_repeating_provider_cursor_cannot_loop_forever(self):
        api = Mock(); api.resources.return_value = {'resources': [], 'next_cursor': 'repeated'}
        with self.assertRaises(MigrationConflict):
            list(inventory(api, 'media', ['verification_documents/']))
        self.assertEqual(api.resources.call_count, 2)

    @patch('talents.management.commands.privatize_media.cloudinary.config')
    @patch('talents.management.commands.privatize_media.PlaybackMediaStorage._get_prefix', return_value='media/')
    @patch('talents.management.commands.privatize_media.api')
    @patch('talents.management.commands.privatize_media.uploader')
    def test_command_plan_apply_limit_resume_and_safe_manifest(self, uploader, api, prefix, config):
        config.return_value.cloud_name = 'fixture-cloud'
        rows = [record(), {**record(), 'public_id': 'media/verification_documents/second', 'asset_id': 'second'}]
        providers = [Provider(row) for row in rows]
        def lookup(name, **kwargs):
            return providers[0 if name == rows[0]['public_id'] else 1].resource(name, **kwargs)
        api.resource.side_effect = lookup
        uploader.rename.side_effect = lambda name, target, **kwargs: providers[0 if name == rows[0]['public_id'] else 1].move(name, target, **kwargs)
        with tempfile.TemporaryDirectory() as directory, patch('talents.management.commands.privatize_media.inventory', return_value=iter(rows)):
            path = Path(directory) / 'manifest.json'
            args = dict(manifest=str(path), cloud_name='fixture-cloud', stdout=StringIO())
            call_command('privatize_media', **args)
            uploader.rename.assert_not_called()
            self.assertEqual(json.loads(path.read_text())['assets'][0]['state'], 'planned')
            call_command('privatize_media', apply=True, limit=1, **args)
            call_command('privatize_media', apply=True, limit=1, **args)
            call_command('privatize_media', apply=True, **args)
            self.assertEqual(uploader.rename.call_count, 2)
            self.assertTrue(all(row['state'] == 'origin_private_cdn_pending' for row in json.loads(path.read_text())['assets']))
            with self.assertRaises(CommandError):
                call_command('privatize_media', **args)

    @patch('talents.management.commands.privatize_media.cloudinary.config')
    @patch('talents.management.commands.privatize_media.api')
    @patch('talents.management.commands.privatize_media.uploader')
    def test_wrong_environment_never_contacts_provider(self, uploader, api, config):
        config.return_value.cloud_name = 'real-target'
        with self.assertRaises(CommandError):
            call_command('privatize_media', manifest='unused.json', cloud_name='wrong')
        api.resources.assert_not_called(); uploader.rename.assert_not_called()

    @patch('talents.management.commands.privatize_media.cloudinary.config')
    @patch('talents.management.commands.privatize_media.PlaybackMediaStorage._get_prefix', return_value='media/')
    @patch('talents.management.commands.privatize_media.api')
    @patch('talents.management.commands.privatize_media.requests.Session')
    def test_command_url_check_records_evidence_and_fails_if_cache_is_still_public(self, session_factory, api, prefix, config):
        config.return_value.cloud_name = 'fixture-cloud'
        row = record(); provider = Provider(row)
        migrate_record(provider, provider, row, 'media', lambda: None)
        api.resource.side_effect = provider.resource
        session = session_factory.return_value.__enter__.return_value
        session.get.return_value.status_code = 200
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / 'manifest.json'; urls = Path(directory) / 'urls.json'
            manifest.write_text(json.dumps(dict(schema=1, cloud='fixture-cloud', prefix='media', assets=[row])))
            urls.write_text(json.dumps(['https://res.cloudinary.com/fixture-cloud/raw/upload/' + row['public_id']]))
            args = dict(manifest=str(manifest), verify_urls=str(urls), cloud_name='fixture-cloud', stdout=StringIO())
            with self.assertRaises(CommandError):
                call_command('privatize_media', **args)
            content = json.loads(manifest.read_text())
            self.assertFalse(content['last_url_check']['observations'][0]['denied'])
            self.assertFalse(session.trust_env)
            session.get.return_value.status_code = 404
            call_command('privatize_media', **args)
            self.assertTrue(json.loads(manifest.read_text())['last_url_check']['observations'][0]['denied'])
            self.assertEqual(json.loads(manifest.read_text())['assets'][0]['state'], 'origin_private_cdn_pending')

    @patch('talents.management.commands.privatize_media.cloudinary.config')
    @patch('talents.management.commands.privatize_media.PlaybackMediaStorage._get_prefix', return_value='media/')
    @patch('talents.management.commands.privatize_media.api')
    @patch('talents.management.commands.privatize_media.uploader')
    def test_conflicting_manifest_or_existing_lock_never_moves_assets(self, uploader, api, prefix, config):
        config.return_value.cloud_name = 'fixture-cloud'
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / 'manifest.json'
            manifest.write_text(json.dumps(dict(schema=1, cloud='fixture-cloud', prefix='media', assets=[record(), record()])))
            args = dict(manifest=str(manifest), cloud_name='fixture-cloud', apply=True, stdout=StringIO())
            with self.assertRaises(CommandError):
                call_command('privatize_media', **args)
            lock = manifest.with_name(manifest.name + '.lock'); lock.write_text('other-process')
            with self.assertRaises(CommandError):
                call_command('privatize_media', **args)
            self.assertEqual(lock.read_text(), 'other-process')
            uploader.rename.assert_not_called(); api.resource.assert_not_called()
