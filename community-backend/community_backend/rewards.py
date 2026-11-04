"""Transactional community chest rewards, inbox and delayed final standings."""
import asyncio
import hashlib
import json
import logging
import math
import secrets
from datetime import timedelta
from uuid import UUID
from fastapi import Depends
from sqlalchemy import select, exists, or_, and_
from .models import User, Wallet, Ownership, Order, Tournament, TournamentEntry, RewardChest, RewardMessage, utcnow
from .catalog import ITEMS
from .schemas import ChestOpen

# Community values; upstream server reward tables are not in this repository.
RULES = {
    'l1': dict(wait=300, tokens=[2, 8], tickets=[50, 150], item_chance=1, card_chance=0),
    'l2': dict(wait=900, tokens=[5, 15], tickets=[100, 300], item_chance=3, card_chance=0),
    'l3': dict(wait=1800, tokens=[10, 30], tickets=[200, 600], item_chance=8, card_chance=0),
    'l4': dict(wait=3600, tokens=[20, 60], tickets=[400, 1200], item_chance=15, card_chance=0),
    'l5': dict(wait=7200, tokens=[40, 120], tickets=[800, 2400], item_chance=30, card_chance=5),
    'l6': dict(wait=14400, tokens=[80, 240], tickets=[1600, 4800], item_chance=60, card_chance=10),
}


def roll_contents(appearance):
    rule = RULES[appearance]
    def between(bounds):
        return bounds[0] + secrets.randbelow(bounds[1] - bounds[0] + 1)
    contents = dict(tokens=between(rule['tokens']), tickets=between(rule['tickets']), items=[], gold_pass_days=0)
    if secrets.randbelow(100) < rule['item_chance']:
        characters = [key for key, item in ITEMS.items() if item.get('character')]
        contents['items'] = [secrets.choice(characters)]
    if secrets.randbelow(100) < rule['card_chance']:
        contents['gold_pass_days'] = 3 if appearance == 'l6' else 1
    return contents


async def free_slot(db, uid):
    occupied = set((await db.scalars(select(RewardChest.slot).where(RewardChest.user_id == uid, RewardChest.slot.is_not(None)))).all())
    return next((i for i in range(4) if i not in occupied), None)


async def issue_reward(db, uid, tournament_id, source, kind, appearance, *, auto_slot=False, rank=None):
    """Caller holds User row lock; source uniqueness is the durable ledger."""
    existing = await db.scalar(select(RewardMessage).where(RewardMessage.user_id == uid, RewardMessage.source == source))
    if existing:
        return None
    now = utcnow()
    slot = await free_slot(db, uid) if auto_slot else None
    chest = RewardChest(user_id=uid, appearance=appearance, slot=slot, contents=roll_contents(appearance),
        unlock_at=now + timedelta(seconds=RULES[appearance]['wait']) if slot is not None else None)
    db.add(chest)
    await db.flush()
    message = RewardMessage(user_id=uid, source=source, tournament_id=tournament_id, chest_id=chest.id,
        kind=kind, rank=rank, claimed_at=now if slot is not None else None)
    db.add(message)
    await db.flush()
    return dict(message_id=message.id, chest_id=chest.id, appearance=appearance, slot=slot, kind=kind, rank=rank)


async def settle_for_user(db, uid):
    """Acquire all event locks before User, matching score ingestion lock order."""
    ranked = exists(select(RewardMessage.id).where(RewardMessage.user_id == uid, RewardMessage.source == 'rank:' + Tournament.id))
    completed = exists(select(RewardMessage.id).where(RewardMessage.user_id == uid, RewardMessage.source == 'complete:' + Tournament.id))
    events = (await db.scalars(select(Tournament).where(Tournament.definition['rewards'].as_boolean().is_(True),
        or_(~completed, and_(Tournament.ends_at < utcnow()-timedelta(minutes=5), ~ranked)),
        Tournament.id.in_(select(TournamentEntry.tournament_id).where(TournamentEntry.user_id == uid, TournamentEntry.score.is_not(None))),
        ).order_by(Tournament.id).limit(64).with_for_update())).all()
    if not events:
        return
    user = await db.scalar(select(User).where(User.id == uid).with_for_update())
    if not user or user.disabled:
        return
    from .tournaments import standings
    for event in events:
        board = await standings(db, event)
        me = next((p for p in board if p['uid'] == uid), None)
        if me is None:
            continue
        await issue_reward(db, uid, event.id, 'complete:' + event.id, 'completion', 'l1', auto_slot=True)
        if event.ends_at >= utcnow()-timedelta(minutes=5):
            continue
        rank = me['rank']
        appearance = 'l6' if rank == 1 else 'l5' if rank <= 3 else 'l4' if rank <= 10 else 'l2'
        await issue_reward(db, uid, event.id, 'rank:' + event.id, 'standings', appearance, rank=rank)


