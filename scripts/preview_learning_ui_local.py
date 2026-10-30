"""Render real Learning templates with synthetic objects, no database/network.

The minimal base isolates Learning from the global shell and external CDN assets.
Output is review/test material only; this does not start a server or deploy.
"""
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from scripts.audit_turn_ice_local import offline_network
    runtime = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'TEMP', 'TMP') if key in os.environ}
    with patch.dict(os.environ, {**runtime, 'DJANGO_SETTINGS_MODULE': 'config.settings',
            'AWINLINK_ENV': 'development', 'DEBUG': 'true',
            'SECRET_KEY': 'learning-ui-preview-fixture-not-for-production-0123456789'}, clear=True), \
            patch('dotenv.load_dotenv', return_value=False), offline_network():
        from django.conf import settings
        settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
        settings.STORAGES = {'default': {'BACKEND': 'django.core.files.storage.InMemoryStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
        styles = (ROOT / 'static/css/learning.css').read_text(encoding='utf-8')
        learning_script = (ROOT / 'static/js/learning.js').read_text(encoding='utf-8')
        # Minimal shell/Bootstrap utilities; no external requests or substituted Learning markup.
        base = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Learning UI fixture</title><style>
body{margin:0;padding:24px;background:#f6f8fc;font-family:Arial,sans-serif}button,input,select,textarea{font:inherit}a{color:inherit}.w-100{width:100%}.mt-0{margin-top:0}.mt-2{margin-top:8px}.mt-3{margin-top:16px}.mb-3{margin-bottom:16px}.visually-hidden{position:absolute!important;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
''' + styles + '''</style></head><body>{% block content %}{% endblock %}</body></html>'''
        config = settings.TEMPLATES[0]
        config['APP_DIRS'] = False
        config['OPTIONS']['context_processors'] = ['django.template.context_processors.request', 'django.template.context_processors.csrf']
        config['OPTIONS']['loaders'] = [('django.template.loaders.locmem.Loader', {'base.html': base}),
            'django.template.loaders.filesystem.Loader', 'django.template.loaders.app_directories.Loader']
        import django
        django.setup()
        from django.db import connection
        from django.template.loader import render_to_string
        from django.test import RequestFactory
        from learning.test_ui import ui_fixture
        user, creator, category, course, lessons, enrollment, quiz, question = ui_fixture()
        sections = [type('Module', (), {'title': 'Foundations'})(), type('Module', (), {'title': 'Practice'})()]
        for lesson in lessons:
            lesson.module = sections[0] if lesson.order < 3 else sections[1]
            lesson.module_id = 1 if lesson.order < 3 else 2
        curriculum_sections = [
            {'title': 'Foundations', 'lessons': lessons[:2]},
            {'title': 'Practice', 'lessons': lessons[2:]},
        ]
        enrollment.total_lessons, enrollment.completed_lessons = 3, 1
        request = RequestFactory().get('/learning/')
        request.user = user
        output = ROOT / '.audit-learning-ui'
        output.mkdir(exist_ok=True)

        def deny_sql(*args, **kwargs):
            raise AssertionError('UI preview must not query a database')

        def render(name, template, **context):
            with connection.execute_wrapper(deny_sql):
                html = render_to_string('learning/' + template + '.html', {'user': user, **context}, request=request)
            if template == 'lesson_detail':
                html = html.replace('</body>', '<script>' + learning_script + '</script></body>')
            (output / (name + '.html')).write_text(html, encoding='utf-8')

        render('home', 'course_list', courses=[course] * 3, categories=[category], continue_enrollments=[enrollment])
        live_session = type('LiveSession', (), {'id': 71, 'title': 'Foundations live Q&A', 'status': 'LIVE',
            'lesson': lessons[1], 'classroom': type('Classroom', (), {'title': 'Learning studio'})(),
            'scheduled_start': None})()
        render('detail', 'course_detail', course=course, lessons=lessons, curriculum_sections=curriculum_sections,
            learning_live_sessions=[live_session], enrollment=enrollment, reviews=[], total_reviews=0)
        render('detail-flat', 'course_detail', course=course, lessons=lessons, enrollment=enrollment, reviews=[], total_reviews=0)
        for item in lessons:
            item.workspace_progress = type('Progress', (), {'completed': item.order == 1})()
        lessons[1].video = type('Media', (), {'url': '/media/learning/private-example.webm'})()
        lessons[1].notes = type('Media', (), {'url': '/media/learning/lesson-notes.pdf'})()
        lessons[1].captions = type('Media', (), {'url': '/media/learning/captions/lesson.vtt'})()
        lessons[1].caption_language = 'en-US'
        lessons[1].transcript = 'Welcome to this lesson. Follow the examples as you watch.'
        render('lesson-workspace', 'lesson_detail', course=course, lesson=lessons[1], lessons=lessons, curriculum_sections=curriculum_sections,
            quiz=lessons[1].quiz, progress=type('Progress', (), {'completed': False})(),
            course_progress_percent=33, latest_attempt=None, learning_live_sessions=[live_session])
        render('quiz', 'take_quiz', course=course, lesson=lessons[0], quiz=quiz, questions=[question], enrollment=enrollment)
        render('quiz-result', 'quiz_result', course=course, lesson=lessons[0], quiz=quiz, enrollment=enrollment,
            score=0, total_questions=1, percentage=0, passed=False,
            question_feedback=[{'question_id': question.id, 'question': question.question, 'selected_answer': 'A',
                'selected_text': question.option_a, 'correct_answer': question.correct_answer,
                'correct_text': question.option_b, 'is_correct': False}])
        course.status = 'REJECTED'
        course.rejection_reason = 'Please add clear learning objectives.'
        checks = [type('Check', (), {'key': 'course', 'label': 'Course information', 'ready': True, 'detail': 'Title, category and description are ready.'})(),
            type('Check', (), {'key': 'curriculum', 'label': 'Lesson curriculum', 'ready': True, 'detail': '3 lessons added.'})(),
            type('Check', (), {'key': 'quizzes', 'label': 'Quiz content', 'ready': False, 'detail': 'Complete each quiz question and select a valid correct answer.'})()]
        render('studio', 'manage_course', course=course, lessons=lessons, modules=[
            type('Section', (), {'id': 1, 'title': 'Foundations', 'order': 1})(),
            type('Section', (), {'id': 2, 'title': 'Practice', 'order': 2})(),
        ], submission_checklist=checks)
        course.status = 'APPROVED'
        course.is_free = False
        render('paid-preview', 'course_detail', course=course, lessons=lessons, reviews=[], total_reviews=0)
        render('empty-home', 'course_list', courses=[], categories=[], continue_enrollments=[])
        print('Rendered nine synthetic Learning fixtures; no database or network access.')


if __name__ == '__main__':
    main()
