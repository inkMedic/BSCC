"""Persistent isolated development backend and real Headless for phone tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
import uuid

import httpx
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'community-backend'))
from community_backend.models import Server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--address', required=True)
    parser.add_argument('--api-port', type=int, default=18080)
    parser.add_argument('--game-port', type=int, default=43210)
    args = parser.parse_args()
    private = Path.home() / '.local/share/bscn-lan'
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    secrets_file = private / 'credentials.json'
    if secrets_file.exists():
        credentials = json.loads(secrets_file.read_text())
    else:
        credentials = dict(secret=secrets.token_urlsafe(32), server_id=str(uuid.uuid4()), key=secrets.token_urlsafe(32))
        with secrets_file.open('x') as output:
            os.chmod(secrets_file, 0o600)
            json.dump(credentials, output)
    env = dict(os.environ, COMMUNITY_DATABASE_URL='postgresql+psycopg://community:community@127.0.0.1:5432/community_dev',
        COMMUNITY_REDIS_URL='redis://127.0.0.1:6379/0', COMMUNITY_SECRET=credentials['secret'],
        COMMUNITY_ALLOWED_SERVER_NETWORKS=args.address + '/32', COMMUNITY_TEST_PURCHASES_ENABLED='1', COMMUNITY_TOURNAMENT_PERIOD_SECONDS='900')
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT / 'community-backend', env=env, check=True)
    engine = create_engine(env['COMMUNITY_DATABASE_URL'])
    with engine.begin() as db:
        if not db.execute(Server.__table__.select().where(Server.id == credentials['server_id'])).first():
            db.execute(Server.__table__.insert().values(id=credentials['server_id'], name='LAN Test Server', key_hash=hashlib.sha256(credentials['key'].encode()).hexdigest(), revoked=False))
    engine.dispose()
    record = ROOT / 'artifacts/community/lan'
    record.mkdir(parents=True, exist_ok=True)
    children = []
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with (record / 'backend.log').open('w') as backend_log, (record / 'headless.log').open('w') as headless_log:
        try:
            backend = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'community_backend.app:create_app', '--factory', '--host', '0.0.0.0', '--port', str(args.api_port), '--workers', '1'],
                cwd=ROOT / 'community-backend', env=env, stdout=backend_log, stderr=subprocess.STDOUT)
            children.append(backend)
            local_url = f'http://127.0.0.1:{args.api_port}'
            with httpx.Client(base_url=local_url, timeout=3) as client:
                for _ in range(100):
                    try:
                        if client.get('/health/ready').status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    if backend.poll() is not None:
                        raise RuntimeError('Backend exited; see LAN logs')
                    time.sleep(.1)
                headless_env = env | dict(COMMUNITY_API_URL=local_url, COMMUNITY_ALLOW_HTTP='1',
                    COMMUNITY_SERVER_ID=credentials['server_id'], COMMUNITY_SERVER_KEY=credentials['key'],
                    COMMUNITY_SERVER_ADDRESS=args.address, COMMUNITY_GAME_PORT=str(args.game_port), COMMUNITY_SERVER_NAME='LAN Test Server',
                    COMMUNITY_CONFIG_DIR=str(private / 'headless'))
                headless = subprocess.Popen(['bash', str(ROOT / 'scripts/run-community-headless.sh')], env=headless_env,
                    stdout=headless_log, stderr=subprocess.STDOUT, stdin=subprocess.PIPE)
                children.append(headless)
                state = dict(api_url=f'http://{args.address}:{args.api_port}', game_address=args.address, game_port=args.game_port,
                    server_id=credentials['server_id'], stack_pid=os.getpid(), backend_pid=backend.pid, headless_pid=headless.pid)
                (record / 'runtime.json').write_text(json.dumps(state, indent=2))
                print(json.dumps(state), flush=True)
                while not stopping:
                    if any(child.poll() is not None for child in children):
                        raise RuntimeError('A LAN service exited; see logs')
                    time.sleep(.5)
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    child.terminate()
            for child in children:
                try:
                    child.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    child.kill()


if __name__ == '__main__':
    main()
