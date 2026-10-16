"""Resolve literal and templated mobile API paths without issuing requests."""
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
import django
django.setup()
from django.urls import resolve, Resolver404

matched, unresolved = [], []
pattern = re.compile(r"\bapiRequest(?:<[^\n]*?>)?\(\s*(['\"`])(.+?)\1", re.S)
for directory in (ROOT / 'mobile/app', ROOT / 'mobile/src'):
    for path in directory.rglob('*.ts*'):
        source = path.read_text(encoding='utf-8')
        for match in pattern.finditer(source):
            endpoints = [match.group(2)]
            replacements = {
                'base': ['scouts', 'coaches'], 'prefix': ['scouts', 'coaches'],
                'kind': ['events', 'competitions'],
                'action': ['approve', 'reject'] if 'learning' in str(path) else ['like', 'unlike'],
                "isFollowed ? 'unfollow' : 'follow'": ['unfollow', 'follow'],
            }
            for expression in re.findall(r'\$\{(.*?)\}', match.group(2)):
                endpoints = [endpoint.replace('${' + expression + '}', value)
                             for endpoint in endpoints for value in replacements.get(expression, ['1'])]
            for endpoint in endpoints:
                route = '/api/' + endpoint.split('?')[0].lstrip('/')
                entry = {'file': str(path.relative_to(ROOT)), 'line': source[:match.start()].count('\n') + 1, 'route': route}
                try:
                    resolved = resolve(route)
                    entry['view'] = resolved.view_name
                    matched.append(entry)
                except Resolver404:
                    unresolved.append(entry)
report = {'resolved': matched, 'unresolved': unresolved,
          'limitation': 'Literal/template path resolution only; dynamic paths, methods, payloads and native runtime need integration tests.'}
(ROOT / 'audit-mobile-contracts.json').write_text(json.dumps(report, indent=2))
print(json.dumps({'resolved_count': len(matched), 'unresolved': unresolved}, indent=2))
