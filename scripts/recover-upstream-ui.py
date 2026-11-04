"""Recover exact historical UI sources and HEAD cloud contracts, without imports.

Writes reference material only. Does not replace runtime modules or fetch Git.
"""
import ast
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reference/upstream-ui'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def resolve(revision):
    return git('rev-parse', revision).decode().strip()


def export(revision, source, bucket):
    commit = resolve(revision)
    data = git('show', f'{commit}:{source}')
    destination = OUT / bucket / source
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.endswith('.py'):
        ast.parse(data.decode('utf-8'), filename=source)
    destination.write_bytes(data)
    assert destination.read_bytes() == data
    return dict(commit=commit, original_path=source, recovered_path=destination.relative_to(ROOT).as_posix(),
        git_blob=git('rev-parse', f'{commit}:{source}').decode().strip(), sha256=hashlib.sha256(data).hexdigest(),
        bytes=len(data), lines=len(data.splitlines()), python_syntax_checked=source.endswith('.py'))


groups = [
    ('739b3140c^', 'before-2026-10-02-docui', [
        'src/assets/ba_data/python/bauiv1lib/chest.py',
        'src/assets/ba_data/python/bauiv1lib/inbox.py',
        'src/assets/ba_data/python/baclassic/_chest.py',
        'tools/bacommon/classic/_msg.py',
        'tools/bacommon/clouddialog/basic.py',
        'tools/bacommon/clouddialog/__init__.py',
    ]),
    ('65c0ce1d6^', 'before-2026-01-08-store-cleanup', [
        'src/assets/ba_data/python/bauiv1lib/store/__init__.py',
        'src/assets/ba_data/python/bauiv1lib/store/browser.py',
        'src/assets/ba_data/python/bauiv1lib/store/item.py',
        'src/assets/ba_data/python/bauiv1lib/store/newstore.py',
        'src/assets/ba_data/python/bauiv1lib/purchase.py',
        'src/assets/ba_data/python/baclassic/_store.py',
    ]),
    ('HEAD', 'current-head-cloud-contracts', [
        'src/assets/ba_data/python/bauiv1lib/store.py',
        'src/assets/ba_data/python/bauiv1lib/chestui.py',
        'src/assets/ba_data/python/bauiv1lib/inboxui.py',
        'src/assets/ba_data/python/bauiv1lib/inventory.py',
        'src/assets/ba_data/python/bauiv1lib/docui/_controller.py',
        'src/assets/ba_data/python/bauiv1lib/docui/_cache.py',
        'tools/bacommon/cloud.py',
        'tools/bacommon/docui/routes/classicstore.py',
        'tools/bacommon/docui/routes/classicchest.py',
        'tools/bacommon/docui/routes/classicinbox.py',
    ]),
]

manifest = []
for revision, bucket, paths in groups:
    for source in paths:
        manifest.append(export(revision, source, bucket))
manifest.append(export('HEAD', 'LICENSE', ''))

all_paths = sorted(set(p for p in git('log', '--all', '--format=', '--name-only').decode().splitlines() if p))
server_paths = [p for p in all_paths if {'bamaster', 'baserver'}.intersection(Path(p).parts)]
routes = []
for source, domain in [('classicstore', ['classicstore', 'classicinventory']),
                       ('classicchest', ['classicchest']), ('classicinbox', ['classicinbox'])]:
    path = f'tools/bacommon/docui/routes/{source}.py'
    tree = ast.parse(git('show', f'HEAD:{path}').decode())
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        keywords = {k.arg: k.value for k in node.keywords}
        if 'path' not in keywords:
            continue
        routes.append(dict(domains=domain, route_class=node.name, path=ast.literal_eval(keywords['path']),
                           method='POST' if 'method' in keywords else 'GET', source=path, line=node.lineno))

report = dict(head=resolve('HEAD'), shallow=git('rev-parse', '--is-shallow-repository').decode().strip() == 'true',
    reachable_commits=int(git('rev-list', '--all', '--count')), historical_distinct_paths=len(all_paths),
    historical_named_server_package_paths=server_paths, files=manifest, current_head_routes=routes,
    scope='Local reachable Git history only; recovered historical clients are not current server templates')
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'recovery-manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(recovered_files=len(manifest), reachable_commits=report['reachable_commits'],
    historical_distinct_paths=len(all_paths), server_package_paths=server_paths,
    routes=len(routes), manifest=str(OUT / 'recovery-manifest.json')), ensure_ascii=False, indent=2))
