#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
: "${COMMUNITY_API_URL:?Set COMMUNITY_API_URL}"
: "${COMMUNITY_SERVER_ID:?Set COMMUNITY_SERVER_ID}"
: "${COMMUNITY_SERVER_KEY:?Set COMMUNITY_SERVER_KEY}"
export BA_COMMUNITY=1
export COMMUNITY_GAME_PORT="${COMMUNITY_GAME_PORT:-43210}"
export BA_UDP_PORT="$COMMUNITY_GAME_PORT"
runtime="${COMMUNITY_HEADLESS_DIR:-$repo/artifacts/community/headless}"
export PYTHONPATH="$runtime/python-site-packages${PYTHONPATH:+:$PYTHONPATH}"
config="${COMMUNITY_CONFIG_DIR:-$HOME/.local/share/bscn-community-headless}"
mkdir -p "$config/cache"
cd "$runtime"
exec ./ballisticakit_headless -d "$runtime" -C "$config" -a "$config/cache" -e \
  "import os, babase; from bacommon.servermanager import ServerConfig; from baclassic._servermode import ServerController; babase.app.classic.server=ServerController(ServerConfig(party_name=os.environ.get('COMMUNITY_SERVER_NAME', 'Community'), party_is_public=True, authenticate_clients=True, max_party_size=int(os.environ.get('COMMUNITY_CAPACITY', '8'))+1, enable_queue=False))"
