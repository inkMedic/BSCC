#!/usr/bin/env bash
# Run from Windows with wsl -d Ubuntu -- bash /mnt/.../bootstrap-audit.sh
set -euo pipefail
source_root="$(cd "$(dirname "$0")/../.." && pwd)"
build_root="$HOME/bscn-android-d89c2d90"
if [[ ! -d "$build_root" ]]; then
  mkdir -p "$build_root"
  cp -a "$source_root/." "$build_root/"
fi
cd "$build_root"
test "$(git rev-parse HEAD)" = d89c2d90cae1593899bd17a1510fef2465acb437
command -v python3.14 >/dev/null
if [[ ! -x .bootstrap/bin/python ]]; then
  python3.14 -m venv .bootstrap
fi
.bootstrap/bin/pip install uv==0.9.4 clang-format==21.1.0
bash "$source_root/tools/community-android/prepare-linux.sh"
