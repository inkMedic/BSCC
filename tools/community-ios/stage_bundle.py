#!/usr/bin/env python3
"""Replace the three owned payload entries before Xcode signs the app."""
from pathlib import Path
import json
import shutil
import sys

from build import digest, stage_scripts

source, app = (Path(p).resolve() for p in sys.argv[1:])
if app.suffix != '.app' or not app.is_dir():
    raise RuntimeError(f'Expected an existing application bundle: {app}')
for name in ('ba_data', 'pylib', 'licenses', 'payload-manifest.json'):
    if not (source / name).exists():
        raise RuntimeError(f'Missing staged payload: {source / name}')
# Xcode can rebuild without running build.py. Refresh scripts from source
# instead of silently shipping the previous staging run's gameplay/settings.
stage_scripts(source)
manifest = {
    str(path.relative_to(source)): digest(path)
    for path in sorted(source.rglob('*'))
    if path.is_file() and path.name != 'payload-manifest.json'
}
(source / 'payload-manifest.json').write_text(
    json.dumps(manifest, sort_keys=True, indent=2) + '\n'
)
for name in ('ba_data', 'pylib', 'licenses'):
    if (app / name).exists():
        shutil.rmtree(app / name)
    shutil.copytree(source / name, app / name)
shutil.copy2(source / 'payload-manifest.json', app / 'payload-manifest.json')
