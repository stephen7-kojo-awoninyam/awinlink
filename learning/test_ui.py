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

    def test_home_sections_preserve_discovery_and_owned_progress_routes(self):
        self.enrollment.total_lessons=3
        self.enrollment.completed_lessons=1
        html=self.render('course_list', courses=[self.course], categories=[self.category], continue_enrollments=[self.enrollment])
        for title in ['Continue Learning', 'Explore Courses', 'Live sessions']:
            self.assertIn(title, html)
        self.assertIn('aria-labelledby="continue-title"',html)
        self.assertIn('id="home-progress-8" value="33" max="100"',html)
        self.assertIn(reverse('learning_classrooms'),html)
        self.assertIn(reverse('course_detail',args=[self.course.slug]),html)
        empty=self.render('course_list', courses=[], categories=[], continue_enrollments=[])
        self.assertIn('Your next skill starts here',empty)
        self.assertIn('No courses found',empty)

    def test_detail_section_navigation_instructor_and_paid_enrollment_state(self):
        self.course.is_free=False
        html=self.render('course_detail',course=self.course,lessons=self.lessons,reviews=[],total_reviews=0)
        for section in ['overview','curriculum','instructor','reviews','enroll']:
            self.assertIn(f'href="#{section}"',html)
            self.assertIn(f'id="{section}"',html)
        self.assertIn('Meet your instructor',html)
        self.assertIn('Jordan Lee',html)
        self.assertIn('type="button" disabled>Paid enrollment unavailable',html)
        self.assertNotIn(f'action="{reverse("enroll_course",args=[4])}"',html)
        self.assertNotIn(f'href="{reverse("lesson_detail",args=[5])}"',html)
        enrolled=self.render('course_detail',course=self.course,lessons=self.lessons,reviews=[],enrollment=self.enrollment)
        self.assertIn(reverse('course_progress',args=[4]),enrolled)
        self.assertNotIn('Paid enrollment unavailable',enrolled)

    def test_learning_content_is_escaped_in_new_presentation(self):
        self.course.title='<script>alert("title")</script>'
        self.course.description='<img src=x onerror=alert(1)>'
        html=self.render('course_detail',course=self.course,lessons=self.lessons,reviews=[])
        self.assertNotIn(self.course.title,html)
        self.assertNotIn(self.course.description,html)
        self.assertIn('&lt;script&gt;',html)

    def test_lesson_viewer_keeps_native_media_quiz_completion_and_adjacent_routes(self):
        lesson=self.lessons[1]
        for item in self.lessons: item.workspace_progress=NS(completed=item.order==1)
        lesson.video=NS(url="/media/learning/example.webm")
        lesson.notes=NS(url="/media/learning/notes.pdf")
        html=self.render("lesson_detail",course=self.course,lesson=lesson,lessons=self.lessons,quiz=self.quiz,progress=NS(completed=False),course_progress_percent=33,latest_attempt=NS(passed=False,percentage=40))
        self.assertIn("controls playsinline preload=",html)
        self.assertIn('aria-label="Course progress"',html)
        self.assertIn("Latest attempt · 40%",html)
        self.assertIn('aria-current="page"',html)
        self.assertIn("Completed",html)
        self.assertIn(lesson.video.url,html)
        self.assertIn(lesson.notes.url,html)
        self.assertIn(reverse("take_quiz",args=[9]),html)
        self.assertIn(f'action="{reverse("complete_lesson",args=[6])}"',html)
        self.assertIn(reverse("lesson_detail",args=[5]),html)
        self.assertIn(reverse("lesson_detail",args=[7]),html)
        completed=self.render("lesson_detail",course=self.course,lesson=lesson,lessons=self.lessons,progress=NS(completed=True),course_progress_percent=100,latest_attempt=NS(passed=True,percentage=100))
        self.assertNotIn(f'action="{reverse("complete_lesson",args=[6])}"',completed)

    def test_creator_preview_renders_without_enrollment_controls_or_completion(self):
        html=self.render('course_detail',course=self.course,lessons=self.lessons,reviews=[],preview=True)
        self.assertIn('Learner preview',html)
        self.assertIn('Preview first lesson',html)
        self.assertNotIn(f'action="{reverse("enroll_course",args=[4])}"',html)
        lesson=self.lessons[0]
        html=self.render('lesson_detail',course=self.course,lesson=lesson,lessons=self.lessons,quiz=self.quiz,
            progress=None,preview=True,course_progress_percent=0,latest_attempt=None)
        self.assertIn('No completion or learner history is recorded',html)
        self.assertNotIn(f'action="{reverse("complete_lesson",args=[5])}"',html)
        self.assertNotIn(reverse('take_quiz',args=[9]),html)

    def test_quiz_radio_contract_and_result_retry_paths(self):
        html=self.render("take_quiz",course=self.course,lesson=self.lessons[0],quiz=self.quiz,questions=[self.question])
        self.assertEqual(html.count('name="question_10"'),4)
        for letter in "ABCD": self.assertIn(f'value="{letter}"',html)
        self.assertIn("required",html)
        self.assertIn('<fieldset class="lc-question">',html)
        self.assertIn('<legend>1. What helps you develop a creative practice?</legend>',html)
        self.assertNotIn("Correct answer:",html)
        for passed,expected in ((True,"Continue learning"),(False,"Try again")):
            feedback=[{"question":"What helps you develop a creative practice?","selected_answer":"A","selected_text":"Waiting for the perfect idea","correct_answer":"B","correct_text":"Exploring and practising regularly","is_correct":False}]
            html=self.render("quiz_result",course=self.course,lesson=self.lessons[0],quiz=self.quiz,percentage=0,score=0,total_questions=1,passed=passed,question_feedback=feedback)
            self.assertIn(expected,html)
            self.assertIn("0%",html)
            self.assertIn('aria-labelledby="quiz-feedback-title"',html)
            self.assertIn('Correct answer: B. Exploring and practising regularly',html)
            self.assertIn('You passed the 70% threshold' if passed else 'You need 70% to pass',html)

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

    def test_creator_dashboard_checklist_preview_and_moderation_feedback(self):
        checks=[NS(key='course',label='Course information',ready=True,detail='Ready.'),
            NS(key='curriculum',label='Lesson curriculum',ready=True,detail='2 lessons.'),
            NS(key='quizzes',label='Quiz content',ready=False,detail='Complete the quiz questions.')]
        self.course.status='REJECTED'
        self.course.rejection_reason='Add a complete final quiz.'
        html=self.render('manage_course',course=self.course,lessons=self.lessons,submission_checklist=checks)
        self.assertIn('Publishing checklist',html)
        self.assertIn('Complete the quiz questions.',html)
        self.assertIn('Preview as learner',html)
        self.assertIn('Changes requested',html)
        self.assertIn('Manage quiz',html)

    def test_creator_forms_preserve_fields_uploads_errors_and_missing_lesson_templates(self):
        for template,form,uploads in (("create_course",CourseForm(),True),("edit_course",CourseForm(),True),("add_lesson",LessonForm(),True),
            ("edit_lesson",LessonForm(),True),("review_course",CourseReviewForm(),False),("edit_quiz",QuizForm(),False),("add_question",QuestionForm(),False)):
            if isinstance(form,CourseForm): form.fields["category"].queryset=LearningCategory.objects.none()
            form.cleaned_data={}
            form.add_error(None,"Please correct the submitted fields.")
            html=self.render(template,form=form,course=self.course,lesson=self.lessons[0],quiz=self.quiz)
            # The global post composer also has an upload form. Check only the
            # learning form so this contract does not depend on shared navigation.
            html=html.split('<form class="lc-card"',1)[1].split('</form>',1)[0]
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
        self.assertFalse(LessonProgress.objects.filter(enrollment=enrollment,lesson=self.lesson,completed=True).exists())
        quiz_url=reverse("take_quiz",args=[self.quiz.pk])
        response=client.post(quiz_url,{"csrfmiddlewaretoken":csrf,f"question_{self.question.pk}":"B"})
        self.assertContains(response,"Try again")
        self.assertContains(response,"Correct answer: A. Practice")
        self.assertContains(response,"You need 70% to pass")
        self.assertEqual(QuizAttempt.objects.get(enrollment=enrollment).percentage,0)
        response=client.post(quiz_url,{"csrfmiddlewaretoken":csrf,f"question_{self.question.pk}":"A"})
        self.assertContains(response,"Quiz passed!")
        self.assertContains(response,"You passed the 70% threshold")
        self.assertContains(response,"Question feedback")
        history=client.get(reverse("my_quiz_attempts"))
        self.assertContains(history,"Pass mark 70%")
        self.assertContains(history,f'href="{quiz_url}">Try quiz again</a>')
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

    def test_creator_preview_is_private_and_does_not_create_enrollment_or_progress(self):
        self.course.status="DRAFT"
        self.course.save(update_fields=["status"])
        self.client.force_login(self.creator)
        detail=self.client.get(reverse("course_detail",args=[self.course.slug]))
        self.assertContains(detail,"Learner preview")
        lesson=self.client.get(reverse("lesson_detail",args=[self.lesson.pk]))
        self.assertContains(lesson,"No completion or learner history is recorded")
        self.assertFalse(Enrollment.objects.filter(course=self.course).exists())
        self.assertFalse(LessonProgress.objects.filter(lesson=self.lesson).exists())
        self.client.force_login(self.learner)
        self.assertEqual(self.client.get(reverse("course_detail",args=[self.course.slug])).status_code,404)
        self.assertEqual(self.client.get(reverse("lesson_detail",args=[self.lesson.pk])).status_code,404)

    def test_draft_deletion_keeps_lesson_quiz_and_question_history(self):
        self.course.status="DRAFT"
        self.course.save(update_fields=["status"])
        enrollment=Enrollment.objects.create(user=self.learner,course=self.course)
        LessonProgress.objects.create(enrollment=enrollment,lesson=self.lesson,completed=True)
        QuizAttempt.objects.create(enrollment=enrollment,quiz=self.quiz,passed=True,score=1,total_questions=1,percentage=100)
        self.client.force_login(self.creator)
        self.client.post(reverse("delete_lesson",args=[self.lesson.pk]))
        self.client.post(reverse("delete_quiz",args=[self.quiz.pk]))
        self.client.post(reverse("delete_question",args=[self.question.pk]))
        self.assertTrue(Lesson.objects.filter(pk=self.lesson.pk).exists())
        self.assertTrue(Quiz.objects.filter(pk=self.quiz.pk).exists())
        self.assertTrue(Question.objects.filter(pk=self.question.pk).exists())
        self.assertTrue(LessonProgress.objects.filter(enrollment=enrollment,lesson=self.lesson).exists())
        self.assertTrue(QuizAttempt.objects.filter(enrollment=enrollment,quiz=self.quiz).exists())

    def test_search_uses_existing_q_category_and_level_filters(self):
        self.client.force_login(self.learner)
        response=self.client.get(reverse("courses"),{"q":"Creative","category":self.category.pk,"level":"BEGINNER"})
        self.assertContains(response,self.course.title)
        response=self.client.get(reverse("courses"),{"q":"No such title"})
        self.assertContains(response,"No courses found")

    def test_home_continue_learning_is_owner_and_approved_scoped(self):
        mine=Enrollment.objects.create(user=self.learner,course=self.course)
        LessonProgress.objects.create(enrollment=mine,lesson=self.lesson,completed=True)
        other=Course.objects.create(creator=self.creator,category=self.category,title='Other learners private progress',slug='other-progress',description='Other',status='APPROVED')
        Enrollment.objects.create(user=self.admin,course=other)
        draft=Course.objects.create(creator=self.creator,category=self.category,title='Draft must stay hidden',slug='private-draft',description='Private',status='DRAFT')
        Enrollment.objects.create(user=self.learner,course=draft)
        self.client.force_login(self.learner)
        response=self.client.get(reverse('courses'))
        self.assertEqual(response.status_code,200)
        shown=response.context['continue_enrollments']
        self.assertEqual([row.pk for row in shown],[mine.pk])
        self.assertEqual(shown[0].progress_percentage,100)
        self.assertNotContains(response,draft.title)
        self.assertContains(response,'Continue Learning')
        self.assertContains(response,'Explore Courses')

    def test_detail_progress_is_read_only_and_drafts_remain_unavailable(self):
        mine=Enrollment.objects.create(user=self.learner,course=self.course)
        LessonProgress.objects.create(enrollment=mine,lesson=self.lesson,completed=True)
        self.client.force_login(self.learner)
        response=self.client.get(reverse('course_detail',args=[self.course.slug]))
        self.assertContains(response,'id="detail-progress" value="100" max="100"')
        mine.refresh_from_db()
        self.assertFalse(mine.completed)  # Reading the UI never awards completion.
        self.course.status='DRAFT'
        self.course.save(update_fields=['status'])
        self.assertEqual(self.client.get(reverse('course_detail',args=[self.course.slug])).status_code,404)
