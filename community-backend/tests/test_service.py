import concurrent.futures
import json
import secrets
import socket
import threading
import time
import uuid

import httpx
from sqlalchemy import create_engine, update
from websockets.sync.client import connect

from community_backend.models import Server, User
from community_backend.security import digest, token

COMPAT = dict(engine_build=23079, scene_protocol=57, community_protocol=1, assets='23079')


def register(client):
    # Client-specific source isn't spoofed; bounded registrations fit rate limit.
    login = 'test_' + secrets.token_hex(5)
    response = client.post('/v1/auth/register', json=dict(login=login, password='correct-password', nickname='中文昵称"'))
    assert response.status_code == 201, response.text
    return login, response.json()


def auth(result):
    return {'Authorization': 'Bearer ' + result['access_token']}


def test_account_lifecycle(client, service):
    login, result = register(client)
    assert client.get('/v1/me', headers=auth(result)).json()['nickname'] == '中文昵称"'
    assert client.post('/v1/auth/register', json=dict(login=login.upper(), password='correct-password', nickname='duplicate')).status_code == 409
    assert client.post('/v1/auth/login', json=dict(login=login, password='incorrect-password')).status_code == 401
    signed_in = client.post('/v1/auth/login', json=dict(login=login.upper(), password='correct-password')).json()
    assert signed_in['user']['uid'] == result['user']['uid']
    old = result['refresh_token']
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda _: client.post('/v1/auth/refresh', json={'refresh_token': old}), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 401]
    rotated = next(r.json() for r in responses if r.status_code == 200)
    assert client.get('/v1/me', headers=auth(result)).status_code == 401
    assert client.post('/v1/auth/refresh', json={'refresh_token': old}).status_code == 401
    assert client.post('/v1/auth/logout', headers=auth(rotated)).status_code == 200
    assert client.get('/v1/me', headers=auth(rotated)).status_code == 401
    assert client.post('/v1/auth/refresh', json={'refresh_token': rotated['refresh_token']}).status_code == 401
    engine = create_engine(service[1]['COMMUNITY_DATABASE_URL'])
    with engine.begin() as db:
        db.execute(update(User).where(User.id == result['user']['uid']).values(disabled=True))
    engine.dispose()
    assert client.get('/v1/me', headers=auth(signed_in)).status_code == 403
    assert client.post('/v1/auth/login', json=dict(login=login, password='correct-password')).status_code == 403


class PingResponder:
    """Explicit protocol test fixture; does not certify real game UDP."""
    def __enter__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        self.port = self.sock.getsockname()[1]
        self.sock.settimeout(.1)
        self.stopping = threading.Event()
        self.enabled = True
        self.worker = threading.Thread(target=self.run)
        self.worker.start()
        return self

    def run(self):
        while not self.stopping.is_set():
            try:
                packet, addr = self.sock.recvfrom(64)
                if packet == b'\x0b' and self.enabled:
                    self.sock.sendto(b'\x0c', addr)
            except socket.timeout:
                pass

    def __exit__(self, *args):
        self.stopping.set()
        self.worker.join()
        self.sock.close()


def test_directory_control_join(client, service):
    _, account = register(client)
    sid, iid, key = str(uuid.uuid4()), str(uuid.uuid4()), token()
    engine = create_engine(service[1]['COMMUNITY_DATABASE_URL'])
    with engine.begin() as db:
        db.execute(Server.__table__.insert().values(id=sid, name='test server', key_hash=digest(key), revoked=False))
    engine.dispose()
    with PingResponder() as ping:
        body = COMPAT | dict(server_id=sid, instance_id=iid, address='127.0.0.1', port=ping.port)
        assert client.post('/v1/servers/register', json=body, headers=auth(account)).status_code == 401
        registered = client.post('/v1/servers/register', json=body, headers={'Authorization': 'Bearer ' + key})
        assert registered.status_code == 200, registered.text
        wsurl = service[0].replace('http:', 'ws:') + '/v1/servers/control'
        with connect(wsurl, additional_headers={'Authorization': 'Bearer ' + registered.json()['control_token']}) as ws:
            welcome = json.loads(ws.recv())
            cid = welcome['control_session_id']

            def send(kind, payload, mid=None):
                ws.send(json.dumps(dict(version=1, message_id=mid or str(uuid.uuid4()), type=kind, server_id=sid, instance_id=iid, control_session_id=cid, payload=payload)))

            send('hello', {})
            state = dict(name='测试服', players=1, devices=1, capacity=4, public=True, ready=True)
            send('party_state', state)
            assert json.loads(ws.recv())['payload']['udp_reachable'] is True
            listing = client.get('/v1/servers').json()['servers']
            assert any(s['server_id'] == sid and s['players'] == 1 for s in listing)
            assert not client.get('/v1/servers?scene_protocol=999').json()['servers']
            join = COMPAT | dict(instance_id=iid, join_attempt_id=str(uuid.uuid4()))
            assert client.post(f'/v1/servers/{sid}/join', json=join).status_code == 401
            assert client.post(f'/v1/servers/{sid}/join', json=join | {'assets': 'wrong'}, headers=auth(account)).status_code == 409
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(client.post, f'/v1/servers/{sid}/join', json=join, headers=auth(account))
                prepare = json.loads(ws.recv())
                assert prepare['type'] == 'prepare_join'
                assert prepare['payload']['uid'] == account['user']['uid']
                assert not future.done()  # Must wait for engine installation ACK.
                send('join_prepared', {}, prepare['message_id'])
                response = future.result()
            assert response.status_code == 200, response.text
            assert digest(response.json()['ticket']) == prepare['payload']['ticket_index']
            duplicate = client.post(f'/v1/servers/{sid}/join', json=join, headers=auth(account))
            assert duplicate.json()['ticket'] == response.json()['ticket']
            send('party_state', state | {'players': 4})
            ws.recv()
            assert client.post(f'/v1/servers/{sid}/join', json=join | {'join_attempt_id': str(uuid.uuid4())}, headers=auth(account)).json()['error']['code'] == 'room_full'
            send('party_state', state)
            ws.recv()
            # No ACK: server must cancel instead of leaking a usable credential.
            timeout = client.post(f'/v1/servers/{sid}/join', json=join | {'join_attempt_id': str(uuid.uuid4())}, headers=auth(account))
            assert timeout.status_code == 504
            assert json.loads(ws.recv())['type'] == 'prepare_join'
            assert json.loads(ws.recv())['type'] == 'ticket_cancel'
            ping.enabled = False
            send('heartbeat', state)
            assert json.loads(ws.recv())['payload']['udp_reachable'] is False
            assert client.get(f'/v1/servers/{sid}').status_code == 409
            ping.enabled = True
            send('heartbeat', state)
            assert json.loads(ws.recv())['payload']['udp_reachable'] is True
            time.sleep(3.2)
            assert client.get(f'/v1/servers/{sid}').status_code == 409
        assert client.get(f'/v1/servers/{sid}').status_code == 409


def test_udp_unreachable_and_rate_limit(client):
    # Registration rate limiting is asserted after the main flows finish.
    for _ in range(6):
        response = client.post('/v1/auth/register', json=dict(login='limit_' + secrets.token_hex(4), password='correct-password', nickname='test'))
    assert response.status_code == 429


def test_validation_redacts_credentials(client):
    password = 'secret-must-never-be-echoed'
    response = client.post('/v1/auth/login', json={'login': '!', 'password': password})
    assert response.status_code == 422
    assert password not in response.text
    assert response.json()['error']['code'] == 'request_invalid'
