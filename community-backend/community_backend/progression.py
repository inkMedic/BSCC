"""Transactional community shop, profile names and trusted seasonal results."""
import hashlib
import json
import unicodedata
from datetime import datetime, timezone, timedelta
from uuid import UUID

from fastapi import Depends, Query, Request
from sqlalchemy import select, func, or_, and_
from sqlalchemy.exc import IntegrityError
from .models import User, Wallet, Ownership, Order, GlobalProfile, Match, LeagueStats, Instance, utcnow
from .schemas import Purchase, UpgradeProfile, MatchReport
from .catalog import ITEMS, CATALOG_VERSION

PACKS = {
    'tokens1': ('金币 ×50', 'tokens', 50), 'tokens2': ('金币 ×500', 'tokens', 500),
    'tokens3': ('金币 ×1200', 'tokens', 1200), 'tokens4': ('金币 ×2600', 'tokens', 2600),
    'tickets1': ('点券 ×300', 'tickets', 300), 'tickets2': ('点券 ×1000', 'tickets', 1000),
    'tickets3': ('点券 ×5000', 'tickets', 5000), 'tickets4': ('点券 ×20000', 'tickets', 20000),
    'gold_pass': ('金卡 · 30天', 'gold_pass', 30),
}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def season_now():
    return utcnow().strftime('%Y-%m')


def tier(points):
    return 'Diamond' if points >= 600 else 'Gold' if points >= 300 else 'Silver' if points >= 100 else 'Bronze'


def normalized_name(name):
    value = unicodedata.normalize('NFKC', name).strip().casefold()
    if not 2 <= len(value) <= 32 or value.startswith('__') or any(unicodedata.category(c).startswith('C') for c in value):
        raise ValueError('invalid global profile name')
    return value


