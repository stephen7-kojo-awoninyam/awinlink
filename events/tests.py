from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from events.models import Event, EventCategory
from organizations.models import Organization


User = get_user_model()


class OrganizationEventDraftAccessTests(APITestCase):
    def setUp(self):
        self.organization_user = User.objects.create_user(
            username="event_owner", password="TestPass123!", role="ORGANIZATION"
        )
        self.other_organization_user = User.objects.create_user(
            username="other_event_owner", password="TestPass123!", role="ORGANIZATION"
        )
        self.athlete = User.objects.create_user(
            username="event_athlete", password="TestPass123!", role="ATHLETE"
        )
        self.organization = Organization.objects.create(
            user=self.organization_user, name="Event Owner Org", country="Nigeria"
        )
        self.other_organization = Organization.objects.create(
            user=self.other_organization_user, name="Other Event Org", country="Ghana"
        )
        self.category = EventCategory.objects.create(name="Test Event Category")
        self.draft = self.create_event(self.organization, "owner-draft", "DRAFT")
        self.published = self.create_event(self.organization, "owner-published", "PUBLISHED")
        self.other_draft = self.create_event(self.other_organization, "other-draft", "DRAFT")
        self.url = "/api/events/my/"

    def create_event(self, organizer, slug, status):
        start = timezone.now() + timedelta(days=3)
        return Event.objects.create(
            organizer=organizer,
            category=self.category,
            title=slug.replace("-", " ").title(),
            slug=slug,
            description="Event description",
            event_type="WORKSHOP",
            location="Lagos",
            start_date=start,
            end_date=start + timedelta(hours=2),
            registration_deadline=start - timedelta(days=1),
            status=status,
        )

    def test_organization_can_reload_its_drafts_and_published_events(self):
        self.client.force_authenticate(user=self.organization_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        ids = {event["id"] for event in response.data}
        self.assertIn(self.draft.id, ids)
        self.assertIn(self.published.id, ids)
        self.assertNotIn(self.other_draft.id, ids)

    def test_another_organization_only_sees_its_own_events(self):
        self.client.force_authenticate(user=self.other_organization_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        ids = {event["id"] for event in response.data}
        self.assertEqual(ids, {self.other_draft.id})

    def test_non_organization_cannot_use_managed_event_list(self):
        self.client.force_authenticate(user=self.athlete)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_cannot_use_managed_event_list(self):
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (401, 403))


class EventMembershipCapabilityTests(APITestCase):
    def setUp(self):
        from organizations.models import OrganizationMembership

        self.owner = User.objects.create_user(
            username="event_membership_owner", role="ORGANIZATION",
        )
        self.other_owner = User.objects.create_user(
            username="event_membership_other_owner", role="ORGANIZATION",
        )
        self.organization = Organization.objects.create(
            user=self.owner, name="Membership Event Org", country="GH",
        )
        self.other_organization = Organization.objects.create(
            user=self.other_owner, name="Other Membership Event Org", country="GH",
        )
        self.manager = User.objects.create_user(
            username="event_membership_manager", role="ATHLETE",
        )
        self.recruiter = User.objects.create_user(
            username="event_membership_recruiter", role="SCOUT",
        )
        self.viewer = User.objects.create_user(
            username="event_membership_viewer", role="COACH",
        )
        self.other_manager = User.objects.create_user(
            username="event_membership_other_manager", role="ATHLETE",
        )
        self.memberships = {}
        for org, user, role in (
            (self.organization, self.owner, "OWNER"),
            (self.organization, self.manager, "MANAGER"),
            (self.organization, self.recruiter, "RECRUITER"),
            (self.organization, self.viewer, "VIEWER"),
            (self.other_organization, self.other_manager, "MANAGER"),
        ):
            self.memberships[user.pk] = OrganizationMembership.objects.create(
                organization=org, user=user, role=role,
            )
        self.category = EventCategory.objects.create(name="Member Events")
        self.event = self.make_event(self.organization, "member-event")
        self.other_event = self.make_event(self.other_organization, "other-member-event")
        athlete = User.objects.create_user(username="event_member_talent", role="ATHLETE")
        from talents.models import TalentProfile
        talent = TalentProfile.objects.create(user=athlete)
        from events.models import EventRegistration
        self.registration = EventRegistration.objects.create(
            event=self.event, talent=talent, status="APPROVED",
        )

    def make_event(self, organization, slug):
        start = timezone.now() + timedelta(days=5)
        return Event.objects.create(
            organizer=organization,
            category=self.category,
            title=slug.replace("-", " ").title(),
            slug=slug,
            description="A membership managed event.",
            event_type="WORKSHOP",
            location="Accra",
            start_date=start,
            end_date=start + timedelta(hours=2),
            registration_deadline=start - timedelta(days=1),
            status="PUBLISHED",
        )

    def test_event_creation_and_organization_list_use_membership_capabilities(self):
        data = {
            "category": self.category.pk,
            "title": "Created by team",
            "slug": "created-by-team",
            "description": "A new team event.",
            "event_type": "WORKSHOP",
            "location": "Accra",
            "start_date": (timezone.now() + timedelta(days=8)).isoformat(),
            "end_date": (timezone.now() + timedelta(days=8, hours=2)).isoformat(),
            "registration_deadline": (timezone.now() + timedelta(days=7)).isoformat(),
            "organizer": self.other_organization.pk,
        }
        self.client.force_authenticate(self.manager)
        response = self.client.post("/api/events/create/", data, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["organizer"], self.organization.pk)
        created_event_id = response.data["id"]

        response = self.client.get("/api/events/my/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {item["id"] for item in response.data},
            {self.event.pk, created_event_id},
        )

        for user in (self.recruiter, self.viewer):
            self.client.force_authenticate(user)
            response = self.client.post("/api/events/create/", data, format="json")
            self.assertEqual(response.status_code, 403)
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get("/api/events/my/").status_code, 200)

    def test_event_object_mutations_require_current_capability_and_organization_scope(self):
        self.client.force_authenticate(self.manager)
        response = self.client.put(
            f"/api/events/{self.event.pk}/update/",
            {"title": "Managed by the team"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], "Managed by the team")

        response = self.client.put(
            f"/api/events/{self.other_event.pk}/update/",
            {"title": "Cross organization edit"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.patch(
            f"/api/events/registrations/{self.registration.pk}/status/",
            {"status": "REJECTED"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        self.client.force_authenticate(self.viewer)
        response = self.client.patch(
            f"/api/events/registrations/{self.registration.pk}/status/",
            {"status": "REJECTED"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

        self.memberships[self.manager.pk].status = "REMOVED"
        self.memberships[self.manager.pk].save(update_fields=["status"])
        self.client.force_authenticate(self.manager)
        response = self.client.put(
            f"/api/events/{self.event.pk}/update/",
            {"title": "Removed member edit"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_suspended_organization_blocks_member_operations_and_selection_cannot_cross_scope(self):
        self.client.force_authenticate(self.manager)
        response = self.client.put(
            f"/api/events/{self.event.pk}/update/?organization_id={self.other_organization.pk}",
            {"title": "Wrong organization"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

        Organization.objects.filter(pk=self.organization.pk).update(status="INACTIVE")
        response = self.client.post("/api/events/create/", {
            "category": self.category.pk,
            "title": "Blocked event",
            "slug": "blocked-event",
            "description": "Should not be created.",
            "event_type": "WORKSHOP",
            "location": "Accra",
            "start_date": (timezone.now() + timedelta(days=8)).isoformat(),
            "end_date": (timezone.now() + timedelta(days=8, hours=2)).isoformat(),
            "registration_deadline": (timezone.now() + timedelta(days=7)).isoformat(),
        }, format="json")
        self.assertEqual(response.status_code, 403)
