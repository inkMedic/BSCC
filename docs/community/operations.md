# 开发与部署

## 1. 后端

后端 Python 3.13；引擎 Linux 系统 Python 3.14、Android 内嵌 Python 3.14，互不混装。首次安装示例（Linux/WSL）：

```bash
cd community-backend
python3.13 -m venv ~/bscn-backend-py313
~/bscn-backend-py313/bin/pip install -r requirements.lock
cp .env.example .env
# 把 COMMUNITY_SECRET 改为 secrets.token_urlsafe(32) 生成的随机值。
docker compose up -d --wait
~/bscn-backend-py313/bin/alembic upgrade head
~/bscn-backend-py313/bin/uvicorn community_backend.app:create_app --factory --host 0.0.0.0 --workers 1
```

默认 Compose PostgreSQL 55432、Redis 56379，仅绑定回环。当前机器基础测试实际使用 WSL 已安装 PostgreSQL 18 的 5432、Redis 6379，数据库 community_test、Redis 15（HTTP 测试）及 14（引擎冒烟）；这些与 Compose 地址不同。使用本机服务须在 .env 相应修改地址。开发 role/database 初始化 SQL 为 `scripts/community-dev-db.sql`，需要 PostgreSQL 管理员执行；不会删除已有数据库。

生产应给数据库和 Redis 独立访问控制，替换示例密码；.env 权限 600。Dockerfile 使用已锁依赖，以非 root 用户启动。迁移在部署前单独执行。不使用 `docker compose down -v`，保留数据卷。数据库/Redis 不暴露公网。
本实现只支持一个 Uvicorn worker；WSS 路由和待确认 Future 在该进程，不能直接横向扩 worker。Redis 用于会话/轮换/限流/目录租约，进程重启不从遗留租约恢复列表，必须等 Headless 重新认证。

## 2. HTTPS/WSS 与游戏 UDP

正式环境使用域名及受信任证书，把 HTTPS 和 `/v1/servers/control` WebSocket 转发到单 worker；Nginx 对控制通道配置 Upgrade/Connection，read timeout 大于 30 秒。也可直接给 Uvicorn 加 `--ssl-certfile ... --ssl-keyfile ...`。
游戏另开放 UDP 43210（或配置端口）。普通 HTTP 反向代理不会转发游戏 UDP。配置 `COMMUNITY_ALLOWED_SERVER_NETWORKS` 为受控服务器实际 IP/网段；地址须 IP 字面量以避免 DNS 重绑定探测。
`COMMUNITY_CA_FILE` 可指定私有 CA，始终校验证书。Android 默认使用包内 certifi CA；不全局关闭 TLS。

## 3. 管理与 Headless

在后端目录、相同 .env 下：

```bash
~/bscn-backend-py313/bin/python -m community_backend.cli create-server --name '社区测试服'
# 仅本次输出原始 key；安全写入单独 600 权限的服务器环境文件。
~/bscn-backend-py313/bin/python -m community_backend.cli revoke-server SERVER_UUID
```

服务器环境（不要提交真实 key）：

```bash
export COMMUNITY_API_URL=https://community.example.org
export COMMUNITY_SERVER_ID=管理员签发的UUID
export COMMUNITY_SERVER_KEY=管理员签发的随机key
export COMMUNITY_SERVER_ADDRESS=受控服务器可达IP
export COMMUNITY_GAME_PORT=43210
export COMMUNITY_SERVER_NAME=社区测试服
export COMMUNITY_CAPACITY=8
bash scripts/run-community-headless.sh
```

构建：`bash scripts/build-community-headless.sh`。复用当前机器 `~/bscn-android-d89c2d90` 中固定引擎工具链/资源缓存；非该机器先完成原 Android 的 setup 流程。需要 GCC 15、CMake、pkg-config、libzstd-dev、系统 Python 3.14 开发库；构建 headless 目标不要求 SDL/OpenAL。
Headless 自启动使用单独 server key，无玩家登录。标准 ServerController 等注册成功后启动本地默认 FFA 播放列表。没有 share code、官方队列、官方 access check。默认数据/config/cache 独立于原游戏目录。
运行包是本机 Linux x86_64 构建，依赖系统 libpython3.14、libzstd、libstdc++ 和 glibc；不是所有发行版可直接运行的静态包。其他 Linux 主机建议按相同说明在目标系统编译。
第一次生成 `store-headless` 资源可能访问上游资源 CAS；运行时携带完整 null 口味，不需要官方资源网络。原 Android 仍用 store-mobile。

## 4. Windows 与 Android

```powershell
./scripts/community.ps1 -Action Check
./scripts/community.ps1 -Action Services
./scripts/community.ps1 -Action Migrate
./scripts/community.ps1 -Action Backend
./scripts/community.ps1 -Action HeadlessBuild
./tools/community-android/build.ps1 -ApiUrl 'https://community.example.org'
./tools/community-android/device.ps1 -Action Install
```

开发 HTTP 仅显式开启：`build.ps1 -ApiUrl 'http://局域网开发地址:8000' -AllowHttp`；Headless 设置 COMMUNITY_ALLOW_HTTP=1。普通构建默认没有 API URL，可进入本地模式并看到配置错误，不会连到未知服务。
手机进入主菜单“联机”或账号按钮 → 输入登录名、密码（隐藏显示）、昵称 → 注册/登录 → 刷新 → 选择服务器。Keystore 存刷新凭据密文，访问凭据仅内存；切换账号/退出清除待入房状态。直接输入 IP/收藏尚不作为社区入口，缺少准备票据会拒绝；不能用它绕过认证。
手机不能用 127.0.0.1 访问电脑。需使用手机可达的电脑 LAN 地址，并确认 Windows 防火墙及 WSL 转发；本次未选定手机/公网地址、未开放入站规则。正式测试优先可达 Linux 主机与受信任 HTTPS 域名。

## 5. 验证和排错

```bash
cd community-backend
~/bscn-backend-py313/bin/python -m pytest -q
cd ..
~/bscn-backend-py313/bin/python scripts/community-headless-smoke.py
```

测试仅使用 community_test 和独立 Redis 库 15/14；测试数据库须先建立。重复测试只清理专用库 15 的 rate:* 限流键，不清空开发/生产服务。冒烟创建临时证书并真实校验 HTTPS/WSS，启动无玩家 FFA 等待大厅，不运行对局。
目录为空：依次检查 `/health/ready`、server key/允许 IP、WSS welcome/hello、ready/public、实际游戏 UDP、版本/资源四元组。控制断线会立即隐藏，超过租约不再在线；backend 重启后 Headless 每 3 秒尝试重新注册，当前实例保留、新控制代次清缓存。
`auth_prepare_timeout`：检查逻辑线程能否处理 pushcall，以及当前控制连接；不要直接放开匿名。`instance_stale`：旧进程正在尝试覆盖新进程，停止旧进程。限流 429 等待一分钟。
日志关联 request_id、join_attempt_id、server_id、instance_id 和引擎连接 ID；不打印密码、原始 ticket/token/key。初始化资源产生的上游 GC 诊断不代表账号失败。
