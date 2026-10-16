"""Add POST guards only to manually confirmed state-changing web actions."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent
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
def apply_guards():
    for app, names in GUARDS.items():
        path = ROOT / app / 'views.py'
        source = path.read_text(encoding='utf-8')
        functions = {node.name: node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}
        lines = source.splitlines(keepends=True)
        for name in sorted(names, key=lambda name: functions[name].lineno, reverse=True):
            function = functions[name]
            if not any(ast.unparse(decorator) == 'require_POST' for decorator in function.decorator_list):
                lines.insert(function.lineno - 1, '@require_POST\n')
        source = ''.join(lines)
        if 'from django.views.decorators.http import require_POST' not in source:
            source = 'from django.views.decorators.http import require_POST\n' + source
        if source != path.read_text(encoding='utf-8'):
            path.write_text(source, encoding='utf-8')
        print(f'{app}: {len(names)} confirmed action guards')


if __name__ == '__main__':
    apply_guards()
