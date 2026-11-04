import json
import secrets
import uuid
import httpx
from sqlalchemy import create_engine
from websockets.sync.client import connect
from websockets.exceptions import InvalidStatus, ConnectionClosed
import pytest
from community_backend.models import Server
from community_backend.security import digest, token
from test_service import COMPAT, PingResponder


def test_reconnect_and_stale_instance(client, service):
    sid, iid, key = str(uuid.uuid4()), str(uuid.uuid4()), token()
    engine = create_engine(service[1]['COMMUNITY_DATABASE_URL'])
    with engine.begin() as db:
        db.execute(Server.__table__.insert().values(id=sid, name='generation test', key_hash=digest(key), revoked=False))
    engine.dispose()
    headers = {'Authorization': 'Bearer ' + key}
    wsurl = service[0].replace('http:', 'ws:') + '/v1/servers/control'
    with pytest.raises(InvalidStatus):
        with connect(wsurl, additional_headers=headers):
            pass
    with PingResponder() as ping:
        body = COMPAT | dict(server_id=sid, instance_id=iid, address='127.0.0.1', port=ping.port)

        def registration(value):
            response = client.post('/v1/servers/register', json=value, headers=headers)
            assert response.status_code == 200, response.text
            return {'Authorization': 'Bearer ' + response.json()['control_token']}

        with connect(wsurl, additional_headers=registration(body)) as old:
            old_welcome = json.loads(old.recv())
            with connect(wsurl, additional_headers=registration(body)) as new:
                welcome = json.loads(new.recv())
                assert welcome['control_session_id'] != old_welcome['control_session_id']
                with pytest.raises(ConnectionClosed):
                    old.recv()
                def send(kind, payload, cid=welcome['control_session_id']):
                    new.send(json.dumps(dict(version=1, message_id=str(uuid.uuid4()), type=kind, server_id=sid, instance_id=iid, control_session_id=cid, payload=payload)))
                send('hello', {})
                state = dict(name='generation', players=0, devices=0, capacity=8, public=True, ready=True)
                send('party_state', state)
                assert json.loads(new.recv())['payload']['udp_reachable']
                assert client.get(f'/v1/servers/{sid}').status_code == 200
                # New process generation hides the old process immediately.
                registration(body | {'instance_id': str(uuid.uuid4())})
                assert client.get(f'/v1/servers/{sid}').status_code == 409
                assert client.post('/v1/servers/register', json=body, headers=headers).json()['error']['code'] == 'instance_stale'
                # A message carrying an old control generation closes the socket.
                send('heartbeat', state, old_welcome['control_session_id'])
                with pytest.raises(ConnectionClosed):
                    new.recv()
