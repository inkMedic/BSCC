# Released under the MIT License. See LICENSE for details.
"""Explicit offline Plus implementation for the community Android host.

No account is invented. Cloud requests fail through the same asynchronous
error contract as a disconnected service. Native networking stays compiled;
room authentication is an explicitly unsupported future integration.
"""
from typing import Any
import concurrent.futures
import copy
import babase
import _baplus  # Installs the source-built native PlusSoftInterface.
from efro.call import CallbackSet
from efro.error import CommunicationError
from baplus._appsubsystem import PlusAppSubsystem
from baplus._cloud import CloudSubsystem
from baplus._ads import AdsSubsystem


def unavailable() -> CommunicationError:
    return CommunicationError('社区在线服务尚未接入；当前可使用本地游戏。')


class OfflineAccounts:
    """Signed-out state; replace at the community account boundary."""
    primary = None
    discord_available = False

    def __init__(self) -> None:
        self.on_primary_account_changed_callbacks = CallbackSet()
        self.login_adapters: dict = {}

    def have_primary_credentials(self) -> bool:
        return False

    def set_primary_credentials(self, credentials: str | None) -> None:
        if credentials is not None:
            raise unavailable()

    def on_app_loading(self) -> None:
        pass


class OfflineCloud(CloudSubsystem):
    def is_connected(self) -> bool:
        return False

    def on_app_running(self) -> None:
        # Do not request official cloud values or update announcements.
        pass

    def get_connected_node_base_url(self) -> None:
        return None

    def get_connected_node_address(self) -> None:
        return None

    def send_message_cb(self, msg: Any, on_response: Any) -> None:
        babase.pushcall(lambda: on_response(unavailable()))

    def send_message(self, msg: Any) -> Any:
        raise unavailable()

    async def send_message_async(self, msg: Any) -> Any:
        raise unavailable()

    def send_message_future(self, msg: Any) -> concurrent.futures.Future:
        future: concurrent.futures.Future = concurrent.futures.Future()
        future.set_exception(unavailable())
        return future


class OfflineAds(AdsSubsystem):
    def can_show_ad(self) -> bool:
        return False

    def has_video_ads(self) -> bool:
        return False

    def have_incentivized_ad(self) -> bool:
        return False

    def call_after_ad(self, call: Any) -> None:
        babase.pushcall(call)

    def show_ad(self, *args: Any, **kwargs: Any) -> None:
        raise unavailable()

    def show_ad_2(self, *args: Any, **kwargs: Any) -> None:
        raise unavailable()


