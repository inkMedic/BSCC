"""Build only source dependencies for ARM64; never fetch a Plus library."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / 'tools'))
DEPS = ROOT / 'build/community-deps'
SDK = Path(os.environ['ANDROID_SDK_ROOT'])
PREFIX = DEPS / 'prefix'
JOBS = os.environ.get('BA_BUILD_JOBS', '6')


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def source(name: str, url: str) -> Path:
    cache = ROOT / 'build/community-downloads'
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / (name + '.tar.gz')
    if not archive.exists():
        print('Fetching', url, flush=True)
        with urllib.request.urlopen(url, timeout=60) as response, archive.with_suffix('.part').open('wb') as out:
            shutil.copyfileobj(response, out)
        archive.with_suffix('.part').replace(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    record = cache / 'sources.json'
    records = json.loads(record.read_text()) if record.exists() else {}
    if name in records and records[name]['sha256'] != digest:
        raise RuntimeError(f'Dependency archive changed: {name}')
    records[name] = {'url': url, 'sha256': digest}
    record.write_text(json.dumps(records, indent=2) + '\n')
    dest = DEPS / name
    if not dest.exists():
        temporary = DEPS / (name + '-extract')
        temporary.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tar:
            tar.extractall(temporary, filter='data')
        dirs = list(temporary.iterdir())
        if len(dirs) != 1:
            raise RuntimeError('Unexpected source archive structure')
        dirs[0].rename(dest)
        temporary.rmdir()
    return dest


def cmake(name: str, src: Path, *extra: str) -> None:
    build = DEPS / (name + '-build')
    run('cmake', '-G', 'Ninja', '-S', str(src), '-B', str(build),
        f'-DCMAKE_TOOLCHAIN_FILE={SDK}/ndk/28.2.13676358/build/cmake/android.toolchain.cmake',
        '-DANDROID_ABI=arm64-v8a', '-DANDROID_PLATFORM=24',
        '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_POSITION_INDEPENDENT_CODE=ON',
        '-DCMAKE_POLICY_VERSION_MINIMUM=3.5', '-DBUILD_SHARED_LIBS=OFF',
        f'-DCMAKE_INSTALL_PREFIX={PREFIX}', *extra)
    run('cmake', '--build', str(build), '-j', JOBS)
    run('cmake', '--install', str(build))


def main() -> None:
    action = sys.argv[1]
    DEPS.mkdir(parents=True, exist_ok=True)
    if action == 'python':
        from efrotools.python_build_android import build
        if not (ROOT / 'build/python_android_arm64_debug/build/usr/lib/libpython3.14d.a').is_file():
            build(str(ROOT), 'arm64', True)
    elif action == 'audio':
        from efrotools.openalbuildandroid import build_openal
        if not (ROOT / 'build/openal-android/arm64_release/libopenal.a').is_file():
            build_openal('arm64', 'release')
        PREFIX.joinpath('lib').mkdir(parents=True, exist_ok=True)
        PREFIX.joinpath('include').mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT / 'build/openal-android/arm64_release/include/AL', PREFIX / 'include/AL', dirs_exist_ok=True)
        shutil.copy2(ROOT / 'build/openal-android/arm64_release/libopenal.a', PREFIX / 'lib')
        shutil.copy2(ROOT / 'build/openal-android/arm64_release_oboe/liboboe.a', PREFIX / 'lib')
        ogg = source('ogg', 'https://downloads.xiph.org/releases/ogg/libogg-1.3.6.tar.gz')
        cmake('ogg', ogg, '-DINSTALL_DOCS=OFF', '-DBUILD_TESTING=OFF')
        vorbis = source('vorbis', 'https://downloads.xiph.org/releases/vorbis/libvorbis-1.3.7.tar.gz')
        cmake('vorbis', vorbis, f'-DOGG_LIBRARY={PREFIX}/lib/libogg.a',
              f'-DOGG_INCLUDE_DIR={PREFIX}/include', '-DBUILD_TESTING=OFF')
    elif action == 'sources':
        source('SDL', 'https://github.com/libsdl-org/SDL/archive/refs/tags/release-3.2.24.tar.gz')
    elif action == 'stage':
        from batools._bundlestage import sync_asset_bundle
        stage = ROOT / 'build/community-stage'
        scripts = stage / 'ba_data/python'
        shutil.copytree(ROOT / 'src/assets/ba_data/python', scripts, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for package in ('efro', 'bacommon'):
            shutil.copytree(ROOT / 'tools' / package, scripts / package, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for obsolete in ('bauiv1lib/community_progression.py', 'bacommon/docui/routes/communityleague.py'):
            (scripts / obsolete).unlink(missing_ok=True)
        # Pure Python runtime packages from the upstream hash-locked venv.
        # Never copy host ELF modules into an Android package.
        site = ROOT / '.venv/lib/python3.14/site-packages'
        for package in ('urllib3', 'requests', 'certifi', 'idna', 'charset_normalizer', 'websockets'):
            shutil.copytree(site / package, scripts / package, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.so'))
        shutil.copy2(site / 'typing_extensions.py', scripts)
        shutil.copytree(ROOT / 'build/python_android_arm64_debug/build/usr/lib/python3.14', stage / 'pylib',
                        dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'test', 'config-*'))
        sync_asset_bundle(str(ROOT), str(stage), 'store-mobile')
        payload = {path.relative_to(stage).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in sorted(stage.rglob('*')) if path.is_file()
                   and path.name not in ('content-version.txt', 'payload-manifest.json')}
        (stage / 'payload-manifest.json').write_text(json.dumps({'format': 2, 'files': payload}, sort_keys=True))
        sha = hashlib.sha256()
        for path in sorted(stage.rglob('*')):
            if path.is_file() and path.name != 'content-version.txt':
                sha.update(path.relative_to(stage).as_posix().encode())
                sha.update(hashlib.sha256(path.read_bytes()).digest())
        (stage / 'content-version.txt').write_text('23079-v2-' + sha.hexdigest() + '\n')
    else:
        raise RuntimeError('Unknown dependency stage')


if __name__ == '__main__':
    main()
