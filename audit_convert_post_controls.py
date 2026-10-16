"""Convert only confirmed state-changing links into existing-route POST forms."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
names = {'update_pipeline_stage', 'add_to_shortlist', 'remove_from_shortlist', 'toggle_star'}
names.add('start_conversation_with_opportunity')
names.add('message_talent')
from audit_guard_mutations import GUARDS, apply_guards
apply_guards()
names.update(name for group in GUARDS.values() for name in group)
files = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], text=True).splitlines()
for name in files:
    if not name.endswith('.html'):
        continue
    path = ROOT / name
    source = path.read_text(encoding='utf-8')
    count = [0]
    def convert(match):
        attrs, body = match.group(1), match.group(2)
        href = re.search(r'\bhref\s*=\s*([\"\'])(.*?)\1', attrs, re.S)
        if href is None or not any(re.search(r"{%\s*url\s+['\"](?:[a-z_]+:)?" + route + r"['\"]", href.group(2)) for route in names):
            return match.group(0)
        count[0] += 1
        remaining = attrs[:href.start()] + attrs[href.end():]
        remaining = re.sub(r'[ \t]+\n', '\n', remaining).strip()
        remaining = (' ' + remaining) if remaining else ''
        return '<form method="post" action="' + href.group(2) + '" class="d-inline">{% csrf_token %}<button type="submit"' + remaining + '>' + body + '</button></form>'
    updated = re.sub(r'<a\b([^>]*?)>(.*?)</a>', convert, source, flags=re.S)
    if count[0]:
        path.write_text(updated, encoding='utf-8')
        print(f'{name}: {count[0]} state-changing controls converted')
