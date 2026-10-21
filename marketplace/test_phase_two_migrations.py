from unittest import skipUnless

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL Phase 2 legacy preservation')
class PhaseTwoMigrationTests(TransactionTestCase):
    def test_0002_upgrade_preserves_legacy_rows_without_inventing_bookings(self):
        executor = MigrationExecutor(connection)
        target = [('marketplace', '0002_workflow_guards')]
        executor.migrate(target)
        self.addCleanup(self.restore_schema)
        targets = [n for n in executor.loader.graph.leaf_nodes() if n[0] != 'marketplace'] + target
        old = executor.loader.project_state(targets).apps
        User = old.get_model('accounts', 'User')
        talent = User.objects.create(username='phase2_legacy_talent')
        sender = User.objects.create(username='phase2_legacy_sender')
        profile = old.get_model('talents', 'TalentProfile').objects.create(user_id=talent.pk)
        domain = old.get_model('domains', 'TalentDomain').objects.create(name='Phase2 legacy domain')
        Listing, Offer, Message = [old.get_model('marketplace', name) for name in ['Listing', 'Offer', 'DealMessage']]
        listing = Listing.objects.create(talent_id=profile.pk, subecosystem_id=domain.pk, ecosystem='SPORTS',
            title='Original legacy listing', description='No price or schedule agreed', status='PUBLISHED', publication_consented_at=timezone.now())
        for status in ['PENDING', 'ACCEPTED', 'DECLINED', 'WITHDRAWN']:
            offer = Offer.objects.create(listing_id=listing.pk, sender_id=sender.pk, terms='Exact legacy terms', status=status,
                decided_at=timezone.now() if status != 'PENDING' else None,
                talent_consented_at=timezone.now() if status == 'ACCEPTED' else None)
            Message.objects.create(offer_id=offer.pk, author_id=sender.pk, body='Original legacy message')
        before = {name: list(model.objects.order_by('pk').values()) for name, model in [('Listing', Listing), ('Offer', Offer), ('DealMessage', Message)]}
        executor = MigrationExecutor(connection)
        leaves = executor.loader.graph.leaf_nodes()
        executor.migrate(leaves)
        new = executor.loader.project_state(leaves).apps
        for name, rows in before.items():
            fields = list(rows[0])
            self.assertEqual(list(new.get_model('marketplace', name).objects.order_by('pk').values(*fields)), rows)
        listing = new.get_model('marketplace', 'Listing').objects.get(pk=listing.pk)
        self.assertFalse(listing.booking_enabled)
        self.assertIsNone(listing.base_price)
        self.assertEqual(listing.pricing_mode, 'QUOTE_ONLY')
        self.assertEqual(listing.revision, 1)
        for offer in new.get_model('marketplace', 'Offer').objects.all():
            self.assertEqual(offer.workflow_version, 1)
            self.assertEqual(offer.quote_snapshot, {})
            for field in ['quoted_amount', 'quoted_currency', 'listing_revision', 'requested_start', 'requested_end']:
                self.assertIsNone(getattr(offer, field))
        self.assertEqual(set(new.get_model('marketplace', 'DealMessage').objects.values_list('scope', flat=True)), {'NEGOTIATION'})
        self.assertFalse(new.get_model('marketplace', 'Booking').objects.exists())
        self.assertFalse(new.get_model('marketplace', 'AvailabilityWindow').objects.exists())

    def restore_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
