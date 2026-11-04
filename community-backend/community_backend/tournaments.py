"""Rotating community co-op events; scores remain client-reported."""
from datetime import datetime, timezone, timedelta
from uuid import UUID
from fastapi import Depends
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from .models import Tournament, TournamentEntry, User, Ownership, utcnow
from .schemas import TournamentQuery, TournamentEnter, TournamentScore
from .progression import fingerprint

GAMES = {
    'runaround': ('Runaround', 'points', False, []),
    'last-stand': ('The Last Stand', 'points', False, []),
    'football': ('Football', 'time', True, []),
    'pro-football': ('Pro Football', 'time', True, []),
    'uber-runaround': ('Uber Runaround', 'points', False, []),
    'meteor': ('Meteor Shower', 'time', False, ['games.meteor_shower']),
    'epic-meteor': ('Epic Meteor Shower', 'time', False, ['games.meteor_shower']),
    'race': ('Race', 'time', True, ['games.race']),
    'pro-race': ('Pro Race', 'time', True, ['games.race']),
    'target': ('Target Practice', 'points', False, ['games.target_practice']),
    'ninja': ('Ninja Fight', 'time', True, ['games.ninja_fight']),
    'eggs': ('Easter Egg Hunt', 'points', False, ['games.easter_egg_hunt']),
}


async def standings(db, event):
    lower = event.definition.get('lower', False)
    aggregate = func.min if lower else func.max
    best = select(TournamentEntry.user_id.label('uid'), aggregate(TournamentEntry.score).label('score')).where(
        TournamentEntry.tournament_id == event.id, TournamentEntry.score.is_not(None)).group_by(TournamentEntry.user_id).subquery()
    rows = (await db.execute(select(best.c.uid, best.c.score, User.nickname).join(User, User.id == best.c.uid)
        .where(User.disabled.is_(False)).order_by(best.c.score.asc() if lower else best.c.score.desc(), best.c.uid))).all()
    result, previous, rank = [], None, 0
    for i, (uid, score, name) in enumerate(rows):
        if previous is None or score != previous:
            rank = i + 1
        result.append(dict(uid=uid, score=score, nickname=name, rank=rank))
        previous = score
    return result


