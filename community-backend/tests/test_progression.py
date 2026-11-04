"""Real DB/Redis money, ownership, naming and trusted result integration.

Match participation keys below are explicit test fixtures, not game evidence.
"""
import concurrent.futures
import secrets
import time
import uuid

import httpx
import pytest
from redis import Redis
from sqlalchemy import create_engine
from community_backend.models import User, Server
from community_backend.security import passwords, digest, token
from test_service import auth, COMPAT


@pytest.fixture(scope='module')
def context(service):
    engine = create_engine(service[1]['COMMUNITY_DATABASE_URL'])
    ids = [str(uuid.uuid4()) for _ in range(3)]
    logins = ['economy_' + secrets.token_hex(5) for _ in ids]
    hashed = passwords.hash('progression-test-password')
    with engine.begin() as db:
        for uid, login in zip(ids, logins):
            db.execute(User.__table__.insert().values(id=uid, login=login, nickname='EconomyTest', password_hash=hashed, disabled=False, player_profiles={}))
    with httpx.Client(base_url=service[0], timeout=12) as client:
        accounts = [client.post('/v1/auth/login', json=dict(login=login, password='progression-test-password')).json() for login in logins]
        yield client, accounts, engine, service[1]
    engine.dispose()


def buy(client, account, item, currency='test', price=0, request_id=None):
    return client.post('/v1/store/purchase', headers=auth(account), json=dict(request_id=request_id or str(uuid.uuid4()), item_id=item, currency=currency, expected_price=price))


def test_shop_atomic_deduction_inventory_and_test_currency(context):
    client, (a, b, card), _, _ = context
    assert client.get('/v1/economy', headers=auth(a)).json()['wallet']['tokens'] == 0
    assert buy(client, a, 'characters.kronk', 'tokens', 100).json()['error']['code'] == 'insufficient_funds'
    request_id = str(uuid.uuid4())
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        topups = list(pool.map(lambda _: buy(client, a, 'tokens2', request_id=request_id), range(2)))
    assert [r.status_code for r in topups] == [200, 200]
    assert client.get('/v1/economy', headers=auth(a)).json()['wallet']['tokens'] == 500
    assert buy(client, a, 'tokens3', request_id=request_id).json()['error']['code'] == 'idempotency_conflict'
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        purchases = list(pool.map(lambda _: buy(client, a, 'characters.kronk', 'tokens', 100), range(2)))
    assert sorted(r.status_code for r in purchases) == [200, 409]
    state = client.get('/v1/economy', headers=auth(a)).json()
    assert state['wallet']['tokens'] == 400
    assert 'characters.kronk' in state['purchases']
    assert buy(client, a, 'characters.zoe', 'tokens', 0).json()['error']['code'] == 'price_changed'
    profile = dict(character='Zoe', color=[1, 1, 1], highlight=[.5, .5, .5], **{'global': False})
    assert client.put('/v1/me/profiles/Locked', headers=auth(a), json=profile).status_code == 403
    assert client.put('/v1/me/profiles/Kronk', headers=auth(a), json=profile | {'character': 'Kronk'}).status_code == 200
    receipt = buy(client, card, 'gold_pass')
    assert receipt.status_code == 200
    assert receipt.json()['state']['wallet']['gold_pass']
    # An actual card grants server-authorized zero-currency redemption.
    redeemed = buy(client, card, 'characters.zoe', 'gold_pass', 0)
    assert redeemed.status_code == 200
    assert 'characters.zoe' in redeemed.json()['state']['purchases']
    assert client.get('/v1/orders', headers=auth(a)).json()['orders']


