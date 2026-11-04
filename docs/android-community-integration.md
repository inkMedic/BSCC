# 后续社区账号与联机边界

固定基线与资源、协议版本见构建文档。本次没有自建测试服或已连接真机，
没有任何联机成功结论。不要将离线兼容状态用于模拟登录或服务器目录。

| 接入能力 | 具体位置与约束 |
| --- | --- |
| 社区账号状态 | `baplus/_community.py: OfflineAccounts`；以真实账号替代 signed_out，维护 primary 与 on_primary_account_changed_callbacks；在引擎逻辑线程同步，初始化判定完成通知仍只能发送一次 |
| HTTPS 服务器目录 | `OfflineCloud` 为传输边界；新建社区目录 DTO/服务，以真实失败结果完成回调；在 `bauiv1lib/mainmenu.py` 的联机入口接 UI，不使用官方地址 getter |
| 申请入房凭据 | 在选定服务器后由 HTTPS 服务发出短期、有目标服务器约束、可验证的凭据；取得后才进入连接流程，失败应返回 UI |
| 客户端握手 | `scene_v1/connection/connection_to_host.cc` 的连接协商及客户端资料封装；`CommunityPlus::CalcV1PeerHash`、`V1SetClientInfo` 当前明确拒绝，不能把空 ID 当认证成功 |
| 服务端认证 | `scene_v1/connection/connection_to_client.cc` 的客户端资料/认证处理、`classic/support/classic_app_mode.h` 的 ClientAuthMode；必须验证签名、有效期、目标和重放；与社区 Python 主服务器协同设计 |
| 实际 UDP | `base/networking/network_reader.cc`、`network_writer.cc`、`scene_v1/connection/connection*.cc`；代码保留，Android API 24+ 使用系统 ifaddrs；未验证直连 |

本次 CommunityPlus::ClientInfoQuery 没有调用官方主服务器，也没有伪造验证结果。
PushPublicPartyState 收到本地人数变化时不发布；后续应只在真实目录服务可用、
服务器明确授权发布时接通。未使用的上游私有 Android message bus 不参与社区目标编译；
此宿主通过 SDL/JNI 提供等价平台入口，网络引擎没有因此删除。

修改协议前应同时固定客户端和自建服务器版本。当前 HostMin 56、ClientMin 24、Max 57
不代表可随意连接所有旧版本：上游还排除开发协议区间，且 Plus 身份机制尚未迁移。
社区凭据的字段及验证策略应做单独的兼容性设计，避免把现有官方凭据格式当作社区身份凭证。