def mount_tournaments(app, sessions, current_user, APIError, cfg):
    async def daily(db):
        now = utcnow()
        period = cfg.tournament_period_seconds
        period_index = int(now.timestamp()) // period
        start = datetime.fromtimestamp(period_index * period, timezone.utc)
        # Five always-unlocked events plus three rotating catalog events.
        pool = list(GAMES)
        rotation = period_index % (len(pool) - 5)
        selected = pool[:5] + [pool[5 + (rotation+i) % (len(pool)-5)] for i in range(3)]
        values = []
        for i, slug in enumerate(selected):
            level, score_type, lower, required = GAMES[slug]
            values.append(dict(id=start.strftime('%Y-%m-%d-t%H%M%S-') + slug, game='Challenges:' + level,
                starts_at=start, ends_at=start + timedelta(seconds=period), definition=dict(rewards=True,
                score_type=score_type, lower=lower, required=required, min_players=1, max_players=(1 if i % 3 == 1 else 2 if i % 3 == 2 else 4))))
        await db.execute(insert(Tournament).values(values).on_conflict_do_nothing(index_elements=['id']))
        return [v['id'] for v in values]

    async def legacy_event(db, event, limit):
        board = await standings(db, event)
        definition = event.definition
        result = dict(tournamentID=event.id, game=event.game, minPlayers=definition.get('min_players', 1), maxPlayers=definition.get('max_players', 4),
            fee=None, allowAds=False, adTriesRemaining=0, freeTriesRemaining=None,
            timeRemaining=max(0, int((event.ends_at - utcnow()).total_seconds())), totalTime=int((event.ends_at-event.starts_at).total_seconds()),
            scoreType=definition.get('score_type', 'points'), requiredLeague=None,
            scores=[[p['score'], p['nickname'], [dict(a=p['uid'], p=None)]] for p in board[:limit]],
            score_source='client_reported', prizes_enabled=definition.get('rewards', False))
        if result['prizes_enabled']:
            result.update(prizeRange1=[1, 1], prizeChest1='l6', prizeRange2=[2, 3], prizeChest2='l5',
                          prizeRange3=[4, 10], prizeChest3='l4', completionChest='l1', settlementGrace=300)
        return result

    @app.post('/v1/tournaments/query')
    async def query(body: TournamentQuery, identity=Depends(current_user)):
        async with sessions() as db:
            current = await daily(db)
            ids = current if body.tournament_ids is None else body.tournament_ids
            events = []
            for tid in ids:
                event = await db.get(Tournament, tid)
                if event is None:
                    raise APIError('tournament_unknown', 404)
                events.append(await legacy_event(db, event, body.num_scores))
            await db.commit()
            return {'t': events}

    @app.post('/v1/tournaments/{tournament_id}/entries')
    async def enter(tournament_id: str, body: TournamentEnter, identity=Depends(current_user)):
        uid = identity[0].id
        async with sessions() as db:
            await daily(db)
            await db.scalar(select(User).where(User.id == uid).with_for_update())
            previous = await db.scalar(select(TournamentEntry).where(TournamentEntry.user_id == uid, TournamentEntry.request_id == str(body.request_id)))
            if previous and previous.tournament_id != tournament_id:
                raise APIError('idempotency_conflict', 409)
            event = await db.get(Tournament, tournament_id)
            if not event:
                raise APIError('tournament_unknown', 404)
            if not event.starts_at <= utcnow() < event.ends_at:
                raise APIError('tournament_ended', 409)
            required = set(event.definition.get('required', []))
            owned = set((await db.scalars(select(Ownership.item_id).where(Ownership.user_id == uid))).all())
            if not required <= owned:
                raise APIError('item_required', 403)
            if previous is None:
                previous = TournamentEntry(user_id=uid, tournament_id=tournament_id, request_id=str(body.request_id))
                db.add(previous)
                await db.flush()
            result = dict(entry_id=previous.id, tournament_id=event.id, game=event.game,
                          ends_at=event.ends_at.timestamp(), fee=0)
            await db.commit()
            return result

    @app.post('/v1/tournaments/{tournament_id}/scores')
    async def submit(tournament_id: str, body: TournamentScore, identity=Depends(current_user)):
        uid = identity[0].id
        hashed = fingerprint(body.model_dump(mode='json'))
        async with sessions() as db:
            # Serialize standings and simultaneous submissions for this event.
            event = await db.scalar(select(Tournament).where(Tournament.id == tournament_id).with_for_update())
            if not event:
                raise APIError('tournament_unknown', 404)
            entry = await db.get(TournamentEntry, str(body.entry_id))
            if not entry or entry.tournament_id != event.id or entry.user_id != uid:
                raise APIError('tournament_entry_invalid', 403)
            if entry.score_hash is not None:
                legacy_hash = fingerprint(body.model_dump(mode='json', exclude={'score_type'}))
                if entry.score_hash != hashed and not (entry.score_hash == legacy_hash and body.score_type == event.definition.get('score_type', 'points')):
                    raise APIError('idempotency_conflict', 409)
                return entry.result
            now = utcnow()
            if body.game != event.game or body.score_type != event.definition.get('score_type', 'points'):
                raise APIError('tournament_game_mismatch', 409)
            if body.score_type == 'time' and body.score == 0:
                raise APIError('tournament_score_time_invalid', 409)
            if now > event.ends_at + timedelta(minutes=5) or now < entry.created_at + timedelta(seconds=1):
                raise APIError('tournament_score_time_invalid', 409)
            entry.score, entry.score_hash, entry.submitted_at = body.score, hashed, now
            await db.flush()
            board = await standings(db, event)
            rank = next(p['rank'] for p in board if p['uid'] == uid)
            result = dict(rank=rank, total=len(board), playerRank=rank, bestPlayerRank=rank,
                tops=[[p['score'], p['nickname']] for p in board[:10]], link='/v1/tournaments/query',
                tournamentSecondsRemaining=max(0, int((event.ends_at-now).total_seconds())),
                score_source='client_reported', rewards=[], entry_id=entry.id)
            entry.result = result
            if event.definition.get('rewards', False):
                from .rewards import issue_reward
                await db.scalar(select(User).where(User.id == uid).with_for_update())
                reward = await issue_reward(db, uid, event.id, 'complete:' + event.id, 'completion', 'l1', auto_slot=True)
                result['rewards'] = [reward] if reward else []
                entry.result = dict(result)
            await db.commit()
            return result

