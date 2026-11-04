#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
# Reuse the existing staged resources/codegen and Python 3.14 toolchain.
work="$HOME/bscn-android-d89c2d90"
rsync -a --checksum --no-times --exclude=.git --exclude=build --exclude=.venv --exclude=artifacts --exclude=.gradle --exclude=.cxx "$repo/" "$work/"
cd "$work"
make codegen VENV_LOCK=pconfig/requirements_build_lock.txt
if [[ ! -f .cache/asset_bundle/store-headless/manifest.json ]]; then
  .venv/bin/python tools/pcommand asset_bundle_build store --form-factor headless
fi
cmake -S ballisticakit-cmake -B build/community-headless -DHEADLESS=ON -DCOMMUNITY_PLUS=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=g++
cmake --build build/community-headless --target ballisticakitbin -j "${BA_BUILD_JOBS:-6}"
mkdir -p "$repo/artifacts/community/headless/ba_data" "$repo/artifacts/community/headless/python-site-packages"
cp build/community-headless/ballisticakit_headless "$repo/artifacts/community/headless/ballisticakit_headless.new"
mv -f "$repo/artifacts/community/headless/ballisticakit_headless.new" "$repo/artifacts/community/headless/ballisticakit_headless"
rsync -a build/community-stage/ba_data/ "$repo/artifacts/community/headless/ba_data/"
rsync -a src/assets/ba_data/python/ "$repo/artifacts/community/headless/ba_data/python/"
PYTHONPATH=tools .venv/bin/python -c 'import sys; from batools._bundlestage import sync_asset_bundle; sync_asset_bundle(".", sys.argv[1], "store-headless")' "$repo/artifacts/community/headless"
for package in bacommon efro; do
  rsync -a --exclude=__pycache__ "tools/$package/" "$repo/artifacts/community/headless/ba_data/python/$package/"
done
python3 -c 'from pathlib import Path; import sys; root=Path(sys.argv[1]); [(root / p).unlink(missing_ok=True) for p in ("bauiv1lib/community_progression.py", "bacommon/docui/routes/communityleague.py")]' "$repo/artifacts/community/headless/ba_data/python"
python3 -m pip install --upgrade --target "$repo/artifacts/community/headless/python-site-packages" 'websockets==17.3'
