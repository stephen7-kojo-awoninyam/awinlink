"""Explicit provider maintenance; never run on application startup or deployment."""
import json
import os
from contextlib import contextmanager
from pathlib import Path

import cloudinary
import requests
from datetime import datetime, timezone
from cloudinary import api, uploader
from django.core.management.base import BaseCommand, CommandError

from config.media_storage import PlaybackMediaStorage
from config.private_media_migration import allowed_id, check_exposed_urls, identity, inventory, migrate_record


@contextmanager
def manifest_lock(path):
    lock = path.with_name(path.name + '.lock')
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, str(os.getpid()).encode())
        yield
    finally:
        os.close(descriptor)
        lock.unlink()


def save_manifest(path, content):
    temporary = path.with_name(path.name + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump(content, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def validate_assets(content, prefix):
    destinations = set()
    for record in content['assets']:
        identity(record)
        key = (record['resource_type'], record['public_id'])
        if (not allowed_id(record['public_id'], prefix) or key in destinations
                or record.get('delivery_type') not in {'upload', 'private'}
                or record.get('state') not in {'planned', 'moving', 'origin_private_cdn_pending'}):
            raise CommandError('Invalid, duplicate or conflicting manifest asset; manual review required.')
        destinations.add(key)


class Command(BaseCommand):
    help = 'Plan or resume private CDN migration. Default is read-only provider inventory; --apply changes provider assets.'

    def add_arguments(self, parser):
        parser.add_argument('--manifest', required=True)
        parser.add_argument('--cloud-name', required=True, help='Explicitly name the target cloud; must match SDK configuration.')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--verify-urls', help='JSON list of historical URLs to check after migration; does not move assets.')
        parser.add_argument('--prefix', action='append', choices=PlaybackMediaStorage.PRIVATE_PREFIXES,
                            help='Private namespace to inventory; default: all private namespaces.')
        parser.add_argument('--limit', type=int, default=100, help='Maximum assets to move in one invocation.')

    def handle(self, *args, **options):
        cloud = cloudinary.config().cloud_name
        if not cloud or options['cloud_name'] != cloud:
            raise CommandError('Cloud name does not match configuration. No provider requests made.')
        if options['limit'] <= 0:
            raise CommandError('Limit must be positive.')
        if options['apply'] and options['verify_urls']:
            raise CommandError('Choose apply or URL verification, not both.')
        path = Path(options['manifest']).resolve()
        storage = PlaybackMediaStorage()
        prefix = storage._get_prefix().strip('/')
        try:
            with manifest_lock(path):
                if not options['apply'] and not options['verify_urls']:
                    if path.exists():
                        raise CommandError('Manifest already exists; preserve it and use another filename for a new inventory.')
                    content = dict(schema=1, cloud=cloud, prefix=prefix,
                                   assets=list(inventory(api, prefix, options['prefix'])))
                    validate_assets(content, prefix)
                    save_manifest(path, content)
                    self.stdout.write(f"Planned {len(content['assets'])} assets. No provider assets changed.")
                    return
                if options['prefix']:
                    raise CommandError('Apply uses the manifest scope; do not supply --prefix.')
                content = json.loads(path.read_text(encoding='utf-8'))
                if (content.get('schema') != 1 or content.get('cloud') != cloud or content.get('prefix') != prefix
                        or not isinstance(content.get('assets'), list)):
                    raise CommandError('Manifest environment or schema mismatch.')
                validate_assets(content, prefix)
                checkpoint = lambda: save_manifest(path, content)
                if options['verify_urls']:
                    urls = json.loads(Path(options['verify_urls']).read_text(encoding='utf-8'))
                    with requests.Session() as session:
                        session.trust_env = False
                        observations = check_exposed_urls(api, session, content['assets'], cloud, urls)
                    content['last_url_check'] = dict(at=datetime.now(timezone.utc).isoformat(), observations=observations)
                    checkpoint()
                    if not all(value['denied'] for value in observations):
                        raise CommandError('One or more historical URLs remain accessible or inconclusive. Evidence saved; CDN remediation is incomplete.')
                    self.stdout.write('Supplied URLs denied at this network location. Global CDN invalidation still requires operational verification.')
                    return
                count = 0
                for record in content['assets']:
                    if record.get('state') == 'origin_private_cdn_pending':
                        continue
                    if count >= options['limit']:
                        break
                    migrate_record(api, uploader, record, prefix, checkpoint)
                    count += 1
                self.stdout.write(f'Moved {count} assets. Origin private; CDN invalidation remains pending verification. Resume this manifest for remaining assets.')
        except CommandError:
            raise
        except Exception as error:
            # Provider errors can contain signed URLs. Keep those out of console/logs.
            raise CommandError(f'Migration stopped ({type(error).__name__}). Preserve the manifest; inspect provider state before resuming.') from None
