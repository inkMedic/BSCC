"""Real backend + real Headless smoke; no players or game rounds are run."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import uuid

import httpx
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'community-backend'))
from community_backend.models import Server


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    output = ROOT / 'artifacts/community'
    headless = output / 'headless'
    env = dict(os.environ, COMMUNITY_DATABASE_URL='postgresql+psycopg://community:community@127.0.0.1:5432/community_test',
        COMMUNITY_REDIS_URL='redis://127.0.0.1:6379/14', COMMUNITY_SECRET=secrets.token_urlsafe(32), COMMUNITY_TEST_PURCHASES_ENABLED='1')
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT / 'community-backend', env=env, check=True)
    sid, key = str(uuid.uuid4()), secrets.token_urlsafe(32)
    engine = create_engine(env['COMMUNITY_DATABASE_URL'])
    with engine.begin() as db:
        db.execute(Server.__table__.insert().values(id=sid, name='Smoke Headless', key_hash=hashlib.sha256(key.encode()).hexdigest(), revoked=False))
    engine.dispose()
    port, game_port = free_port(), free_port()
    url = f'https://127.0.0.1:{port}'
    report = {'kind': 'real_headless_control_smoke', 'game_rounds_run': 0, 'server_id': sid}
    with tempfile.TemporaryDirectory(prefix='bscn-smoke-') as temporary:
        (Path(temporary) / 'cache').mkdir()
        certificate, private_key = Path(temporary) / 'cert.pem', Path(temporary) / 'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
            '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1', '-keyout', str(private_key), '-out', str(certificate)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        backend_log = open(output / 'backend-smoke.log', 'w')
        engine_log = open(output / 'headless-smoke.log', 'w')
        backend = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'community_backend.app:create_app', '--factory', '--port', str(port), '--workers', '1', '--ssl-certfile', str(certificate), '--ssl-keyfile', str(private_key)], cwd=ROOT / 'community-backend', env=env, stdout=backend_log, stderr=subprocess.STDOUT)
        process = None
        try:
            with httpx.Client(base_url=url, timeout=8, verify=ssl.create_default_context(cafile=str(certificate))) as client:
                for _ in range(100):
                    try:
                        if client.get('/health/ready').status_code == 200:
                            break
                    except httpx.ConnectError:
                        pass
                    time.sleep(.1)
                runtime = env | dict(BA_COMMUNITY='1', COMMUNITY_API_URL=url, COMMUNITY_ALLOW_HTTP='0', COMMUNITY_CA_FILE=str(certificate), COMMUNITY_SERVER_ID=sid, COMMUNITY_SERVER_KEY=key,
                    COMMUNITY_SERVER_ADDRESS='127.0.0.1', COMMUNITY_GAME_PORT=str(game_port), COMMUNITY_SERVER_NAME='Smoke Headless',
                    BA_UDP_PORT=str(game_port),
                    PYTHONPATH=str(headless / 'python-site-packages'))
                # Start a waiting FFA lobby only. No participant or match.
                command = "import babase; from bacommon.servermanager import ServerConfig; from baclassic._servermode import ServerController; babase.app.classic.server=ServerController(ServerConfig(party_name='Smoke Headless', party_is_public=True, authenticate_clients=True, enable_queue=False))"
                process = subprocess.Popen([str(headless / 'ballisticakit_headless'), '-d', str(headless), '-C', temporary, '-a', temporary + '/cache', '-e', command], cwd=headless, env=runtime, stdin=subprocess.PIPE, stdout=engine_log, stderr=subprocess.STDOUT)
                for _ in range(150):
                    if process.poll() is not None:
                        raise RuntimeError('Headless exited; see headless-smoke.log')
                    listing = client.get('/v1/servers').json()['servers']
                    target = next((item for item in listing if item['server_id'] == sid), None)
                    if target:
                        break
                    time.sleep(.2)
                else:
                    raise RuntimeError('Headless failed to become visible; see logs')
                report['directory'] = target
                account = client.post('/v1/auth/register', json=dict(login='smoke_' + secrets.token_hex(4), password=secrets.token_urlsafe(18), nickname='冒烟测试')).json()
                headers = {'Authorization': 'Bearer ' + account['access_token']}
                join = client.post(f'/v1/servers/{sid}/join', headers=headers, json=dict(instance_id=target['instance_id'], join_attempt_id=str(uuid.uuid4()), engine_build=23079, scene_protocol=57, community_protocol=1, assets='23079'))
                assert join.status_code == 200, join.text
                report['prepare_ack'] = True
                report['verified_https_wss'] = True
                report['uid'] = account['user']['uid']
                # Exercise actual engine hook/cache on logic thread, without
                # claiming this as UDP client handshake or game completion.
                ticket = join.json()['ticket']
                ticket_file = Path(temporary) / 'ticket'
                ticket_file.touch(mode=0o600)
                ticket_file.write_text(ticket)
                verify = f"import babase._hooks as hooks; from pathlib import Path; t=Path({str(ticket_file)!r}).read_text(); a=hooks.v2_auth_data(t, 1000001); b=hooks.v2_auth_data(t, 1000001); c=hooks.v2_auth_data(t, 1000002); print('COMMUNITY_CLAIM_OK', a is not None and a[0]=={report['uid']!r} and b==a and c is None, flush=True)\n"
                process.stdin.write(verify.encode())
                process.stdin.flush()
                for _ in range(50):
                    if 'COMMUNITY_CLAIM_OK True' in (output / 'headless-smoke.log').read_text():
                        break
                    time.sleep(.1)
                else:
                    raise RuntimeError('Real logic-thread auth hook check failed')
                report['real_engine_ticket_claim'] = True
                # Exercise account and DocUI models in a second desktop engine.
                # Headless cannot act as a UDP client. No phone access.
                login = 'native_' + secrets.token_hex(4)
                password = secrets.token_urlsafe(18)
                created = client.post('/v1/auth/register', json=dict(login=login, password=password, nickname='NativeProbe'))
                assert created.status_code == 201, created.text
                # Explicit isolated reward fixtures exercise DocUI/opening;
                # these are not claimed to be earned from a played round.
                from datetime import datetime, timezone, timedelta
                from community_backend.models import RewardChest, RewardMessage
                from sqlalchemy.orm import Session
                native_account = created.json()
                fixture_event = client.post('/v1/tournaments/query', headers={'Authorization': 'Bearer ' + native_account['access_token']}, json={}).json()['t'][0]
                fixture_engine = create_engine(env['COMMUNITY_DATABASE_URL'])
                with Session(fixture_engine) as db:
                    for i in range(3):
                        chest = RewardChest(user_id=native_account['user']['uid'], appearance='l4', slot=0 if i == 0 else None,
                            unlock_at=datetime.now(timezone.utc)-timedelta(seconds=1) if i == 0 else None,
                            contents=(dict(tokens=0, tickets=0, purple_tickets=9999, items=[], gold_pass_days=0, fixed=True) if i == 2 else dict(tokens=7, tickets=80, items=['characters.zoe'], gold_pass_days=0)))
                        db.add(chest)
                        db.flush()
                        db.add(RewardMessage(user_id=native_account['user']['uid'], chest_id=chest.id,
                            tournament_id=None if i == 2 else fixture_event['tournamentID'], source='explicit-docui-fixture-' + str(i), kind='admin_gift' if i == 2 else 'standings', rank=None if i == 2 else 1,
                            claimed_at=datetime.now(timezone.utc) if i == 0 else None))
                    db.commit()
                fixture_engine.dispose()
                report['chest_ui_data_source'] = 'explicit_isolated_fixture_not_earned_gameplay'
                client_credentials = Path(temporary) / 'native-client.json'
                client_credentials.touch(mode=0o600)
                client_credentials.write_text(json.dumps(dict(login=login, password=password)))
                client_config = Path(temporary) / 'native-config'
                (client_config / 'cache').mkdir(parents=True)
                client_env = {k: v for k, v in runtime.items() if k not in ('COMMUNITY_SERVER_KEY', 'COMMUNITY_SERVER_ID')}
                client_env.update(BA_UDP_PORT='0', COMMUNITY_PROBE_CREDENTIALS=str(client_credentials), COMMUNITY_PROBE_SERVER=sid)
                client_command = f"import runpy; runpy.run_path({str(ROOT / 'scripts/community-native-client-probe.py')!r})"
                probe = subprocess.run([str(headless / 'ballisticakit_headless'), '-d', str(headless), '-C', str(client_config), '-a', str(client_config / 'cache'), '-e', client_command],
                    cwd=headless, env=client_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=40)
                (output / 'native-client-probe.log').write_text(probe.stdout)
                assert probe.returncode == 0 and 'NATIVE_CLIENT_COMMUNITY_PRIMARY_OK' in probe.stdout, 'Native account probe failed; see log'
                report['real_engine_primary_account'] = True
                assert 'NATIVE_CLIENT_SHOP_UPGRADE_INVENTORY_LEAGUE_MODELS_OK' in probe.stdout, 'Native shop/profile/league model probe failed; see log'
                report['real_engine_shop_profile_inventory_league_models'] = True
                assert 'NATIVE_CLIENT_TOURNAMENT_SESSION_START_OK' in probe.stdout, 'Native tournament session start failed; see log'
                report['real_engine_tournament_entry_and_coop_session_start'] = True
                assert 'NATIVE_CLIENT_CHEST_OPEN_AND_INBOX_MODELS_OK' in probe.stdout, 'Native chest/inbox model check failed; see log'
                report['real_engine_chest_open_and_inbox_models'] = True
                report['real_udp_client_and_local_leave'] = ('NOT_EXECUTED_HEADLESS' if 'NATIVE_CLIENT_UDP_NOT_AVAILABLE_HEADLESS' in probe.stdout else 'NATIVE_CLIENT_LOCAL_LEAVE_OK' in probe.stdout)
                process.terminate()
                process.wait(timeout=10)
                for _ in range(100):
                    if client.get(f'/v1/servers/{sid}').status_code == 409:
                        break
                    time.sleep(.1)
                else:
                    raise RuntimeError('Disconnected Headless stayed visible')
                report['disconnect_hidden'] = True
                report['status'] = 'PASS'
        finally:
            if process and process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            backend.terminate()
            backend.wait(timeout=10)
            backend_log.close()
            engine_log.close()
            (output / 'headless-smoke.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
