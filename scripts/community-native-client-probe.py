"""Run *inside the desktop engine*, never on a user's Android device."""
import json
import os
import time
from pathlib import Path
import babase
import bascenev1 as bs

credentials = json.loads(Path(os.environ['COMMUNITY_PROBE_CREDENTIALS']).read_text())
plus = babase.app.plus
started = time.monotonic()
connected_since = None
timer = None


def fail(message):
    print('NATIVE_CLIENT_PROBE_FAILED', message, flush=True)
    babase.quit()


def connected():
    global connected_since, timer
    info = bs.get_connection_to_host_info()
    if info:
        if connected_since is None:
            connected_since = time.monotonic()
        if time.monotonic() - connected_since >= 5:
            print('NATIVE_CLIENT_STABLE_CONNECTION_OK', flush=True)
            bs.disconnect_from_host()
            timer = None
            babase.apptimer(3, disconnected)
            return
    elif connected_since is not None:
        timer = None
        fail('Connection dropped after acceptance')
    if time.monotonic() - started > 20:
        timer = None
        fail('Connection timeout')


def disconnected():
    if bs.get_connection_to_host_info():
        fail('Still connected after local leave')
        return
    print('NATIVE_CLIENT_LOCAL_LEAVE_OK', flush=True)
    babase.quit()


def prepared(value):
    global timer
    if isinstance(value, Exception):
        fail(str(value))
        return
    bs.connect_to_party(value['address'], port=value['port'])
    timer = babase.AppTimer(.25, connected, repeat=True)


def servers(value):
    if isinstance(value, Exception):
        fail(str(value))
        return
    server = next((s for s in value['servers'] if s['server_id'] == os.environ['COMMUNITY_PROBE_SERVER']), None)
    if not server:
        fail('Target not listed')
        return
    plus.prepare_join(server, prepared)


