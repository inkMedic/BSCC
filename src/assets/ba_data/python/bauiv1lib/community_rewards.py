"""Community rewards through the existing chest/inbox DocUI domains."""
import uuid
import bauiv1 as bui
import bacommon.docui.v2 as dui
import bacommon.clienteffect as effects
import bacommon.docui.routes.classicchest as croutes
import bacommon.docui.routes.classicinbox as iroutes
from bacommon.langstr import LangStrSpecValue
from bacommon.classic import ClassicChestAppearance
from bauiv1 import _commonassets, _classiccatalogassets, _classicuiassets
from baclassic._chest import CHEST_APPEARANCE_DISPLAY_INFOS, CHEST_APPEARANCE_DISPLAY_INFO_DEFAULT

literal = LangStrSpecValue.literal


def text(value):
    return dui.SubtitleRow(literal(value), attach=False)


def button(label, action):
    return dui.Button(literal(label), action=action, size=(240, 65), label_scale=.8)


def purple_row(count):
    from bacommon.legacydisplayitem import PurpleTickets, Wrapper
    from bacommon.displayitem import DisplayItemStyle
    from baclassic._displayitem import display_item_decorations
    decorations = display_item_decorations(Wrapper.for_item(PurpleTickets(count)),
        position=(0., 0.), size=(260., 130.), style=DisplayItemStyle.COMPACT)
    return dui.ButtonRow([dui.Button(size=(280., 150.), color=(1., 1., 1., 0.), decorations=decorations)])


def chest_art(appearance, opened=False):
    info = CHEST_APPEARANCE_DISPLAY_INFOS.get(ClassicChestAppearance(appearance), CHEST_APPEARANCE_DISPLAY_INFO_DEFAULT)
    image = dui.Image((info.texopen if opened else info.texclosed).ui(), position=(0., 0.), size=(210., 210.),
        tint_texture=(info.texopentint if opened else info.texclosedtint).ui(),
        color=(*info.color, 1.), tint_color=info.tint, tint2_color=info.tint2, tint3_color=info.tint3, anim_id='chest')
    return dui.ButtonRow([dui.Button(size=(230., 220.), color=(1., 1., 1., 0.), decorations=[image])])


