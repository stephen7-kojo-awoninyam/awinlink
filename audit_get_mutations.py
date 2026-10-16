"""Static candidates for manual GET-mutation review, not a vulnerability proof."""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
candidates = []
for path in ROOT.glob('*/views.py'):
    source = path.read_text(encoding='utf-8')
    tree = ast.parse(source)
    for function in tree.body:
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        code = ast.get_source_segment(source, function)
        decorators = [ast.unparse(item) for item in function.decorator_list]
        if any('require_POST' in item or 'require_http_methods' in item for item in decorators) or 'request.method' in code:
            continue
        writes = sorted({node.func.attr for node in ast.walk(function) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                         and node.func.attr in {'save', 'delete', 'create', 'update', 'get_or_create', 'update_or_create', 'accept', 'decline'}})
        if writes and any('login_required' in item for item in decorators):
            candidates.append({'file': str(path.relative_to(ROOT)), 'line': function.lineno, 'function': function.name, 'writes': writes})
(ROOT / 'audit-get-mutation-candidates.json').write_text(json.dumps(candidates, indent=2))
print(json.dumps(candidates, indent=2))
