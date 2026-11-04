"""Capture source/dependency provenance from the Linux build workspace."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import datetime

root = Path(__file__).resolve().parents[2]
output = Path(sys.argv[1])
output.mkdir(parents=True, exist_ok=True)
files = []
for relative in ('src', 'tools', 'pconfig', 'ballisticakit-android', 'tests'):
    for path in (root / relative).rglob('*'):
        if not path.is_file() or any(p in {'build', '.cxx', '.gradle', '__pycache__'} for p in path.relative_to(root).parts):
            continue
        if path.name == 'local.properties' or path.suffix in {'.pyc', '.pyo'}:
            continue
        files.append({'path': path.relative_to(root).as_posix(),
                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
files.sort(key=lambda item: item['path'])
record = {'upstream_commit': 'd89c2d90cae1593899bd17a1510fef2465acb437',
          'captured_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'files': files}
(output / 'build-source-inventory.json').write_text(json.dumps(record, indent=2) + '\n')
archives = []
for directory in ('build/python_deps_cache', 'build/community-downloads', 'build/openal-android/_downloads'):
    for path in (root / directory).rglob('*'):
        if path.is_file() and path.name.endswith(('.zip', '.gz', '.xz', '.bz2')):
            archives.append({'path': path.relative_to(root).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
sdk = Path(os.environ['ANDROID_SDK_ROOT'])
sdk_info = {}
for relative in ('ndk/28.2.13676358/source.properties', 'build-tools/35.0.0/source.properties',
                 'platforms/android-35/source.properties', 'cmake/3.22.1/source.properties'):
    sdk_info[relative] = (sdk / relative).read_text()
report = {'archives': archives, 'sdk_components': sdk_info,
          'target_python': '3.14.7 Py_DEBUG arm64-v8a API24',
          'host_python': sys.version,
          'linux_packages': subprocess.check_output(['dpkg-query', '-W', 'openjdk-21-jdk-headless',
              'cmake', 'ninja-build', 'zstd', 'gcc', 'make'], text=True)}
(output / 'build-dependencies.json').write_text(json.dumps(report, indent=2) + '\n')
# Link evidence is explicit: the build must not depend on an official Plus archive.
builds = list((root / 'ballisticakit-android/BallisticaKit/.cxx').glob('Debug/*/arm64-v8a/build.ninja'))
if len(builds) != 1:
    raise RuntimeError(f'Expected exactly one native build tree; got {builds}')
ninja = builds[0].read_text()
if 'libballisticaplus' in ninja or 'BallisticaKitGenericPlus' in ninja:
    raise RuntimeError('Official Plus library found in native build rules')
(output / 'plus-link-audit.txt').write_text(
    'PASS: no official Plus archive in native build rules.\n'
    'Community implementation: ballisticakit-android/native/community_plus.cc\n'
    + '\n'.join(line for line in ninja.splitlines() if 'build ' in line and ('libmain.so:' in line or 'community_plus.cc.o:' in line)) + '\n')
