"""Explicit engine/transport fixtures for worker scheduling and cancellation."""
import importlib.util
import queue
import sys
import threading
import time
import types
from pathlib import Path
from unittest.mock import patch


def test_client_single_flight_and_logout_cancellation():
    calls, logic = [], queue.Queue()
    identities, sign_in_states = [], []
    entered, release = threading.Event(), threading.Event()

    class Callbacks:
        def getcalls(self):
            return []

    class Accounts:
        def __init__(self):
            self.primary = None
            self.on_primary_account_changed_callbacks = Callbacks()

    class Plus:
        def __init__(self):
            self._initial_notification_sent = False

    class Transport:
        def request(self, method, path, body=None, token=None):
            calls.append(path)
            if path == '/v1/auth/refresh':
                entered.set()
                assert release.wait(3)
                return dict(access_token='new_access', refresh_token='new_refresh', expires_in=900)
            return {'ok': True}

    class Error(Exception):
        pass

    modules = {}
    for name, attrs in {
        'babase': dict(pushcall=lambda call, **kw: logic.put(call), in_logic_thread=lambda: False,
                       charstr=lambda value: '<google-play>',
                       SpecialChar=types.SimpleNamespace(GOOGLE_PLAY_GAMES_LOGO='google-play'),
                       app=types.SimpleNamespace(config=type('Config', (dict,), {'commit': lambda self: None})())),
        '_babase': dict(set_account_sign_in_state=lambda *args: sign_in_states.append(args)),
        '_baplus': dict(set_identity=lambda uid, name: identities.append((uid, name))),
        'baplus._community': dict(CommunityPlusAppSubsystem=Plus, OfflineAccounts=Accounts),
        'baplus._community_http': dict(Transport=Transport, CommunityError=Error),
    }.items():
        modules[name] = types.ModuleType(name)
        modules[name].__dict__.update(attrs)
    path = Path(__file__).resolve().parents[2] / 'src/assets/ba_data/python/baplus/_community_online.py'
    modules['baplus'] = types.ModuleType('baplus')
    modules['baplus'].__path__ = [str(path.parent)]
    with patch.dict(sys.modules, modules), patch.dict('os.environ', {'BA_COMMUNITY_ANDROID': '0'}):
        spec = importlib.util.spec_from_file_location('community_online_fixture', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        plus = module.CommunityOnlinePlus()
        plus.refresh_economy = lambda: None
        observed = []
        plus.accounts.on_primary_account_changed_callbacks.getcalls = lambda: [observed.append]
        plus._accept(dict(access_token='verified_access', refresh_token='verified_refresh', expires_in=900,
            user=dict(uid='verified_uid', account_tag='c_verified', nickname='社区玩家', player_profiles={})))
        assert plus.accounts.primary.accountid == 'verified_uid'
        assert plus.accounts.primary.tag == '社区玩家'
        assert plus.accounts.primary.account_tag == 'c_verified'
        assert identities == [('verified_uid', '社区玩家')]
        assert sign_in_states == [(True, '社区玩家')]
        assert plus.get_v1_account_name() == '社区玩家'
        assert plus.get_v1_account_display_string() == '<google-play>社区玩家'
        assert plus.get_v1_account_display_string(full=False) == '社区玩家'
        assert plus.get_v1_account_public_login_id() == 'verified_uid'
        assert observed == [plus.accounts.primary]
        assert plus.state == 'signed_in'
        plus._refresh = 'refresh'
        plus._expires = 0
        results = []
        try:
            plus.request('GET', '/v1/me', None, results.append, True)
            assert entered.wait(2)
            plus.request('GET', '/v1/me', None, results.append, True)
            release.set()
            for _ in range(2):
                logic.get(timeout=2)()
            assert calls.count('/v1/auth/refresh') == 1
            assert results == [{'ok': True}, {'ok': True}]
            # A blocked network refresh must never block logic-thread logout.
            release.clear()
            entered.clear()
            plus._expires = 0
            plus.request('GET', '/v1/me', None, results.append, True)
            assert entered.wait(2)
            start = time.monotonic()
            plus.logout()
            assert time.monotonic() - start < .1
            release.set()
            plus._executor.shutdown(wait=True)
            while not logic.empty():
                logic.get()()
            assert len(results) == 2  # Old generation result was discarded.
            assert plus.user is None and plus._access is None
            assert plus.accounts.primary is None and observed[-1] is None
            assert identities[-1] == ('', '')
            assert sign_in_states[-1] == (False,)
            assert plus.get_v1_account_display_string() == ''
        finally:
            release.set()
            plus._executor.shutdown(wait=True)
