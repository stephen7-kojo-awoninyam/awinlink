"""Remove only newly reported whitespace; preserve the two baseline findings."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
result = subprocess.run(['git', 'diff', '--check'], capture_output=True, text=True)
changes = {}
for line in result.stdout.splitlines():
    match = re.match(r'(.+?):(\d+): trailing whitespace\.', line)
    if match and match.group(1) not in {'dashboard/views.py', 'organizations/views.py'}:
        changes.setdefault(match.group(1), set()).add(int(match.group(2)))
for filename, numbers in changes.items():
    path = ROOT / filename
    lines = path.read_text(encoding='utf-8').splitlines(keepends=True)
    for number in numbers:
        lines[number - 1] = lines[number - 1].rstrip('\r\n').rstrip(' \t') + '\n'
    path.write_text(''.join(lines), encoding='utf-8')
    print(f'{filename}: trimmed {len(numbers)} added whitespace lines')
