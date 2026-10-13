"""Focused learning UI contracts and CSRF-enforced learner/creator workflows."""
from copy import deepcopy
from types import SimpleNamespace as NS
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse as django_reverse
from django.utils import timezone

from .forms import CourseForm, LessonForm, CourseReviewForm, QuizForm, QuestionForm
from .models import Course, LearningCategory, Lesson, Enrollment, LessonProgress, Quiz, Question, QuizAttempt, CourseReview
from . import views


def reverse(name, args=None, kwargs=None):
    web_names = {"my_courses", "lesson_detail", "course_progress", "my_certificates", "my_quiz_attempts"}
    return django_reverse(getattr(views, name) if name in web_names else name, args=args, kwargs=kwargs)

UI_TEMPLATES = deepcopy(settings.TEMPLATES)
UI_TEMPLATES[0]["OPTIONS"]["context_processors"] = [
    "django.template.context_processors.csrf", "django.template.context_processors.request",
]
UI_STORAGE = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def ui_fixture():
    user = NS(pk=1,id=1,is_authenticated=True,is_superuser=False,role="ATHLETE",username="alex",get_full_name=lambda:"Alex Morgan")
    creator = NS(pk=2,id=2,is_authenticated=True,is_superuser=False,role="COACH",username="jordan",get_full_name=lambda:"Jordan Lee")
    category = NS(id=3,name="Creative practice")
    empty = NS(count=lambda:0,all=lambda:[],filter=lambda **kwargs:NS(exists=lambda:False))
    course = NS(pk=4,id=4,title="Find your creative voice",slug="find-your-creative-voice",creator=creator,category=category,
        thumbnail=None,level="BEGINNER",duration=45,is_free=True,status="APPROVED",created_at=timezone.now(),
        rejection_reason="Please add clear learning objectives.",description="Start with curiosity. Build a creative practice that fits your life.\nExplore new ideas, find your perspective, and make something that feels like you.",
        get_level_display=lambda:"Beginner",likes=empty,comments=empty)
    course.get_status_display=lambda:course.status.title()
    lessons=[NS(pk=5+i,id=5+i,course=course,title=title,order=i+1,duration=15,description="Take a fresh look at your creative process.",
        video=None,notes=None,quiz=None,progress=NS(completed=i==0)) for i,title in enumerate(["Start with what you notice","Turn an idea into a practice","Share your perspective"])]
    course.lessons=NS(all=lambda:lessons,count=lambda:len(lessons),exists=lambda:bool(lessons))
    enrollment=NS(pk=8,id=8,user=user,course=course,completed=False,progress_percentage=33,enrolled_at=timezone.now(),certificate=None)
    quiz=NS(pk=9,id=9,title="A fresh perspective",passing_score=70,lesson=lessons[0])
    lessons[0].quiz=quiz
    question=NS(id=10,quiz=quiz,question="What helps you develop a creative practice?",option_a="Waiting for the perfect idea",option_b="Exploring and practising regularly",option_c="Avoiding new perspectives",option_d="Comparing every step with others",correct_answer="B")
    quiz.questions=NS(all=lambda:[question],count=lambda:1)
    return user,creator,category,course,lessons,enrollment,quiz,question


