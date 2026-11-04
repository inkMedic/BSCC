"""Account form flows with an explicit lightweight engine widget fixture."""

import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import patch

import pytest


@pytest.fixture
def account_ui():
    class Widget:
        def __init__(self, **attrs):
            self.attrs = attrs
            self.children = []
            self.alive = True
            if attrs.get('parent'):
                attrs['parent'].children.append(self)

        def __bool__(self):
            return self.alive

        def delete(self):
            self.alive = False
            for child in self.children:
                child.delete()

    def widget(**attrs):
        if 'query' in attrs:
            return attrs['query'].attrs['text']
        if 'edit' in attrs:
            target = attrs.pop('edit')
            assert target.alive
            target.attrs.update(attrs)
            return target
        return Widget(**attrs)

    class MainWindow:
        def __init__(self, root_widget, **kwargs):
            self._root_widget = root_widget
            self.control = True

        def main_window_has_control(self):
            return self.control

        def main_window_back(self):
            self.control = False

    class Plus:
        state = 'signed_out'
        user = None

        def __init__(self):
            self.calls = []

        def authenticate(self, login, password, nickname, callback):
            self.calls.append((login, password, nickname))
            self.callback = callback
            self.state = 'signing_in'

        def finish(self, error=None):
            self.state = 'signed_out' if error else 'signed_in'
            self.user = None if error else dict(uid='u1', nickname='玩家', account_tag='c_test')
            self.callback(error or {'user': self.user})

        def logout(self):
            self.state, self.user = 'signed_out', None

    plus = Plus()
    ui = types.ModuleType('bauiv1')
    ui.MainWindow = MainWindow
    ui.UIScale = types.SimpleNamespace(SMALL='small')
    ui.app = types.SimpleNamespace(plus=plus, ui_v1=types.SimpleNamespace(uiscale='small'))
    ui.containerwidget = ui.textwidget = ui.buttonwidget = widget
    ui.AppTimer = lambda *args, **kwargs: None
    ui.WeakCall = lambda call: call
    confirmations = []
    confirm = types.ModuleType('bauiv1lib.confirm')
    confirm.ConfirmWindow = lambda *args, **kwargs: confirmations.append(kwargs)
    path = Path(__file__).resolve().parents[1] / 'src/assets/ba_data/python/bauiv1lib/community_account.py'
    with patch.dict(sys.modules, {'bauiv1': ui, 'bauiv1lib.confirm': confirm}):
        spec = importlib.util.spec_from_file_location('account_ui_fixture', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        window = module.CommunityAccountWindow()
        yield window, plus, confirmations


def fill(window, **values):
    for name, value in values.items():
        window._fields[name].attrs['text'] = value


def test_login_validation_retry_and_duplicate_submit(account_ui):
    window, plus, _ = account_ui
    assert set(window._fields) == {'login', 'password'}
    fill(window, login='中文账号', password='1234567890')
    window._auth()
    assert not plus.calls
    assert '登录名须为' in window._status.attrs['text']
    fill(window, login=' Player_1 ', password='short')
    window._auth()
    assert not plus.calls
    fill(window, password=' 1234567890 ')
    window._auth()
    window._auth()
    window._switch_mode()
    window._update()
    assert plus.calls == [('Player_1', ' 1234567890 ', None)]
    assert window._busy and not window._register
    assert window._fields['password'].attrs['text'] == ''
    assert not window._submit.attrs['enabled']
    plus.finish(ValueError('登录名或密码错误，请重新输入。'))
    assert not window._busy
    assert window._fields['login'].attrs['text'] == 'Player_1'
    assert '登录名或密码错误' in window._status.attrs['text']
    fill(window, password='1234567890')
    window._auth()
    assert len(plus.calls) == 2


def test_registration_confirmation_and_account_logout(account_ui):
    window, plus, confirmations = account_ui
    window._switch_mode()
    fill(window, login='new_player', password='1234567890', confirm='different', nickname='玩家')
    window._auth()
    assert not plus.calls
    assert '不一致' in window._status.attrs['text']
    fill(window, confirm='1234567890', nickname='   ')
    window._auth()
    assert not plus.calls
    fill(window, nickname=' 玩家 ')
    window._auth()
    assert plus.calls == [('new_player', '1234567890', '玩家')]
    assert window._fields['confirm'].attrs['text'] == ''
    plus.finish()
    assert not window._fields
    window._auth()
    assert len(plus.calls) == 1
    window._confirm_logout()
    assert plus.user is not None
    confirmations[-1]['action']()
    assert plus.user is None
    assert not window._register
    assert set(window._fields) == {'login', 'password'}
    assert window._status.attrs['text'] == '已退出登录。'


def test_restore_expiration_and_navigation_during_login(account_ui):
    window, plus, _ = account_ui
    plus.state = 'restoring'
    window._update()
    assert not window._fields
    window._auth()
    assert not plus.calls
    plus.state = 'expired'
    window._update()
    assert '已失效' in window._status.attrs['text']
    fill(window, login='player', password='1234567890')
    window._auth()
    window.control = False
    plus.finish()
    assert not window._busy
    window.control = True
    window._update()
    assert not window._fields
    plus.logout()
    window._update()
    assert set(window._fields) == {'login', 'password'}


def test_mode_switch_clears_passwords(account_ui):
    window, _, _ = account_ui
    fill(window, login='player', password='1234567890')
    window._switch_mode()
    assert window._fields['login'].attrs['text'] == 'player'
    assert window._fields['password'].attrs['text'] == ''
    fill(window, nickname='玩家', password='1234567890', confirm='1234567890')
    window._switch_mode()
    window._switch_mode()
    assert window._fields['nickname'].attrs['text'] == '玩家'
    assert window._fields['password'].attrs['text'] == ''
    assert window._fields['confirm'].attrs['text'] == ''


def test_external_logout_cancels_pending_form(account_ui):
    window, plus, _ = account_ui
    fill(window, login='player', password='1234567890')
    window._auth()
    plus.logout()
    window._update()
    assert not window._busy
    assert window._fields['password'].attrs['text'] == ''
    fill(window, password='1234567890')
    window._auth()
    assert len(plus.calls) == 2
