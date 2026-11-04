"""Explicit score/chest fixtures exercise real HTTP, transactions and slots."""
import concurrent.futures
from datetime import timedelta
import uuid
from sqlalchemy import update
from community_backend.models import Tournament, TournamentEntry, RewardChest, RewardMessage, utcnow
from test_progression import context, buy
from test_service import auth


def event(engine, *, lower=False, required=None, game='Challenges:Runaround', score_type='points'):
    tid = 'explicit-reward-fixture-' + str(uuid.uuid4())
    with engine.begin() as db:
        db.execute(Tournament.__table__.insert().values(id=tid, game=game,
            starts_at=utcnow()-timedelta(hours=1), ends_at=utcnow()+timedelta(hours=1),
            definition=dict(rewards=True, lower=lower, score_type=score_type, required=required or [])))
    return tid


def score(client, engine, account, tid, value, *, game='Challenges:Runaround', score_type='points'):
    entered = client.post(f'/v1/tournaments/{tid}/entries', headers=auth(account), json=dict(request_id=str(uuid.uuid4())))
    assert entered.status_code == 200, entered.text
    entry = entered.json()
    with engine.begin() as db:
        db.execute(update(TournamentEntry).where(TournamentEntry.id == entry['entry_id']).values(created_at=utcnow()-timedelta(seconds=3)))
    result = client.post(f'/v1/tournaments/{tid}/scores', headers=auth(account), json=dict(entry_id=entry['entry_id'], game=game, score=value, score_type=score_type))
    assert result.status_code == 200, result.text
    return result.json()


def test_reward_open_is_atomic_and_grants_inventory(context):
    client, (a, b, _), engine, _ = context
    tid = event(engine)
    first = score(client, engine, a, tid, 100)
    assert len(first['rewards']) == 1
    assert score(client, engine, a, tid, 200)['rewards'] == []
    data = client.get('/v1/chests', headers=auth(a)).json()
    chest = data['chests'][0]
    url = '/v1/chests/' + chest['id'] + '/open'
    body = dict(request_id=str(uuid.uuid4()), expected_price=chest['unlock_tokens'])
    assert client.post(url, headers=auth(b), json=body).status_code == 404
    assert client.post(url, headers=auth(a), json=body).json()['error']['code'] == 'insufficient_funds'
    assert buy(client, a, 'tokens2').status_code == 200
    assert client.post(url, headers=auth(a), json=body | {'expected_price': 0}).status_code == 409
    # Explicit payout fixture verifies all grant types, not a probability claim.
    with engine.begin() as db:
        db.execute(update(RewardChest).where(RewardChest.id == chest['id']).values(contents=dict(tokens=7, tickets=80, items=['characters.kronk'], gold_pass_days=1)))
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda _: client.post(url, headers=auth(a), json=body), range(2)))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    state = client.get('/v1/economy', headers=auth(a)).json()
    assert state['wallet']['tokens'] == 500 - chest['unlock_tokens'] + 7
    assert state['wallet']['tickets'] == 80 and state['wallet']['gold_pass']
    assert 'characters.kronk' in state['purchases'] and state['chests'] == []
    assert client.post(url, headers=auth(a), json=body | {'request_id': str(uuid.uuid4())}).status_code == 409
    # A second chest with the same character pays compensation, not a duplicate.
    tid2 = event(engine)
    score(client, engine, a, tid2, 10)
    another = client.get('/v1/chests', headers=auth(a)).json()['chests'][0]
    with engine.begin() as db:
        db.execute(update(RewardChest).where(RewardChest.id == another['id']).values(contents=dict(tokens=3, tickets=4, items=['characters.kronk'], gold_pass_days=0)))
    receipt = client.post('/v1/chests/' + another['id'] + '/open', headers=auth(a), json=dict(request_id=str(uuid.uuid4()), expected_price=0)).json()
    assert receipt['payouts']['compensation_tokens'] == 50 and receipt['payouts']['items'] == []


def test_dock_overflow_claim_and_stale_open_cannot_consume_replacement(context):
    client, (_, b, c), engine, _ = context
    for _ in range(6):
        score(client, engine, b, event(engine), 10)
    state = client.get('/v1/economy', headers=auth(b)).json()
    assert len(state['chests']) == 4 and state['inbox_count'] == 2
    inbox = client.get('/v1/inbox', headers=auth(b)).json()['messages']
    claim_url = '/v1/inbox/' + inbox[0]['id'] + '/claim'
    assert client.post(claim_url, headers=auth(c), json={}).status_code == 404
    assert client.post(claim_url, headers=auth(b), json={}).json()['error']['code'] == 'chest_dock_full'
    old = state['chests'][0]
    with engine.begin() as db:
        db.execute(update(RewardChest).where(RewardChest.id == old['id']).values(unlock_at=utcnow()-timedelta(seconds=1)))
    old_url = '/v1/chests/' + old['id'] + '/open'
    opening = dict(request_id=str(uuid.uuid4()), expected_price=0)
    assert client.post(old_url, headers=auth(b), json=opening).status_code == 200
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        replies = list(pool.map(lambda _: client.post(claim_url, headers=auth(b), json={}), range(2)))
    assert all(r.status_code == 200 for r in replies)
    new_state = client.get('/v1/economy', headers=auth(b)).json()
    assert len(new_state['chests']) == 4 and new_state['inbox_count'] == 1
    replacement = next(ch for ch in new_state['chests'] if ch['slot'] == old['slot'])
    assert replacement['id'] != old['id']
    assert client.post(old_url, headers=auth(b), json=opening).status_code == 200
    assert client.post(old_url, headers=auth(b), json=opening | {'request_id': str(uuid.uuid4())}).status_code == 409
    assert replacement['id'] in [ch['id'] for ch in client.get('/v1/economy', headers=auth(b)).json()['chests']]


