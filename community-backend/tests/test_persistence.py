import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from test_service import register, auth


def test_account_and_sessions_survive_backend_process_restart(client, service):
    login, account = register(client)
    import uuid
    event = client.post('/v1/tournaments/query', headers=auth(account), json={}).json()['t'][0]
    entry_path = '/v1/tournaments/' + event['tournamentID'] + '/entries'
    entry_request = dict(request_id=str(uuid.uuid4()))
    entry = client.post(entry_path, headers=auth(account), json=entry_request)
    assert entry.status_code == 200
    # Explicit chest fixture, never presented as earned gameplay.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from community_backend.models import RewardChest, utcnow
    from datetime import timedelta
    fixture_engine = create_engine(service[1]['COMMUNITY_DATABASE_URL'])
    with Session(fixture_engine) as db:
        chest = RewardChest(user_id=account['user']['uid'], appearance='l1', slot=0,
            contents=dict(tokens=3, tickets=5, items=[], gold_pass_days=0), unlock_at=utcnow()-timedelta(seconds=1))
        db.add(chest)
        db.commit()
        chest_id = chest.id
    fixture_engine.dispose()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    # A fresh process shares only the real database and Redis, never app memory.
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'community_backend.app:create_app', '--factory', '--port', str(port), '--log-level', 'error'], cwd=Path(__file__).resolve().parents[1], env=service[1] | {'COMMUNITY_TEST_PURCHASES_ENABLED': '0'})
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}') as fresh:
            for _ in range(100):
                try:
                    if fresh.get('/health/ready').status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(.05)
            assert fresh.get('/v1/me', headers=auth(account)).json()['uid'] == account['user']['uid']
            assert fresh.post(entry_path, headers=auth(account), json=entry_request).json() == entry.json()
            assert fresh.get('/v1/chests', headers=auth(account)).json()['chests'][0]['id'] == chest_id
            opened = fresh.post('/v1/chests/' + chest_id + '/open', headers=auth(account), json=dict(request_id=str(uuid.uuid4()), expected_price=0))
            assert opened.status_code == 200, opened.text
            assert client.get('/v1/economy', headers=auth(account)).json()['wallet']['tokens'] == 3
            # Online state cannot be resurrected from stale database records.
            assert fresh.get('/v1/servers').json()['servers'] == []
            blocked = fresh.post('/v1/store/purchase', headers=auth(account), json=dict(request_id=str(uuid.uuid4()), item_id='tokens1', currency='test', expected_price=0))
            assert blocked.status_code == 403 and blocked.json()['error']['code'] == 'test_purchases_disabled'
    finally:
        process.terminate()
        process.wait(timeout=10)
