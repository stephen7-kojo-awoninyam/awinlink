"""Reversing the PostgreSQL-only operations must also be safe on SQLite."""
from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.postgres.operations import BtreeGistExtension
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone


operation = import_module("marketplace.migrations.0004_booking_overlap")


class BookingExtensionOperationTests(SimpleTestCase):
    def test_sqlite_directions_never_open_a_postgresql_catalog_cursor(self):
        editor = SimpleNamespace(connection=SimpleNamespace(vendor="sqlite"))
        extension = operation.PostgresBtreeGistExtension()
        extension.database_forwards("marketplace", editor, None, None)
        extension.database_backwards("marketplace", editor, None, None)

    def test_postgresql_reverse_keeps_django_extension_behavior(self):
        editor = SimpleNamespace(connection=SimpleNamespace(vendor="postgresql"))
        extension = operation.PostgresBtreeGistExtension()
        with patch.object(BtreeGistExtension, "database_backwards") as reverse_extension:
            extension.database_backwards("marketplace", editor, None, None)
        reverse_extension.assert_called_once_with("marketplace", editor, None, None)


class BookingOverlapMigrationTests(TransactionTestCase):
    def test_0004_reverse_and_reapply_preserve_booking_and_history(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(latest))
        apps = executor.loader.project_state(latest).apps
        User = apps.get_model("accounts", "User")
        talent_user = User.objects.create(username="overlap_migration_talent")
        buyer = User.objects.create(username="overlap_migration_buyer")
        profile = apps.get_model("talents", "TalentProfile").objects.create(user_id=talent_user.pk)
        domain = apps.get_model("domains", "TalentDomain").objects.create(name="Overlap migration domain")
        Listing, Offer, Booking, Event, Window = [apps.get_model("marketplace", name) for name in
                                                 ["Listing", "Offer", "Booking", "BookingEvent", "AvailabilityWindow"]]
        now = timezone.now()
        listing = Listing.objects.create(talent_id=profile.pk, subecosystem_id=domain.pk, ecosystem="SPORTS", title="Preserved listing")
        offer = Offer.objects.create(listing_id=listing.pk, sender_id=buyer.pk, terms="Original terms",
                                     status="ACCEPTED", decided_at=now, talent_consented_at=now)
        booking = Booking.objects.create(offer_id=offer.pk, talent_id=profile.pk,
            starts_at=now, ends_at=now + timedelta(hours=1), busy_start=now, busy_end=now + timedelta(hours=1),
            amount="10.00", currency="GHS", snapshot={"terms": "Original terms"})
        Event.objects.create(booking_id=booking.pk, actor_id=talent_user.pk, action="CONFIRMED", reason="Original history")
        Window.objects.create(talent_id=profile.pk, starts_at=now, ends_at=now + timedelta(hours=2))
        models = [Listing, Offer, Booking, Event, Window]
        before = [list(model.objects.order_by("pk").values()) for model in models]
        if connection.vendor == "postgresql":
            self.assert_constraint_exists(True)
        with CaptureQueriesContext(connection) as captured:
            executor.migrate([("marketplace", "0003_phase_two")])
            self.assertEqual([list(model.objects.order_by("pk").values()) for model in models], before)
            if connection.vendor == "postgresql":
                self.assert_constraint_exists(False)
            MigrationExecutor(connection).migrate(latest)
        self.assertEqual([list(model.objects.order_by("pk").values()) for model in models], before)
        if connection.vendor == "sqlite":
            self.assertFalse(any("pg_extension" in query["sql"] for query in captured))
        elif connection.vendor == "postgresql":
            self.assert_constraint_exists(True)

    def assert_constraint_exists(self, expected):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_constraint WHERE conname = %s AND conrelid = 'marketplace_booking'::regclass", ["market_booking_no_overlap"])
            self.assertEqual(cursor.fetchone() is not None, expected)