@override_settings(TEMPLATES=UI_TEMPLATES,STORAGES=UI_STORAGE)
class LearningTemplateContracts(SimpleTestCase):
    def setUp(self):
        self.user,self.creator,self.category,self.course,self.lessons,self.enrollment,self.quiz,self.question=ui_fixture()

    def render(self, template, query=None, **context):
        request=RequestFactory().get("/learning/",query or {})
        request.user=self.user
        return render_to_string("learning/"+template+".html",{"user":self.user,**context},request=request)

    def test_discovery_uses_backend_query_names_and_retains_filter_selection(self):
        html=self.render("course_list",query={"q":"practice","category":"3","level":"ADVANCED"},courses=[self.course],categories=[self.category])
        html=html.split('<div class="learning-page">',1)[1]
        self.assertIn('name="q" value="practice"',html)
        self.assertNotIn('name="search"',html)
        self.assertIn('value="ADVANCED" selected',html)
        self.assertIn('value="3" selected',html)
        self.assertIn(reverse("course_detail",args=[self.course.slug]),html)

    def test_course_detail_is_course_content_with_enrollment_access_controls(self):
        html=self.render("course_detail",course=self.course,lessons=self.lessons,reviews=[],total_reviews=0)
        self.assertIn("About this course",html)
        self.assertNotIn("Certificate of Completion",html)
        self.assertIn(f'action="{reverse("enroll_course",args=[4])}"',html)
        self.assertNotIn(f'href="{reverse("lesson_detail",args=[5])}"',html)
        enrolled=self.render("course_detail",course=self.course,lessons=self.lessons,enrollment=self.enrollment,reviews=[])
        self.assertNotIn(f'action="{reverse("enroll_course",args=[4])}"',enrolled)
        self.assertIn(reverse("lesson_detail",args=[5]),enrolled)
        self.assertIn(reverse("review_course",args=[4]),enrolled)
        self.assertIn('name="csrfmiddlewaretoken"',enrolled)

    def test_lesson_viewer_keeps_native_media_quiz_completion_and_adjacent_routes(self):
        lesson=self.lessons[1]
        lesson.video=NS(url="/media/learning/example.webm")
        lesson.notes=NS(url="/media/learning/notes.pdf")
        html=self.render("lesson_detail",course=self.course,lesson=lesson,lessons=self.lessons,quiz=self.quiz,progress=NS(completed=False))
        self.assertIn("controls playsinline preload=",html)
        self.assertIn(lesson.video.url,html)
        self.assertIn(lesson.notes.url,html)
        self.assertIn(reverse("take_quiz",args=[9]),html)
        self.assertIn(f'action="{reverse("complete_lesson",args=[6])}"',html)
        self.assertIn(reverse("lesson_detail",args=[5]),html)
        self.assertIn(reverse("lesson_detail",args=[7]),html)
        completed=self.render("lesson_detail",course=self.course,lesson=lesson,lessons=self.lessons,progress=NS(completed=True))
        self.assertNotIn(f'action="{reverse("complete_lesson",args=[6])}"',completed)

    def test_quiz_radio_contract_and_result_retry_paths(self):
        html=self.render("take_quiz",course=self.course,lesson=self.lessons[0],quiz=self.quiz,questions=[self.question])
        self.assertEqual(html.count('name="question_10"'),4)
        for letter in "ABCD": self.assertIn(f'value="{letter}"',html)
        self.assertIn("required",html)
        self.assertNotIn("Correct answer:",html)
        for passed,expected in ((True,"Continue learning"),(False,"Try again")):
            html=self.render("quiz_result",course=self.course,lesson=self.lessons[0],quiz=self.quiz,percentage=0,score=0,total_questions=1,passed=passed)
            self.assertIn(expected,html)
            self.assertIn("0%",html)

    def test_studio_editing_and_submission_controls_follow_approval_state(self):
        self.user=self.creator
        for status,editable in (("DRAFT",True),("REJECTED",True),("PENDING",False),("APPROVED",False)):
            self.course.status=status
            html=self.render("manage_course",course=self.course,lessons=self.lessons)
            self.assertEqual(reverse("add_lesson",args=[4]) in html,editable)
            self.assertEqual(f'action="{reverse("delete_lesson",args=[5])}"' in html,editable)
            self.assertEqual(f'action="{reverse("submit_course",args=[4])}"' in html,editable)
        self.user.role="ADMIN"
        self.assertIn(reverse("admin_courses"),self.render("course_list",courses=[],categories=[]))

    def test_creator_forms_preserve_fields_uploads_errors_and_missing_lesson_templates(self):
        for template,form,uploads in (("create_course",CourseForm(),True),("edit_course",CourseForm(),True),("add_lesson",LessonForm(),True),
            ("edit_lesson",LessonForm(),True),("review_course",CourseReviewForm(),False),("edit_quiz",QuizForm(),False),("add_question",QuestionForm(),False)):
            if isinstance(form,CourseForm): form.fields["category"].queryset=LearningCategory.objects.none()
            form.cleaned_data={}
            form.add_error(None,"Please correct the submitted fields.")
            html=self.render(template,form=form,course=self.course,lesson=self.lessons[0],quiz=self.quiz)
            for name in form.fields: self.assertIn(f'name="{name}"',html)
            self.assertEqual('enctype="multipart/form-data"' in html,uploads)
            self.assertIn("Please correct the submitted fields.",html)
            self.assertIn('name="csrfmiddlewaretoken"',html)


