"""Template contracts for discovery, application eligibility, and status actions."""
from datetime import date, timedelta
from copy import deepcopy
from types import SimpleNamespace as NS

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse


def ui_fixture():
    organization = NS(id=11, name="Awinlink Athletics Academy", verified=True,
                      description="Helping emerging talent find their next opportunity.", user=NS(id=12))
    talent = NS(id=13, verified=True, headline="Athlete and community mentor",
                user=NS(username="alex", get_full_name=lambda: "Alex Morgan"),
                skills=NS(all=lambda: [NS(name="Teamwork")]))
    opportunity = NS(id=14, title="Youth development and community coaching opportunity",
        organization=organization, domain=NS(id=1, name="Sports"), active=True,
        description="Build your career with a team that believes in your potential.\nWork with young athletes and support community training.",
        location="Accra, Ghana", deadline=date.today() + timedelta(days=30), created_at=date.today(),
        skills=NS(all=lambda: [NS(name="Teamwork"), NS(name="Leadership")]),
        requirements=NS(all=lambda: [NS(skill=NS(name="Teamwork"), importance=4)]),
        get_opportunity_type_display=lambda: "Sports Trial",
        get_experience_level_display=lambda: "Intermediate", get_work_type_display=lambda: "On Site")
    application = NS(id=15, talent=talent, opportunity=opportunity, status="PENDING",
                     message="I would love to bring my coaching experience to your team.\nThank you for considering my application.",
                     created_at=date.today())
    application.get_status_display = lambda: application.status.title()
    return organization, talent, opportunity, application


UI_TEMPLATES = deepcopy(settings.TEMPLATES)
UI_TEMPLATES[0]["OPTIONS"]["context_processors"] = ["django.template.context_processors.csrf"]


@override_settings(TEMPLATES=UI_TEMPLATES, STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class OpportunityTemplateContracts(SimpleTestCase):
    def setUp(self):
        self.organization, self.talent, self.opportunity, self.application = ui_fixture()
        self.user = NS(is_authenticated=True, talent_profile=self.talent, role="ATHLETE",
                       username="alex", id=13, get_full_name=lambda: "Alex Morgan")

    def render(self, template, **context):
        request = RequestFactory().get("/opportunities/")
        request.user = self.user
        return render_to_string(template, {"user": self.user, "today": date.today(), **context}, request=request)

    def test_discovery_preserves_filter_names_values_and_detail_route(self):
        html = self.render("opportunities/list.html", opportunities=[self.opportunity], domains=[NS(id=1, name="Sports")],
            opportunity_types=[("TRIAL", "Sports Trial")], experience_levels=[("INTERMEDIATE", "Intermediate")],
            work_types=[("ONSITE", "On Site")], search="coach", location="Accra", selected_domain="1",
            selected_opportunity_type="TRIAL", selected_experience_level="INTERMEDIATE", selected_work_type="ONSITE")
        for name in ("search", "domain", "opportunity_type", "experience_level", "work_type", "location"):
            self.assertIn(f'name="{name}"', html)
        self.assertEqual(html.count("selected>"), 4)
        self.assertIn(reverse("opportunity_detail", args=[14]), html)
        self.assertNotIn("Match score", html)

    def test_apply_form_preserves_post_message_csrf_and_action(self):
        html = self.render("opportunities/detail.html", opportunity=self.opportunity)
        self.assertIn(f'action="{reverse("apply_opportunity", args=[14])}"', html)
        self.assertIn('method="post"', html)
        self.assertIn('name="message"', html)
        self.assertIn('name="csrfmiddlewaretoken"', html)
        self.assertIn('for="application-message"', html)

    def test_application_eligibility_branches_hide_submission(self):
        for active, deadline, talent, application, expected in (
            (False, date.today(), self.talent, None, "currently closed"),
            (True, date.today()-timedelta(days=1), self.talent, None, "deadline has passed"),
            (True, date.today(), None, None, "need a talent profile"),
            (True, date.today(), self.talent, self.application, "already applied"),
        ):
            with self.subTest(expected=expected):
                self.opportunity.active, self.opportunity.deadline = active, deadline
                self.user.talent_profile = talent
                html = self.render("opportunities/detail.html", opportunity=self.opportunity, application=application)
                self.assertIn(expected, html)
                self.assertNotIn('name="message"', html)

    def test_status_history_renders_each_application_once_and_gates_messaging(self):
        for status in ("PENDING", "REVIEWING", "ACCEPTED", "REJECTED"):
            self.application.status = status
            html = self.render("opportunities/my_applications.html", applications=[self.application])
            self.assertEqual(html.count(self.opportunity.title), 1)
            self.assertIn(f"op-status--{status.lower()}", html)
            self.assertEqual("Message organization" in html, status == "ACCEPTED")

    def test_recruiter_status_actions_preserve_post_and_csrf(self):
        for status, actions in (("PENDING", ("review", "accept", "reject")), ("REVIEWING", ("accept", "reject")),
                                ("ACCEPTED", ()), ("REJECTED", ())):
            self.application.status = status
            html = self.render("organizations/applications.html", organization=self.organization, applications=[self.application])
            html = html.split('<article class="op-card">', 1)[1].split("</article>", 1)[0]
            for action in ("review", "accept", "reject"):
                self.assertEqual(reverse(f"{action}_application", args=[15]) in html, action in actions)
            self.assertEqual(html.count('method="POST"'), len(actions))
            self.assertEqual(html.count('name="csrfmiddlewaretoken"'), len(actions))

    def test_empty_and_missing_profile_states(self):
        for template, context, expected in (
            ("opportunities/list.html", {"opportunities": []}, "No opportunities found"),
            ("opportunities/my_applications.html", {"applications": []}, "No applications yet"),
            ("opportunities/my_applications.html", {"applications": [], "no_talent_profile": True}, "Talent profile required"),
            ("organizations/applications.html", {"applications": [], "organization": self.organization}, "No applications received yet"),
            ("opportunities/recommendations.html", {"recommendations": []}, "No recommendations available"),
        ):
            with self.subTest(template=template, expected=expected):
                self.assertIn(expected, self.render(template, **context))

    def test_recommendation_match_score_and_anonymous_discovery(self):
        html = self.render("opportunities/recommendations.html", recommendations=[{"opportunity": self.opportunity, "score": 82}])
        self.assertIn('value="82"', html)
        self.user = AnonymousUser()
        html = self.render("opportunities/list.html", opportunities=[self.opportunity])
        self.assertIn("Discover opportunities", html)
        self.assertNotIn("My applications", html)
