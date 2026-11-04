"""Real HTTP/DB entry and score contracts; scores here are explicit fixtures."""
import concurrent.futures
from datetime import timedelta
import uuid
from sqlalchemy import update
from community_backend.models import Tournament, TournamentEntry, utcnow
from test_progression import context
from test_service import auth


def test_tournament_listing_entry_and_expiry(context):
    client, (a, _, _), engine, _ = context
    assert client.post('/v1/tournaments/query', json={}).status_code == 401
    events = client.post('/v1/tournaments/query', headers=auth(a), json={}).json()['t']
    assert len(events) == 8
    assert all(e['timeRemaining'] > 0 and e['fee'] is None for e in events)
    assert {'Challenges:Runaround', 'Challenges:The Last Stand'} <= {e['game'] for e in events}
    assert all(e['prizes_enabled'] and e['prizeChest1'] == 'l6' for e in events)
    tid = events[0]['tournamentID']
    before = client.get('/v1/economy', headers=auth(a)).json()['wallet']
    request_id = str(uuid.uuid4())
    url = f'/v1/tournaments/{tid}/entries'
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        replies = list(pool.map(lambda _: client.post(url, headers=auth(a), json=dict(request_id=request_id)), range(2)))
    assert all(r.status_code == 200 for r in replies)
    assert replies[0].json() == replies[1].json()
    assert replies[0].json()['fee'] == 0
    assert client.get('/v1/economy', headers=auth(a)).json()['wallet'] == before
    other = events[1]['tournamentID']
    assert client.post(f'/v1/tournaments/{other}/entries', headers=auth(a), json=dict(request_id=request_id)).status_code == 409
    assert client.post('/v1/tournaments/query', headers=auth(a), json=dict(tournament_ids=['missing'])).status_code == 404
    expired = 'explicit-expired-fixture-' + str(uuid.uuid4())
    with engine.begin() as db:
        db.execute(Tournament.__table__.insert().values(id=expired, game='Challenges:Runaround', starts_at=utcnow()-timedelta(days=2), ends_at=utcnow()-timedelta(days=1)))
    assert client.post(f'/v1/tournaments/{expired}/entries', headers=auth(a), json=dict(request_id=str(uuid.uuid4()))).status_code == 409


def test_tournament_result_auth_idempotency_best_score_and_no_rewards(context):
    client, (a, b, _), engine, _ = context
    event = client.post('/v1/tournaments/query', headers=auth(a), json={}).json()['t'][0]
    tid = 'explicit-results-fixture-' + str(uuid.uuid4())
    with engine.begin() as db:
        db.execute(Tournament.__table__.insert().values(id=tid, game=event['game'], starts_at=utcnow()-timedelta(minutes=1), ends_at=utcnow()+timedelta(hours=1)))
    entry = client.post(f'/v1/tournaments/{tid}/entries', headers=auth(a), json=dict(request_id=str(uuid.uuid4()))).json()
    body = dict(entry_id=entry['entry_id'], game=event['game'], score=123)
    url = f'/v1/tournaments/{tid}/scores'
    assert client.post(url, headers=auth(b), json=body).status_code == 403
    assert client.post(url, headers=auth(a), json=body | {'game': 'Default:Rookie Onslaught'}).status_code == 409
    assert client.post(url, headers=auth(a), json=body | {'score': 1.5}).status_code == 422
    assert client.post(url, headers=auth(a), json=body | {'uid': b['user']['uid']}).status_code == 422
    with engine.begin() as db:
        db.execute(update(TournamentEntry).where(TournamentEntry.id == entry['entry_id']).values(created_at=utcnow()+timedelta(minutes=1)))
    assert client.post(url, headers=auth(a), json=body).status_code == 409  # Explicit invalid-time fixture.
    # Fixture backdate, not a fabricated game or bypass in application code.
    with engine.begin() as db:
        db.execute(update(TournamentEntry).where(TournamentEntry.id == entry['entry_id']).values(created_at=utcnow()-timedelta(seconds=2)))
    before = client.get('/v1/economy', headers=auth(a)).json()
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda _: client.post(url, headers=auth(a), json=body), range(2)))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert responses[0].json() == responses[1].json()
    result = responses[0].json()
    assert result['rank'] == 1 and result['rewards'] == [] and result['score_source'] == 'client_reported'
    assert client.post(url, headers=auth(a), json=body | {'score': 124}).status_code == 409
    after = client.get('/v1/economy', headers=auth(a)).json()
    assert after['wallet'] == before['wallet'] and after['league'] == before['league']
    another = client.post(f'/v1/tournaments/{tid}/entries', headers=auth(a), json=dict(request_id=str(uuid.uuid4()))).json()
    with engine.begin() as db:
        db.execute(update(TournamentEntry).where(TournamentEntry.id == another['entry_id']).values(created_at=utcnow()-timedelta(seconds=2)))
    assert client.post(url, headers=auth(a), json=body | {'entry_id': another['entry_id'], 'score': 50}).status_code == 200
    board = client.post('/v1/tournaments/query', headers=auth(a), json=dict(tournament_ids=[tid], num_scores=50)).json()['t'][0]['scores']
    assert len(board) == 1 and board[0][0] == 123 and board[0][2][0]['a'] == a['user']['uid']