class CommunityPlusAppSubsystem(PlusAppSubsystem):
    community_offline = True
    def __init__(self) -> None:
        self.cloud = OfflineCloud()
        self.accounts = OfflineAccounts()
        self.ads = OfflineAds()
        self._initial_notification_sent = False
        self._rejected_transactions: list[Any] = []
        self._local_profile_transactions: list[tuple[dict, Any]] = []

    def on_app_loading(self) -> None:
        if 'Player Profiles' not in babase.app.config:
            babase.app.config['Player Profiles'] = {}
            babase.app.config.commit()
        if not self._initial_notification_sent:
            self._initial_notification_sent = True
            babase.pushcall(babase.app.on_initial_sign_in_complete)

    @staticmethod
    def set_v1_account_client_active(active: bool) -> None:
        # No legacy account client runs in this build.
        pass

    @staticmethod
    def get_v1_account_state() -> str:
        return 'signed_out'

    @staticmethod
    def get_v1_account_state_num() -> int:
        return 0

    @staticmethod
    def get_v1_account_type() -> str:
        return 'Invalid'

    @staticmethod
    def get_v1_account_name() -> str:
        return ''

    @staticmethod
    def get_v1_account_display_string(full: bool = True) -> str:
        return ''

    @staticmethod
    def get_v1_account_public_login_id() -> None:
        return None

    @staticmethod
    def get_v1_account_misc_read_val(name: str, default_value: Any) -> Any:
        return default_value

    get_v1_account_misc_read_val_2 = get_v1_account_misc_read_val
    get_v1_account_misc_val = get_v1_account_misc_read_val

    @staticmethod
    def is_blessed() -> bool:
        return False

    @staticmethod
    def get_blessing_state() -> None:
        return None

    @staticmethod
    def blessed_state() -> bool:
        return False

    @staticmethod
    def purchase(item: str) -> None:
        raise unavailable()

    @staticmethod
    def in_game_purchase(item: str, price: int) -> None:
        raise unavailable()

    @staticmethod
    def restore_purchases() -> None:
        raise unavailable()

    @staticmethod
    def reset_achievements() -> None:
        raise unavailable()

    @staticmethod
    def game_service_has_leaderboard(game: str, config: str) -> bool:
        return False

    @staticmethod
    def show_game_service_ui(*args: Any, **kwargs: Any) -> None:
        raise unavailable()

    @staticmethod
    def power_ranking_query(callback: Any, season: Any = None) -> None:
        babase.pushcall(lambda: callback(None))

    @staticmethod
    def tournament_query(callback: Any, args: dict) -> None:
        babase.pushcall(lambda: callback(None))

    @staticmethod
    def submit_score(game: str, config: str, name: Any, score: int | None,
                     callback: Any, **kwargs: Any) -> None:
        babase.pushcall(lambda: callback(None))

    @staticmethod
    def supports_purchases() -> bool:
        return False

    @staticmethod
    def get_price(item: str) -> None:
        return None

    @staticmethod
    def get_classic_news_show() -> str:
        return ''

    @staticmethod
    def get_bootstrap_server_addresses() -> list[str]:
        return []

    @staticmethod
    def get_bootstrap_server_address() -> None:
        return None

    @staticmethod
    def get_master_server_address() -> str:
        raise unavailable()

    get_legacy_master_server_address = get_master_server_address

    @staticmethod
    def get_v2_fleet() -> str:
        return 'community-offline'

    def add_v1_account_transaction(self, transaction: dict, callback: Any = None) -> None:
        kind = transaction.get('type')
        name = transaction.get('name')
        if kind in ('ADD_PLAYER_PROFILE', 'REMOVE_PLAYER_PROFILE'):
            if not isinstance(name, str) or not name or (name.startswith('__') and name != '__account__'):
                raise ValueError('Only named local player profiles are supported')
            if kind == 'ADD_PLAYER_PROFILE' and transaction.get('profile', {}).get('global', False):
                raise unavailable()
            self._local_profile_transactions.append((copy.deepcopy(transaction), callback))
            return
        if kind in ('ACHIEVEMENT', 'COMPLETE_LEVEL', 'SET_LEVEL_LOCAL_HIGH_SCORES'):
            classic = babase.app.classic
            assert classic is not None
            if kind == 'ACHIEVEMENT':
                classic.ach.get_achievement(transaction['name']).set_complete()
            else:
                level = classic.getcampaign(transaction['campaign']).getlevel(
                    transaction['level']
                )
                if kind == 'COMPLETE_LEVEL':
                    level.set_complete(True)
                else:
                    if transaction['scoreVersion'] != level.get_score_version_string():
                        raise ValueError('Local high scores have the wrong version')
                    level.set_high_scores(copy.deepcopy(transaction['scores']))
            babase.app.config.commit()
            if callback is not None:
                babase.pushcall(lambda: callback({}))
            return
        # Unsupported legacy service requests finish with a failure callback.
        if callback is not None:
            self._rejected_transactions.append(callback)

    def run_v1_account_transactions(self) -> None:
        local, self._local_profile_transactions = self._local_profile_transactions, []
        if local:
            profiles = babase.app.config.setdefault('Player Profiles', {})
            for transaction, callback in local:
                if transaction['type'] == 'ADD_PLAYER_PROFILE':
                    profiles[transaction['name']] = transaction['profile']
                else:
                    profiles.pop(transaction['name'], None)
            babase.app.config.commit()
            for transaction, callback in local:
                if callback is not None:
                    babase.pushcall(lambda callback=callback: callback({}))
        calls, self._rejected_transactions = self._rejected_transactions, []
        for call in calls:
            babase.pushcall(lambda call=call: call(None))

    def have_outstanding_v1_account_transactions(self) -> bool:
        return bool(self._rejected_transactions or self._local_profile_transactions)

    @staticmethod
    def sign_in_v1(account_type: str) -> None:
        raise unavailable()

    @staticmethod
    def sign_out_v1(v2_embedded: bool = False) -> None:
        pass

    @staticmethod
    def report_achievement(achievement: str, pass_to_account: bool = True) -> None:
        # Local achievements remain managed by baclassic, with no cloud write.
        pass
