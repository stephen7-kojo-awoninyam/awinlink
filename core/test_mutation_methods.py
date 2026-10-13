import importlib
import inspect

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse, NoReverseMatch

GUARDS = {
    'events': ['register_event', 'like_event', 'cancel_registration', 'reject_registration', 'mark_attendance', 'approve_registration', 'delete_event_media'],
    'learning': ['like_course', 'enroll_course', 'submit_course'],
    'connections': ['follow_user', 'unfollow_user', 'follow_organization', 'unfollow_organization', 'accept_connection_request', 'reject_connection_request', 'cancel_connection_request', 'remove_connection'],
    'feed': ['like_post', 'save_post'],
    'dashboard': ['toggle_user_status', 'toggle_talent_status'],
    'portfolio': ['delete_portfolio_item'],
    'talents': ['delete_experience', 'delete_certification', 'delete_achievement', 'follow_talent', 'unfollow_talent'],
    'coaches': ['save_talent', 'follow_talent', 'unfollow_talent'],
    'messaging': ['start_conversation', 'start_coach_conversation'],
}


class MutationMethodSecurityTests(TestCase):
    def test_confirmed_web_actions_reject_get_and_csrf_less_post(self):
        user = get_user_model().objects.create_user(username='method_audit_admin', role='ADMIN')
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(user)
        factory = RequestFactory()
        for app, names in GUARDS.items():
            views = importlib.import_module(app + '.views')
            for name in names:
                with self.subTest(app=app, view=name):
                    view = getattr(views, name)
                    arguments = {parameter: 1 for parameter, detail in inspect.signature(view).parameters.items()
                                 if parameter != 'request' and detail.default is inspect.Parameter.empty}
                    request = factory.get('/')
                    request.user = user
                    self.assertEqual(view(request, **arguments).status_code, 405)
                    try:
                        url = reverse(view, kwargs=arguments)
                    except NoReverseMatch:
                        url = reverse(f'{app}:{name}', kwargs=arguments)
                    self.assertEqual(browser.post(url).status_code, 403)
