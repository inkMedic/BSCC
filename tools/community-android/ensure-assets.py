"""Use verified local pinned resources, fetching only when no bundle exists."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'tools'))
from batools._bundlestage import collect_bundle_hashes, assetdata_blob_path, _verify_builtin_package_bundled
from batools.assetbundleprofiles import _scanned_apvernums, all_bundle_languages

manifest_path = root / '.cache/asset_bundle/store-mobile/manifest.json'
if not manifest_path.exists():
    subprocess.run([str(root / 'tools/pcommand'), 'asset_bundle_build', 'store', '--form-factor', 'mobile'], check=True)
manifest = json.loads(manifest_path.read_text())
packages = manifest['asset_package_versions']
expected = {str(n) for n in _scanned_apvernums(root)}
if set(packages) != expected:
    raise RuntimeError('Cached resource package set differs from the fixed source requirements')
coords = {f'language/{language}' for language in all_bundle_languages()}
coords.add('textures/mobile_v1.gamma.regular')
for package in packages.values():
    if not coords.issubset(package['flavor_manifests']):
        raise RuntimeError('Incomplete offline language/texture flavors')
_verify_builtin_package_bundled(str(root), 'store-mobile', str(manifest_path))
hashes = collect_bundle_hashes(str(root), str(manifest_path))
for digest in hashes:
    path = root / assetdata_blob_path(digest)
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise RuntimeError(f'Missing or corrupt pinned resource: {path}')
print(f'PASS: {len(packages)} fixed resource packages, {len(hashes)} verified blobs, no cloud request for cached bundle')
