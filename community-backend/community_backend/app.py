"""Single-worker service. Redis is authoritative for all temporary state."""
import asyncio
import contextlib
import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import time
import uuid
from contextlib import asynccontextmanager

from argon2.exceptions import VerificationError
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .models import User, Server, Instance, GlobalProfile, Ownership
from .schemas import Login, Register, Refresh, ServerRegister, Join, Control, PartyState, PlayerProfile
from .security import digest, token, passwords

log = logging.getLogger('community')


class APIError(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status


async def udp_probe(address, port):
    """Ballistica SIMPLE_PING (11) / SIMPLE_PONG (12), on game UDP port."""
    family = socket.AF_INET6 if ':' in address else socket.AF_INET
    with socket.socket(family, socket.SOCK_DGRAM) as sock:
        sock.setblocking(False)
        loop = asyncio.get_running_loop()
        try:
            await loop.sock_connect(sock, (address, port))
            await loop.sock_sendall(sock, b'\x0b')
            return await asyncio.wait_for(loop.sock_recv(sock, 32), 1) == b'\x0c'
        except (TimeoutError, OSError):
            return False


def create_app(settings=None):
    cfg = settings or Settings()
    engine = create_async_engine(cfg.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    redis = Redis.from_url(cfg.redis_url, decode_responses=True)
    controls = {}
    pending = {}

    @asynccontextmanager
    async def lifespan(app):
        from .rewards import reward_worker
        rewards_task = asyncio.create_task(reward_worker(sessions))
        yield
        rewards_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await rewards_task
        for control in list(controls.values()):
            await control['ws'].close(code=1012)
        await redis.aclose()
        await engine.dispose()

    app = FastAPI(title='Ballistica Community', version='1.0', lifespan=lifespan)
    app.state.sessions, app.state.redis = sessions, redis

    @app.exception_handler(APIError)
    async def error(request, exc):
        return JSONResponse({'error': {'code': exc.code}, 'request_id': request.state.request_id}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic's default errors include submitted password/token values.
        fields = [{'field': '.'.join(map(str, err['loc'])), 'type': err['type']} for err in exc.errors()]
        return JSONResponse({'error': {'code': 'request_invalid', 'fields': fields}, 'request_id': request.state.request_id}, status_code=422)

    @app.middleware('http')
    async def request_id(request, next_handler):
        request.state.request_id = str(uuid.uuid4())
        response = await next_handler(request)
        response.headers['X-Request-ID'] = request.state.request_id
        log.info('request_id=%s method=%s path=%s status=%s', request.state.request_id, request.method, request.url.path, response.status_code)
        return response

    async def rate_limit(request, action, maximum):
        address = request.client.host if request.client else 'unknown'
        key = f'rate:{action}:{digest(address)}:{int(time.time()) // 60}'
        # INCR + expiry in one transaction: no immortal keys on process failure.
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(key).expire(key, 65)
            count, _ = await pipe.execute()
        if count > maximum:
            raise APIError('rate_limited', 429)

    def bearer(request):
        auth = request.headers.get('authorization', '')
        if not auth.startswith('Bearer ') or len(auth) > 200:
            raise APIError('credentials_invalid', 401)
        return auth[7:]

    async def current_user(request: Request):
        value = await redis.get('access:' + digest(bearer(request)))
        if not value:
            raise APIError('login_expired', 401)
        uid, sid = json.loads(value)
        if not await redis.exists('session:' + sid):
            raise APIError('login_expired', 401)
        async with sessions() as db:
            user = await db.get(User, uid)
        if not user or user.disabled:
            raise APIError('account_disabled', 403)
        return user, sid

    def profile(user):
        return {'uid': user.id, 'account_tag': 'c_' + user.id.replace('-', ''), 'nickname': user.nickname, 'player_profiles': user.player_profiles}

    async def issue(user):
        access, refresh, sid = token(), token(), token()
        rh = digest(refresh)
        async with redis.pipeline(transaction=True) as pipe:
            pipe.set('session:' + sid, json.dumps({'uid': user.id, 'refresh': rh, 'access': digest(access)}), ex=cfg.refresh_seconds)
            pipe.set('access:' + digest(access), json.dumps([user.id, sid]), ex=cfg.access_seconds)
            pipe.set('refresh:' + rh, sid, ex=cfg.refresh_seconds)
            await pipe.execute()
        return {'access_token': access, 'refresh_token': refresh, 'expires_in': cfg.access_seconds, 'user': profile(user)}

    @app.get('/health/live')
    async def live():
        return {'status': 'alive'}

    @app.get('/health/ready')
    async def ready():
        try:
            async with sessions() as db:
                await db.execute(text('SELECT 1'))
            await redis.ping()
        except Exception:
            raise APIError('dependencies_unavailable', 503) from None
        return {'status': 'ready'}

    @app.post('/v1/auth/register', status_code=201)
    async def register(body: Register, request: Request):
        await rate_limit(request, 'register', 5)
        pw = await run_in_threadpool(passwords.hash, body.password)
        async with sessions() as db:
            user = User(login=body.login, nickname=body.nickname, password_hash=pw)
            db.add(user)
            try:
                await db.commit()
            except IntegrityError:
                raise APIError('login_exists', 409) from None
        return await issue(user)

    # Equal-cost missing-account verification avoids an inexpensive user oracle.
    dummy_hash = passwords.hash(token())

    @app.post('/v1/auth/login')
    async def login(body: Login, request: Request):
        await rate_limit(request, 'login', 20)
        async with sessions() as db:
            user = await db.scalar(select(User).where(User.login == body.login))
        try:
            await run_in_threadpool(passwords.verify, user.password_hash if user else dummy_hash, body.password)
        except VerificationError:
            raise APIError('credentials_invalid', 401) from None
        if not user:
            raise APIError('credentials_invalid', 401)
        if user.disabled:
            raise APIError('account_disabled', 403)
        return await issue(user)

    @app.post('/v1/auth/refresh')
    async def refresh(body: Refresh):
        old = digest(body.refresh_token)
        sid = await redis.get('refresh:' + old)
        if not sid:
            raise APIError('credentials_invalid', 401)
        value = await redis.get('session:' + sid)
        if not value:
            raise APIError('login_expired', 401)
        state = json.loads(value)
        async with sessions() as db:
            user = await db.get(User, state['uid'])
        if not user or user.disabled:
            raise APIError('account_disabled', 403)
        access, new_refresh = token(), token()
        new_hash = digest(new_refresh)
        state.update(refresh=new_hash, access=digest(access))
        # Compare + consume + rotate is indivisible, including access revocation.
        result = await redis.eval('''
            local raw = redis.call('GET', KEYS[1])
            if not raw then return 0 end
            local s = cjson.decode(raw)
            if s.refresh ~= ARGV[1] then return 0 end
            redis.call('DEL', 'access:' .. s.access, KEYS[2])
            redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[5])
            redis.call('SET', KEYS[3], ARGV[3], 'EX', ARGV[4])
            redis.call('SET', KEYS[4], ARGV[6], 'EX', ARGV[5])
            return 1
        ''', 4, 'session:' + sid, 'refresh:' + old, 'access:' + digest(access), 'refresh:' + new_hash,
            old, json.dumps(state), json.dumps([user.id, sid]), cfg.access_seconds, cfg.refresh_seconds, sid)
        if not result:
            raise APIError('refresh_reused', 401)
        return {'access_token': access, 'refresh_token': new_refresh, 'expires_in': cfg.access_seconds, 'user': profile(user)}

    @app.post('/v1/auth/logout')
    async def logout(identity=Depends(current_user)):
        _, sid = identity
        await redis.eval('''
            local raw = redis.call('GET', KEYS[1])
            if raw then
                local s = cjson.decode(raw)
                redis.call('DEL', 'access:' .. s.access, 'refresh:' .. s.refresh, KEYS[1])
            end
            return 1
        ''', 1, 'session:' + sid)
        return {'status': 'signed_out'}

    @app.get('/v1/me')
    async def me(identity=Depends(current_user)):
        return profile(identity[0])

    def profile_name(name):
        if not name.strip() or len(name) > 64 or (name.startswith('__') and name != '__account__'):
            raise APIError('profile_name_invalid', 422)

    @app.put('/v1/me/profiles/{name}')
    async def save_profile(name: str, body: PlayerProfile, identity=Depends(current_user)):
        profile_name(name)
        async with sessions() as db:
            user = await db.scalar(select(User).where(User.id == identity[0].id).with_for_update())
            profiles = dict(user.player_profiles)
            existing = profiles.get(name, {})
            if body.global_ != bool(existing.get('global', False)):
                raise APIError('profile_upgrade_required', 403)
            from .catalog import ITEMS
            required = next((sku for sku, item in ITEMS.items() if item.get('character') == body.character), None)
            if required and not await db.get(Ownership, (user.id, required)):
                raise APIError('item_required', 403)
            if name not in profiles and len(profiles) >= 64:
                raise APIError('profile_limit', 409)
            profiles[name] = body.model_dump(mode='json', by_alias=True)
            user.player_profiles = profiles
            await db.commit()
        return {'name': name, 'profile': profiles[name]}

    @app.delete('/v1/me/profiles/{name}')
    async def delete_profile(name: str, identity=Depends(current_user)):
        profile_name(name)
        async with sessions() as db:
            user = await db.scalar(select(User).where(User.id == identity[0].id).with_for_update())
            profiles = dict(user.player_profiles)
            profiles.pop(name, None)
            global_profile = await db.scalar(select(GlobalProfile).where(GlobalProfile.user_id == user.id, GlobalProfile.profile_name == name))
            if global_profile:
                await db.delete(global_profile)
            user.player_profiles = profiles
            await db.commit()
        return {'status': 'deleted'}

    async def server_auth(raw, server_id):
        async with sessions() as db:
            server = await db.get(Server, server_id)
        if not server or server.revoked or not hmac.compare_digest(server.key_hash, digest(raw)):
            raise APIError('server_credentials_invalid', 401)
        return server

    @app.post('/v1/servers/register')
    async def server_register(body: ServerRegister, request: Request):
        sid, iid = str(body.server_id), str(body.instance_id)
        server = await server_auth(bearer(request), sid)
        try:
            address = ipaddress.ip_address(body.address)
            allowed = any(address in ipaddress.ip_network(net.strip()) for net in cfg.allowed_server_networks.split(','))
        except ValueError:
            allowed = False
        if not allowed:
            raise APIError('server_address_forbidden', 403)
        async with sessions() as db:
            instance = await db.get(Instance, iid)
            newest = await db.scalar(select(Instance).where(Instance.server_id == sid).order_by(Instance.created_at.desc()).limit(1))
            if instance and newest and newest.id != iid:
                raise APIError('instance_stale', 409)
            if instance and (instance.server_id != sid or instance.address != str(address) or instance.port != body.port):
                raise APIError('instance_conflict', 409)
            if not instance:
                db.add(Instance(id=iid, server_id=sid, address=str(address), port=body.port))
                await db.commit()
        control_token = token()
        data = body.model_dump(mode='json') | {'name': server.name}
        await redis.set('server-session:' + digest(control_token), json.dumps(data), ex=60)
        return {'server_id': sid, 'instance_id': iid, 'control_token': control_token, 'expires_in': 60}

    async def online(sid):
        control = controls.get(sid)
        if not control:
            return None
        raw = await redis.get('lease:' + sid)
        if not raw:
            return None
        data = json.loads(raw)
        if data['control_session_id'] != control['cid']:
            return None
        async with sessions() as db:
            server = await db.get(Server, sid)
            newest = await db.scalar(select(Instance).where(Instance.server_id == sid).order_by(Instance.created_at.desc()).limit(1))
        if not server or server.revoked:
            return None
        if not newest or newest.id != data['instance_id']:
            return None
        if not (data.get('ready') and data.get('public') and data.get('udp_reachable')):
            return None
        return data

    @app.get('/v1/servers')
    async def directory(engine_build: int = 23079, scene_protocol: int = 57, community_protocol: int = 1, assets: str = '23079'):
        result = []
        for sid in list(controls):
            data = await online(sid)
            if data and data['players'] < data['capacity'] and data['devices'] < data['device_capacity'] and all(data[k] == v for k, v in dict(engine_build=engine_build, scene_protocol=scene_protocol, community_protocol=community_protocol, assets=assets).items()):
                result.append(data)
        return {'servers': result, 'version': 1}

    @app.get('/v1/servers/{server_id}')
    async def detail(server_id: uuid.UUID):
        data = await online(str(server_id))
        if not data:
            raise APIError('server_offline', 409)
        return data

    def message(control, kind, payload, mid=None):
        return {'version': 1, 'message_id': mid or str(uuid.uuid4()), 'type': kind, 'server_id': control['sid'], 'instance_id': control['iid'], 'control_session_id': control['cid'], 'payload': payload}

    async def send(control, kind, payload, mid=None):
        async with control['send_lock']:
            await control['ws'].send_json(message(control, kind, payload, mid))

    @app.post('/v1/servers/{server_id}/join')
    async def join(server_id: uuid.UUID, body: Join, identity=Depends(current_user)):
        user, login_sid = identity
        sid, iid, attempt = str(server_id), str(body.instance_id), str(body.join_attempt_id)
        data = await online(sid)
        if not data or data['instance_id'] != iid:
            raise APIError('server_offline', 409)
        if any(data[key] != value for key, value in body.model_dump().items() if key in ('engine_build', 'scene_protocol', 'community_protocol', 'assets')):
            raise APIError('version_incompatible', 409)
        if data['players'] >= data['capacity'] or data['devices'] >= data['device_capacity']:
            raise APIError('room_full', 409)
        control = controls[sid]
        # Secret-derived per-attempt ticket permits idempotent responses without
        # storing a reusable raw bearer credential in Redis.
        attempt_key = 'attempt:' + digest(json.dumps([user.id, login_sid, sid, iid, attempt, control['cid']]))
        attempt_raw = await redis.eval('''
            local value = redis.call('GET', KEYS[1])
            if value then return value end
            redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
            return ARGV[1]
        ''', 1, attempt_key, json.dumps({'nonce': token(), 'expires_at': time.time() + cfg.join_seconds}), cfg.join_seconds)
        attempt_state = json.loads(attempt_raw)
        material = json.dumps([user.id, login_sid, sid, iid, attempt, control['cid'], attempt_state['nonce']])
        ticket = hmac.new(cfg.secret.encode(), material.encode(), hashlib.sha256).hexdigest()
        index = digest(ticket)
        key = 'join:' + index
        cached = await redis.get(key)
        if cached and json.loads(cached).get('prepared'):
            return json.loads(cached)['response'] | {'ticket': ticket}
        if not await redis.set(key + ':lock', '1', nx=True, ex=7):
            # Concurrent duplicate callers observe the original preparation.
            for _ in range(100):
                await asyncio.sleep(.05)
                cached = await redis.get(key)
                if cached:
                    return json.loads(cached)['response'] | {'ticket': ticket}
            raise APIError('auth_prepare_timeout', 504)
        event = asyncio.get_running_loop().create_future()
        mid = str(uuid.uuid4())
        pending[mid] = (control['cid'], event)
        expiry = attempt_state['expires_at']
        async with sessions() as db:
            purchases = list((await db.scalars(select(Ownership.item_id).where(Ownership.user_id == user.id))).all())
        payload = {'ticket_index': index, 'uid': user.id, 'account_tag': profile(user)['account_tag'], 'nickname': user.nickname, 'profiles': user.player_profiles, 'purchases': purchases, 'expires_at': expiry, 'join_attempt_id': attempt}
        try:
            await send(control, 'prepare_join', payload, mid)
            accepted = await asyncio.wait_for(event, cfg.prepare_seconds)
            if not accepted or controls.get(sid) is not control or not await online(sid):
                raise APIError('auth_prepare_rejected', 409)
            response = {'server_id': sid, 'instance_id': iid, 'join_attempt_id': attempt, 'address': data['address'], 'port': data['port'], 'expires_at': expiry}
            await redis.set(key, json.dumps({'prepared': True, 'response': response}), ex=max(1, int(expiry - time.time())))
            await redis.set(f'participant:{iid}:{user.id}', '1', ex=86400)
            log.info('join_prepared uid=%s server_id=%s instance_id=%s join_attempt_id=%s', user.id, sid, iid, attempt)
            return response | {'ticket': ticket}
        except (TimeoutError, WebSocketDisconnect, RuntimeError):
            raise APIError('auth_prepare_timeout', 504) from None
        finally:
            pending.pop(mid, None)
            await redis.delete(key + ':lock')
            if not await redis.exists(key):
                with contextlib.suppress(Exception):
                    await send(control, 'ticket_cancel', {'ticket_index': index})

    async def remove_control(control):
        if controls.get(control['sid']) is control:
            controls.pop(control['sid'], None)
            # Fence old connection cleanup against a replacement lease.
            await redis.eval('''
                local v = redis.call('GET', KEYS[1])
                if v and cjson.decode(v).control_session_id == ARGV[1] then redis.call('DEL', KEYS[1]) end
                return 1
            ''', 1, 'lease:' + control['sid'], control['cid'])
        for cid, future in list(pending.values()):
            if cid == control['cid'] and not future.done():
                future.set_result(False)

    @app.post('/v1/servers/{server_id}/unregister')
    async def unregister(server_id: uuid.UUID, request: Request):
        await server_auth(bearer(request), str(server_id))
        control = controls.get(str(server_id))
        if control:
            await remove_control(control)
            await control['ws'].close(code=1000)
        return {'status': 'offline'}

    @app.websocket('/v1/servers/control')
    async def control_channel(ws: WebSocket):
        raw = ws.headers.get('authorization', '').removeprefix('Bearer ')
        value = await redis.getdel('server-session:' + digest(raw))
        if not value:
            await ws.close(code=4401)
            return
        data = json.loads(value)
        sid, iid = data['server_id'], data['instance_id']
        async with sessions() as db:
            registered = await db.get(Server, sid)
            newest = await db.scalar(select(Instance).where(Instance.server_id == sid).order_by(Instance.created_at.desc()).limit(1))
        if not registered or registered.revoked or not newest or newest.id != iid:
            await ws.close(code=4401)
            return
        await ws.accept()
        old = controls.get(sid)
        control = {'sid': sid, 'iid': iid, 'cid': str(uuid.uuid4()), 'ws': ws, 'send_lock': asyncio.Lock()}
        controls[sid] = control
        if old:
            await old['ws'].close(code=4001)
        data.update(control_session_id=control['cid'], ready=False, public=False, udp_reachable=False, players=0, devices=0, capacity=1)
        # Never inherit an older connection's lease while awaiting first state.
        await redis.delete('lease:' + sid)
        greeted = False
        try:
            await send(control, 'welcome', {'heartbeat_seconds': 10, 'lease_seconds': cfg.lease_seconds})
            while controls.get(sid) is control:
                msg = Control.model_validate(await asyncio.wait_for(ws.receive_json(), cfg.lease_seconds))
                if (str(msg.server_id), str(msg.instance_id), str(msg.control_session_id)) != (sid, iid, control['cid']):
                    await ws.close(code=4409)
                    break
                if msg.type == 'hello':
                    greeted = True
                    continue
                if not greeted:
                    await ws.close(code=4400)
                    break
                if msg.type in ('heartbeat', 'party_state'):
                    state = PartyState.model_validate(msg.payload)
                    reachable = await udp_probe(data['address'], data['port'])
                    if controls.get(sid) is not control:
                        break
                    data.update(state.model_dump(), udp_reachable=reachable, updated_at=time.time())
                    await redis.set('lease:' + sid, json.dumps(data), ex=cfg.lease_seconds)
                    await send(control, 'heartbeat_ack', {'lease_seconds': cfg.lease_seconds, 'udp_reachable': reachable})
                elif msg.type in ('join_prepared', 'join_rejected'):
                    entry = pending.get(str(msg.message_id))
                    if entry and entry[0] == control['cid'] and not entry[1].done():
                        entry[1].set_result(msg.type == 'join_prepared')
        except (WebSocketDisconnect, TimeoutError, ValueError):
            pass
        finally:
            await remove_control(control)
            with contextlib.suppress(Exception):
                await ws.close()

    from .progression import mount_progression
    app.state.account_snapshot = mount_progression(app, sessions, redis, cfg, current_user, server_auth, APIError)
    from .tournaments import mount_tournaments
    mount_tournaments(app, sessions, current_user, APIError, cfg)
    from .rewards import mount_rewards
    mount_rewards(app, sessions, current_user, APIError)
    return app
