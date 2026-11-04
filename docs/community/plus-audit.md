# Plus 调用与替换

| 调用方/接口 | 用途与本次处理 | 验证方式 |
| --- | --- | --- |
| `_baplus` / `SetPlus()` | 自有原生模块安装完整 PlusSoftInterface；Android 与 CMake COMMUNITY_PLUS 共用实现 | APK 原生符号、Headless 加载 |
| App 生命周期 | 无凭据立即异步完成；恢复登录最多等待 8 秒，不阻塞本地启动；只通知一次 | 离线单测、Headless 启动 |
| `GetAccountID()` / `set_identity()` | 真实后端 UID 同步原生与 Classic V1 展示状态；不会伪造官方账号 | 编译；手机登录待验 |
| `set_instance()` / `GlobalAppInstanceUUID()` | WSS 心跳确认续租，断线清空；使用本版本要求的 UTC 墙钟秒 | 真实 Headless 目录与准备 |
| `PushPublicPartyState()` | 原生置脏；逻辑线程每秒采样，网络线程合并状态变化并发送；心跳 10 秒 | 引擎目录冒烟 |
| `BuildPublicPartyStateVal()` | 通过 ClassicSoftInterface 读取房名、容量与设备语义；设备容量扣除服务器自身 | 编译及冒烟目录数据 |
| `CalcV1PeerHash()` / `V1SetClientInfo()` | V2 认证成功分支跳过旧 V1；旧分支明确拒绝，不返回假哈希 | 编译；完整 UDP 握手待验 |
| `ClientInfoQuery()` | 社区房间要求 V2，认证成功后不运行旧官方查询；旧路径仍拒绝 | 源码检查、编译 |
| `_hooks.v2_auth_request()` | 查询当前已准备的入房票据，不在轮询时发 HTTP；直连无准备则拒绝 | 接口检查；手机握手待验 |
| `_hooks.v2_auth_data()` | 六项资料元组，来自可信预投递缓存；绑定连接生命周期序号，区别可复用 UDP 槽位 | 缓存单测、真实引擎钩子 |
| `ConnectionToClient::ApplyV2AuthToken_` | 接受前认领，随后绑定 `peer_public_account_id_`、ASCII tag 与资料；票据日志删除 | 编译、真实钩子；网络接受点待验 |
| `_servermode.py` / `_accountv1.py` | 使用服务器注册状态，不再等待官方 Local 登录或云连接；支持本地播放列表、关闭队列/官方 access check | 标准 ServerController 真实 Headless 冒烟 |
| 大厅/账号工具栏 | 导向同一社区窗口，保留 server_id/instance_id；准备完成后才 connect_to_party | APK 构建；实际 UI 待验 |
| Android JNI secure_refresh | Keystore AES-GCM，配置中只保存密文和 IV；访问凭据仅内存，密码不保存 | Java/JNI 编译；真机加解密待验 |
| 广告、支付、排行榜、官方云资料 | 保留离线实现的不可用状态；不声称购买权益 | 原离线策略 7 项测试 |

`baplus._community` 保留原本地资料处理；`_community_online` 是同一 Plus 的在线扩展，不是第二套认证后门。官方 `AccountV2Handle` 不被伪造；社区资料放在 `plus.user`，原官方账号云订阅保持空。
Android 仍沿用原生 FeatureSet 初始化符号，CMake 通过 `-DCOMMUNITY_PLUS=ON` 选择源码，不需要官方库。其他未选择该选项的上游平台构建仍保留原行为。
本期启动路径关闭官方网络 warm-start；首次资源包构建仍可能访问上游资源 CAS。运行包携带固定资源，运行时不依赖该下载。
