# 社区 Plus 与后端

本次范围为补齐代码和基础验证。游戏内双账号加入、手机 HTTPS/Keystore 行为、连续三局、输入音频回归按用户要求暂不执行；不能据此宣称真实联机验收完成。

代码入口：

| 内容 | 位置 |
| --- | --- |
| 后端、管理 CLI、迁移、锁定依赖 | `community-backend/` |
| 原生 Plus | `src/ballistica/plus/community_plus.cc` |
| 客户端、HTTPS、票据缓存、Headless 控制 | `src/assets/ba_data/python/baplus/_community*.py` |
| 登录/注册/目录/入房界面 | `src/assets/ba_data/python/bauiv1lib/community.py` |
| PowerShell 总入口 | `scripts/community.ps1` |
| Headless 构建/启动 | `scripts/build-community-headless.sh`、`scripts/run-community-headless.sh` |
| 真实后端和 Headless 冒烟 | `scripts/community-headless-smoke.py` |

构建产物：Android `artifacts/android/ballistica-community-arm64-debug.apk`；Linux Headless `artifacts/community/headless/`。
后端测试记录 `artifacts/community/backend-tests.log`；真实引擎检查 `artifacts/community/headless-smoke.json` 及相邻日志。

进一步说明：`baseline.md`、`plus-audit.md`、`protocol.md`、`operations.md`、`acceptance.md`。
内网真机反馈后的修正和当前手动验证步骤以 `lan-corrections.md` 为准；此前验收记录不代表修复版手机回归已通过。
