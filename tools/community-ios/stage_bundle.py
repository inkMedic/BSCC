#!/usr/bin/env python3
"""Replace the three owned payload entries before Xcode signs the app."""
from pathlib import Path
import shutil
import sys

source, app = (Path(p).resolve() for p in sys.argv[1:])
if app.suffix != '.app' or not app.is_dir():
    raise RuntimeError(f'Expected an existing application bundle: {app}')
for name in ('ba_data', 'pylib', 'licenses', 'payload-manifest.json'):
    if not (source / name).exists():
        raise RuntimeError(f'Missing staged payload: {source / name}')
for name in ('ba_data', 'pylib', 'licenses'):
    if (app / name).exists():
        shutil.rmtree(app / name)
    shutil.copytree(source / name, app / name)
shutil.copy2(source / 'payload-manifest.json', app / 'payload-manifest.json')