async def reward_worker(sessions):
    while True:
        await asyncio.sleep(30)
        try:
            async with sessions() as db:
                ranked = exists(select(RewardMessage.id).where(RewardMessage.user_id == TournamentEntry.user_id,
                    RewardMessage.source == 'rank:' + Tournament.id))
                completed = exists(select(RewardMessage.id).where(RewardMessage.user_id == TournamentEntry.user_id,
                    RewardMessage.source == 'complete:' + Tournament.id))
                uids = list((await db.scalars(select(TournamentEntry.user_id).join(Tournament).where(
                    Tournament.definition['rewards'].as_boolean().is_(True), TournamentEntry.score.is_not(None),
                    or_(~completed, and_(Tournament.ends_at < utcnow()-timedelta(minutes=5), ~ranked))).distinct().limit(100))).all())
            for uid in uids:
                async with sessions() as db:
                    await settle_for_user(db, uid)
                    await db.commit()
        except Exception:
            logging.exception('Community reward settlement failed; will retry')


def open_cost(chest, wallet):
    if chest.contents.get('fixed'):
        return 0
    if wallet.gold_pass_until and wallet.gold_pass_until > utcnow():
        return 0
    return max(0, math.ceil(((chest.unlock_at or utcnow()) - utcnow()).total_seconds() / 300))


async def reward_snapshot(db, user, wallet):
    chests = (await db.scalars(select(RewardChest).where(RewardChest.user_id == user.id, RewardChest.slot.is_not(None)).order_by(RewardChest.slot))).all()
    inbox = list((await db.scalars(select(RewardMessage.id).where(RewardMessage.user_id == user.id, RewardMessage.claimed_at.is_(None)))).all())
    return dict(chests=[dict(id=c.id, slot=c.slot, appearance=c.appearance, create_time=c.created_at.timestamp(),
        unlock_time=c.unlock_at.timestamp(), unlock_tokens=open_cost(c, wallet),
        fixed_contents=c.contents if c.contents.get('fixed') else None) for c in chests], inbox_count=len(inbox))