def authenticated(value):
    if isinstance(value, Exception):
        fail(str(value))
        return
    assert plus.accounts.primary.accountid == value['user']['uid']
    assert plus.accounts.primary.tag == value['user']['nickname']
    assert plus.accounts.primary.account_tag == value['user']['account_tag']
    assert plus.get_v1_account_display_string() == (
        babase.charstr(babase.SpecialChar.GOOGLE_PLAY_GAMES_LOGO) + value['user']['nickname'])
    print('NATIVE_CLIENT_COMMUNITY_PRIMARY_OK', flush=True)
    if babase.app.env.headless:
        def work():
            from bauiv1lib.store import StoreUIController
            from bauiv1lib.inventory import InventoryUIController
            from baplus._community_uicompat import league_data
            import bacommon.docui.routes.classicstore as routes
            from efro.dataclassio import dataclass_to_json
            from uuid import uuid4
            controller = StoreUIController()
            import bacommon.classic
            catalog = plus.request_sync('GET', '/v1/store', authenticated=False)
            amounts = {p['id']: p.get('amount') for p in catalog['items']}
            for i in range(1, 5):
                assert amounts['tokens' + str(i)] == getattr(bacommon.classic, f'TOKENS{i}_COUNT')
            for route in [routes.Root()]:
                root_page = controller.fulfill_route(route)
                assert len(root_page.page.rows) >= 5, dataclass_to_json(root_page)
                dataclass_to_json(root_page)
            def buy(sku):
                if sku in ('tokens2', 'tickets1', 'gold_pass'):
                    plus.request_sync('POST', '/v1/store/purchase', dict(request_id=str(uuid4()), item_id=sku, currency='test', expected_price=0))
                    return
                page = controller.fulfill_route(routes.Purchase(sku))
                dataclass_to_json(page)
                action = page.page.rows[-1].buttons[0].action
                confirm = routes.StoreRoute.from_request(action.request)
                assert isinstance(confirm, routes.CommunityPurchaseConfirm)
                dataclass_to_json(controller.fulfill_route(confirm))
            buy('tokens2')
            state = plus.request_sync('GET', '/v1/economy')
            assert state['wallet']['tokens'] == 500, state
            buy('characters.kronk')
            state = plus.request_sync('GET', '/v1/economy')
            assert state['wallet']['tokens'] == 400 and 'characters.kronk' in state['purchases']
            buy('tickets1')
            profile = dict(character='Kronk', color=[1, 1, 1], highlight=[.5, .5, .5], **{'global': False})
            profile_name = 'Probe' + value['user']['uid'].replace('-', '')[:12]
            plus.request_sync('PUT', '/v1/me/profiles/' + profile_name, profile)
            upgraded = plus.request_sync('POST', '/v1/profiles/upgrade', dict(name=profile_name, request_id=str(uuid4()), expected_price=100))
            assert upgraded['state']['player_profiles'][profile_name]['global']
            assert upgraded['state']['wallet']['tickets'] == 200
            buy('gold_pass')
            assert plus.request_sync('GET', '/v1/economy')['wallet']['gold_pass']
            league = league_data(plus.request_sync('GET', '/v1/league'), value['user']['uid'])
            assert babase.app.classic.accounts.get_league_rank_points(league) == 0
            # Explicit renderer fixture only; never submitted as match results.
            fixture = plus.request_sync('GET', '/v1/league') | {'me': dict(games=4, wins=2, points=80, rank=1, tier='Bronze')}
            assert babase.app.classic.accounts.get_league_rank_points(league_data(fixture, value['user']['uid'])) == 80
            dataclass_to_json(InventoryUIController().fulfill_route(routes.Root()))
            from bauiv1lib.chestui import ChestUIController
            from bauiv1lib.inboxui import InboxUIController
            import bacommon.docui.routes.classicchest as chest_routes
            import bacommon.docui.routes.classicinbox as inbox_routes
            chest_controller = ChestUIController()
            chest = plus.request_sync('GET', '/v1/chests')['chests'][0]
            dataclass_to_json(chest_controller.fulfill_route(chest_routes.Root(chest['slot'])))
            opened = chest_controller.fulfill_route(chest_routes.Open(chest['slot'], 0, chest['id'], str(uuid4())))
            dataclass_to_json(opened)
            assert opened.client_effects, dataclass_to_json(opened)
            state = plus.request_sync('GET', '/v1/economy')
            assert state['wallet']['tokens'] == 407 and 'characters.zoe' in state['purchases'], state
            inbox_controller = InboxUIController()
            dataclass_to_json(inbox_controller.fulfill_route(inbox_routes.Root()))
            message = next(m for m in plus.request_sync('GET', '/v1/inbox')['messages'] if m['tournament_id'])
            dataclass_to_json(inbox_controller.fulfill_route(inbox_routes.Respond(message['id'])))
            state = plus.request_sync('GET', '/v1/economy')
            assert state['inbox_count'] == 1 and len(state['chests']) == 1, state
            gift = next(m for m in plus.request_sync('GET', '/v1/inbox')['messages'] if m['kind'] == 'admin_gift')
            dataclass_to_json(inbox_controller.fulfill_route(inbox_routes.Respond(gift['id'])))
            gift_chest = next(c for c in plus.request_sync('GET', '/v1/chests')['chests'] if c.get('fixed_contents'))
            dataclass_to_json(chest_controller.fulfill_route(chest_routes.Root(gift_chest['slot'])))
            gift_page = chest_controller.fulfill_route(chest_routes.Open(gift_chest['slot'], 0, gift_chest['id'], str(uuid4())))
            dataclass_to_json(gift_page)
            state = plus.request_sync('GET', '/v1/economy')
            assert state['wallet']['purple_tickets'] == 9999 and state['wallet']['tokens'] == 407
            assert state['wallet']['tickets'] == 280 and state['inbox_count'] == 0
            dataclass_to_json(InventoryUIController().fulfill_route(routes.Root()))
            print('NATIVE_CLIENT_PURPLE_TICKETS_GIFT_OK', flush=True)
            print('NATIVE_CLIENT_CHEST_OPEN_AND_INBOX_MODELS_OK', flush=True)
            return True
        def finished(result):
            if isinstance(result, Exception):
                fail(type(result).__name__ + ': ' + str(result))
            else:
                assert plus.economy['wallet']['tokens'] == 407
                assert 'characters.kronk' in babase.app.classic.purchases
                def queried(response):
                    import bacommon.cloud
                    assert isinstance(response, bacommon.cloud.StoreQueryResponse), response
                    assert response.gold_pass and response.tokens == 407
                    assert plus.get_price('tokens2') is not None
                    def ranked(data):
                        assert data is not None and data['rank'] is None
                        print('NATIVE_CLIENT_SHOP_UPGRADE_INVENTORY_LEAGUE_MODELS_OK', flush=True)
                        print('NATIVE_CLIENT_STOCK_UI_ADAPTERS_OK', flush=True)
                        def tournaments(data):
                            assert data is not None and len(data['t']) == 8
                            babase.app.classic.accounts.cache_tournament_info(data['t'])
                            event = data['t'][0]
                            game = event['game']
                            assert babase.app.classic.is_game_unlocked(game)
                            assert event['fee'] is None and event['timeRemaining'] > 0
                            def entered(value):
                                assert not isinstance(value, Exception), value
                                campaign, level = game.split(':')
                                babase.app.classic.coop_session_args = dict(campaign=campaign, level=level,
                                    min_players=event['minPlayers'], max_players=event['maxPlayers'],
                                    tournament_id=event['tournamentID'], submit_score=True,
                                    community_tournament_entry_id=value['entry_id'])
                                # Real native session and game-class construction.
                                # No players are injected and no game round is run.
                                bs.new_host_session(bs.CoopSession)
                                def session_started():
                                    session = bs.get_foreground_host_session()
                                    assert isinstance(session, bs.CoopSession)
                                    assert session.tournament_id == event['tournamentID']
                                    assert session.campaign_level_name == level
                                    assert session.get_current_game_instance() is not None
                                    assert session.community_tournament_entry_id == value['entry_id']
                                    session.submit_score = False
                                    def practice_ignored(result):
                                        assert result is None
                                        session.submit_score = True
                                        print('NATIVE_CLIENT_TOURNAMENT_SESSION_START_OK', flush=True)
                                        print('NATIVE_CLIENT_TOURNAMENT_PRACTICE_NO_SUBMISSION_OK', flush=True)
                                        print('NATIVE_CLIENT_UDP_NOT_AVAILABLE_HEADLESS', flush=True)
                                        babase.quit()
                                    plus.submit_score('explicit-practice-fixture', '', '', 123, practice_ignored,
                                        tournament_id=event['tournamentID'], campaign=campaign, level=level)
                                babase.apptimer(1, session_started)
                            from uuid import uuid4
                            plus.enter_tournament(event['tournamentID'], str(uuid4()), entered)
                        plus.tournament_query(tournaments, dict(source='desktop session-start probe'))
                    plus.power_ranking_query(ranked)
                plus.query_store(queried)
        plus._submit(work, finished)
        return
    plus.request('GET', '/v1/servers', None, servers)


plus.authenticate(credentials['login'], credentials['password'], None, authenticated)
