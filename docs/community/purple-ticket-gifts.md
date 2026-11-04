# 原版紫券类型与定向宝箱（2026-10-31）

原仓库核对结果：`tools/bacommon/legacydisplayitem.py` 有 PurpleTickets（类型ID `tp`），`displayitem.py` 使用 tickets_purple 素材渲染它；`classicstore.PurchaseMethod` 包含 PURPLE_TICKETS（`p`）。它与普通 Tickets 的显示类型不同。

原仓库 AccountLiveData 只有 tickets/tokens，没有独立紫券余额字段；官方钱包与兑换规则位于未提供的云端。此前社区实现漏接紫券奖励类型。本次为社区钱包增加独立 purple_tickets 持久化，避免把紫券冒充或换算为普通点券；通过原版 PurpleTickets/DisplayItem 画法在开箱和库存显示。未改变原工具栏普通点券计数，也未推断官方兑换率或自行配置紫券商品价格。

迁移0006新增余额和独立管理员礼物（无须伪造锦标赛记录）。固定礼物会明确显示其保证内容，不显示随机宝箱概率，领取后立即可免费开启。开箱事务保留请求UUID去重；紫券与币/普通点券分别计账。

按本次用户指令，从 community_dev（不含隔离测试库）查询到2个用户。发放时锁定用户行并重新计算代币排行，接收者为登录名 susu1、昵称 susu，代币187200。已向其收件箱发放一个L6外观固定礼物：只含9999紫券，不直接代开、不扣币、不额外随机掉落。幂等来源与实际宝箱/消息ID记录在 `artifacts/community/top-token-purple-gift-receipt.json`。

后端19项通过，新增验证固定紫券宝箱并发开箱只加9999紫券、普通点券和代币不变。真实桌面引擎验证原版紫券图示、独立赠礼领取、开箱和库存数据模型；这些引擎测试使用隔离fixture，不是给真实用户代开宝箱。真实接收者宝箱已只读核对为未领取、未开启。

使用 `artifacts/android/ballistica-community-purple-gift-test.apk` 保留数据覆盖安装，强行停止后重开；登录 susu1，在收件箱领取后从宝箱位打开，库存可见紫券余额。手机操作仍由用户完成。
