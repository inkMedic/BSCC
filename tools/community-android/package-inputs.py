"""Export exact resource blobs and upstream dependency source archives."""
from pathlib import Path
import sys
import tarfile

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'tools'))
from batools._bundlestage import collect_bundle_hashes, assetdata_blob_path

bundle = root / '.cache/asset_bundle/store-mobile/manifest.json'
paths = [bundle]
paths.extend(root / assetdata_blob_path(h) for h in sorted(collect_bundle_hashes(str(root), str(bundle))))
for relative in ('build/python_deps_cache', 'build/openal-android/_downloads', 'build/community-downloads'):
    paths.extend(p for p in (root / relative).glob('*') if p.name.endswith(('.tar.gz', '.tar.xz', '.tar.bz2')))
output = Path(sys.argv[1])
with tarfile.open(output, 'w:gz', compresslevel=3) as archive:
    for path in paths:
        archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
print(f'Exported {len(paths)} exact build inputs: {output}')
