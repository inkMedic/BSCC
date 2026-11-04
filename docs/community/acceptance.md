# 验收记录（2026-10-30）

完成的是代码实现、构建及基础联调。尚未完成“Android 注册登录 → 列表 → UDP 入房 → 两玩家真实联机”的端到端验收；按本次用户要求，没有运行玩家对局，也没有三局记录。

| 检查 | 状态 | 证据/范围 |
| --- | --- | --- |
| Python 3.13 后端 + PostgreSQL 18 + Redis | 通过 | 19 项测试，`artifacts/community/backend-tests.log`；真实 TCP Uvicorn 进程、真实数据库/缓存 |
| 注册、规范化去重、错误密码、禁用账号、退出撤销 | 通过 | 同上；中文昵称与引号资料 |
| 并发刷新、旧凭据重用、客户端 single-flight、退出不阻塞 | 通过 | 原子 Redis Lua + 客户端调度测试；客户端调度部分明确使用 fixture |
| 新后端进程读取已有账号/会话 | 通过 | PostgreSQL/Redis 跨进程持久化；未用内存替身 |
| 控制重连、旧代次、旧实例、心跳过期 | 通过 | 真实 WebSocket 协议测试 |
| UDP 可达/不可达对目录影响 | 通过 | 协议测试使用明确标记的 PingResponder；另有真实 Headless UDP 探测 |
| 入房确认、超时取消、尝试去重、版本/满员拒绝 | 通过 | HTTP/控制通道测试 |
| 独立 Linux Headless 编译 | 通过 | `artifacts/community/headless/ballisticakit_headless`，系统 Python 3.14.4；自有 Plus |
| 标准 ServerController → 注册 → 真实 UDP → 目录 | 通过 | `artifacts/community/headless-smoke.json`，真实 Linux 引擎进程，0 个玩家 |
| HTTPS/WSS 证书信任与加密通信 | 通过（Linux） | 临时测试 CA，真实校验证书，未关闭 TLS；同上 |
| 预投递进入真实逻辑线程、ACK、可信 UID 资料与重放拒绝 | 通过（真实钩子） | 同上及 headless-smoke.log 的 COMMUNITY_CLAIM_OK；不是实际 UDP 客户端握手 |
| 断线隐藏、控制线程正常退出 | 通过 | 真实 Headless 冒烟；不保留“线程仍在运行”告警 |
| 原有离线策略/本地资料 | 通过（单测） | `artifacts/community/offline-tests.log`，8 项；不等同手机本地玩法回归 |
| 无 API/凭据的真实引擎启动 | 通过 | `artifacts/community/offline-engine-smoke.log`；没有创建游戏场景 |
| APK 构建/静态资源/签名/ARM64 导出 | 通过 | `artifacts/android/apk-verification.json`、apk-signature.txt、native-exports.txt |
| 社区商店、升级、库存、联赛数据模型 | 通过（真实引擎） | native-client-probe.log；真实购买、扣费、权益、档案升级和金卡；未渲染手机界面 |
| 购买/名称竞争/比赛重复上报 | 通过（真实后端） | test_progression.py，幂等去重、余额/权限校验；参赛身份fixture明确仅用于测试 |
| 锦标赛查询、报名、原生合作会话创建 | 通过（真实引擎） | native-client-probe.log；含练习不上传，0名注入玩家、0局完整对局；详见 tournaments.md |
| 奖励结算、开箱、收件箱与溢出保护 | 通过 | 后端真实事务；原生开箱模型使用明确隔离奖励fixture，非真实玩家对局；详见 rewards.md |
| 真实 UDP 客户端的握手接受点与游戏身份 | 未执行 | 代码已接入并编译；真实钩子测试不能替代网络握手 |
| Android UI、中文输入、HTTPS、Keystore 重启恢复 | 未执行 | Java/JNI 与 Python 已打包；需要真机运行验证 |
| 双账号加入、三局、手机输入音频后台回归 | 未执行 | 用户本次明确允许暂缓游戏实际测试 |
| 公网部署与手机到服务地址 | 未执行 | 尚无指定域名、受信任证书或公网部署目标；未改生产服务/防火墙 |

最终 APK：`artifacts/android/ballistica-community-arm64-debug.apk`，SHA256：
`943a46c9be15c06516cae50068b5c01a2d12d81e8ced7d0f43adf70ac0bea221`。
本轮另存 `artifacts/android/ballistica-community-purple-gift-test.apk`，内容相同。紫券接入范围见 purple-ticket-gifts.md。当前测试包明确注入开发地址 `http://10.60.0.11:18080`；正式部署需按 operations.md 用可达HTTPS地址重建。
Linux 包依赖系统 Python 3.14/zstd/新版 libc，部署到其他发行版需在目标平台重建。
后台仅支持单 worker。服务器仅受控专用实例；不支持匿名公共房间、官方客户端、官方账户迁移、手机公网开房、NAT 穿透或分享码。社区商城、档案升级和联赛已按后续用户需求扩展，详见 progression.md。

残余上游功能入口没有被宣称全部移除；社区账号/联机入口走自有流程，广告支付等保持不可用。首次资源构建仍使用上游资源 CAS，运行期资源已随包附带。
引擎启动存在上游 GC 对 50 个对象的诊断，本次不影响注册、控制、目录或认证钩子检查。

下一步：指定可达 HTTPS API 地址并重建 APK，在两台 Android 设备验证 Keystore、目录 Ping、真实 UDP 握手和 UID 绑定，再补游戏回归。当前无自动推送、无生产部署、无破坏性 Git 操作。
