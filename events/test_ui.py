"""Event presentation contracts; fixtures never write application data."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace as NS
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.template.loader import render_to_string
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import EventForm, EventFeedbackForm, EventMediaForm
from .models import EventCategory
from .templatetags.events_ui import event_registration_open, event_workspace

from .models import Event, EventRegistration, EventCertificate
from organizations.models import Organization
from talents.models import TalentProfile


UI_TEMPLATES = deepcopy(settings.TEMPLATES)
UI_TEMPLATES[0]["OPTIONS"]["context_processors"] = [
    "django.template.context_processors.csrf", "django.template.context_processors.request",
]
UI_STORAGE = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def ui_fixture():
    user = NS(pk=1, id=1, is_authenticated=True, username="alex", role="ATHLETE",
              get_full_name=lambda: "Alex Morgan")
    talent = NS(id=2, user=user, profile_photo=None)
    user.talent_profile = talent
    owner = NS(pk=3, id=3, is_authenticated=True, username="studio", role="ORGANIZATION",
               get_full_name=lambda: "Awinlink Studio", talent_profile=None)
    org = NS(pk=4, id=4, name="Awinlink Creative Studio", user=owner, status="ACTIVE", verified=True)
    event = NS(id=5, organizer=org, title="Create, connect, and grow: a community workshop",
        category="Creative Arts", event_type="WORKSHOP", status="PUBLISHED", image=None,
        description="A day to explore your craft and connect with people who share your ambition.\nLearn practical skills, share ideas, and leave with a fresh perspective.",
        start_date=timezone.now()+timedelta(days=10), end_date=timezone.now()+timedelta(days=10,hours=4),
        registration_deadline=timezone.now()+timedelta(days=9), capacity=40,
        location="Accra Creative Hub, Ghana", online=False, meeting_link="https://example.com/meeting",
        participants=12, attended=8, rating=4.8, get_event_type_display=lambda: "Workshop")
    event.get_status_display = lambda: event.status.title()
    registration = NS(id=6, event=event, talent=talent, status="REGISTERED",
        registered_at=timezone.now(), attendance_time=timezone.now(), certificate=NS(certificate_code="AW-EVENT-005"))
    registration.get_status_display = lambda: registration.status.title()
    return user, owner, org, event, registration


@override_settings(TEMPLATES=UI_TEMPLATES, STORAGES=UI_STORAGE)
class EventTemplateContracts(SimpleTestCase):
    def setUp(self):
        self.user, self.owner, self.org, self.event, self.registration = ui_fixture()
        self.access = patch("events.templatetags.events_ui.has_organization_capability", return_value=False).start()
        self.workspace = patch("events.templatetags.events_ui.get_request_organization", return_value=self.org).start()
        self.addCleanup(patch.stopall)

    def render(self, template, **context):
        request = RequestFactory().get("/events/", {"organization_id": self.org.id})
        request.user = self.user
        return render_to_string("events/"+template+".html", {"user":self.user, **context}, request=request)

    def content(self, html):
        return html.split('<div class="event-page">', 1)[1].split("<!--", 1)[0]

    def test_discovery_cards_and_progressive_filters(self):
        html = self.render("event_list", events=[self.event])
        for name in ("search", "event_type", "category", "format", "when"):
            self.assertIn(f'name="{name}"', html)
        self.assertIn("data-event-filters hidden", html)
        self.assertIn(reverse("event_detail", args=[5]), html)
        self.assertIn('data-category="Creative Arts"', html)
        self.assertNotIn("Match", html)

    def test_creation_links_only_show_for_authorized_organization_accounts(self):
        for user, authorized, expected in ((self.user, True, False), (self.owner, False, False), (self.owner, True, True)):
            self.user = user
            self.access.return_value = authorized
            html = self.render("event_list", events=[])
            self.assertEqual('> Create event</a>' in html, expected)

    def test_registration_is_one_post_form_with_csrf(self):
        html = self.content(self.render("event_details", event=self.event, participants=[], feedbacks=[]))
        self.assertEqual(html.count(f'action="{reverse("register_event", args=[5])}"'), 1)
        self.assertIn('method="POST"', html)
        self.assertIn('name="csrfmiddlewaretoken"', html)

    def test_closed_capacity_and_missing_profile_hide_registration(self):
        for state in ("deadline", "capacity", "draft", "inactive", "no-profile"):
            with self.subTest(state=state):
                self.user, self.owner, self.org, self.event, self.registration = ui_fixture()
                if state == "deadline": self.event.registration_deadline = timezone.now()-timedelta(seconds=1)
                if state == "draft": self.event.status = "DRAFT"
                if state == "inactive": self.org.status = "INACTIVE"
                if state == "no-profile": self.user.talent_profile = None
                html = self.render("event_details", event=self.event, capacity_full=state=="capacity")
                self.assertNotIn(f'action="{reverse("register_event", args=[5])}"', html)

    def test_cancelled_registration_can_register_again(self):
        self.registration.status = "CANCELLED"
        html = self.render("event_details", event=self.event, current_registration=self.registration, registered=True)
        self.assertIn("Register again", html)
        self.assertNotIn(f'action="{reverse("cancel_registration", args=[5])}"', html)

    def test_feedback_and_cancellation_follow_current_registration(self):
        for status in ("REGISTERED", "APPROVED", "ATTENDED", "REJECTED"):
            self.registration.status = status
            html = self.render("event_details", event=self.event, current_registration=self.registration)
            self.assertEqual(reverse("give_feedback", args=[5]) in html, status=="ATTENDED")
            self.assertEqual(f'action="{reverse("cancel_registration", args=[5])}"' in html, status!="ATTENDED")
            self.assertNotIn(f'action="{reverse("register_event", args=[5])}"', html)

    def test_feedback_is_not_duplicated(self):
        feedback = NS(reviewer=self.user, rating=5, comment="A unique review message.")
        html = self.render("event_details", event=self.event, feedbacks=[feedback])
        self.assertEqual(html.count(feedback.comment), 1)

    def test_participant_actions_follow_status_and_permissions(self):
        for status, role, expected in (
            ("REGISTERED", "owner", ("approve", "reject")),
            ("REGISTERED", "manager", ()),
            ("APPROVED", "manager", ("attendance",)),
            ("APPROVED", "viewer", ()),
            ("ATTENDED", "owner", ()),
        ):
            self.user = self.owner if role=="owner" else NS(pk=9, id=9, role="COACH", is_authenticated=True, username="team", talent_profile=None)
            self.access.return_value = role != "viewer"
            self.registration.status = status
            html = self.content(self.render("event_participants", event=self.event, registrations=[self.registration]))
            for action, route in (("approve", "approve_registration"), ("reject", "reject_registration"), ("attendance", "mark_attendance")):
                self.assertEqual(f'action="{reverse(route,args=[6])}' in html, action in expected)
            self.assertEqual(html.count('name="csrfmiddlewaretoken"'), len(expected))
        self.assertIn(reverse("verify_certificate", args=["AW-EVENT-005"]), html)

    def test_creation_keeps_every_field_upload_and_errors(self):
        self.user = self.owner
        form = EventForm()
        form.fields["category"].queryset = EventCategory.objects.none()
        form.cleaned_data = {}
        form.add_error("title", "Title is required.")
        form.add_error(None, "End date must be after start date.")
        html = self.content(self.render("create_event", form=form))
        for name in EventForm.Meta.fields:
            self.assertIn(f'name="{name}"', html)
        self.assertIn('enctype="multipart/form-data"', html)
        self.assertIn('for="id_online"', html)
        self.assertIn('name="csrfmiddlewaretoken"', html)
        self.assertIn("Title is required.", html)
        self.assertIn("End date must be after start date.", html)

    def test_media_and_feedback_forms_keep_csrf_and_fields(self):
        for template, form in (("upload_event_media", EventMediaForm()), ("give_feedback", EventFeedbackForm())):
            html = self.content(self.render(template, event=self.event, form=form))
            for name in form.fields:
                self.assertIn(f'name="{name}"', html)
            self.assertIn('name="csrfmiddlewaretoken"', html)
            self.assertIn('method="POST"', html)

    def test_empty_states_and_recommendation_score(self):
        for template, context in (("event_list", {"events":[]}), ("my_events", {"registrations":[]}),
            ("event_participants", {"event":self.event,"registrations":[]}), ("organization_events", {"events":[]}),
            ("recommended_events", {"recommendations":[]})):
            self.assertIn("ev-empty", self.render(template, **context))
        self.assertIn('value="82"', self.render("recommended_events", recommendations=[{"event":self.event,"score":82}]))

    def test_registration_helper_and_workspace_deny_invalid_scope(self):
        self.assertTrue(event_registration_open(self.event))
        self.assertFalse(event_registration_open(self.event, True))
        request = RequestFactory().get("/events/?organization_id=999")
        request.user = self.user
        self.workspace.side_effect = PermissionDenied
        self.assertIsNone(event_workspace({"request":request}))


@override_settings(STORAGES=UI_STORAGE, ALLOWED_HOSTS=["testserver"])
class EventWebUIIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username="event_ui_owner", role="ORGANIZATION")
        cls.athlete = User.objects.create_user(username="event_ui_athlete", role="ATHLETE")
        cls.organization = Organization.objects.create(user=cls.owner, name="Event UI Studio", country="GH")
        cls.talent = TalentProfile.objects.create(user=cls.athlete)
        cls.category = EventCategory.objects.create(name="UI Workshops")
        start = timezone.now() + timedelta(days=10)
        cls.event = Event.objects.create(organizer=cls.organization, category=cls.category,
            title="UI workshop", slug="ui-workshop", description="Learn together.", event_type="WORKSHOP",
            location="Accra", start_date=start, end_date=start+timedelta(hours=2),
            registration_deadline=start-timedelta(days=1), capacity=20, status="PUBLISHED")

    def csrf_client(self, user, route, **kwargs):
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        response = client.get(reverse(route, kwargs=kwargs))
        self.assertEqual(response.status_code, 200)
        return client, client.cookies["csrftoken"].value

    def test_organizer_workspace_renders_aggregates_without_relation_collision(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("organization_events"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.title)
        self.assertEqual(response.context['total_events'], 1)
        self.assertEqual(response.context['events'][0].certificate_count, 0)

    def test_personal_accounts_cannot_open_creation_or_organizer_management(self):
        self.client.force_login(self.athlete)
        for route in ("create_event", "organization_events"):
            self.assertEqual(self.client.get(reverse(route)).status_code, 403)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("create_event"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_registration_cancel_and_reregister_work_as_csrf_protected_posts(self):
        client, csrf = self.csrf_client(self.athlete, "event_detail", event_id=self.event.pk)
        url = reverse("register_event", args=[self.event.pk])
        self.assertEqual(client.post(url).status_code, 403)
        self.assertEqual(client.post(url, {"csrfmiddlewaretoken":csrf}).status_code, 302)
        registration = EventRegistration.objects.get(event=self.event, talent=self.talent)
        self.assertEqual(registration.status, "REGISTERED")
        self.assertEqual(client.post(reverse("cancel_registration", args=[self.event.pk]), {"csrfmiddlewaretoken":csrf}).status_code, 302)
        registration.refresh_from_db()
        self.assertEqual(registration.status, "CANCELLED")
        self.assertEqual(client.post(url, {"csrfmiddlewaretoken":csrf}).status_code, 302)
        registration.refresh_from_db()
        self.assertEqual(registration.status, "REGISTERED")
        self.assertEqual(EventRegistration.objects.filter(event=self.event, talent=self.talent).count(), 1)

    def test_approval_attendance_and_event_certificate_work_as_posts(self):
        registration = EventRegistration.objects.create(event=self.event, talent=self.talent)
        client, csrf = self.csrf_client(self.owner, "event_participants", event_id=self.event.pk)
        self.assertEqual(client.post(reverse("approve_registration", args=[registration.pk]), {"csrfmiddlewaretoken":csrf}).status_code, 302)
        registration.refresh_from_db()
        self.assertEqual(registration.status, "APPROVED")
        self.assertEqual(client.post(reverse("mark_attendance", args=[registration.pk]), {"csrfmiddlewaretoken":csrf}).status_code, 302)
        registration.refresh_from_db()
        self.assertEqual(registration.status, "ATTENDED")
        certificate = EventCertificate.objects.get(event=self.event, talent=self.talent)
        response = client.get(reverse("event_participants", args=[self.event.pk]))
        self.assertContains(response, reverse("verify_certificate", args=[certificate.certificate_code]))
