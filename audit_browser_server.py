"""Synthetic, loopback-only browser audit. Uses its own database and media."""
import json
import os
import sys
from pathlib import Path
from datetime import timedelta

ROOT = Path(__file__).resolve().parent
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
os.environ['DATABASE_URL'] = ''
os.environ['REDIS_URL'] = ''
from django.conf import settings
settings.DEBUG = True
settings.ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
settings.SECURE_SSL_REDIRECT = False
settings.SESSION_COOKIE_SECURE = False
settings.CSRF_COOKIE_SECURE = False
settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(ROOT / '.audit-browser.sqlite3')}}
settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
settings.CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}
settings.STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
settings.MEDIA_ROOT = ROOT / '.audit-media'
settings.WEB_PUSH_PUBLIC_KEY = ''
settings.WEB_PUSH_PRIVATE_KEY = ''
import django
django.setup()
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from organizations.models import Organization, OrganizationMembership
from talents.models import TalentProfile
from learning.models import Course, LearningCategory, Lesson, Quiz, Question
from events.models import Event, EventCategory
from competitions.models import Competition
from domains.models import TalentDomain
from opportunities.models import Opportunity
from recruitment.models import RecruitmentStage
from shortlists.models import Shortlist
from coaches.models import CoachProfile, CoachTalentBookmark

call_command('migrate', interactive=False, verbosity=0)
User = get_user_model()
users = {}
for role in ('ATHLETE', 'ORGANIZATION', 'SCOUT', 'COACH', 'ADMIN'):
    user, _ = User.objects.get_or_create(username='audit_' + role.lower(), defaults={'role': role})
    user.set_password('SyntheticAuditPass123!')
    user.save()
    users[role] = user
TalentProfile.objects.get_or_create(user=users['ATHLETE'])
org, _ = Organization.objects.get_or_create(user=users['ORGANIZATION'], defaults={'name': 'Audit Studio', 'country': 'GH'})
OrganizationMembership.objects.get_or_create(organization=org, user=users['ORGANIZATION'], defaults={'role': 'OWNER'})
OrganizationMembership.objects.get_or_create(organization=org, user=users['SCOUT'], defaults={'role': 'VIEWER'})
category, _ = LearningCategory.objects.get_or_create(name='Audit Creative Practice')
course, _ = Course.objects.get_or_create(slug='audit-creative-practice', defaults={
    'creator': users['COACH'], 'category': category, 'title': 'Audit creative practice',
    'description': 'Learn, practise, and share your next idea.', 'status': 'APPROVED'})
lesson, _ = Lesson.objects.get_or_create(course=course, order=1, defaults={'title': 'Find a fresh perspective', 'duration': 10})
quiz, _ = Quiz.objects.get_or_create(lesson=lesson, defaults={'title': 'Creative knowledge check', 'passing_score': 70})
Question.objects.get_or_create(quiz=quiz, question='What helps you learn?', defaults={
    'option_a': 'Practice', 'option_b': 'Never try', 'option_c': 'Never ask', 'option_d': 'Never explore', 'correct_answer': 'A'})
event_category, _ = EventCategory.objects.get_or_create(name='Audit Workshops')
start = timezone.now() + timedelta(days=10)
event, _ = Event.objects.get_or_create(slug='audit-workshop', defaults={
    'organizer': org, 'category': event_category, 'title': 'Audit workshop', 'description': 'Learn together.',
    'event_type': 'WORKSHOP', 'location': 'Accra', 'start_date': start, 'end_date': start + timedelta(hours=2),
    'registration_deadline': start - timedelta(days=1), 'capacity': 20, 'status': 'PUBLISHED'})
today = timezone.localdate()
competition, _ = Competition.objects.get_or_create(title='Audit Innovation Challenge', organization=org, defaults={
    'category': 'SCIENCE_TECHNOLOGY', 'description': 'Build a fresh idea.', 'status': 'PUBLISHED',
    'registration_start': today - timedelta(days=1), 'registration_end': today + timedelta(days=3),
    'competition_start': today + timedelta(days=4), 'competition_end': today + timedelta(days=6), 'max_participants': 10})
domain, _ = TalentDomain.objects.get_or_create(name='Audit Arts')
opportunity, _ = Opportunity.objects.get_or_create(organization=org, title='Audit creative opportunity', defaults={
    'domain': domain, 'description': 'Share your creative portfolio.', 'deadline': today + timedelta(days=10)})
Shortlist.objects.get_or_create(organization=org, talent=TalentProfile.objects.get(user=users['ATHLETE']))
RecruitmentStage.objects.get_or_create(organization=org, talent=TalentProfile.objects.get(user=users['ATHLETE']), opportunity=opportunity)
coach, _ = CoachProfile.objects.get_or_create(user=users['COACH'], defaults={'coach_category': 'SPORTS'})
CoachTalentBookmark.objects.get_or_create(coach=coach, talent=TalentProfile.objects.get(user=users['ATHLETE']))
manifest = {'users': {role: user.username for role, user in users.items()}, 'routes': {
    'event': reverse('event_detail', args=[event.id]),
    'event_register': reverse('register_event', args=[event.id]),
    'competition': reverse('competition_detail', args=[competition.id]),
    'competition_register': reverse('competition_register', args=[competition.id]),
    'course': reverse('course_detail', args=[course.slug]),
    'enroll': reverse('enroll_course', args=[course.id]),
    'opportunity': reverse('opportunity_detail', args=[opportunity.id]),
    'apply': reverse('apply_opportunity', args=[opportunity.id]),
}, 'ids': {'event': event.id, 'competition': competition.id, 'course': course.id, 'lesson': lesson.id, 'quiz': quiz.id}}
(ROOT / 'audit-browser-manifest.json').write_text(json.dumps(manifest, indent=2))
print('Synthetic loopback audit server ready.', flush=True)
if '--seed-only' in sys.argv:
    raise SystemExit(0)
from daphne.cli import CommandLineInterface
CommandLineInterface().run(['-b', '127.0.0.1', '-p', '8765', 'config.asgi:application'])