def test_global_profile_upgrade_is_unique_and_charged_once(context):
    client, (a, b, _), _, _ = context
    for account in [a, b]:
        assert buy(client, account, 'tickets1').status_code == 200
    name = 'Global' + secrets.token_hex(4)
    profile = dict(character='Spaz', color=[1, 1, 1], highlight=[.5, .5, .5], **{'global': False})
    for account, spelling in [(a, name), (b, name.lower())]:
        assert client.put('/v1/me/profiles/' + spelling, headers=auth(account), json=profile).status_code == 200
        assert client.get('/v1/profiles/availability', params={'name': spelling}, headers=auth(account)).json()['available']
    requests = [(a, name, str(uuid.uuid4())), (b, name.lower(), str(uuid.uuid4()))]

    def upgrade(args):
        account, spelling, request_id = args
        return client.post('/v1/profiles/upgrade', headers=auth(account), json=dict(name=spelling, request_id=request_id, expected_price=100))
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(upgrade, requests))
    assert sorted(r.status_code for r in responses) == [200, 409]
    index = next(i for i, r in enumerate(responses) if r.status_code == 200)
    winner, spelling, request_id = requests[index]
    assert upgrade(requests[index]).status_code == 200
    winner_state = client.get('/v1/economy', headers=auth(winner)).json()
    loser_state = client.get('/v1/economy', headers=auth(requests[1-index][0])).json()
    assert winner_state['wallet']['tickets'] == 200
    assert loser_state['wallet']['tickets'] == 300
    assert winner_state['player_profiles'][spelling]['global'] is True
    assert client.put('/v1/me/profiles/' + spelling, headers=auth(winner), json=profile | {'global': True}).status_code == 200
    assert client.put('/v1/me/profiles/' + spelling, headers=auth(winner), json=profile).status_code == 403
    assert client.delete('/v1/me/profiles/' + spelling, headers=auth(winner)).status_code == 200
    assert client.get('/v1/profiles/availability', params={'name': spelling}, headers=auth(requests[1-index][0])).json()['available']


def test_trusted_match_rewards_league_and_replay(context):
    client, (a, b, c), engine, env = context
    sid, iid, key = str(uuid.uuid4()), str(uuid.uuid4()), token()
    with engine.begin() as db:
        db.execute(Server.__table__.insert().values(id=sid, name='Explicit league fixture', key_hash=digest(key), revoked=False))
    headers = {'Authorization': 'Bearer ' + key}
    assert client.post('/v1/servers/register', headers=headers, json=COMPAT | dict(server_id=sid, instance_id=iid, address='127.0.0.1', port=43210)).status_code == 200
    body = dict(instance_id=iid, match_id=str(uuid.uuid4()), started_at=time.time()-20, ended_at=time.time()-2,
                players=[dict(uid=a['user']['uid'], placement=1), dict(uid=b['user']['uid'], placement=2)])
    url = f'/v1/servers/{sid}/matches'
    assert client.post(url, headers=auth(a), json=body).status_code == 401
    assert client.post(url, headers=headers, json=body).json()['error']['code'] == 'match_player_unverified'
    with Redis.from_url(env['COMMUNITY_REDIS_URL']) as cache:
        for account in [a, b]:
            cache.set(f"participant:{iid}:{account['user']['uid']}", '1', ex=60)
    balances = [client.get('/v1/economy', headers=auth(account)).json()['wallet']['tokens'] for account in [a, b]]
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: client.post(url, headers=headers, json=body), range(2)))
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert results[0].json() == results[1].json()
    for account, before, reward, points in [(a, balances[0], 10, 30), (b, balances[1], 3, 10)]:
        state = client.get('/v1/economy', headers=auth(account)).json()
        assert state['wallet']['tokens'] == before + reward
        assert state['league']['points'] == points and state['league']['games'] == 1
    league = client.get('/v1/league', headers=auth(a)).json()
    assert league['me']['points'] == 30 and league['me']['games'] == 1
    assert league['leaderboard'] and client.get('/v1/league', headers=auth(c)).json()['me'] is None
    altered = body | {'players': [dict(uid=a['user']['uid'], placement=2), dict(uid=b['user']['uid'], placement=1)]}
    assert client.post(url, headers=headers, json=altered).json()['error']['code'] == 'idempotency_conflict'
