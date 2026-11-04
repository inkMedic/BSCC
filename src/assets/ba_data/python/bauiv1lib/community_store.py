"""Community data adapter for the stock store renderer and catalog.

The upstream server-composed store template is not part of this repo.
Use its bundled catalog, item sizes, translated names and asset references;
do not add community navigation, order-history or test dashboard pages.
"""
import uuid
import bauiv1 as bui
import bacommon.docui.v2 as dui
import bacommon.docui.routes.classicstore as routes
from bacommon.langstr import LangStrSpecValue
from bauiv1 import _commonassets, _classicassets

literal = LangStrSpecValue.literal
TITLES = {'characters': '角色', 'maps': '地图', 'minigames': '小游戏', 'icons': '图标', 'extras': '其他'}


def item_button(item, action, caption=''):
    classic = bui.app.classic
    sku = item['id']
    info = classic.store.get_store_items().get(sku, {})
    name = classic.store.get_store_item_name_translated(sku).evaluate() if sku in classic.store.get_store_items() else item['name']
    button = dui.Button(literal(name + ('\n' + caption if caption else '')), action=action,
                        size=classic.store.get_store_item_display_size(sku), label_scale=.75)
    if item.get('character'):
        from bascenev1lib.actor.spazappearance import texture_spec
        appearance = classic.spaz_appearances[item['character']]
        button.icon = texture_spec(appearance.icon_texture)
        button.icon_scale = 1.5
    elif info.get('map_type'):
        button.icon = info['map_type'].get_preview_texture_spec()
        button.icon_scale = 1.5
    elif info.get('icon'):
        button.label = literal(info['icon'] + '\n' + caption)
    return button


def catalog_rows(items, state, *, owned_only=False, unlockreqs=None):
    classic = bui.app.classic
    rows = []
    for category, sections in classic.store.get_store_layout().items():
        buttons = []
        for section in sections:
            for sku in section['items']:
                item = items.get(sku)
                if not item or (unlockreqs and not set(item['grants']) & set(unlockreqs)):
                    continue
                owned = all(grant in state['purchases'] for grant in item['grants'])
                if owned_only and not owned:
                    continue
                caption = '✓' if owned else (
                    _classicassets.strings.get_tokens.gold_pass.evaluate() if state['wallet']['gold_pass'] else
                    (bui.SpecialChar.TOKEN.value if item['currency'] == 'tokens' else bui.SpecialChar.TICKET.value) + str(item['price']))
                action = (routes.SpawnBot(item['character']).local() if item.get('character') else routes.ShowStore().local()) if owned_only else routes.Purchase(sku).browse()
                buttons.append(item_button(item, action, caption))
        if buttons:
            rows.append(dui.ButtonRow(buttons, title=literal(TITLES[category])))
    return rows


def store_page(controller, route):
    plus = bui.app.plus
    rows = []
    try:
        state = plus.request_sync('GET', '/v1/economy')
        catalog = plus.request_sync('GET', '/v1/store', authenticated=False)
        items = {item['id']: item for item in catalog['items']}
        if isinstance(route, (routes.PurchaseConfirm, routes.CommunityPurchaseConfirm)):
            quote = (route.currency, route.price) if isinstance(route, routes.CommunityPurchaseConfirm) else controller._community_quotes[route.purchase_id]
            attempt = route.request_id if isinstance(route, routes.CommunityPurchaseConfirm) else controller._community_attempts[route.purchase_id]
            result = plus.request_sync('POST', '/v1/store/purchase', dict(request_id=attempt,
                item_id=route.purchase_id, currency=quote[0], expected_price=quote[1]))
            state = result['state']
            rows.append(dui.SubtitleRow(literal('✓')))
        elif isinstance(route, routes.Purchase):
            item = items[route.purchase_id]
            owned = bool(item['grants']) and all(grant in state['purchases'] for grant in item['grants'])
            rows.append(dui.ButtonRow([item_button(item, None)]))
            if not owned:
                currency = 'test' if item.get('test_only') else 'gold_pass' if state['wallet']['gold_pass'] else item['currency']
                price = 0 if currency in ('test', 'gold_pass') else item['price']
                attempt = str(uuid.uuid4())
                controller._community_attempts[item['id']] = attempt
                controller._community_quotes[item['id']] = (currency, price)
                glyph = bui.SpecialChar.TOKEN.value if currency == 'tokens' else bui.SpecialChar.TICKET.value
                caption = '免费（测试）' if currency == 'test' else (_classicassets.strings.get_tokens.gold_pass.evaluate() if currency == 'gold_pass' else glyph + str(price))
                rows.append(dui.ButtonRow([dui.Button(literal(caption), action=routes.CommunityPurchaseConfirm(item['id'], currency, price, attempt).replace(), size=(220, 65))]))
            return dui.Response(page=dui.Page(title=literal('商店'), rows=rows), for_build=23079)
        rows += catalog_rows(items, state, unlockreqs=getattr(route, 'unlockreqs', None))
        rows.append(dui.ButtonRow([dui.Button(_classicassets.strings.resource_type_info.get_tokens.spec, action=routes.GetTokens().local(), size=(220, 65))]))
    except Exception as exc:
        rows = [dui.SubtitleRow(literal(str(exc))), dui.ButtonRow([dui.Button(_commonassets.strings.actions.retry.spec, action=routes.Root().replace())])]
    return dui.Response(page=dui.Page(title=literal('商店'), rows=rows), for_build=23079)