def chest_page(route):
    plus = bui.app.plus
    fx = []
    try:
        if isinstance(route, croutes.Open):
            if not route.chest_id or not route.request_id:
                raise ValueError('请重新打开宝箱页面确认。')
            result = plus.request_sync('POST', '/v1/chests/' + route.chest_id + '/open',
                dict(request_id=route.request_id, expected_price=route.token_payment))
            payout, wallet = result['payouts'], result['state']['wallet']
            rows = [chest_art(result['appearance'], True)]
            if payout['tokens'] + payout['compensation_tokens']:
                rows.append(text(bui.SpecialChar.TOKEN.value + str(payout['tokens'] + payout['compensation_tokens'])))
            if payout['tickets']:
                rows.append(text(bui.SpecialChar.TICKET.value + str(payout['tickets'])))
            if payout.get('purple_tickets'):
                rows.append(purple_row(payout['purple_tickets']))
            if payout['compensation_tokens']:
                rows.append(text('重复商品已兑换为币。'))
            for item in payout['items']:
                rows.append(text(plus_item_name(item)))
            if payout['gold_pass_days']:
                rows.append(text('金卡 +' + str(payout['gold_pass_days']) + ' 天'))
            rows.append(dui.ButtonRow([button('完成', croutes.Root(route.slot).replace())]))
            fx = [effects.PlaySoundV2(_classiccatalogassets.audio.rev_up),
                  effects.KeyframeAnimation('chest', [effects.Keyframe(0., scale=.6), effects.Keyframe(.25, scale=1.15), effects.Keyframe(.5)]),
                  effects.Delay(.25), effects.PlaySoundV2(_classiccatalogassets.audio.cork_pop2)]
            if wallet['tokens'] != result['before']['tokens']:
                fx.append(effects.TokensAnimation(.8, result['before']['tokens'], wallet['tokens']))
            if payout['tickets']:
                fx += [effects.TicketsAnimation(.8, result['before']['tickets'], wallet['tickets']),
                       effects.ScreenMessageV2(_classicuiassets.strings.economy.received_tickets(count=payout['tickets']).spec)]
            if payout.get('purple_tickets'):
                fx.append(effects.ScreenMessageV2(literal('获得 ' + str(payout['purple_tickets']) + ' 紫券')))
        else:
            if isinstance(route, croutes.AdWatched):
                raise ValueError('当前未接入广告平台，不能通过广告缩短等待。')
            data = plus.request_sync('GET', '/v1/chests')
            chest = next((c for c in data['chests'] if c['slot'] == route.slot), None)
            if chest is None:
                rows = [text('这个宝箱位为空。'), text('完成锦标赛可获得参与宝箱；赛事结算奖励在收件箱领取。')]
            else:
                rule = data['rules'][chest['appearance']]
                rows = [chest_art(chest['appearance'])]
                fixed = chest.get('fixed_contents')
                if fixed:
                    rows.append(text('固定奖励'))
                    if fixed.get('purple_tickets'):
                        rows.append(purple_row(fixed['purple_tickets']))
                else:
                    rows += [text('币 ' + '–'.join(map(str, rule['tokens'])) + '　点券 ' + '–'.join(map(str, rule['tickets']))),
                             text(f"角色概率 {rule['item_chance']}%　金卡概率 {rule['card_chance']}%")]
                cost = chest['unlock_tokens']
                if cost:
                    import time
                    rows.append(text('剩余等待 ' + str(max(1, int((chest['unlock_time'] - time.time()) / 60))) + ' 分钟'))
                action = croutes.Open(route.slot, cost, chest['id'], str(uuid.uuid4())).replace()
                rows.append(dui.ButtonRow([button('打开' if cost == 0 else '立即打开 ' + bui.SpecialChar.TOKEN.value + str(cost), action),
                                          button('刷新', croutes.Root(route.slot).replace())]))
    except Exception as exc:
        rows = [text(str(exc)), dui.ButtonRow([dui.Button(_commonassets.strings.actions.retry.spec, action=croutes.Root(route.slot).replace())])]
    return dui.Response(page=dui.Page(title=literal('宝箱'), rows=rows), client_effects=fx, for_build=23079)


def plus_item_name(sku):
    if sku in bui.app.classic.store.get_store_items():
        return bui.app.classic.store.get_store_item_name_translated(sku).evaluate()
    catalog = bui.app.plus.request_sync('GET', '/v1/store', authenticated=False)
    return next((item['name'] for item in catalog['items'] if item['id'] == sku), sku)


def inbox_page(route):
    plus = bui.app.plus
    rows = []
    try:
        if isinstance(route, iroutes.Respond) and route.positive:
            plus.request_sync('POST', '/v1/inbox/' + route.entry_id + '/claim', {})
        data = plus.request_sync('GET', '/v1/inbox')
        for message in data['messages']:
            if message['game']:
                campaign, level = message['game'].split(':')
                name = bui.app.classic.getcampaign(campaign).getlevel(level).displayname_langstr.evaluate()
                label = '参赛奖励' if message['kind'] == 'completion' else '赛事结算 · 第 ' + str(message['rank']) + ' 名'
            else:
                name, label = '宝箱礼物', '管理员赠礼'
            message_rows = [dui.TitleRow(literal(label)), text(name), chest_art(message['appearance'])]
            fixed = message.get('fixed_contents')
            if fixed and fixed.get('purple_tickets'):
                message_rows.append(purple_row(fixed['purple_tickets']))
            actions = [button('领取', iroutes.Respond(message['id']).replace())]
            if message['tournament_id']:
                actions.append(button('成绩', iroutes.TourneyScores(message['tournament_id']).local()))
            message_rows.append(dui.ButtonRow(actions))
            rows.append(dui.Section(rows=message_rows))
        if not rows:
            rows.append(text('暂无待领取奖励。'))
        rows.append(dui.ButtonRow([button('刷新', iroutes.Root().replace())]))
    except Exception as exc:
        rows = [text(str(exc)), dui.ButtonRow([dui.Button(_commonassets.strings.actions.retry.spec, action=iroutes.Root().replace())])]
    return dui.Response(page=dui.Page(title=literal('收件箱'), rows=rows), for_build=23079)
