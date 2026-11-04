"""Record deliverable hashes and OpenAPI; never serialize runtime secrets."""
import hashlib
import json
from pathlib import Path
import platform
import secrets
import sys
import tarfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'community-backend'))
from community_backend.app import create_app
from community_backend.config import Settings

output = root / 'artifacts/community'
(output / 'openapi.json').write_text(json.dumps(create_app(Settings(secret=secrets.token_urlsafe(32))).openapi(), ensure_ascii=False, indent=2))
runtime = output / 'headless'
archive = output / 'ballistica-community-headless-linux-x86_64.tar.gz'
with tarfile.open(archive, 'w:gz') as package:
    for path in sorted(runtime.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            package.add(path, arcname='headless/' + path.relative_to(runtime).as_posix(), recursive=False)

files = [root / 'artifacts/android/ballistica-community-arm64-debug.apk', runtime / 'ballisticakit_headless', archive,
         root / 'community-backend/requirements.lock', output / 'openapi.json']
report = {'backend_python': platform.python_version(), 'platform': platform.platform(), 'files': {}}
for path in files:
    report['files'][path.relative_to(root).as_posix()] = dict(size=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
(output / 'build-manifest.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
