"""Community account sign-in, registration and current identity."""

import re
import weakref

import bauiv1 as bui


class CommunityAccountWindow(bui.MainWindow):
    def __init__(self, transition='in_right', origin_widget=None):
        uiscale = bui.app.ui_v1.uiscale
        root = bui.containerwidget(
            size=(680, 560),
            scale=1.3 if uiscale is bui.UIScale.SMALL else 1.0,
            toolbar_visibility='menu_minimal',
        )
        super().__init__(root_widget=root, transition=transition,
                         origin_widget=origin_widget)
        self.plus = bui.app.plus
        self._busy = False
        self._register = False
        self._body = None
        self._fields = {}
        self._login = ''
        self._nickname = ''
        back = bui.buttonwidget(
            parent=root, position=(30, 490), size=(90, 42), label='返回',
            autoselect=True, on_activate_call=self.main_window_back,
        )
        bui.containerwidget(edit=root, cancel_button=back)
        bui.textwidget(parent=root, position=(160, 495), size=(360, 35),
                       text='社区账号', h_align='center', scale=1.2)
        bui.textwidget(
            parent=root, position=(40, 457), size=(600, 26),
            text='登录社区账号，使用在线服务与账号档案。',
            scale=.72, color=(.75, .8, .9), h_align='center', maxwidth=590,
        )
        self._render()
        self._timer = bui.AppTimer(.3, bui.WeakCall(self._update), repeat=True)

    def _signature(self):
        return self.plus.state, self.plus.user['uid'] if self.plus.user else None

    def _update(self):
        if not self._root_widget or not self.main_window_has_control():
            return
        if (self._signature() != self._shown_state
                or (self._busy and self.plus.state != 'signing_in')):
            if self._busy and self.plus.state == 'signing_in':
                return
            self._busy = False
            self._render()

    def _text(self, text, y, *, color=(.8, .83, .9), scale=.75):
        return bui.textwidget(
            parent=self._body, position=(40, y), size=(600, 28), text=text,
            scale=scale, color=color, h_align='center', maxwidth=580,
        )

    def _render(self, message=None):
        if self._body:
            self._body.delete()
        self._body = bui.containerwidget(
            parent=self._root_widget, size=(680, 450), background=False,
        )
        self._fields = {}
        self._shown_state = self._signature()
        user = self.plus.user
        self._status = self._text('', 405)
        if user:
            self._text('账号已登录', 350, color=(.55, 1, .65), scale=1.1)
            self._text(user['nickname'], 292, color=(1, 1, 1), scale=1.2)
            self._text('账号标识：' + user['account_tag'], 246)
            self._text('在线服务将使用当前账号身份。', 185)
            self._text('如需切换账号，请先退出当前账号。', 153)
            logout = bui.buttonwidget(
                parent=self._body, position=(220, 77), size=(240, 50),
                label='退出登录', autoselect=True,
                on_activate_call=self._confirm_logout,
            )
            bui.containerwidget(edit=self._root_widget, start_button=logout)
        elif self.plus.state in ('restoring', 'signing_in'):
            self._text('正在恢复登录状态…' if self.plus.state == 'restoring'
                       else '正在验证账号，请稍候…', 265, scale=.95)
        else:
            self._text('创建社区账号' if self._register else '登录社区账号',
                       375, color=(1, 1, 1), scale=1.0)
            fields = [('login', '登录名', 310, 32),
                      ('password', '密码', 225, 128)]
            if self._register:
                fields = [('login', '登录名', 295, 32),
                          ('password', '密码', 230, 128),
                          ('confirm', '确认密码', 165, 128),
                          ('nickname', '玩家昵称', 100, 40)]
            for key, label, y, limit in fields:
                bui.textwidget(
                    parent=self._body, position=(48, y + 5), size=(150, 32),
                    text=label, scale=.85, color=(.85, .88, .95),
                )
                self._fields[key] = bui.textwidget(
                    parent=self._body, position=(205, y), size=(425, 42),
                    editable=True,
                    text=self._login if key == 'login' else
                        self._nickname if key == 'nickname' else '',
                    description=label, max_chars=limit,
                    password=key in ('password', 'confirm'),
                    on_return_press_call=self._auth,
                )
            if not self._register:
                self._text('登录名为 3–32 位英文字母、数字或下划线。', 279, scale=.65)
                self._text('密码为 10–128 位字符，区分大小写。', 194, scale=.65)
                self._text('请妥善保管密码；当前暂不支持自助找回。', 145, scale=.67)
            else:
                self._text('登录名 3–32 位字母、数字或下划线；密码 10–128 位。',
                           340, scale=.62)
            self._submit = bui.buttonwidget(
                parent=self._body, position=(55, 40), size=(280, 48),
                label='注册并登录' if self._register else '登录',
                autoselect=True, on_activate_call=self._auth,
            )
            self._switch = bui.buttonwidget(
                parent=self._body, position=(355, 40), size=(270, 48),
                label='已有账号？前往登录' if self._register else '创建新账号',
                autoselect=True, on_activate_call=self._switch_mode,
            )
            bui.containerwidget(edit=self._root_widget, start_button=self._submit,
                                selected_child=self._body)
            bui.containerwidget(edit=self._body, selected_child=self._fields['login'])
        self._text('本地游戏无需登录。在线服务器请前往“集会”查看。', 2, scale=.65)
        if message:
            self._set_status(message)
        elif self.plus.state == 'expired':
            self._set_status('登录状态已失效，请重新登录。', error=True)

    def _set_status(self, text, error=False):
        bui.textwidget(edit=self._status, text=text,
                       color=(1, .6, .5) if error else (.65, .85, 1))

    def _switch_mode(self):
        if self._busy or not self._fields:
            return
        self._login = bui.textwidget(query=self._fields['login']).strip()
        if 'nickname' in self._fields:
            self._nickname = bui.textwidget(query=self._fields['nickname']).strip()
        self._register = not self._register
        self._render()

    def _invalid(self, key, message):
        self._set_status(message, error=True)
        bui.containerwidget(edit=self._body, selected_child=self._fields[key])

    def _auth(self):
        if self._busy or self.plus.user or self.plus.state in ('restoring', 'signing_in'):
            return
        values = {key: bui.textwidget(query=field)
                  for key, field in self._fields.items()}
        login = values['login'].strip()
        password = values['password']
        nickname = values.get('nickname', '').strip()
        if not re.fullmatch(r'[a-zA-Z0-9_]{3,32}', login):
            self._invalid('login', '登录名须为 3–32 位英文字母、数字或下划线。')
            return
        if not 10 <= len(password) <= 128:
            self._invalid('password', '请输入 10–128 位密码。')
            return
        if self._register and password != values['confirm']:
            self._invalid('confirm', '两次输入的密码不一致，请重新确认。')
            return
        if self._register and not 1 <= len(nickname) <= 40:
            self._invalid('nickname', '请输入 1–40 位玩家昵称。')
            return
        self._login = login
        self._nickname = nickname
        self._busy = True
        for key in ('password', 'confirm'):
            if key in self._fields:
                bui.textwidget(edit=self._fields[key], text='')
        bui.buttonwidget(edit=self._submit, enabled=False,
                         label='正在注册…' if self._register else '正在登录…')
        bui.buttonwidget(edit=self._switch, enabled=False)
        self._set_status('正在创建账号，请稍候…' if self._register else '正在验证账号，请稍候…')
        ref = weakref.ref(self)

        def finished(result):
            window = ref()
            if not window or not window._root_widget:
                return
            window._busy = False
            if not window.main_window_has_control():
                window._shown_state = None
                return
            window._render()
            if isinstance(result, Exception):
                window._set_status(str(result), error=True)

        self.plus.authenticate(login, password, nickname if self._register else None, finished)

    def _confirm_logout(self):
        from bauiv1lib.confirm import ConfirmWindow

        ConfirmWindow(
            '确认退出当前账号？\n退出后仍可使用本地游戏。', action=self._logout,
            width=440, height=130, text_scale=.85,
            ok_text='退出登录', cancel_text='取消',
        )

    def _logout(self):
        if not self._root_widget or not self.main_window_has_control():
            return
        self.plus.logout()
        self._busy = False
        self._register = False
        self._render('已退出登录。')

    def get_main_window_state(self):
        return bui.BasicMainWindowState(
            create_call=lambda transition, origin_widget:
                CommunityAccountWindow(transition, origin_widget))

    def main_window_should_preserve_selection(self):
        return False