@override_settings(STORAGES=UI_STORAGE,ALLOWED_HOSTS=["testserver"])
class LearningWebUIIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User=get_user_model()
        cls.creator=User.objects.create_user(username="learning_ui_creator",role="COACH")
        cls.learner=User.objects.create_user(username="learning_ui_learner",role="ATHLETE")
        cls.admin=User.objects.create_user(username="learning_ui_admin",role="ADMIN")
        cls.category=LearningCategory.objects.create(name="UI Creative practice")
        cls.course=Course.objects.create(creator=cls.creator,category=cls.category,title="Creative learning UI",slug="creative-learning-ui",description="An introduction to creative practice.",status="APPROVED")
        cls.lesson=Lesson.objects.create(course=cls.course,title="Notice your next idea",order=1,duration=10)
        cls.quiz=Quiz.objects.create(lesson=cls.lesson,title="Creative knowledge check",passing_score=70)
        cls.question=Question.objects.create(quiz=cls.quiz,question="Which approach helps?",option_a="Practice",option_b="Never try",option_c="Never learn",option_d="Never ask",correct_answer="A")

    def csrf_client(self,user,route,*args):
        client=Client(enforce_csrf_checks=True)
        client.force_login(user)
        response=client.get(reverse(route,args=args))
        self.assertEqual(response.status_code,200)
        return client,client.cookies["csrftoken"].value

    def test_enrollment_is_csrf_protected_unique_and_lessons_require_enrollment(self):
        client,csrf=self.csrf_client(self.learner,"course_detail",self.course.slug)
        self.assertEqual(client.get(reverse("lesson_detail",args=[self.lesson.pk])).status_code,404)
        self.assertEqual(client.get(reverse("take_quiz",args=[self.quiz.pk])).status_code,404)
        url=reverse("enroll_course",args=[self.course.pk])
        self.assertEqual(client.post(url).status_code,403)
        for _ in range(2): self.assertEqual(client.post(url,{"csrfmiddlewaretoken":csrf}).status_code,302)
        self.assertEqual(Enrollment.objects.filter(user=self.learner,course=self.course).count(),1)
        self.assertEqual(client.get(reverse("lesson_detail",args=[self.lesson.pk])).status_code,200)

    @patch("learning.views.generate_certificate",return_value=None)
    def test_quiz_must_pass_before_explicit_lesson_completion(self,generate):
        enrollment=Enrollment.objects.create(user=self.learner,course=self.course)
        client,csrf=self.csrf_client(self.learner,"lesson_detail",self.lesson.pk)
        complete=reverse("complete_lesson",args=[self.lesson.pk])
        response=client.post(complete,{"csrfmiddlewaretoken":csrf})
        self.assertRedirects(response,reverse("take_quiz",args=[self.quiz.pk]))
        self.assertFalse(LessonProgress.objects.get(enrollment=enrollment,lesson=self.lesson).completed)
        quiz_url=reverse("take_quiz",args=[self.quiz.pk])
        response=client.post(quiz_url,{"csrfmiddlewaretoken":csrf,f"question_{self.question.pk}":"B"})
        self.assertContains(response,"Try again")
        self.assertEqual(QuizAttempt.objects.get(enrollment=enrollment).percentage,0)
        response=client.post(quiz_url,{"csrfmiddlewaretoken":csrf,f"question_{self.question.pk}":"A"})
        self.assertContains(response,"Quiz passed!")
        self.assertFalse(LessonProgress.objects.get(enrollment=enrollment,lesson=self.lesson).completed)
        response=client.post(complete,{"csrfmiddlewaretoken":csrf})
        self.assertEqual(response.status_code,302)
        self.assertEqual(response.url,reverse("lesson_detail",args=[self.lesson.pk]))
        enrollment.refresh_from_db()
        self.assertTrue(enrollment.completed)
        self.assertTrue(LessonProgress.objects.get(enrollment=enrollment,lesson=self.lesson).completed)
        generate.assert_called_once()

    def test_enrolled_review_is_updated_instead_of_duplicated(self):
        Enrollment.objects.create(user=self.learner,course=self.course)
        client,csrf=self.csrf_client(self.learner,"review_course",self.course.pk)
        url=reverse("review_course",args=[self.course.pk])
        for rating,text in ((4,"Useful course"),(5,"Excellent course")):
            self.assertEqual(client.post(url,{"csrfmiddlewaretoken":csrf,"rating":rating,"review":text}).status_code,302)
        self.assertEqual(CourseReview.objects.filter(course=self.course,user=self.learner).count(),1)
        self.assertEqual(CourseReview.objects.get(course=self.course,user=self.learner).review,"Excellent course")

    def test_all_existing_creator_roles_can_access_studio_and_nonowners_cannot_edit(self):
        User=get_user_model()
        for role in ("ATHLETE","ORGANIZATION","SCOUT","COACH","ADMIN"):
            user=User.objects.create_user(username="learning_ui_role_"+role,role=role)
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("create_course")).status_code,200)
            self.assertEqual(self.client.get(reverse("my_courses")).status_code,200)
        self.assertEqual(self.client.get(reverse("edit_course",args=[self.course.pk])).status_code,404)

    def test_draft_lesson_templates_and_approval_lock_preserve_existing_workflow(self):
        self.course.status="DRAFT"
        self.course.save(update_fields=["status"])
        client,csrf=self.csrf_client(self.creator,"manage_course",self.course.pk)
        self.assertEqual(client.get(reverse("add_lesson",args=[self.course.pk])).status_code,200)
        self.assertEqual(client.get(reverse("edit_lesson",args=[self.lesson.pk])).status_code,200)
        response=client.post(reverse("submit_course",args=[self.course.pk]),{"csrfmiddlewaretoken":csrf})
        self.assertEqual(response.status_code,302)
        self.assertEqual(response.url,reverse("my_courses"))
        self.course.refresh_from_db()
        self.assertEqual(self.course.status,"PENDING")
        self.assertEqual(client.get(reverse("add_lesson",args=[self.course.pk])).status_code,302)
        admin,csrf=self.csrf_client(self.admin,"admin_course_detail",self.course.pk)
        self.assertEqual(admin.post(reverse("approve_course",args=[self.course.pk]),{"csrfmiddlewaretoken":csrf}).status_code,302)
        self.course.refresh_from_db()
        self.assertEqual(self.course.status,"APPROVED")
        self.assertEqual(client.get(reverse("edit_lesson",args=[self.lesson.pk])).status_code,302)

    def test_search_uses_existing_q_category_and_level_filters(self):
        self.client.force_login(self.learner)
        response=self.client.get(reverse("courses"),{"q":"Creative","category":self.category.pk,"level":"BEGINNER"})
        self.assertContains(response,self.course.title)
        response=self.client.get(reverse("courses"),{"q":"No such title"})
        self.assertContains(response,"No courses found")
