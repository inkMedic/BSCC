"""Small stdlib HTTPS transport shared by client and Headless; no backend deps."""
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request


class CommunityError(Exception):
    def __init__(self, code):
        self.code = code
        messages = {
            'insufficient_funds': '余额不足，请先获取币或点券。',
            'already_owned': '该商品已拥有，不会重复扣费。',
            'price_changed': '价格或支付方式已变化，请重新打开商品页确认。',
            'test_purchases_disabled': '服务未开启免费测试购买。',
            'profile_name_taken': '该全局档案名称已被其他账号使用。',
            'profile_name_invalid': '全局档案名称需为 2–32 位有效字符，不能使用保留名称。',
            'profile_missing': '请先保存档案，再进行升级。',
            'profile_upgrade_required': '需要通过档案升级流程保留全局名称。',
            'already_upgraded': '该档案已经升级。',
            'item_required': '需要先在商店解锁该角色。',
            'idempotency_conflict': '请求内容已变化，请重新发起操作。',
            'tournament_unknown': '赛事不存在，请刷新锦标赛列表。',
            'tournament_ended': '本场赛事已结束，请选择当前赛事。',
            'tournament_entry_invalid': '本次参赛记录无效，请通过锦标赛报名入口重新开始。',
            'tournament_game_mismatch': '比赛项目与参赛记录不符，成绩未保存。',
            'tournament_score_time_invalid': '成绩提交时间无效或赛事已结束，成绩未保存。',
            'chest_dock_full': '四个宝箱位已满，请先打开一个宝箱，再领取奖励。',
            'reward_unknown': '奖励不存在或不属于当前账号。',
            'chest_unknown': '宝箱不存在或不属于当前账号。',
            'chest_already_opened': '这个宝箱已经打开或尚未从收件箱领取，请刷新。',
            'credentials_invalid': '账号、密码或凭据无效，请重新登录。',
            'login_expired': '登录已过期，请重新登录。',
            'account_disabled': '该账号已停用。',
            'login_exists': '登录名已被使用。',
            'request_failed': '请求未能完成，请稍后重试。',
            'refresh_reused': '登录凭据已更新，请重新登录。',
            'rate_limited': '操作过于频繁，请稍后重试。',
            'server_offline': '服务器已离线或重新启动，请刷新列表。',
            'room_full': '房间已满，请选择其他服务器。',
            'version_incompatible': '客户端与服务器版本或资源不兼容。',
            'auth_prepare_timeout': '入房认证准备超时，请重试。',
            'auth_prepare_rejected': '服务器未能准备入房认证，请重试。',
            'request_invalid': '请检查登录名（3–32 位字母数字下划线）、密码（10–128 位）及昵称。',
        }
        super().__init__(messages.get(code, code))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CommunityError('社区 API 不允许重定向，请直接配置最终 HTTPS 地址。')


class Transport:
    def __init__(self):
        self.url = os.environ.get('COMMUNITY_API_URL', '').rstrip('/')
        parsed = urllib.parse.urlsplit(self.url)
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and os.environ.get('COMMUNITY_ALLOW_HTTP') == '1'):
            raise CommunityError('请配置社区 HTTPS API 地址（开发 HTTP 需显式启用）。')
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise CommunityError('API 地址不能包含凭据、查询或片段。')
        cafile = os.environ.get('COMMUNITY_CA_FILE')
        if not cafile and (os.environ.get('BA_COMMUNITY_ANDROID') == '1' or os.environ.get('BA_COMMUNITY_IOS') == '1'):
            import certifi
            cafile = certifi.where()
        self.ssl = ssl.create_default_context(cafile=cafile)
        self.opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=self.ssl))

    def request(self, method, path, body=None, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        req = urllib.request.Request(self.url + path, data=None if body is None else json.dumps(body).encode(), headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=7) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                code = json.load(exc).get('error', {}).get('code', 'request_failed')
            except (ValueError, AttributeError):
                code = 'request_failed'
            raise CommunityError(code) from None
        except (OSError, ValueError):
            raise CommunityError('社区服务连接失败，请检查网络与 API 配置。') from None
