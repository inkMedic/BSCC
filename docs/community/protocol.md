# 社区协议 v1

REST 定义以运行后 `/openapi.json`、`/docs` 及 `community_backend/schemas.py` 为准。
默认兼容元组 `(engine_build=23079, scene_protocol=57, community_protocol=1, assets="23079")`。
升级资源或协议时同时修改后端默认值和客户端 `COMPATIBILITY`，不能只改显示版本。

| 接口 | 鉴权/返回 |
| --- | --- |
| GET `/health/live`, `/health/ready` | 存活/数据库与 Redis 就绪 |
| POST `/v1/auth/register` | `{login,password,nickname}`；登录名 3–32 位 ASCII 字母数字下划线，统一小写；密码 10–128 位；昵称 1–40 字符 |
| POST `/v1/auth/login` | `{login,password}` |
| POST `/v1/auth/refresh` | `{refresh_token}`；Lua 原子轮换并撤销旧访问凭据 |
| POST `/v1/auth/logout` | 玩家 Bearer；撤销当前会话 |
| GET `/v1/me` | 玩家 Bearer；`{uid,account_tag,nickname}` |
| PUT `/v1/me/profiles/{name}` | 玩家 Bearer；保存社区账号档案，验证角色/颜色/名称，禁止伪造官方全局档案 |
| DELETE `/v1/me/profiles/{name}` | 玩家 Bearer；删除当前 UID 的账号档案 |
| GET `/v1/servers` | 可选兼容查询；`{version:1,servers:[...]}` |
| GET `/v1/servers/{id}` | 当前有效公开实例；离线 409 |
| POST `/v1/servers/{id}/join` | 玩家 Bearer；兼容元组 + instance_id + join_attempt_id |
| POST `/v1/servers/register` | 服务器专用 Bearer；兼容元组 + server_id、instance_id、address（IP 字面量）、port |
| POST `/v1/servers/{id}/unregister` | 服务器专用 Bearer；主动关闭控制通道 |
| WS(S) `/v1/servers/control` | Authorization Bearer 为注册返回的短时 control_token，单次使用；不放 URL |

登录响应：`{access_token,refresh_token,expires_in:900,user:{uid,account_tag,nickname}}`。访问 15 分钟，刷新 30 天，可配置。凭据 32 随机字节；服务端只存哈希/索引。Redis AOF/卷负责会话重启持久化，Redis 清空后必须重新登录。

账号字段分工：`uid` 是稳定的内部身份 ID；`account_tag` 是服务端生成的 ASCII 社区标识，供入房认证使用；`nickname` 是玩家可见的用户名。客户端 `accounts.primary.accountid` 对应 `uid`，`accounts.primary.tag` 对应可见昵称，`accounts.primary.account_tag` 保留社区标识。原生 `set_identity(uid, nickname)` 分别传入身份 ID 与显示名称。此版本主界面与完整显示字符串使用 Google Play Games 图标，昵称本身不包含图标；账号类型仍使用 V2，认证仍由社区服务负责。昵称不作为鉴权或唯一身份依据。

入房响应：`{ticket,server_id,instance_id,join_attempt_id,address,port,expires_at}`。`expires_at` 为 UTC Unix 秒，`expires_in` 和 `lease_seconds` 都是秒。默认票据 30 秒，确认等待 5 秒，失败不会返回 ticket。
票据使用服务端秘密和每次尝试的随机 nonce 派生；Redis 保存 nonce、索引、状态与无 ticket 的响应，以便有效期内去重；过期后重新准备生成不同票据。

控制信封：

```json
{"version":1,"message_id":"UUID","type":"heartbeat","server_id":"UUID","instance_id":"UUID","control_session_id":"UUID","payload":{"name":"社区服","players":0,"devices":0,"capacity":8,"device_capacity":7,"public":true,"ready":true}}
```

后端先返回 welcome（新 control_session_id、heartbeat_seconds、lease_seconds），Headless 回复 hello。
支持 heartbeat / heartbeat_ack、party_state、prepare_join / join_prepared / join_rejected、ticket_cancel。
确认使用 prepare_join 原 message_id，必须属于当前控制代次；迟到确认不产生新的响应。重连会清空缓存并取得新代次，进程重启生成新实例，旧实例不能重新覆盖较新实例。
prepare_join payload 包含 ticket_index(SHA256)、UID、ASCII account_tag、中文 nickname、profiles、expires_at、join_attempt_id。只有逻辑线程确实安装后才发 join_prepared。

目录必须同时满足有效控制连接、Redis 租约、ready、public 和真实 UDP 探测。默认 10 秒心跳、30 秒租约。断线立即隐藏；租约过期后也不能返回在线。SIMPLE_PING 为单字节 11、响应为 12；仅向管理凭据授权且在允许网段内的 IP 发探测。
设备数不含服务器自己；真实玩家数为 roster 内各设备 players 之和。玩家与设备容量任一达到上限即视为满员。公开目录不会把数据库遗留标记当在线。

入房状态：申请 → 校验 → prepare_join → 对战服逻辑线程安装 → ACK → 返回 ticket → UDP 握手认领 → 绑定 UID。超时/拒绝/断线走取消。认领使用进程内单调递增的连接生命周期序号，不使用 IP 或会复用的 UDP 8 位槽位。同连接重传幂等，其他连接拒绝。缓存到期仅影响新认证；已建立连接身份不被定时撤销。控制通道断开时拒绝新的认证；既有游戏连接保留。

错误格式：`{"error":{"code":"login_expired"},"request_id":"UUID"}`。主要错误：credentials_invalid、login_expired、account_disabled、login_exists、refresh_reused、rate_limited、server_credentials_invalid、server_address_forbidden、instance_conflict、instance_stale、server_offline、room_full、version_incompatible、auth_prepare_timeout、auth_prepare_rejected、request_invalid。HTTP 对应 401/403/409/429/504/422；本地握手无可用票据时返回认证拒绝，不回退匿名。凭据重放在引擎缓存处拒绝，无额外 REST 返回码。