def test_final_standings_settle_once_and_share_tied_rewards(context):
    client, (a, b, c), engine, _ = context
    tid = event(engine)
    score(client, engine, a, tid, 999)
    score(client, engine, b, tid, 999)
    score(client, engine, c, tid, 500)
    with engine.begin() as db:
        db.execute(update(Tournament).where(Tournament.id == tid).values(ends_at=utcnow()-timedelta(minutes=2)))
    assert not [m for m in client.get('/v1/inbox', headers=auth(c)).json()['messages'] if m['tournament_id'] == tid and m['kind'] == 'standings']
    with engine.begin() as db:
        db.execute(update(Tournament).where(Tournament.id == tid).values(ends_at=utcnow()-timedelta(minutes=6)))
    for account, rank, appearance in [(a, 1, 'l6'), (b, 1, 'l6'), (c, 3, 'l5')]:
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            responses = list(pool.map(lambda _: client.get('/v1/inbox', headers=auth(account)), range(2)))
        assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
        prizes = [m for m in responses[0].json()['messages'] if m['tournament_id'] == tid and m['kind'] == 'standings']
        assert len(prizes) == 1 and prizes[0]['rank'] == rank and prizes[0]['appearance'] == appearance
    assert client.post('/v1/tournaments/query', headers=auth(a), json=dict(tournament_ids=[tid])).json()['t'][0]['scores'][0][0] == 999


def test_timed_events_require_ownership_and_rank_lower_times_first(context):
    client, (_, b, c), engine, _ = context
    tid = event(engine, lower=True, required=['games.race'], game='Challenges:Race', score_type='time')
    assert client.post(f'/v1/tournaments/{tid}/entries', headers=auth(c), json=dict(request_id=str(uuid.uuid4()))).status_code == 403
    for account in (b, c):
        assert buy(client, account, 'tokens2').status_code == 200
        assert buy(client, account, 'games.race', 'tokens', 200).status_code == 200
    score(client, engine, b, tid, 2000, game='Challenges:Race', score_type='time')
    score(client, engine, c, tid, 1000, game='Challenges:Race', score_type='time')
    board = client.post('/v1/tournaments/query', headers=auth(c), json=dict(tournament_ids=[tid], num_scores=50)).json()['t'][0]
    assert board['scoreType'] == 'time'
    assert [p[0] for p in board['scores']] == [1000, 2000]
    assert board['scores'][0][2][0]['a'] == c['user']['uid']


def test_fixed_purple_gift_keeps_currency_identity_and_cannot_duplicate(context):
    client, (a, b, _), engine, _ = context
    from sqlalchemy.orm import Session
    with Session(engine) as db:
        chest = RewardChest(user_id=a['user']['uid'], appearance='l6', slot=None,
            contents=dict(tokens=0, tickets=0, purple_tickets=9999, items=[], gold_pass_days=0, fixed=True))
        db.add(chest)
        db.flush()
        message = RewardMessage(user_id=a['user']['uid'], source='explicit-purple-fixture-' + str(uuid.uuid4()),
            tournament_id=None, chest_id=chest.id, kind='admin_gift')
        db.add(message)
        db.commit()
        cid, mid = chest.id, message.id
    inbox = client.get('/v1/inbox', headers=auth(a)).json()['messages']
    gift = next(m for m in inbox if m['id'] == mid)
    assert gift['game'] is None and gift['fixed_contents']['purple_tickets'] == 9999
    assert client.post('/v1/inbox/' + mid + '/claim', headers=auth(b), json={}).status_code == 404
    assert client.post('/v1/inbox/' + mid + '/claim', headers=auth(a), json={}).status_code == 200
    state = client.get('/v1/economy', headers=auth(a)).json()
    purple_before, tickets_before, tokens_before = (state['wallet'][k] for k in ('purple_tickets', 'tickets', 'tokens'))
    box = next(c for c in state['chests'] if c['id'] == cid)
    assert box['unlock_tokens'] == 0
    body = dict(request_id=str(uuid.uuid4()), expected_price=0)
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        replies = list(pool.map(lambda _: client.post('/v1/chests/' + cid + '/open', headers=auth(a), json=body), range(2)))
    assert all(r.status_code == 200 for r in replies), [r.text for r in replies]
    after = client.get('/v1/economy', headers=auth(a)).json()['wallet']
    assert after['purple_tickets'] == purple_before + 9999
    assert after['tickets'] == tickets_before and after['tokens'] == tokens_before
