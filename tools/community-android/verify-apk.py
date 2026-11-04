"""Validate real APK payloads. This is a static check, not a device test."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile

apk = Path(sys.argv[1])
with zipfile.ZipFile(apk) as z:
    names = set(z.namelist())
    payload = json.loads(z.read('assets/payload-manifest.json'))
    for relative, digest in payload['files'].items():
        entry = 'assets/' + relative
        if entry not in names or hashlib.sha256(z.read(entry)).hexdigest() != digest:
            raise RuntimeError(f'Packaged payload missing or changed: {entry}')
    if any(n.startswith('assets/') and n.endswith(('.so', '.pyd', '.dll', '.pyc')) for n in names):
        raise RuntimeError('Unexpected binary module or host bytecode in packaged Python data')
    for required in ('AndroidManifest.xml', 'classes.dex', 'lib/arm64-v8a/libmain.so',
                     'lib/arm64-v8a/libSDL3.so', 'lib/arm64-v8a/libc++_shared.so',
                     'assets/pylib/encodings/__init__.py', 'assets/pylib/asyncio/__init__.py',
                     'assets/ba_data/python/babase/__init__.py',
                     'assets/ba_data/python/bascenev1lib/game/onslaught.py',
                     'assets/ba_data/python/baplus/_community.py', 'assets/ba_data/manifest.json'):
        if required not in names:
            raise RuntimeError(f'Missing APK entry: {required}')
    root = Path(__file__).resolve().parents[2]
    community_sources = {
        'baplus/_community_online.py': 'src/assets/ba_data/python/baplus/_community_online.py',
        'bauiv1lib/community_store.py': 'src/assets/ba_data/python/bauiv1lib/community_store.py',
        'bauiv1lib/gettokens.py': 'src/assets/ba_data/python/bauiv1lib/gettokens.py',
        'bauiv1lib/league/rankwindow.py': 'src/assets/ba_data/python/bauiv1lib/league/rankwindow.py',
        'baplus/_community_uicompat.py': 'src/assets/ba_data/python/baplus/_community_uicompat.py',
        'bauiv1lib/coop/browser.py': 'src/assets/ba_data/python/bauiv1lib/coop/browser.py',
        'bauiv1lib/tournamententry.py': 'src/assets/ba_data/python/bauiv1lib/tournamententry.py',
        'bauiv1lib/community_rewards.py': 'src/assets/ba_data/python/bauiv1lib/community_rewards.py',
        'bauiv1lib/chestui.py': 'src/assets/ba_data/python/bauiv1lib/chestui.py',
        'bauiv1lib/inboxui.py': 'src/assets/ba_data/python/bauiv1lib/inboxui.py',
        'bascenev1/_coopsession.py': 'src/assets/ba_data/python/bascenev1/_coopsession.py',
        'bauiv1lib/profile/upgrade.py': 'src/assets/ba_data/python/bauiv1lib/profile/upgrade.py',
        'bauiv1lib/inventory.py': 'src/assets/ba_data/python/bauiv1lib/inventory.py',
        'bacommon/docui/routes/classicstore.py': 'tools/bacommon/docui/routes/classicstore.py',
        'bacommon/docui/routes/classicchest.py': 'tools/bacommon/docui/routes/classicchest.py',
    }
    for packaged, source in community_sources.items():
        if z.read('assets/ba_data/python/' + packaged) != (root / source).read_bytes():
            raise RuntimeError(f'Community source was not staged correctly: {source}')
    libraries = sorted(n for n in names if n.startswith('lib/') and n.endswith('.so'))
    for library in libraries:
        data = z.read(library)
        if not data.startswith(b'\x7fELF\x02\x01') or struct.unpack_from('<H', data, 18)[0] != 183:
            raise RuntimeError(f'Non ARM64 ELF library: {library}')
    manifest = json.loads(z.read('assets/ba_data/manifest.json'))
    packages = manifest['asset_package_versions']
    if len(packages) != 11:
        raise RuntimeError('Unexpected pinned resource package count')
    # Every transitive CAS object must be present, nonempty and have its real
    # SHA256 content. Dummy assets cannot satisfy these checks.
    blobs = set()
    for package in packages.values():
        for bucket_hash in package['flavor_manifests'].values():
            path = f'assets/ba_data/assets/{bucket_hash[:2]}/{bucket_hash[2:]}'
            bucket_data = z.read(path)
            if hashlib.sha256(bucket_data).hexdigest() != bucket_hash:
                raise RuntimeError(f'Corrupt bucket manifest: {path}')
            blobs.add(bucket_hash)
            for parts in json.loads(bucket_data)['e'].values():
                for part in parts.values():
                    blobs.add(part['h'])
    for digest in blobs:
        data = z.read(f'assets/ba_data/assets/{digest[:2]}/{digest[2:]}')
        if hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError(f'Corrupt asset blob: {digest}')
    report = {'status': 'PASS', 'scope': 'static APK payload only', 'apk': str(apk.resolve()),
              'sha256': hashlib.sha256(apk.read_bytes()).hexdigest(), 'libraries': libraries,
              'resource_packages': sorted(packages), 'verified_blobs': len(blobs),
              'community_sources_match_workspace': True,
              'python_sources': sum(n.endswith('.py') for n in names)}
print(json.dumps(report, indent=2))
