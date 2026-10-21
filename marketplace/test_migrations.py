"""Seed real pre-0002 rows and verify PostgreSQL upgrade preservation/rollback."""
from io import StringIO
import json
from unittest import skipUnless

from django.core.management import call_command, CommandError
from django.db import connection, IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase
from django.utils import timezone

from .legacy_audit import audit_legacy_marketplace


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL migration audit')
class LegacyMarketMigrationTests(TransactionTestCase):
    before = [('marketplace', '0001_initial')]
    after = [('marketplace', '0002_workflow_guards')]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        targets = [node for node in executor.loader.graph.leaf_nodes() if node[0] != 'marketplace'] + self.before
        self.apps = executor.loader.project_state(targets).apps
        User = self.apps.get_model('accounts', 'User')
        self.talent = User.objects.create(username='legacy_talent')
        self.sender = User.objects.create(username='legacy_sender')
        profile = self.apps.get_model('talents', 'TalentProfile').objects.create(user_id=self.talent.pk)
        domain = self.apps.get_model('domains', 'TalentDomain').objects.create(name='Legacy domain')
        self.Listing = self.apps.get_model('marketplace', 'Listing')
        self.Offer = self.apps.get_model('marketplace', 'Offer')
        self.Message = self.apps.get_model('marketplace', 'DealMessage')
        self.listing = self.Listing.objects.create(talent_id=profile.pk, subecosystem_id=domain.pk,
            ecosystem='SPORTS', title='Original title', description='Original description',
            status='PUBLISHED', publication_consented_at=timezone.now())

    def tearDown(self):
        # Only synthetic rows in Django's test database; restore schema for the rest of the suite.
        self.Message.objects.all().delete()
        self.Offer.objects.all().delete()
        self.Listing.objects.all().delete()
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def offer(self, **values):
        return self.Offer.objects.create(listing_id=self.listing.pk, sender_id=self.sender.pk,
                                         terms='Exact legacy terms', **values)

    def snapshot(self):
        return {name: list(model.objects.order_by('pk').values()) for name, model in
                [('listings', self.Listing), ('offers', self.Offer), ('messages', self.Message)]}

    def test_clean_upgrade_preserves_all_data_and_allows_final_offer_history(self):
        now = timezone.now()
        for values in [{}, {'status': 'ACCEPTED', 'decided_at': now, 'talent_consented_at': now},
                       {'status': 'DECLINED', 'decided_at': now}, {'status': 'WITHDRAWN', 'decided_at': now}]:
            offer = self.offer(**values)
            self.Message.objects.create(offer_id=offer.pk, author_id=self.sender.pk, body='Legacy history')
        before = self.snapshot()
        self.assertTrue(audit_legacy_marketplace(self.apps)['ready'])
        output = StringIO()
        call_command('audit_marketplace_legacy', stdout=output)
        self.assertTrue(json.loads(output.getvalue())['ready'])
        MigrationExecutor(connection).migrate(self.after)
        self.assertEqual(self.snapshot(), before)
        self.assertIn(('marketplace', '0002_workflow_guards'), MigrationRecorder(connection).applied_migrations())

    def test_dirty_upgrade_fails_atomically_without_repairing_or_losing_history(self):
        self.Listing.objects.filter(pk=self.listing.pk).update(publication_consented_at=None)
        self.Listing.objects.create(talent_id=self.listing.talent_id, subecosystem_id=self.listing.subecosystem_id,
            ecosystem='SPORTS', title='Unknown status', description='Preserved', status='INVALID')
        personal = self.offer()
        self.offer()
        org = self.apps.get_model('organizations', 'Organization').objects.create(name='Legacy org', user_id=self.sender.pk)
        self.offer(organization_id=org.pk)
        self.offer(organization_id=org.pk)
        self.offer(status='ACCEPTED')
        self.offer(status='DECLINED')
        self.offer(status='WITHDRAWN', decided_at=timezone.now(), talent_consented_at=timezone.now())
        self.offer(status='INVALID')
        self.Message.objects.create(offer_id=personal.pk, author_id=self.sender.pk, body='Never discard this')
        before = self.snapshot()
        report = audit_legacy_marketplace(self.apps)
        self.assertFalse(report['ready'])
        self.assertTrue(all(check['count'] > 0 for check in report['checks'].values()))
        output = StringIO()
        with self.assertRaises(CommandError):
            call_command('audit_marketplace_legacy', stdout=output)
        self.assertFalse(json.loads(output.getvalue())['ready'])
        with self.assertRaises(IntegrityError):
            MigrationExecutor(connection).migrate(self.after)
        self.assertNotIn(('marketplace', '0002_workflow_guards'), MigrationRecorder(connection).applied_migrations())
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, self.Listing._meta.db_table)
        self.assertNotIn('market_listing_valid_status', constraints)
        self.assertEqual(self.snapshot(), before)

    def test_each_guard_rejects_its_legacy_violation_and_rolls_back(self):
        cases = ['market_listing_valid_status', 'market_listing_publication_consent',
                 'market_pending_personal_offer', 'market_pending_org_offer',
                 'market_offer_valid_status', 'market_offer_decision_consent']
        for name in cases:
            with self.subTest(constraint=name):
                if name == 'market_listing_valid_status':
                    self.Listing.objects.filter(pk=self.listing.pk).update(status='INVALID')
                elif name == 'market_listing_publication_consent':
                    self.Listing.objects.filter(pk=self.listing.pk).update(publication_consented_at=None)
                elif name == 'market_pending_personal_offer':
                    self.offer()
                    self.offer()
                elif name == 'market_pending_org_offer':
                    org = self.apps.get_model('organizations', 'Organization').objects.create(name='Duplicate org', user_id=self.sender.pk)
                    self.offer(organization_id=org.pk)
                    self.offer(organization_id=org.pk)
                elif name == 'market_offer_valid_status':
                    self.offer(status='INVALID')
                else:
                    self.offer(status='ACCEPTED', decided_at=timezone.now())
                before = self.snapshot()
                self.assertGreater(audit_legacy_marketplace(self.apps)['checks'][name]['count'], 0)
                with self.assertRaises(IntegrityError) as caught:
                    MigrationExecutor(connection).migrate(self.after)
                self.assertEqual(caught.exception.__cause__.diag.constraint_name, name)
                self.assertEqual(self.snapshot(), before)
                self.assertNotIn(('marketplace', '0002_workflow_guards'), MigrationRecorder(connection).applied_migrations())
                self.Offer.objects.all().delete()
                self.Listing.objects.filter(pk=self.listing.pk).update(status='PUBLISHED', publication_consented_at=self.listing.publication_consented_at)
