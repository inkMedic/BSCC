#!/usr/bin/env python3
"""Build the community iOS app from source; no proprietary Plus binary.

Run with .venv/bin/python after make env VENV_LOCK=pconfig/requirements_build_lock.txt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import urllib.parse
from xml.sax.saxutils import escape
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
DEPS = ROOT / 'build/community-ios-deps'
SOURCES = {
    'SDL': ('https://github.com/libsdl-org/SDL/archive/refs/tags/release-3.2.24.tar.gz',
            '66c374ee7f786abcd8592d18fc5b18b1e3f1c67e923867eee5f9c503cb253afd'),
    'ogg': ('https://downloads.xiph.org/releases/ogg/libogg-1.3.6.tar.gz',
            '83e6704730683d004d20e21b8f7f55dcb3383cdf84c0daedf30bde175f774638'),
    'vorbis': ('https://downloads.xiph.org/releases/vorbis/libvorbis-1.3.7.tar.gz',
            '0e982409a9c3fc82ee06e08205b1355e5c6aa4c36bca58146ef399621b0ce5ab'),
    'openal': ('https://github.com/kcat/openal-soft/archive/refs/tags/1.25.2.tar.gz',
            'fb27e5839aa11f0e5b9d33756965291fad5d6909ab928ea1f796f4a1a6877894'),
}


def run(*args: str) -> None:
    print('+', ' '.join(args), flush=True)
    subprocess.run(args, cwd=ROOT, check=True)


def digest(path: Path) -> str:
    with path.open('rb') as infile:
        return hashlib.file_digest(infile, 'sha256').hexdigest()


def sources() -> None:
    cache = ROOT / 'build/community-ios-downloads'
    cache.mkdir(parents=True, exist_ok=True)
    DEPS.mkdir(parents=True, exist_ok=True)
    for name, (url, expected) in SOURCES.items():
        archive = cache / (name + '.tar.gz')
        if not archive.exists():
            partial = archive.with_suffix('.part')
            with urllib.request.urlopen(url, timeout=60) as response, partial.open('wb') as out:
                shutil.copyfileobj(response, out)
            partial.replace(archive)
        if digest(archive) != expected:
            raise RuntimeError(f'SHA256 mismatch: {archive}; remove corrupt archive and retry')
        stamp = DEPS / name / '.community-source-sha256'
        if stamp.exists() and stamp.read_text() == expected:
            continue
        if (DEPS / name).exists():
            raise RuntimeError(f'Unverified source directory: {DEPS / name}; move it aside and retry')
        temporary = DEPS / (name + '-extract')
        temporary.mkdir(exist_ok=True)
        with tarfile.open(archive) as tar:
            tar.extractall(temporary, filter='data')
        entries = list(temporary.iterdir())
        if len(entries) != 1 or not entries[0].is_dir():
            raise RuntimeError(f'Unexpected archive layout: {archive}')
        entries[0].rename(DEPS / name)
        temporary.rmdir()
        if name == 'openal':
            from efrotools.openalbuildapple import _patch_checkout
            _patch_checkout(DEPS / name)
        stamp.write_text(expected)


def stage_scripts(destination: Path) -> None:
    """Stage current game scripts, including direct builds from Xcode."""
    scripts = destination / 'ba_data/python'
    if scripts.exists():
        shutil.rmtree(scripts)
    ignore = shutil.ignore_patterns('__pycache__', '*.pyc', '*.so', '*.dylib')
    shutil.copytree(ROOT / 'src/assets/ba_data/python', scripts, ignore=ignore)
    for name in ('efro', 'bacommon'):
        shutil.copytree(ROOT / 'tools' / name, scripts / name, ignore=ignore)
    site = Path(next(iter((ROOT / '.venv/lib').glob('python3.14/site-packages'))))
    for name in ('urllib3', 'requests', 'certifi', 'idna', 'charset_normalizer', 'websockets'):
        shutil.copytree(site / name, scripts / name, ignore=ignore)
    shutil.copy2(site / 'typing_extensions.py', scripts)


def stage(sdk: str) -> None:
    from batools._bundlestage import sync_asset_bundle
    destination = ROOT / 'build/community-ios-stage' / sdk
    # Clean staging only; stale scripts or host extensions must never enter IPA.
    if destination.exists():
        shutil.rmtree(destination)
    stage_scripts(destination)
    pyroot = ROOT / f'build/python_apple_{sdk}_arm64'
    stdlibs = list((pyroot / 'install').glob('**/lib/python3.14'))
    if len(stdlibs) != 1:
        raise RuntimeError(f'Expected exactly one target Python stdlib: {stdlibs}')
    shutil.copytree(stdlibs[0], destination / 'pylib',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.so', 'test', 'config-*'))
    licenses = destination / 'licenses'
    licenses.mkdir()
    notices = {'Ballistica.txt': ROOT / 'LICENSE',
               'SDL.txt': DEPS / 'SDL/LICENSE.txt',
               'Ogg.txt': DEPS / 'ogg/COPYING',
               'Vorbis.txt': DEPS / 'vorbis/COPYING',
               'OpenAL-Soft.txt': DEPS / 'openal/COPYING',
               'Python.txt': pyroot / 'src/Python-3.14.7/LICENSE'}
    for name, path in notices.items():
        shutil.copy2(path, licenses / name)
    sync_asset_bundle(str(ROOT), str(destination), 'store-mobile')
    manifest = {str(p.relative_to(destination)): digest(p) for p in sorted(destination.rglob('*')) if p.is_file()}
    (destination / 'payload-manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')


def package(app: Path, output: Path, sdk: str, signed: bool) -> None:
    with (app / 'Info.plist').open('rb') as f:
        info = plistlib.load(f)
    binary = app / info['CFBundleExecutable']
    run('xcrun', 'lipo', '-verify_arch', 'arm64', str(binary))
    load_commands = subprocess.check_output(['xcrun', 'vtool', '-show-build', str(binary)], text=True)
    expected_platform = 'IOS' if sdk == 'iphoneos' else 'IOSSIMULATOR'
    platforms = re.findall(r'platform\s+(\w+)', load_commands)
    if platforms != [expected_platform]:
        raise RuntimeError(f'Wrong Mach-O platform: {platforms}, expected {expected_platform}')
    manifest = json.loads((app / 'payload-manifest.json').read_text())
    for relative, expected in manifest.items():
        path = app / relative
        if not path.is_file() or digest(path) != expected:
            raise RuntimeError(f'Missing or corrupt packaged payload: {relative}')
    for name in ('pylib', 'ba_data', 'licenses'):
        for path in (app / name).rglob('*'):
            if path.is_file() and (str(path.relative_to(app)) not in manifest
                                   or path.suffix in ('.so', '.dylib', '.pyc')):
                raise RuntimeError(f'Unexpected runtime file: {path}')
    # Simulator .app bundles are delivered separately; they are not device IPAs.
    prefix = 'Payload' if sdk == 'iphoneos' else 'Simulator'
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.partial')
    with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(app.rglob('*')):
            if path.is_file():
                archive.write(path, f'{prefix}/{app.name}/{path.relative_to(app)}')
    temporary.replace(output)
    report = {'sdk': sdk, 'configuration': ARGS.configuration, 'signed': signed,
              'bundle_id': info['CFBundleIdentifier'], 'artifact': output.name,
              'sha256': digest(output), 'xcode': subprocess.check_output(['xcodebuild', '-version'], text=True),
              'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'sources': SOURCES, 'device_tested': False}
    output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'Created {output}\nSHA256: {report["sha256"]}', flush=True)


def main() -> None:
    if sys.platform != 'darwin':
        raise RuntimeError('iOS builds require macOS with full Xcode')
    os.chdir(ROOT)
    if ARGS.api_url:
        parsed = urllib.parse.urlsplit(ARGS.api_url)
        if (parsed.scheme not in ('https', 'http') or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError('API URL must be HTTP(S) without credentials, query or fragment')
        if parsed.scheme == 'http' and not ARGS.allow_http:
            raise ValueError('LAN HTTP requires --allow-http')
    sdk = ARGS.sdk
    sources()
    if ARGS.prepare_sources_only:
        return
    from efrotools.python_build_apple import build
    pyroot = ROOT / f'build/python_apple_{sdk}_arm64'
    if not (pyroot / 'libpython_merged.a').is_file():
        build(str(ROOT), sdk + '.arm64')
    run('make', 'codegen', 'VENV_LOCK=pconfig/requirements_build_lock.txt')
    if not ARGS.compile_only:
        run(sys.executable, 'tools/community-android/ensure-assets.py')
        stage(sdk)
    buildroot = ROOT / 'build/community-ios' / sdk
    run('cmake', '-G', 'Xcode', '-S', str(ROOT / 'ballisticakit-ios'), '-B', str(buildroot),
        '-DCMAKE_SYSTEM_NAME=iOS', '-DCMAKE_OSX_ARCHITECTURES=arm64',
        f'-DCMAKE_OSX_SYSROOT={sdk}', '-DCMAKE_OSX_DEPLOYMENT_TARGET=16.0',
        '-DCMAKE_POLICY_VERSION_MINIMUM=3.5', f'-DAPPLE_SDK={sdk}',
        f'-DCOMMUNITY_PYTHON={sys.executable}', f'-DCOMMUNITY_BUNDLE_ID={ARGS.bundle_id}', f'-DCOMMUNITY_TEAM_ID={ARGS.team_id or ""}',
        f'-DCOMMUNITY_COMPILE_ONLY={"ON" if ARGS.compile_only else "OFF"}',
        f'-DCOMMUNITY_SIGNING={"YES" if ARGS.team_id else "NO"}',
        f'-DCOMMUNITY_API_URL_XML={escape(ARGS.api_url)}',
        f'-DCOMMUNITY_HTTP_PLIST={"true" if ARGS.allow_http else "false"}')
    if ARGS.configure_only:
        print(f'Xcode project ready: {buildroot / "BallisticaCommunityIOS.xcodeproj"}')
        return
    run('cmake', '--build', str(buildroot), '--config', ARGS.configuration,
        '--target', 'BallisticaCommunity', '--parallel', str(ARGS.jobs))
    if ARGS.compile_only:
        print('Native compile passed. Resources not staged; no installable artifact produced.')
        return
    app = buildroot / f'{ARGS.configuration}-{sdk}/BallisticaCommunity.app'
    if ARGS.team_id:
        run('codesign', '--verify', '--deep', '--strict', str(app))
    name = ('ballistica-community-arm64' + ('-signed' if ARGS.team_id else '-unsigned') + '.ipa'
            if sdk == 'iphoneos' else 'ballistica-community-simulator-arm64.zip')
    package(app, ROOT / 'artifacts/ios' / name, sdk, bool(ARGS.team_id))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', choices=('iphoneos', 'iphonesimulator'), default='iphoneos')
    parser.add_argument('--configuration', choices=('Debug', 'Release'), default='Release')
    parser.add_argument('--team-id', help='Apple team for automatic development signing')
    parser.add_argument('--bundle-id', default='org.ballistica.community.ios')
    parser.add_argument('--api-url', default=os.environ.get('COMMUNITY_API_URL', ''))
    parser.add_argument('--allow-http', action='store_true', help='Explicit opt-in for LAN HTTP testing')
    parser.add_argument('--jobs', type=int, default=6)
    parser.add_argument('--configure-only', action='store_true', help='Prepare resources and Xcode project without building')
    parser.add_argument('--compile-only', action='store_true', help='Compile without resources; never produce an IPA')
    parser.add_argument('--prepare-sources-only', action='store_true')
    ARGS = parser.parse_args()
    main()
