"""Package tracked and new project source, excluding caches and outputs."""
from pathlib import Path
import hashlib
import io
import json
import subprocess
import tarfile

root = Path(__file__).resolve().parents[2]
output = root / 'artifacts/android/ballistica-community-source.tar.gz'
paths = subprocess.check_output(['git', '-C', str(root), 'ls-files', '--cached', '--others', '--exclude-standard', '-z']).decode().split('\0')
excluded = {'.git', 'build', '.cache', '.venv', '.bootstrap', '.gradle', '.cxx', '__pycache__', 'artifacts'}
files = []
with tarfile.open(output, 'w:gz', compresslevel=6) as archive:
    for relative in sorted(set(paths)):
        if not relative:
            continue
        path = root / relative
        if not path.is_file() or any(p in excluded for p in Path(relative).parts) or path.suffix in {'.pyc', '.pyo'}:
            continue
        archive.add(path, arcname='bscn/' + relative, recursive=False)
        files.append({'path': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    state = json.dumps({'upstream_commit': subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
                        'files': files}, indent=2).encode()
    entry = tarfile.TarInfo('bscn/SOURCE-STATE.json')
    entry.size = len(state)
    archive.addfile(entry, io.BytesIO(state))
    for name in ('build-dependencies.json', 'dependency-sources.json', 'apk-verification.json', 'plus-link-audit.txt'):
        path = output.parent / name
        if path.is_file():
            archive.add(path, arcname='bscn/provenance/' + name)
print(f'{output}\nSHA256 {hashlib.sha256(output.read_bytes()).hexdigest()}\n{len(files)} source files')