def mount_progression(app, sessions, redis, cfg, current_user, server_auth, APIError):
    async def locked_wallet(db, uid):
        # A user row exists before a wallet does: this serializes first creation
        # as well as all debits, credits and idempotency checks for that user.
        user = await db.scalar(select(User).where(User.id == uid).with_for_update())
        wallet = await db.get(Wallet, uid)
        if wallet is None:
            wallet = Wallet(user_id=uid, tokens=0, tickets=0)
            db.add(wallet)
            await db.flush()
        return user, wallet

    def wallet_data(wallet):
        until = wallet.gold_pass_until
        return dict(tokens=wallet.tokens, tickets=wallet.tickets, purple_tickets=wallet.purple_tickets,
            gold_pass=until is not None and until > utcnow(), gold_pass_until=None if until is None else until.timestamp())

    async def snapshot_db(db, user, wallet):
        from .rewards import reward_snapshot
        owned = list((await db.scalars(select(Ownership.item_id).where(Ownership.user_id == user.id))).all())
        stats = await db.get(LeagueStats, (user.id, season_now()))
        rank = None
        if stats:
            ahead = or_(LeagueStats.points > stats.points,
                and_(LeagueStats.points == stats.points, LeagueStats.wins > stats.wins),
                and_(LeagueStats.points == stats.points, LeagueStats.wins == stats.wins, LeagueStats.user_id < user.id))
            rank = 1 + (await db.scalar(select(func.count()).select_from(LeagueStats).join(User, User.id == LeagueStats.user_id)
                .where(LeagueStats.season == season_now(), User.disabled.is_(False), ahead)))
        return dict(wallet=wallet_data(wallet), purchases=sorted(owned), player_profiles=user.player_profiles,
            league=dict(season=season_now(), points=stats.points if stats else 0, games=stats.games if stats else 0,
                        wins=stats.wins if stats else 0, tier=tier(stats.points if stats else 0), rank=rank),
            test_purchases_enabled=cfg.test_purchases_enabled, catalog_version=CATALOG_VERSION,
            **(await reward_snapshot(db, user, wallet)))

    async def snapshot(uid):
        from .rewards import settle_for_user
        async with sessions() as db:
            await settle_for_user(db, uid)
            user, wallet = await locked_wallet(db, uid)
            result = await snapshot_db(db, user, wallet)
            await db.commit()
            return result

    async def previous(db, uid, request_id, request_hash):
        order = await db.get(Order, (uid, str(request_id)))
        if order and order.request_hash != request_hash:
            raise APIError('idempotency_conflict', 409)
        return order.result if order else None

    @app.get('/v1/economy')
    async def economy(identity=Depends(current_user)):
        return await snapshot(identity[0].id)

    @app.get('/v1/store')
    async def catalog():
        packs = [dict(id=sku, name=name, category='currency' if currency != 'gold_pass' else 'cards',
                      currency='test', price=0, grants=[], amount=amount, resource=currency, test_only=True)
                 for sku, (name, currency, amount) in PACKS.items()]
        return {'version': CATALOG_VERSION, 'test_purchases_enabled': cfg.test_purchases_enabled,
                'items': list(ITEMS.values()) + packs}

    @app.post('/v1/store/purchase')
    async def purchase(body: Purchase, identity=Depends(current_user)):
        uid = identity[0].id
        request_hash = fingerprint(body.model_dump(mode='json'))
        async with sessions() as db:
            user, wallet = await locked_wallet(db, uid)
            cached = await previous(db, uid, body.request_id, request_hash)
            if cached is not None:
                return cached | {'state': await snapshot_db(db, user, wallet)}
            item = ITEMS.get(body.item_id)
            if body.item_id in PACKS:
                if not cfg.test_purchases_enabled:
                    raise APIError('test_purchases_disabled', 403)
                if body.currency != 'test' or body.expected_price != 0:
                    raise APIError('price_changed', 409)
                _, resource, amount = PACKS[body.item_id]
                if resource == 'gold_pass':
                    wallet.gold_pass_until = max(wallet.gold_pass_until or utcnow(), utcnow()) + timedelta(days=amount)
                else:
                    if getattr(wallet, resource) + amount > 1000000000:
                        raise APIError('wallet_limit', 409)
                    setattr(wallet, resource, getattr(wallet, resource) + amount)
                price, currency, grants = 0, 'test', []
            elif item:
                owned = set((await db.scalars(select(Ownership.item_id).where(Ownership.user_id == uid))).all())
                if all(grant in owned for grant in item['grants']):
                    raise APIError('already_owned', 409)
                if body.currency == 'gold_pass' and wallet_data(wallet)['gold_pass']:
                    price, currency = 0, 'gold_pass'
                else:
                    price, currency = item['price'], item['currency']
                if body.expected_price != price or body.currency != currency:
                    raise APIError('price_changed', 409)
                if currency in ('tokens', 'tickets'):
                    if getattr(wallet, currency) < price:
                        raise APIError('insufficient_funds', 409)
                    setattr(wallet, currency, getattr(wallet, currency) - price)
                grants = item['grants']
                for grant in grants:
                    if grant not in owned:
                        db.add(Ownership(user_id=uid, item_id=grant))
                await db.flush()
            else:
                raise APIError('item_unknown', 404)
            receipt = dict(order_id=str(body.request_id), item_id=body.item_id, currency=currency,
                           price=price, grants=grants, test_order=currency == 'test')
            db.add(Order(user_id=uid, request_id=str(body.request_id), kind='purchase', request_hash=request_hash, result=receipt))
            await db.flush()
            result = receipt | {'state': await snapshot_db(db, user, wallet)}
            await db.commit()
            return result

    @app.get('/v1/orders')
    async def orders(identity=Depends(current_user), limit: int = Query(30, ge=1, le=100)):
        async with sessions() as db:
            rows = (await db.scalars(select(Order).where(Order.user_id == identity[0].id).order_by(Order.created_at.desc()).limit(limit))).all()
        return {'orders': [o.result | {'created_at': o.created_at.timestamp()} for o in rows]}

    @app.get('/v1/profiles/availability')
    async def availability(name: str, identity=Depends(current_user)):
        try:
            normalized = normalized_name(name)
        except ValueError:
            raise APIError('profile_name_invalid', 422) from None
        async with sessions() as db:
            owner = await db.get(GlobalProfile, normalized)
            _, wallet = await locked_wallet(db, identity[0].id)
            cost = 0 if wallet_data(wallet)['gold_pass'] else cfg.profile_upgrade_tickets
            await db.commit()
        return dict(available=owner is None or (owner.user_id == identity[0].id and owner.profile_name == name),
                    already_upgraded=owner is not None and owner.user_id == identity[0].id and owner.profile_name == name,
                    ticket_cost=cost, name=name)

    @app.post('/v1/profiles/upgrade')
    async def upgrade(body: UpgradeProfile, identity=Depends(current_user)):
        try:
            normalized = normalized_name(body.name)
        except ValueError:
            raise APIError('profile_name_invalid', 422) from None
        uid = identity[0].id
        request_hash = fingerprint({'upgrade': body.model_dump(mode='json')})
        try:
            async with sessions() as db:
                user, wallet = await locked_wallet(db, uid)
                cached = await previous(db, uid, body.request_id, request_hash)
                if cached is not None:
                    return cached | {'state': await snapshot_db(db, user, wallet)}
                stored = user.player_profiles.get(body.name)
                if not stored:
                    raise APIError('profile_missing', 404)
                owner = await db.get(GlobalProfile, normalized)
                if owner:
                    raise APIError('already_upgraded' if owner.user_id == uid and owner.profile_name == body.name else 'profile_name_taken', 409)
                cost = 0 if wallet_data(wallet)['gold_pass'] else cfg.profile_upgrade_tickets
                if cost != body.expected_price:
                    raise APIError('price_changed', 409)
                if wallet.tickets < cost:
                    raise APIError('insufficient_funds', 409)
                db.add(GlobalProfile(normalized_name=normalized, user_id=uid, profile_name=body.name))
                # Acquire unique name before charging; a conflicting concurrent
                # transaction rolls back both reservation and wallet change.
                await db.flush()
                wallet.tickets -= cost
                profiles = dict(user.player_profiles)
                profiles[body.name] = dict(stored, **{'global': True})
                user.player_profiles = profiles
                receipt = dict(order_id=str(body.request_id), name=body.name, currency='tickets', price=cost, upgraded=True, test_order=False)
                db.add(Order(user_id=uid, request_id=str(body.request_id), kind='profile_upgrade', request_hash=request_hash, result=receipt))
                await db.flush()
                result = receipt | {'state': await snapshot_db(db, user, wallet)}
                await db.commit()
                return result
        except IntegrityError:
            raise APIError('profile_name_taken', 409) from None

    @app.get('/v1/league')
    async def league(season: str | None = Query(None, pattern=r'^\d{4}-(0[1-9]|1[0-2])$'), identity=Depends(current_user)):
        season = season or season_now()
        async with sessions() as db:
            rows = (await db.execute(select(LeagueStats, User.nickname).join(User, User.id == LeagueStats.user_id)
                .where(LeagueStats.season == season, User.disabled.is_(False))
                .order_by(LeagueStats.points.desc(), LeagueStats.wins.desc(), LeagueStats.user_id))).all()
            seasons = list((await db.scalars(select(LeagueStats.season).distinct().order_by(LeagueStats.season.desc()))).all())
        leaderboard = [dict(uid=s.user_id, nickname=nickname, rank=i+1, points=s.points, wins=s.wins, games=s.games, tier=tier(s.points)) for i, (s, nickname) in enumerate(rows)]
        me = next((p for p in leaderboard if p['uid'] == identity[0].id), None)
        year, month = map(int, season.split('-'))
        if year < 1 or year > 9998:
            raise APIError('season_invalid', 422)
        end = datetime(year + (month == 12), 1 if month == 12 else month + 1, 1, tzinfo=timezone.utc)
        return dict(season=season, ends_at=end.timestamp(), seasons=sorted(set(seasons + [season_now()]), reverse=True),
            leaderboard=leaderboard[:100], me=me, participants=len(leaderboard),
            rules=dict(participation_points=10, winner_bonus=20, minimum_accounts=2, source='registered_servers'))

    @app.post('/v1/servers/{server_id}/matches')
    async def match_report(server_id: UUID, body: MatchReport, request: Request):
        auth = request.headers.get('authorization', '')
        if not auth.startswith('Bearer '):
            raise APIError('server_credentials_invalid', 401)
        await server_auth(auth[7:], str(server_id))
        now = utcnow().timestamp()
        if not (body.started_at <= body.ended_at <= now + 30 and 1 <= body.ended_at - body.started_at <= 86400 and now - body.ended_at <= 86400):
            raise APIError('match_time_invalid', 422)
        uids = [str(p.uid) for p in body.players]
        if len(uids) != len(set(uids)) or min(p.placement for p in body.players) != 1 or max(p.placement for p in body.players) > len(uids):
            raise APIError('match_players_invalid', 422)
        iid, mid = str(body.instance_id), str(body.match_id)
        report_hash = fingerprint(body.model_dump(mode='json'))
        async with sessions() as db:
            instance = await db.get(Instance, iid)
            if not instance or instance.server_id != str(server_id):
                raise APIError('instance_invalid', 403)
            # Instance row serializes duplicate result ingestion across all
            # participants. User locks follow in stable UID order.
            await db.scalar(select(Instance).where(Instance.id == iid).with_for_update())
            previous_match = await db.get(Match, (iid, mid))
            if previous_match:
                if previous_match.report_hash != report_hash:
                    raise APIError('idempotency_conflict', 409)
                return previous_match.result
            for uid in uids:
                if not await redis.exists(f'participant:{iid}:{uid}'):
                    raise APIError('match_player_unverified', 403)
            ranked = sorted(body.players, key=lambda p: str(p.uid))
            season = datetime.fromtimestamp(body.ended_at, timezone.utc).strftime('%Y-%m')
            rewards = []
            for player in ranked:
                uid = str(player.uid)
                user, wallet = await locked_wallet(db, uid)
                if not user or user.disabled:
                    raise APIError('account_disabled', 403)
                stats = await db.get(LeagueStats, (uid, season))
                if stats is None:
                    stats = LeagueStats(user_id=uid, season=season, points=0, games=0, wins=0)
                    db.add(stats)
                won = player.placement == 1
                points = 10 + (20 if won else 0)
                tokens, tickets = (10, 30) if won else (3, 10)
                wallet.tokens = min(1000000000, wallet.tokens + tokens)
                wallet.tickets = min(1000000000, wallet.tickets + tickets)
                stats.points += points
                stats.games += 1
                stats.wins += int(won)
                rewards.append(dict(uid=uid, points=points, tokens=tokens, tickets=tickets))
            result = dict(match_id=mid, season=season, rewards=rewards)
            db.add(Match(instance_id=iid, match_id=mid, report_hash=report_hash, result=result))
            await db.commit()
        return result

    return snapshot
