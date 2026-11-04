"""Headless control agent. Only its worker imports websockets (not APK)."""
import json
import asyncio
import os
import threading
import time
import uuid
from pathlib import Path

import babase
import _baplus
from baplus._community_auth import TicketCache
from baplus._community_http import Transport


class CommunityServer:
    def __init__(self):
        self.tickets = TicketCache()
        self.instance_id = str(uuid.uuid4())
        self.server_id = os.environ['COMMUNITY_SERVER_ID']
        self.registered = False
        self.stopping = threading.Event()
        self._lock = threading.Lock()
        self._state = dict(name=os.environ.get('COMMUNITY_SERVER_NAME', 'Community'), players=0, devices=0,
                           capacity=8, public=False, ready=False)
        self._timer = None
        self._revision = 0
        self._thread = None
        config_root = Path(os.environ.get('COMMUNITY_CONFIG_DIR', str(Path.home() / '.local/share/bscn-community-headless')))
        config_root.mkdir(parents=True, exist_ok=True)
        self._outbox_path = config_root / ('match-outbox-' + self.server_id + '.json')
        try:
            self._outbox = json.loads(self._outbox_path.read_text()) if self._outbox_path.exists() else []
        except (OSError, ValueError):
            self._outbox = []
            if self._outbox_path.exists():
                os.replace(self._outbox_path, self._outbox_path.with_suffix('.corrupt-' + str(uuid.uuid4()) + '.json'))
            print('Community match outbox could not be read; original quarantined')

    def _persist_outbox(self):
        temporary = self._outbox_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self._outbox))
        os.replace(temporary, self._outbox_path)

    def record_match_start(self, activity, sessionplayers):
        """Take identities from native authenticated session players only."""
        players = {}
        for player in sessionplayers:
            try:
                uid = player.get_account_id()
                if uid and player.sessionteam is not None:
                    uuid.UUID(uid)
                    players[uid] = player.sessionteam.id
            except (ValueError, babase.NotFoundError):
                continue
        activity._community_ranked_start = dict(instance_id=self.instance_id, match_id=str(uuid.uuid4()), started_at=time.time(), players=players)

    def record_match_end(self, activity, results):
        import bascenev1 as bs
        start = getattr(activity, '_community_ranked_start', None)
        if not start or len(start['players']) < 2 or not isinstance(results, bs.GameResults):
            return
        placements, rank = {}, 1
        for group in results.winnergroups:
            teams = {team.id for team in group.teams}
            uids = [uid for uid, team in start['players'].items() if team in teams]
            if uids:
                for uid in uids:
                    placements[uid] = rank
                rank += len(uids)
        if len(placements) < 2 or time.time() - start['started_at'] < 1:
            return
        payload = {key: value for key, value in start.items() if key != 'players'}
        payload.update(ended_at=time.time(), players=[dict(uid=uid, placement=place) for uid, place in placements.items()])
        with self._lock:
            self._outbox.append(payload)
            self._persist_outbox()
        del activity._community_ranked_start

    def start(self):
        import bascenev1 as bs
        # Require authentication before creating any playable session.
        bs.set_authenticate_clients(True)
        self._timer = babase.AppTimer(1, self.snapshot, repeat=True)
        self._thread = threading.Thread(target=self._run, name='community-control', daemon=True)
        self._thread.start()
        babase.app.add_shutdown_task(self.wait_stopped())

    def snapshot(self):
        import bascenev1 as bs
        roster = bs.get_game_roster()
        values = _baplus.party_state()
        native = {} if values is None else dict(name=values[5], capacity=values[4], device_capacity=max(1, values[2] - 1))
        # Roster rows are devices; a device can contain multiple players.
        state = dict(name=native.get('name') or os.environ.get('COMMUNITY_SERVER_NAME', 'Community'),
                     players=sum(len(row.get('players', [])) for row in roster),
                     devices=sum(row.get('client_id') != -1 for row in roster),
                     capacity=native.get('capacity', -1) if native.get('capacity', -1) > 0 else int(os.environ.get('COMMUNITY_CAPACITY', '8')),
                     device_capacity=native.get('device_capacity', 8),
                     public=bs.get_public_party_enabled(),
                     ready=bs.get_foreground_host_session() is not None)
        with self._lock:
            if state != self._state:
                self._revision += 1
            self._state = state
        _baplus.party_dirty()

    def _logic(self, function):
        """Wait for real logic-thread installation before acknowledging."""
        done = threading.Event()
        result = []

        def apply():
            try:
                result.append(function())
            finally:
                done.set()
        babase.pushcall(apply, from_other_thread=True)
        if not done.wait(4):
            raise TimeoutError('Engine logic thread did not acknowledge')
        return result[0] if result else None

    def _run(self):
        from websockets.sync.client import connect
        from baplus._community_online import COMPATIBILITY
        while not self.stopping.is_set():
            try:
                transport = Transport()
                registered = transport.request('POST', '/v1/servers/register', COMPATIBILITY | dict(
                    server_id=self.server_id, instance_id=self.instance_id,
                    address=os.environ.get('COMMUNITY_SERVER_ADDRESS', '127.0.0.1'),
                    port=int(os.environ.get('COMMUNITY_GAME_PORT', '43210'))), os.environ['COMMUNITY_SERVER_KEY'])
                url = transport.url.replace('https://', 'wss://', 1).replace('http://', 'ws://', 1) + '/v1/servers/control'
                options = {'ssl': transport.ssl} if url.startswith('wss:') else {}
                with connect(url, additional_headers={'Authorization': 'Bearer ' + registered['control_token']}, open_timeout=7, **options) as ws:
                    welcome = json.loads(ws.recv(timeout=5))
                    cid = welcome['control_session_id']
                    self._logic(lambda: self.tickets.reset(self.instance_id, cid))
                    self.registered = True

                    def send(kind, payload, mid=None):
                        ws.send(json.dumps(dict(version=1, message_id=mid or str(uuid.uuid4()), type=kind,
                            server_id=self.server_id, instance_id=self.instance_id, control_session_id=cid, payload=payload)))
                    send('hello', {})
                    next_heartbeat = 0
                    next_report = 0
                    sent_revision = -1
                    while not self.stopping.is_set():
                        if time.monotonic() >= next_report:
                            with self._lock:
                                report = dict(self._outbox[0]) if self._outbox else None
                            if report:
                                try:
                                    transport.request('POST', f'/v1/servers/{self.server_id}/matches', report, os.environ['COMMUNITY_SERVER_KEY'])
                                except Exception as exc:
                                    code = getattr(exc, 'code', None)
                                    print('Community match upload pending:', code or type(exc).__name__)
                                    if code in ('match_time_invalid', 'match_players_invalid', 'match_player_unverified', 'instance_invalid'):
                                        # Preserve rejected evidence separately; don't endlessly
                                        # block later results behind a permanently invalid report.
                                        rejected = self._outbox_path.with_name('match-rejected-' + report['match_id'] + '.json')
                                        rejected.write_text(json.dumps(dict(error=code, report=report)))
                                        with self._lock:
                                            self._outbox.pop(0)
                                            self._persist_outbox()
                                else:
                                    with self._lock:
                                        self._outbox.pop(0)
                                        self._persist_outbox()
                            next_report = time.monotonic() + 5
                        with self._lock:
                            state, revision = dict(self._state), self._revision
                        if time.monotonic() >= next_heartbeat or revision != sent_revision:
                            send('heartbeat' if time.monotonic() >= next_heartbeat else 'party_state', state)
                            sent_revision = revision
                            next_heartbeat = time.monotonic() + 10
                        try:
                            msg = json.loads(ws.recv(timeout=1))
                        except TimeoutError:
                            continue
                        if (msg.get('server_id'), msg.get('instance_id'), msg.get('control_session_id')) != (self.server_id, self.instance_id, cid):
                            raise ValueError('Control generation mismatch')
                        payload = msg['payload']
                        if msg['type'] == 'heartbeat_ack':
                            expiry = time.time() + payload['lease_seconds']
                            self._logic(lambda: _baplus.set_instance(self.instance_id, expiry))
                        elif msg['type'] == 'prepare_join':
                            installed = self._logic(lambda: self.tickets.prepare(self.instance_id, cid, payload))
                            send('join_prepared' if installed else 'join_rejected', {}, msg['message_id'])
                        elif msg['type'] == 'ticket_cancel':
                            self._logic(lambda: self.tickets.entries.pop(payload['ticket_index'], None))
            except Exception as exc:
                # Never log request headers, exception bodies or credentials.
                print('Community control unavailable:', type(exc).__name__)
            finally:
                self.registered = False
                try:
                    self._logic(lambda: (self.tickets.reset(), _baplus.set_instance('', 0)))
                except TimeoutError:
                    pass
            self.stopping.wait(3)

    def stop(self):
        self.stopping.set()
        self.tickets.reset()
        _baplus.set_instance('', 0)

    async def wait_stopped(self):
        self.stop()
        while self._thread and self._thread.is_alive():
            await asyncio.sleep(.05)
