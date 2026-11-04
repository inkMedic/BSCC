# Released under the MIT License. See LICENSE for details.
#
"""Shiny new doc-ui based store."""

from typing import override, assert_never, TYPE_CHECKING

import bacommon.docui.routes.classicstore as sroutes

from bauiv1lib.docui import TypedDocUIController

import bauiv1 as bui
from bauiv1 import _classicassets
from bauiv1 import _builtinassets

if TYPE_CHECKING:
    import bacommon.docui.v2
    import bacommon.docui.routes.classicstore
    from bacommon.docui import DocUIResponse

    from bauiv1lib.docui import DocUILocalAction


class StoreUIController(
    TypedDocUIController[sroutes.AnyStoreRoute, sroutes.AnyStoreLocalAction]
):
    """DocUI setup for store."""

    def get_cache_key_extra(self):
        return None if getattr(bui.app.plus, 'community_online', False) else ''

    @override
    @classmethod
    def get_route_type(
        cls,
    ) -> type[bacommon.docui.routes.classicstore.StoreRoute]:
        return sroutes.StoreRoute

    @override
    @classmethod
    def get_local_action_type(
        cls,
    ) -> type[bacommon.docui.routes.classicstore.StoreLocalAction]:
        return sroutes.StoreLocalAction

    @override
    def fulfill_route(
        self, route: bacommon.docui.routes.classicstore.AnyStoreRoute
    ) -> DocUIResponse:
        if getattr(bui.app.plus, 'community_online', False):
            if not hasattr(self, '_community_attempts'):
                self._community_attempts, self._community_quotes = {}, {}
            from bauiv1lib.community_store import store_page
            return store_page(self, route)
        return self.fulfill_request_cloud(route, 'classicstore')

    @override
    def fulfill_unrouted_request(
        self, request: bacommon.docui.v2.Request, error: str
    ) -> DocUIResponse:
        # Something newer than us from the server; let it handle it.
        return self.fulfill_request_cloud(request, 'classicstore')

    @override
    def run_local_action(
        self,
        action: bacommon.docui.routes.classicstore.AnyStoreLocalAction,
        context: DocUILocalAction,
    ) -> None:
        match action:
            case sroutes.GetTokens():
                self._get_tokens(context)
            case sroutes.RestorePurchases():
                self._restore_purchases()
            case _:
                assert_never(action)

    def _restore_purchases(self) -> None:

        plus = bui.app.plus
        assert plus is not None

        # We should always be signed in here. Make noise if not.
        if plus.accounts.primary is None:
            bui.screenmessage(
                _classicassets.strings.ui.not_signed_in_status, color=(1, 0, 0)
            )
            _builtinassets.audio.error.get().play()
            return

        if getattr(plus, 'community_online', False):
            plus.refresh_economy()
            bui.screenmessage('正在从社区账号恢复库存与余额。')
        else:
            plus.restore_purchases()

    def _get_tokens(self, action: DocUILocalAction) -> None:
        from bauiv1lib.gettokens import show_get_tokens_window

        bui.play_swish()

        show_get_tokens_window(origin_widget=bui.existing(action.widget))
