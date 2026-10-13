"""Competition presentation contracts and CSRF-enforced workflow checks."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from organizations.models import Organization
from talents.models import TalentProfile
from .forms import CompetitionForm, EvaluationForm, JudgeAssignmentForm, SubmissionForm
from .models import Competition, CompetitionParticipant, CompetitionJudge, CompetitionEvaluation, CompetitionResult

UI_TEMPLATES = deepcopy(settings.TEMPLATES)
UI_TEMPLATES[0]["OPTIONS"]["context_processors"] = [
    "django.template.context_processors.csrf", "django.template.context_processors.request",
]
UI_STORAGE = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def ui_fixture(category="SPORTS"):
    athlete = NS(pk=1,id=1,is_authenticated=True,is_superuser=False,role="ATHLETE",username="alex",get_full_name=lambda:"Alex Morgan")
    owner = NS(pk=2,id=2,is_authenticated=True,is_superuser=False,role="ORGANIZATION",username="studio",talent_profile=None,get_full_name=lambda:"Awinlink Studio")
    organization = NS(pk=3,id=3,user=owner,name="Awinlink Talent Collective",logo=None,verified=True)
    talent = NS(id=4,user=athlete,profile_photo=None,talent_area="Emerging talent",get_talent_category_display=lambda:dict(Competition.CATEGORIES)[category])
    athlete.talent_profile = talent
    today = timezone.localdate()
    titles = {"SPORTS":"The next generation sports challenge", "SCIENCE_TECHNOLOGY":"Build tomorrow: the innovation challenge", "ARTS":"New voices: the creative showcase", "OTHERS":"Big ideas, real impact"}
    disciplines = {"SPORTS":"Football", "SCIENCE_TECHNOLOGY":"Robotics & innovation", "ARTS":"Visual arts", "OTHERS":"Community leadership"}
    competition = NS(pk=5,id=5,organization=organization,title=titles[category],category=category,
        discipline=disciplines[category],status="PUBLISHED",online=category=="SCIENCE_TECHNOLOGY",
        description="A challenge for emerging talent with the ambition to go further.\nBring your skills, share your perspective, and make your next move.",
        registration_start=today-timedelta(days=2),registration_end=today+timedelta(days=7),
        competition_start=today+timedelta(days=8),competition_end=today+timedelta(days=10),
        location="Accra, Ghana",participant_count=24,max_participants=50,registration_open=True,
        requirements="Bring your portfolio and a willingness to collaborate.",rules="Respect the community and submit original work.",
        prizes="Recognition, new connections, and an opportunity to grow.",review_note="Please clarify the judging criteria.")
    competition.get_category_display = lambda:dict(Competition.CATEGORIES)[competition.category]
    competition.get_status_display = lambda:dict(Competition.STATUS_CHOICES)[competition.status]
    participant = NS(id=6,talent=talent,competition=competition,status="REGISTERED",submission="My original competition entry.",
        submission_url="https://example.com/my-work",submitted_at=timezone.now(),registered_at=timezone.now())
    participant.get_status_display = lambda:participant.status.title()
    result = NS(participant=participant,position=1,score=Decimal("0.00"),award="Community choice",published_at=timezone.now())
    participant.result = result
    return athlete,owner,organization,competition,participant,result


@override_settings(TEMPLATES=UI_TEMPLATES,STORAGES=UI_STORAGE)
class CompetitionTemplateContracts(SimpleTestCase):
    def setUp(self):
        self.user,self.owner,self.org,self.competition,self.participant,self.result = ui_fixture()
        self.access = self.enterContext(patch("competitions.templatetags.competition_ui.has_organization_capability",return_value=False))
        self.enterContext(patch("competitions.templatetags.competition_ui.get_owned_organization",return_value=self.org))

    def render(self, template, **context):
        request = RequestFactory().get("/competitions/",{"organization_id":self.org.id})
        request.user = self.user
        return render_to_string("competitions/"+template+".html",{"user":self.user,**context},request=request)

    def test_discovery_keeps_get_filters_and_all_four_categories(self):
        html = self.render("competition_list",competitions=[self.competition],categories=Competition.CATEGORIES,query="robot & art",selected_category="SCIENCE_TECHNOLOGY")
        self.assertIn('name="q" value="robot &amp; art"',html)
        self.assertIn('value="SCIENCE_TECHNOLOGY" selected',html)
        for category,_ in Competition.CATEGORIES:
            self.assertIn(f"category={category}",html)
        self.assertIn("q=robot%20%26%20art",html)
        self.assertIn("data-competition-refinements hidden",html)

    def test_posters_cover_every_category_without_unsupported_image_fields(self):
        for category,_ in Competition.CATEGORIES:
            _,_,_,competition,_,_ = ui_fixture(category)
            html = self.render("competition_card",competition=competition)
            self.assertIn(f"cp-poster--{category.lower()}",html)
            self.assertIn(reverse("competition_detail",args=[competition.id]),html)

    def test_recommendations_preserve_score_and_reasons(self):
        html = self.render("competition_list",competitions=[],categories=Competition.CATEGORIES,
            competition_recommendations=[{"competition":self.competition,"score":92,"reasons":["Matches your skills"]}])
        self.assertIn("92/100 match score",html)
        self.assertIn("Matches your skills",html)
        self.assertIn("Personalized",html)

    def test_detail_registration_role_capacity_and_csrf(self):
        for role,open_now,expected in (("ATHLETE",True,True),("ATHLETE",False,False),("COACH",True,False),("SCOUT",True,False)):
            self.user.role=role
            self.competition.registration_open=open_now
            html = self.render("competition_detail",competition=self.competition)
            self.assertEqual(f'action="{reverse("competition_register",args=[5])}"' in html,expected)
            if expected: self.assertIn('name="csrfmiddlewaretoken"',html)
            if role=="SCOUT": self.assertIn(reverse("competition_participants",args=[5]),html)

    def test_registered_submission_action_only_when_supported(self):
        for status,participant_status,expected in (("PUBLISHED","REGISTERED",False),("ONGOING","REGISTERED",True),("ONGOING","DISQUALIFIED",False),("JUDGING","REGISTERED",False)):
            self.competition.status=status
            self.participant.status=participant_status
            html = self.render("competition_detail",competition=self.competition,participation=self.participant)
            self.assertEqual(reverse("competition_submission",args=[5]) in html,expected)
            self.assertNotIn(f'action="{reverse("competition_register",args=[5])}"',html)

    def test_lifecycle_actions_keep_action_names_post_and_csrf(self):
        self.user=self.owner
        self.access.return_value=True
        stages={"DRAFT":["submit","cancel"],"REJECTED":["submit","cancel"],"SUBMITTED":["cancel"],
            "APPROVED":["publish","cancel"],"PUBLISHED":["close_registration","start","cancel"],
            "REGISTRATION_CLOSED":["start","cancel"],"ONGOING":["start_judging","cancel"],
            "JUDGING":["publish_results","cancel"],"RESULTS":["complete","cancel"],"COMPLETED":[],"CANCELLED":[]}
        for stage,actions in stages.items():
            self.competition.status=stage
            html = self.render("management_actions",competition=self.competition)
            for action in ("submit","publish","close_registration","start","start_judging","publish_results","complete","cancel"):
                self.assertEqual(f'name="action" value="{action}"' in html,action in actions)
            self.assertEqual(html.count('name="csrfmiddlewaretoken"'),len(actions))

    def test_read_only_members_and_admins_do_not_receive_owner_mutation_controls(self):
        html = self.render("management_actions",competition=self.competition)
        self.assertNotIn('name="action"',html)
        self.user.role="ADMIN"
        html = self.render("management_actions",competition=self.competition)
        self.assertIn('name="action" value="cancel"',html)
        self.assertNotIn('value="start"',html)

    def test_scout_submission_privacy_and_judging_state(self):
        html = self.render("participants",competition=self.competition,participants=[self.participant],is_scout=True)
        self.assertNotIn(self.participant.submission,html)
        self.assertNotIn(self.participant.submission_url,html)
        self.competition.status="JUDGING"
        html = self.render("participants",competition=self.competition,participants=[self.participant],can_evaluate=True)
        self.assertIn(reverse("competition_evaluate",args=[5,6]),html)

    def test_forms_retain_fields_and_non_field_errors(self):
        for template,form in (("competition_create",CompetitionForm()),("registration",SubmissionForm()),("evaluation",EvaluationForm()),("judging",JudgeAssignmentForm())):
            if isinstance(form,JudgeAssignmentForm): form.fields["coach"].queryset=get_user_model().objects.none()
            form.cleaned_data={}
            form.add_error(None,"Please correct the competition details.")
            html=self.render(template,form=form,competition=self.competition,participant=self.participant,is_organizer=True)
            for name in form.fields: self.assertIn(f'name="{name}"',html)
            self.assertIn("Please correct the competition details.",html)
            self.assertIn('name="csrfmiddlewaretoken"',html)
        mentor_html=self.render("evaluation",form=EvaluationForm(require_score=False),competition=self.competition,participant=self.participant,is_mentor=True)
        self.assertNotIn('name="score"',mentor_html)
        self.assertIn("Save feedback",mentor_html)

    def test_link_only_submission_is_available_to_evaluators(self):
        self.participant.submission=""
        html=self.render("evaluation",form=EvaluationForm(),competition=self.competition,participant=self.participant)
        self.assertIn(self.participant.submission_url,html)

    def test_result_entry_preserves_zero_score_and_only_supported_stages(self):
        for status,expected in (("JUDGING",True),("RESULTS",True),("COMPLETED",False)):
            self.competition.status=status
            html=self.render("results",competition=self.competition,participants=[self.participant],results=[self.result],can_manage=True)
            self.assertEqual('name="score"' in html,expected)
            if expected:
                self.assertIn('value="0.00"',html)
                self.assertIn('for="result-score-6"',html)
                self.assertIn(reverse("competition_save_result",args=[5,6]),html)
        html=self.render("results",competition=self.competition,participants=[self.participant],results=[self.result],can_manage=False)
        self.assertNotIn('name="score"',html)

    def test_anonymous_discovery_and_empty_states(self):
        self.user=AnonymousUser()
        html=self.render("competition_list",competitions=[],categories=Competition.CATEGORIES)
        self.assertIn("No matching competitions",html)
        self.assertNotIn("Create competition",html)
        self.user = ui_fixture()[0]
        for template,context in (("my_competitions",{"participants":[]}), ("participants",{"competition":self.competition,"participants":[]}),
            ("judging",{"assignments":[]}), ("results",{"competition":self.competition,"results":[]}), ("moderation",{"competitions":[]})):
            self.assertIn("cp-empty",self.render(template,**context))


@override_settings(STORAGES=UI_STORAGE,ALLOWED_HOSTS=["testserver"])
class CompetitionWebUIIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User=get_user_model()
        cls.owner=User.objects.create_user(username="cp_ui_owner",role="ORGANIZATION")
        cls.athlete=User.objects.create_user(username="cp_ui_athlete",role="ATHLETE")
        cls.coach=User.objects.create_user(username="cp_ui_coach",role="COACH")
        cls.org=Organization.objects.create(user=cls.owner,name="Competition UI Studio",country="GH")
        cls.talent=TalentProfile.objects.create(user=cls.athlete)
        today=timezone.localdate()
        cls.competition=Competition.objects.create(organization=cls.org,title="UI Innovation Challenge",category="SCIENCE_TECHNOLOGY",
            description="An innovation challenge.",status="PUBLISHED",registration_start=today-timedelta(days=1),
            registration_end=today+timedelta(days=3),competition_start=today+timedelta(days=4),competition_end=today+timedelta(days=6),max_participants=10)

    def csrf_client(self,user,route,*args):
        client=Client(enforce_csrf_checks=True)
        client.force_login(user)
        response=client.get(reverse(route,args=args))
        self.assertEqual(response.status_code,200)
        return client,client.cookies["csrftoken"].value

    def test_csrf_registration_and_submission_work_without_changing_routes(self):
        client,csrf=self.csrf_client(self.athlete,"competition_detail",self.competition.pk)
        url=reverse("competition_register",args=[self.competition.pk])
        self.assertEqual(client.post(url).status_code,403)
        self.assertEqual(client.post(url,{"csrfmiddlewaretoken":csrf}).status_code,302)
        self.assertEqual(client.post(url,{"csrfmiddlewaretoken":csrf}).status_code,302)
        self.assertEqual(CompetitionParticipant.objects.filter(competition=self.competition,talent=self.talent).count(),1)
        self.competition.status="ONGOING"
        self.competition.save(update_fields=["status"])
        url=reverse("competition_submission",args=[self.competition.pk])
        response=client.get(url)
        self.assertContains(response,'name="submission_url"')
        self.assertEqual(client.post(url,{"csrfmiddlewaretoken":csrf,"submission":"Original work","submission_url":"https://example.com/work"}).status_code,302)
        self.assertEqual(CompetitionParticipant.objects.get(talent=self.talent).submission,"Original work")

    def test_judging_zero_score_result_entry_and_publication_posts(self):
        participant=CompetitionParticipant.objects.create(competition=self.competition,talent=self.talent,submission_url="https://example.com/work")
        CompetitionJudge.objects.create(competition=self.competition,coach=self.coach,role="JUDGE")
        self.competition.status="JUDGING"
        self.competition.save(update_fields=["status"])
        client,csrf=self.csrf_client(self.coach,"competition_evaluate",self.competition.pk,participant.pk)
        self.assertEqual(client.post(reverse("competition_evaluate",args=[self.competition.pk,participant.pk]),{"csrfmiddlewaretoken":csrf,"score":"0","feedback":"Needs refinement"}).status_code,302)
        self.assertEqual(CompetitionEvaluation.objects.get(participant=participant).score,0)
        client,csrf=self.csrf_client(self.owner,"competition_results",self.competition.pk)
        self.assertEqual(client.post(reverse("competition_save_result",args=[self.competition.pk,participant.pk])+f"?organization_id={self.org.pk}",{"csrfmiddlewaretoken":csrf,"position":"1","score":"0","award":"Originality"}).status_code,302)
        response=client.get(reverse("competition_results",args=[self.competition.pk]))
        self.assertContains(response,'value="0.00"')
        self.assertEqual(client.post(reverse("competition_action",args=[self.competition.pk])+f"?organization_id={self.org.pk}",{"csrfmiddlewaretoken":csrf,"action":"publish_results"}).status_code,302)
        self.competition.refresh_from_db()
        self.assertEqual(self.competition.status,"RESULTS")
        self.assertIsNotNone(CompetitionResult.objects.get(participant=participant).published_at)

    def test_four_categories_are_discoverable_using_existing_get_filter(self):
        for category,label in Competition.CATEGORIES:
            self.competition.category=category
            self.competition.save(update_fields=["category"])
            response=self.client.get(reverse("competition_list"),{"q":"Innovation","category":category})
            self.assertEqual(response.status_code,200)
            self.assertContains(response,"UI Innovation Challenge")
            self.assertContains(response,f"cp-poster--{category.lower()}")
