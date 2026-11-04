# 从原仓库恢复的 UI 源码与云端路径

恢复日期：2026-10-31。来源：本地 `origin=https://github.com/efroemling/ballistica.git` 的可达 Git 对象；没有联网下载，也没有抓取官方账户或手机页面。

**结果：能够恢复旧版完整客户端布局和当前云端请求路径；没有找到当前1.8.5的云端页面生成器。** 本目录保存原始字节，不对旧代码做移植。各文件的完整提交、Git blob、SHA256、行数及原路径见 [recovery-manifest.json](recovery-manifest.json)。

## 恢复出的完整旧版布局

| 内容 | 原始路径 | 恢复位置 | 来源 |
| --- | --- | --- | --- |
| 宝箱窗口、概率区、开箱操作和动画 | src/assets/ba_data/python/bauiv1lib/chest.py | [chest.py](before-2026-10-02-docui/src/assets/ba_data/python/bauiv1lib/chest.py) | b3da947ec29ab432947d5128331e07cffebd8850 |
| 收件箱、消息卡片及物品区布局 | src/assets/ba_data/python/bauiv1lib/inbox.py | [inbox.py](before-2026-10-02-docui/src/assets/ba_data/python/bauiv1lib/inbox.py) | 同上 |
| 宝箱外观及当时消息类型 | baclassic/_chest.py、tools/bacommon/classic/_msg.py | [外观](before-2026-10-02-docui/src/assets/ba_data/python/baclassic/_chest.py)、[消息](before-2026-10-02-docui/tools/bacommon/classic/_msg.py) | 同上 |
| 收件箱所需云端对话数据类型 | tools/bacommon/clouddialog/ | [basic.py](before-2026-10-02-docui/tools/bacommon/clouddialog/basic.py) | 同上 |
| 旧商店浏览器 | src/assets/ba_data/python/bauiv1lib/store/browser.py | [browser.py](before-2026-01-08-store-cleanup/src/assets/ba_data/python/bauiv1lib/store/browser.py) | 618b7aca0d00f1eb32b6a163ccf135943469fe1d |
| 旧商品卡片布局 | src/assets/ba_data/python/bauiv1lib/store/item.py | [item.py](before-2026-01-08-store-cleanup/src/assets/ba_data/python/bauiv1lib/store/item.py) | 同上 |
| 旧购买确认窗口 | src/assets/ba_data/python/bauiv1lib/purchase.py | [purchase.py](before-2026-01-08-store-cleanup/src/assets/ba_data/python/bauiv1lib/purchase.py) | 同上 |

删除沿革可由以下命令复核：

```powershell
git show --stat 739b3140c -- src/assets/ba_data/python/bauiv1lib/chest.py src/assets/ba_data/python/bauiv1lib/inbox.py
git show --stat 65c0ce1d6 -- src/assets/ba_data/python/bauiv1lib/store
```

2026-10-02的739b3140c删除了1289行宝箱窗口和1265行收件箱窗口，改用DocUI；2026-01-08的65c0ce1d6清理旧store包。`store/newstore.py` 当时就已经是云端DocUI桥接器，不能把它误认为完整商店模板。

## 当前版本的云端请求路径

[current-head-cloud-contracts](current-head-cloud-contracts/) 是未修改的HEAD `d89c2d90cae1593899bd17a1510fef2465acb437` 源码快照，避免把本轮社区扩展混同为原版。

原调用链：客户端Controller → `fulfill_request_cloud` → `bacommon.cloud.FulfillDocUIRequest(domain, request)` → 云端返回 `FulfillDocUIResponse.response` → DocUI渲染器。

| domain | DocUI方法及路径 | 原始路由文件 |
| --- | --- | --- |
| classicstore | GET /、GET /p、POST /pc | [classicstore.py](current-head-cloud-contracts/tools/bacommon/docui/routes/classicstore.py) |
| classicinventory | 与商店共享路由家族，另有 /profile、/profile/save、/profile/character 等 | 同上；共享定义不代表每域都接受每条操作 |
| classicchest | GET /、POST /open、POST /adwatched | [classicchest.py](current-head-cloud-contracts/tools/bacommon/docui/routes/classicchest.py) |
| classicinbox | GET /、POST / | [classicinbox.py](current-head-cloud-contracts/tools/bacommon/docui/routes/classicinbox.py) |

完整17条路由及原行号由脚本从HEAD的AST直接提取，保存在manifest。**domain不是磁盘目录，DocUI path也不是已经证实的HTTP URL。** 仅知道这些名称，不能凭空恢复服务器地址或文件源码。

原始 [inventory.py](current-head-cloud-contracts/src/assets/ba_data/python/bauiv1lib/inventory.py) 注释还明确提到 `bamaster classic/profileui.py` 与 `classic/profilelistui.py`，并给出某些按钮须保持一致的尺寸/样式。这些是服务端路径线索；本地树中没有相应实现文件，不能把推测的新文件当作找回的原文件。

## 搜索范围及边界

- 仓库不是浅克隆；扫描了所有本地可达引用的4086个提交、4924种历史文件路径。
- 未发现路径组成部分为 bamaster 或 baserver 的历史文件；当前客户端代码确实引用这些服务端包。这一结论仅覆盖本地现有Git对象，不代表已检查所有外部/私有仓库。
- 原DocUI响应缓存 `_cache.py` 是进程内缓存，不是仓库中可恢复的页面模板文件。
- 共恢复23个文件（包括LICENSE）；所有Python文件完成AST语法检查，输出与Git blob逐字节一致。没有通过导入来执行旧窗口，也没有宣称其能直接在当前引擎运行。

这些原始布局可以作为后续移植和视觉复原的依据；当前版云端模板源码仍然缺失。切换运行时需要适配旧资产接口、窗口管理及云端消息，并连接现有社区业务，不能直接覆盖同名store模块造成新旧包冲突。

重跑恢复（只写本参考目录）：

```powershell
python scripts/recover-upstream-ui.py
```