def mount_rewards(app, sessions, current_user, APIError):
    snapshot = app.state.account_snapshot

    @app.get('/v1/rewards/rules')
    async def rules():
        return dict(chests=RULES, source='community', compensation_tokens=50,
                    completion_once_per_event=True, slots=4, seconds_per_unlock_token=300)

    @app.get('/v1/chests')
    async def chests(identity=Depends(current_user)):
        state = await snapshot(identity[0].id)
        return dict(chests=state['chests'], state=state, rules=RULES)

    @app.get('/v1/inbox')
    async def inbox(identity=Depends(current_user)):
        state = await snapshot(identity[0].id)
        async with sessions() as db:
            rows = (await db.execute(select(RewardMessage, RewardChest, Tournament.game).join(RewardChest, RewardChest.id == RewardMessage.chest_id)
                .outerjoin(Tournament, Tournament.id == RewardMessage.tournament_id).where(RewardMessage.user_id == identity[0].id,
                RewardMessage.claimed_at.is_(None)).order_by(RewardMessage.created_at.desc()))).all()
            messages = [dict(id=m.id, kind=m.kind, rank=m.rank, appearance=chest.appearance, tournament_id=m.tournament_id,
                             game=game, created_at=m.created_at.timestamp(), fixed_contents=chest.contents if chest.contents.get('fixed') else None) for m, chest, game in rows]
        return dict(messages=messages, state=state)

    @app.post('/v1/inbox/{message_id}/claim')
    async def claim(message_id: UUID, identity=Depends(current_user)):
        uid = identity[0].id
        async with sessions() as db:
            await db.scalar(select(User).where(User.id == uid).with_for_update())
            message = await db.get(RewardMessage, str(message_id))
            if not message or message.user_id != uid:
                raise APIError('reward_unknown', 404)
            if message.claimed_at is None:
                slot = await free_slot(db, uid)
                if slot is None:
                    raise APIError('chest_dock_full', 409)
                chest = await db.get(RewardChest, message.chest_id)
                chest.slot = slot
                chest.unlock_at = utcnow() if chest.contents.get('fixed') else utcnow() + timedelta(seconds=RULES[chest.appearance]['wait'])
                message.claimed_at = utcnow()
                await db.commit()
        return dict(claimed=True, state=await snapshot(uid))

    @app.post('/v1/chests/{chest_id}/open')
    async def open_chest(chest_id: UUID, body: ChestOpen, identity=Depends(current_user)):
        uid = identity[0].id
        hashed = hashlib.sha256(json.dumps(dict(chest_id=str(chest_id), **body.model_dump(mode='json')), sort_keys=True).encode()).hexdigest()
        async with sessions() as db:
            await db.scalar(select(User).where(User.id == uid).with_for_update())
            previous = await db.get(Order, (uid, str(body.request_id)))
            if previous:
                if previous.request_hash != hashed:
                    raise APIError('idempotency_conflict', 409)
                receipt = previous.result
            else:
                chest = await db.get(RewardChest, str(chest_id))
                if not chest or chest.user_id != uid:
                    raise APIError('chest_unknown', 404)
                if chest.opened_at or chest.slot is None:
                    raise APIError('chest_already_opened', 409)
                wallet = await db.get(Wallet, uid)
                if wallet is None:
                    wallet = Wallet(user_id=uid, tokens=0, tickets=0)
                    db.add(wallet)
                cost = open_cost(chest, wallet)
                if body.expected_price != cost:
                    raise APIError('price_changed', 409)
                if wallet.tokens < cost:
                    raise APIError('insufficient_funds', 409)
                before = dict(tokens=wallet.tokens, tickets=wallet.tickets, purple_tickets=wallet.purple_tickets or 0)
                payouts = dict(chest.contents)
                purple = payouts.get('purple_tickets', 0)
                if (wallet.purple_tickets or 0) + purple > 1000000000:
                    raise APIError('wallet_limit', 409)
                wallet.purple_tickets = (wallet.purple_tickets or 0) + purple
                compensation = 0
                owned = set((await db.scalars(select(Ownership.item_id).where(Ownership.user_id == uid))).all())
                granted = []
                for sku in payouts['items']:
                    if all(grant in owned for grant in ITEMS[sku]['grants']):
                        compensation += 50
                    else:
                        for grant in ITEMS[sku]['grants']:
                            if grant not in owned:
                                db.add(Ownership(user_id=uid, item_id=grant))
                                owned.add(grant)
                        granted.append(sku)
                payouts.update(items=granted, compensation_tokens=compensation)
                wallet.tokens = min(1000000000, wallet.tokens-cost+payouts['tokens']+compensation)
                wallet.tickets = min(1000000000, wallet.tickets+payouts['tickets'])
                days = payouts.get('gold_pass_days', 0)
                if days:
                    wallet.gold_pass_until = max(wallet.gold_pass_until or utcnow(), utcnow()) + timedelta(days=days)
                chest.opened_at, chest.slot = utcnow(), None
                receipt = dict(order_id=str(body.request_id), item_id='chest:' + chest.id, currency='tokens', price=cost,
                    test_order=False, chest_id=chest.id, appearance=chest.appearance, payouts=payouts, before=before)
                db.add(Order(user_id=uid, request_id=str(body.request_id), kind='chest_open', request_hash=hashed, result=receipt))
                await db.commit()
        return receipt | dict(state=await snapshot(uid))
