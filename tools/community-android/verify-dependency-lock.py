"""Reject changed download archives before building the APK."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parents[2]
lock = json.loads((root / 'tools/community-android/dependency-lock.json').read_text())
for item in lock['archives']:
    path = root / item['path']
    if not path.is_file():
        raise RuntimeError(f'Missing locked archive: {path}; run setup/dependency stages first')
    if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
        raise RuntimeError(f'Dependency SHA256 mismatch: {path}')
print(f"PASS: {len(lock['archives'])} locked source/tool archives")
