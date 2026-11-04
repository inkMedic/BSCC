"""Community client subsystem. Network work never runs on the logic thread."""
import concurrent.futures
import copy
import os
import threading
import time
import uuid
import logging
import urllib.parse
from dataclasses import dataclass

import babase
import _baplus
from baplus._community import CommunityPlusAppSubsystem, OfflineAccounts
from baplus._community_http import Transport, CommunityError

COMPATIBILITY = dict(engine_build=23079, scene_protocol=57, community_protocol=1, assets='23079')


@dataclass(frozen=True)
class CommunityAccount:
    """A verified community identity, distinct from an official cloud handle."""
    accountid: str
    # The engine's tag is a visible account name, without the account icon.
    tag: str
    nickname: str
    account_tag: str


class Accounts(OfflineAccounts):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def have_primary_credentials(self):
        return self.owner.user is not None

    def auth_request(self, global_app_instance_id, optional=False):
        join = self.owner.join_result
        if (join and join['instance_id'] == global_app_instance_id
                and join['expires_at'] > time.time() and self.owner.user):
            return True, join['ticket'], None
        # A direct IP/favorite route cannot bypass community join preparation.
        return False, '请从社区服务器列表重新申请入房。', None


class CommunityOnlinePlus(CommunityPlusAppSubsystem):
    community_online = True
    community_offline = False

    def __init__(self):
        super().__init__()
        self.accounts = Accounts(self)
        self.user = None
        self.join_result = None
        self.server = None
        self.state = 'signed_out'
        self._generation = 0
        self._account_state_num = 0
        self._join_generation = 0
        self._access = None
        self._refresh = None
        self._expires = 0
        self._local_playlists = []
        self._profile_sync = []
        self._tournament_entries = {}
        self.economy = None
        self.economy_received = 0.0
        self._economy_timer = None
        self._session_lock = threading.RLock()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix='community')

    def _submit(self, work, callback, generation=None):
        generation = self._generation if generation is None else generation
        future = self._executor.submit(work)

        def done(result):
            try:
                value = result.result()
            except Exception as exc:
                value = exc

            def apply():
                if self._generation == generation:
                    callback(value)
            babase.pushcall(apply, from_other_thread=not babase.in_logic_thread())
        future.add_done_callback(done)

    def _notify_initial(self):
        if not self._initial_notification_sent:
            self._initial_notification_sent = True
            babase.pushcall(babase.app.on_initial_sign_in_complete)

    def on_app_loading(self):
        if 'Player Profiles' not in babase.app.config:
            babase.app.config['Player Profiles'] = {}
            babase.app.config.commit()
        if os.environ.get('COMMUNITY_SERVER_KEY'):
            from baplus._community_server import CommunityServer
            self.server = CommunityServer()
            self._notify_initial()
            return
        if not os.environ.get('COMMUNITY_API_URL'):
            self._notify_initial()
            return
        self.state = 'restoring'

        generation = self._generation
        def restore():
            saved = _baplus.secure_refresh() if os.environ.get('BA_COMMUNITY_ANDROID') == '1' else None
            if not saved:
                return None
            result = Transport().request('POST', '/v1/auth/refresh', {'refresh_token': saved})
            if self._generation != generation:
                Transport().request('POST', '/v1/auth/logout', {}, result['access_token'])
                return None
            _baplus.secure_refresh(result['refresh_token'])
            return result

        def restored(result):
            if isinstance(result, dict):
                self._accept(result)
            else:
                self.state = 'signed_out'
            self._notify_initial()
        self._submit(restore, restored)
        # Network/DNS failure cannot indefinitely stall local startup.
        babase.apptimer(8, self._notify_initial)

    def on_app_mode_activated(self):
        super().on_app_mode_activated()
        from baclassic import ClassicAppMode
        if self.server and self.server._timer is None and isinstance(babase.app.mode, ClassicAppMode):
            self.server.start()

    def on_app_running(self):
        self._economy_timer = babase.AppTimer(30, self.refresh_economy, repeat=True)

    def refresh_economy(self):
        if self.user:
            self.request('GET', '/v1/economy', None, lambda _: None, True)

    def query_store(self, callback):
        import bacommon.cloud
        def work():
            catalog = self.request_sync('GET', '/v1/store', authenticated=False)
            state = self.request_sync('GET', '/v1/economy')
            return catalog, state
        def complete(value):
            if isinstance(value, Exception):
                callback(value)
                return
            catalog, state = value
            self._ui_store_catalog = {item['id']: item for item in catalog['items']}
            self._ui_test_purchases = catalog['test_purchases_enabled']
            callback(bacommon.cloud.StoreQueryResponse(
                result=bacommon.cloud.StoreQueryResponse.Result.SUCCESS,
                tokens=state['wallet']['tokens'], gold_pass=state['wallet']['gold_pass'],
                available_purchases=[bacommon.cloud.StoreQueryResponse.Purchase(item['id'])
                    for item in catalog['items'] if item.get('test_only') and catalog['test_purchases_enabled']],
                token_info_url=''))
        self._submit(work, complete)

    def get_price(self, item):
        catalog = getattr(self, '_ui_store_catalog', {})
        product = catalog.get(item)
        return '免费（测试）' if product and product.get('test_only') and getattr(self, '_ui_test_purchases', False) else None

    def supports_purchases(self):
        return True

    def purchase(self, item):
        from bauiv1lib.confirm import ConfirmWindow
        if self.get_price(item) is None:
            return
        attempt = str(uuid.uuid4())
        def purchased(value):
            babase.screenmessage(str(value) if isinstance(value, Exception) else '购买成功',
                                 color=(1, .5, 0) if isinstance(value, Exception) else (0, 1, 0))
        ConfirmWindow('免费测试购买，不产生真实扣款。', action=lambda: self.request('POST', '/v1/store/purchase',
            dict(request_id=attempt, item_id=item, currency='test', expected_price=0), purchased, True))

    def power_ranking_query(self, callback, season=None):
        from baplus._community_uicompat import league_data
        path = '/v1/league' + ('' if season is None else '?season=' + urllib.parse.quote(season))
        uid = self.user['uid'] if self.user else None
        def received(value):
            callback(None if isinstance(value, Exception) else league_data(value, uid))
        self.request('GET', path, None, received, True)

    def tournament_query(self, callback, args):
        body = dict(tournament_ids=args.get('tournamentIDs'), num_scores=args.get('numScores', 1))
        self.request('POST', '/v1/tournaments/query', body,
                     lambda value: callback(None if isinstance(value, Exception) else value), True)

    def enter_tournament(self, tournament_id, request_id, callback):
        def entered(value):
            if not isinstance(value, Exception):
                self._tournament_entries[tournament_id] = value
            callback(value)
        self.request('POST', '/v1/tournaments/' + urllib.parse.quote(tournament_id, safe='') + '/entries',
                     dict(request_id=request_id), entered, True)

    def submit_score(self, game, config, name, score, callback, **kwargs):
        import bascenev1 as bs
        tournament_id = kwargs.get('tournament_id')
        session = bs.get_foreground_host_session()
        entry_id = getattr(session, 'community_tournament_entry_id', None)
        if (not entry_id or score is None or not session.submit_score
                or session.tournament_id != tournament_id):
            babase.pushcall(lambda: callback(None))
            return
        actual_game = kwargs.get('campaign', '') + ':' + kwargs.get('level', '')
        def submitted(value):
            if isinstance(value, Exception):
                babase.screenmessage(str(value), color=(1, .5, 0))
                callback(None)
            else:
                value['link'] = Transport().url + value['link']
                if value.get('rewards'):
                    self.refresh_economy()
                    babase.screenmessage('获得宝箱，已放入宝箱栏或收件箱。', color=(0, 1, 0))
                callback(value)
        self.request('POST', '/v1/tournaments/' + urllib.parse.quote(tournament_id, safe='') + '/scores',
            dict(entry_id=entry_id, game=actual_game, score=score, score_type=kwargs.get('score_type', 'points')), submitted, True)

    def apply_economy(self, state):
        """Commit authoritative balances, entitlements and profile flags on logic."""
        if not self.user:
            return
        self.economy = state
        self.economy_received = time.monotonic()
        self.user['player_profiles'] = copy.deepcopy(state['player_profiles'])
        config = babase.app.config
        remote = state['player_profiles']
        profiles = copy.deepcopy(config.get('Player Profiles', {}))
        profiles.update(remote)
        if profiles != config.get('Player Profiles'):
            config['Player Profiles'] = profiles
            config.setdefault('Community Account Profiles', {})[self.user['uid']] = copy.deepcopy(profiles)
            config.commit()
        classic = getattr(babase.app, 'classic', None)
        if classic is None:
            return
        wallet, league = state['wallet'], state['league']
        classic.tokens, classic.tickets = wallet['tokens'], wallet['tickets']
        classic.purple_tickets = wallet.get('purple_tickets', 0)
        classic.gold_pass = wallet['gold_pass']
        classic.purchases = frozenset(state['purchases'])
        classic.remove_ads = 'upgrades.pro' in classic.purchases
        import _baclassic
        points = league['points']
        values = dict(tickets=wallet['tickets'], tokens=wallet['tokens'], gold_pass=wallet['gold_pass'],
            league_type=league['tier'][0].lower() if league['games'] else '', league_number=1 if league['games'] else -1,
            league_rank=league.get('rank') or -1, achievements_percent_text='', level_text=str(points // 100 + 1),
            xp_text=f'{points % 100}/100', inbox_count=state.get('inbox_count', 0), inbox_count_is_max=False,
            inbox_announce_text='有待领取的奖励' if state.get('inbox_count') else '', store_style='')
        for i in range(4):
            values[f'chest_{i}_appearance'] = ''
            for key in ('create_time', 'unlock_time', 'ad_allow_time'):
                values[f'chest_{i}_{key}'] = -1.0
            values[f'chest_{i}_unlock_tokens'] = -1
        for chest in state.get('chests', []):
            i = chest['slot']
            values[f'chest_{i}_appearance'] = chest['appearance']
            values[f'chest_{i}_create_time'] = float(chest['create_time'])
            values[f'chest_{i}_unlock_time'] = float(chest['unlock_time'])
            values[f'chest_{i}_unlock_tokens'] = chest['unlock_tokens']
        classic.chest_dock_full = len(state.get('chests', [])) == 4
        _baclassic.set_root_ui_account_values(**values)
        _baclassic.set_have_live_account_values(True)

    def _accept(self, result):
        self._access = result['access_token']
        self._refresh = result['refresh_token']
        self._expires = time.monotonic() + result['expires_in']
        self.user = result['user']
        self.accounts.primary = CommunityAccount(
            accountid=self.user['uid'], tag=self.user['nickname'],
            nickname=self.user['nickname'], account_tag=self.user['account_tag'])
        config = babase.app.config
        local = config.setdefault('Community Local Profiles', copy.deepcopy(config.get('Player Profiles', {})))
        cached = config.setdefault('Community Account Profiles', {}).get(self.user['uid'], {})
        profiles = copy.deepcopy(local)
        profiles.update(cached)
        profiles.update(self.user.get('player_profiles', {}))
        config['Player Profiles'] = profiles
        config['Community Profile Owner'] = self.user['uid']
        config.commit()
        self.state = 'signed_in'
        self._account_state_num += 1
        # Official AccountV2Handle semantics are deliberately not impersonated.
        _baplus.set_identity(self.user['uid'], self.user['nickname'])
        import _babase
        _babase.set_account_sign_in_state(True, self.user['nickname'])
        for call in self.accounts.on_primary_account_changed_callbacks.getcalls():
            try:
                call(self.accounts.primary)
            except Exception:
                logging.exception('Community account observer failed')
        self.refresh_economy()

    def authenticate(self, login, password, nickname, callback):
        # Switching accounts starts by revoking/clearing the previous identity.
        if self.user is not None:
            self.logout()
        self._generation += 1
        self.join_result = None
        generation = self._generation
        self.state = 'signing_in'
        body = dict(login=login, password=password)
        if nickname is not None:
            body['nickname'] = nickname

        def work():
            result = Transport().request('POST', '/v1/auth/register' if nickname is not None else '/v1/auth/login', body)
            with self._session_lock:
                if generation != self._generation:
                    Transport().request('POST', '/v1/auth/logout', {}, result['access_token'])
                    raise CommunityError('登录已取消')
                if os.environ.get('BA_COMMUNITY_ANDROID') == '1':
                    _baplus.secure_refresh(result['refresh_token'])
            return result

        def complete(result):
            if isinstance(result, dict):
                self._accept(result)
            else:
                self.state = 'signed_in' if self.user else 'signed_out'
            callback(result)
        self._submit(work, complete, generation)

    def request(self, method, path, body, callback, authenticated=False):
        generation = self._generation

        def work():
            return self.request_sync(method, path, body, authenticated, generation)
        def complete(result):
            if isinstance(result, CommunityError) and result.code in (
                'login_expired', 'credentials_invalid', 'account_disabled', 'refresh_reused'
            ):
                self.logout()
                self.state = 'expired'
            callback(result)
        self._submit(work, complete, generation)

    def request_sync(self, method, path, body=None, authenticated=True, generation=None):
        """For DocUI's background request workers; never call on logic thread."""
        if babase.in_logic_thread():
            raise RuntimeError('Community network request cannot run on logic thread')
        generation = self._generation if generation is None else generation
        transport = Transport()
        with self._session_lock:
            if generation != self._generation:
                raise CommunityError('账号已切换')
            if authenticated and self._expires <= time.monotonic() + 15:
                if not self._refresh:
                    raise CommunityError('请先登录社区账号')
                result = transport.request('POST', '/v1/auth/refresh', {'refresh_token': self._refresh})
                if generation != self._generation:
                    transport.request('POST', '/v1/auth/logout', {}, result['access_token'])
                    raise CommunityError('账号已切换')
                self._access, self._refresh = result['access_token'], result['refresh_token']
                self._expires = time.monotonic() + result['expires_in']
                if os.environ.get('BA_COMMUNITY_ANDROID') == '1':
                    _baplus.secure_refresh(self._refresh)
            access = self._access if authenticated else None
        result = transport.request(method, path, body, access)
        state = result.get('state') if isinstance(result, dict) else None
        if path == '/v1/economy':
            state = result
        if state is not None:
            def apply():
                if self._generation == generation:
                    self.apply_economy(state)
            babase.pushcall(apply, from_other_thread=True)
        return result

    def prepare_join(self, server, callback):
        self.cancel_join()
        generation = self._join_generation
        attempt = str(uuid.uuid4())

        def complete(result):
            if generation != self._join_generation:
                return
            if isinstance(result, dict):
                self.join_result = result
            callback(result)
        self.request('POST', '/v1/servers/' + server['server_id'] + '/join',
                     COMPATIBILITY | dict(instance_id=server['instance_id'], join_attempt_id=attempt), complete, True)

    def cancel_join(self):
        self._join_generation += 1
        self.join_result = None

    def logout(self):
        # Clear logical identity immediately; revoke captured session off-thread.
        self._generation += 1
        self.cancel_join()
        access, self._access = self._access, None
        self._profile_sync = []
        self.economy, self.economy_received = None, 0.0
        self._tournament_entries = {}
        self._refresh, self._expires = None, 0
        self.user = self.join_result = None
        self.accounts.primary = None
        config = babase.app.config
        if config.get('Community Profile Owner'):
            config['Player Profiles'] = copy.deepcopy(config.get('Community Local Profiles', {}))
            config['Community Profile Owner'] = None
            config.commit()
        self.state = 'signed_out'
        _baplus.set_identity('', '')
        self._account_state_num += 1
        import _babase
        _babase.set_account_sign_in_state(False)
        # Clear durable credentials before returning, even if the app exits
        # before a queued network revocation can run. This performs no network I/O.
        if os.environ.get('BA_COMMUNITY_ANDROID') == '1':
            _baplus.secure_refresh(None)
        for call in self.accounts.on_primary_account_changed_callbacks.getcalls():
            call(None)

        def revoke():
            if access:
                Transport().request('POST', '/v1/auth/logout', {}, access)
        self._submit(revoke, lambda _: None)

    def get_v1_account_state(self):
        return 'signed_in' if self.user else 'signed_out'

    def get_v1_account_name(self):
        return self.user['nickname'] if self.user else ''

    def get_v1_account_display_string(self, full=True):
        if not self.user:
            return ''
        icon = babase.charstr(babase.SpecialChar.GOOGLE_PLAY_GAMES_LOGO) if full else ''
        return icon + self.get_v1_account_name()

    def get_v1_account_public_login_id(self):
        return self.user['uid'] if self.user else None

    def sign_out_v1(self, v2_embedded=False):
        if not v2_embedded:
            self.logout()

    def get_v1_account_state_num(self):
        return self._account_state_num

    def get_v1_account_type(self):
        return 'V2' if self.user else 'Invalid'

    def add_v1_account_transaction(self, transaction, callback=None):
        if transaction.get('type') in ('ADD_PLAYER_PROFILE', 'REMOVE_PLAYER_PROFILE'):
            if transaction.get('profile', {}).get('global') and self.user and self.user.get('player_profiles', {}).get(transaction.get('name'), {}).get('global'):
                self._local_profile_transactions.append((copy.deepcopy(transaction), callback))
            else:
                super().add_v1_account_transaction(transaction, callback)
            if self.user:
                self._profile_sync.append(copy.deepcopy(transaction))
            return
        if transaction.get('type') == 'ADD_PLAYLIST':
            if (transaction.get('playlistType') not in ('Free-for-All', 'Team Tournament')
                    or not isinstance(transaction.get('playlistName'), str)
                    or not isinstance(transaction.get('playlist'), list)):
                raise ValueError('Invalid local server playlist')
            self._local_playlists.append((copy.deepcopy(transaction), callback))
            return
        super().add_v1_account_transaction(transaction, callback)

    def run_v1_account_transactions(self):
        playlists, self._local_playlists = self._local_playlists, []
        for transaction, callback in playlists:
            key = transaction['playlistType'] + ' Playlists'
            babase.app.config.setdefault(key, {})[transaction['playlistName']] = transaction['playlist']
        if playlists:
            babase.app.config.commit()
        for _, callback in playlists:
            if callback is not None:
                babase.pushcall(lambda callback=callback: callback({}))
        super().run_v1_account_transactions()
        config = babase.app.config
        if self.user:
            config.setdefault('Community Account Profiles', {})[self.user['uid']] = copy.deepcopy(config.get('Player Profiles', {}))
        else:
            config['Community Local Profiles'] = copy.deepcopy(config.get('Player Profiles', {}))
        config.commit()
        pending, self._profile_sync = self._profile_sync, []
        def synced(result):
            if isinstance(result, Exception):
                babase.screenmessage('档案已保存在本机，账号同步失败：' + str(result), color=(1, .7, 0))
        for transaction in pending:
            path = '/v1/me/profiles/' + urllib.parse.quote(transaction['name'], safe='')
            remove = transaction['type'] == 'REMOVE_PLAYER_PROFILE'
            self.request('DELETE' if remove else 'PUT', path, None if remove else transaction['profile'], synced, True)

    def have_outstanding_v1_account_transactions(self):
        return bool(self._local_playlists) or super().have_outstanding_v1_account_transactions()

    def on_app_shutdown(self):
        self._generation += 1
        if self.server:
            self.server.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
