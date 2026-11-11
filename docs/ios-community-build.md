# 社区 iOS 构建

本目标直接构建本仓库的引擎与 `src/ballistica/plus/community_plus.cc`，不链接官方
Plus，不引入 VR。引擎基线与 Android 相同：1.8.5 / build 23079 / API 9。
参考了 https://github.com/RYDE-PLAY/BombSquadVR-iOS 的依赖与宿主分层思路，
没有复制其 VR、闭源 Plus 适配或应用代码。

## 环境与命令

需要 Apple Silicon Mac、完整 Xcode（接受许可证并选中 Developer 目录）、
Python 3.14、uv、CMake 3.28+、clang-format、rsync。目标为 iOS 16+ ARM64。

```bash
make env VENV_LOCK=pconfig/requirements_build_lock.txt
.venv/bin/python tools/community-ios/build.py
```

默认 Release、真机 SDK、无签名。成功后产物：
`artifacts/ios/ballistica-community-arm64-unsigned.ipa`，旁边 JSON 记录摘要与构建信息。
未签名 IPA 需要用自己的签名工具、证书和配置文件重签后安装，不能直接安装或上传 TestFlight。
构建脚本不会把模拟器产物命名为 IPA，也不会在缺失资源时输出安装包。

第一次构建从源码构建 SDL 3.2.24、Ogg 1.3.6、Vorbis 1.3.7、OpenAL Soft 1.25.2；
这四个下载均校验固定 SHA256。Python 3.14.7 沿用上游 Apple 脚本，BeeWare 固定到
`5cc6b88127581ccfa0cdcbaf264d698076fd43d3`，避免浮动分支版本变化。
Apple Python 脚本的其余输入仍沿用其原有下载与校验策略。
构建和第三方源码留在 `build/`，不会进入 Git。

指定后端地址，允许在本地网络使用 HTTP（生产应配置 HTTPS）：

```bash
.venv/bin/python tools/community-ios/build.py --api-url https://your-api.example
.venv/bin/python tools/community-ios/build.py --api-url http://192.168.1.10:8000 --allow-http
```

HTTP 开关只设置社区传输的显式允许项；不全局放宽 ATS。iOS 会弹出局域网访问提示。
API 地址会进入 Info.plist，请勿在地址中放入密钥或密码。

使用已配置好开发证书和 provisioning profile 的 Apple Team：

```bash
.venv/bin/python tools/community-ios/build.py --team-id YOUR_TEAM_ID \
  --bundle-id your.unique.community.ios --api-url https://your-api.example
```

签名包仍为开发用途，不等于 App Store / Ad Hoc 分发导出；是否可装取决于所用配置文件。
首次自动签名可在生成的 `build/community-ios/iphoneos/BallisticaCommunityIOS.xcodeproj`
中完成账号与设备配置。私钥、证书和 provisioning profile 不进入源码。

```bash
# 独立的模拟器构建与 ZIP（不能在真机安装）
.venv/bin/python tools/community-ios/build.py --sdk iphonesimulator
# 资源服务不可用时只验证原生编译，不输出 IPA
.venv/bin/python tools/community-ios/build.py --compile-only
```

## 资源客户端更新

已从上游 `efroemling/ballistica` 提交 `2842f7b526142698c2a56c6440f411b15022f12d`
合并 `tools/bacommontools/bacloud.py` 与 `tools/bacommon/bacloud.py` 的 v30 更新：
压缩签名下载先以 zstd 流式解码，再校验解码内容的大小与 SHA256；上传请求回传存储 form code。
会话实现与现有版本相同，未变更游戏引擎或场景协议。
本地回归命令：`.venv/bin/python tests/test_bacommontools/test_bacloud_downloads.py`。

## 在 Xcode 中选择设备运行

本地 workspace：`ballisticakit-ios/BallisticaCommunity.xcworkspace`。
它引用 `build/community-ios/iphoneos/BallisticaCommunityIOS.xcodeproj`；生成的工程不要手动提交到 Git。
首次准备或重新生成：

```bash
.venv/bin/python tools/community-ios/build.py --configure-only \
  --team-id YOUR_TEAM_ID --api-url http://YOUR_MAC_LAN_IP:8000 --allow-http
open -a Xcode ballisticakit-ios/BallisticaCommunity.xcworkspace
```

选择 Scheme `BallisticaCommunity`，选择已配对的 iPhone，然后按 ⌘R。
Scheme 默认使用已验证的 Release 配置，资源在签名前写入 app bundle。
目标已开启 Automatically manage signing，签名身份为 Apple Development。
如果 Xcode 报 `No Account for Team`，在 Xcode Settings → Accounts 登录对应 Apple ID，
或在目标 Signing & Capabilities 中选择可用的 Team；证书存在并不意味着 Xcode 已登录账号。
重新生成工程时，请把所用 Team ID 传入上述命令以保留选择。

### 本机测试后端

本机已安装锁定的 Python 3.13 后端依赖，使用独立 PostgreSQL 与 Redis 实例：

```bash
community-backend/.venv/bin/python scripts/community-backend-local.py start
community-backend/.venv/bin/python scripts/community-backend-local.py status
community-backend/.venv/bin/python scripts/community-backend-local.py stop
```

脚本首次生成仅本机使用的随机数据库密码和服务密钥，保存在已忽略的
`community-backend/.env`（权限 600）；不覆盖已有配置。数据和日志保存在
`artifacts/community/local-backend/`。重复 start 复用现有实例；stop 保留数据。
API 监听 `0.0.0.0:8000`，PostgreSQL/Redis 分别仅监听 `127.0.0.1:55432` 和
`127.0.0.1:56379`。手机与 Mac 在同一网络时可访问
`http://192.168.50.243:8000/health/ready`；应返回 `{"status":"ready"}`。
Mac IP 变化后须重新生成 Xcode 工程中的 API 地址。

本次（2026-11-05）后端迁移与两个地址的健康检查通过。按最近证书选择的 Team 为
`SZF295SYT6`，但 Xcode 签名预检返回 `No Account for Team` 和缺少开发 profile；
需要用户在 Xcode 登录该 Team 的账号或选择其他有效 Team，再进行真机运行。

## 固定资源复用

使用 Android 的 `store-mobile` 资源集合和同一校验脚本。
如果服务器拒绝旧版 bacloud 客户端，在仓库根目录恢复此前 Android 交付的
`ballistica-community-build-inputs.tar.gz` 中 `.cache/asset_bundle/`、`.cache/assetdata/`
（以实际归档路径为准），然后重新构建。不要用别的引擎版本资源代替。
可以先执行 `.venv/bin/python tools/community-android/ensure-assets.py` 验证缓存。
资源、Python 标准库、游戏脚本统一放在只读 app bundle；配置与 mods 使用
Application Support，缓存使用 Caches，禁止写 bundle 或携带宿主的 `.so` / `.pyc`。
资源使用和分发授权仍遵循上游要求。

## 宿主行为和真机验收

SDL UIKit 宿主提供 GLES3、触摸、键盘/IME、控制器与生命周期事件。
共享 Android 的多指触摸分流和后台 SuspendApp/UnsuspendApp 路径；iOS 的平台对象
使用 CoreText 字体测量、换行与纹理生成。Keychain 保存 refresh token，TLS 使用 certifi；
主线程启动时缓存屏幕类型和安装 ID，后台 Python 工作线程不执行同步主线程跳转。

以下项目必须在实际 iPhone/iPad 上验收，编译通过不代表这些行为通过：

1. 冷启动、中文菜单、离线本地对局、结算返回。
2. 多指摇杆/动作键，抬起、取消触摸、前后台后无卡键。
3. 中文组合输入、密码输入、取消、再次编辑，检查字体方向与换行。
4. 三次前后台、锁屏恢复、音频中断与恢复。
5. 后端注册/登录、重启恢复登录、退出清除 Keychain、服务列表和实际联机。
6. 局域网权限拒绝/允许，以及 HTTPS 证书校验失败行为。

当前目标使用系统 OpenGLES（已被 Apple 弃用但仍可在当前 SDK 编译）；尚未移植 ANGLE/Metal，
陀螺仪、官方 Game Center/StoreKit 和官方网页登录不属于社区宿主的已实现功能。

## 本次构建记录（2026-11-05）

- macOS / Xcode 27.2（27B52），iPhoneOS SDK 27.2，最低 iOS 16.0。
- iPhone ARM64 Release：`BUILD SUCCEEDED`；Python 3.14.7 与全部原生依赖构建通过。
- bacloud v30 下载成功；11 个固定资源包、1762 个 CAS blob 校验通过。
- IPA 大小：70,011,404 字节；校验 ZIP 完整性与 3225 个 payload 文件 SHA256。
- SHA256：`327e6416114368059325607313ce2e9bb8ee06f47361179290e76d4a42adcf53`。
- 本机测试 API：`http://192.168.50.243:8000`，显式允许开发 HTTP；该 IP 可能随网络变化。
- 后续已初始化并启动本机后端（`0.0.0.0:8000`），回环与局域网 ready 检查通过。
- bacloud 下载回归 5 项通过，社区离线策略 8 项通过，`git diff --check` 通过。
- 包未签名；未执行真机安装、启动或联机验收，也未验证模拟器与 Apple Team 签名路径。
- 日志：`artifacts/ios/logs/build-iphoneos.log`；压缩包复核：`artifacts/ios/ipa-verification.json`。


## 图标、触屏光标与文字方向修订（2026-11-05）

应用显示名称为“炸弹小分队”。`ballisticakit-ios/Assets.xcassets/AppIcon.appiconset`
包含用户提供图片对应的 iPhone/iPad 和 1024px 图标，均为不透明 PNG，Xcode 用 AppIcon 资源集编译。

iOS 的 SDL adapter 与 UIKit adapter 一样禁止引擎光标，防止关闭硬件光标后仍绘制软件箭头；
其他平台的光标策略不变。
CoreText 渲染仅将 TextPacker 的基线坐标转换一次，不再反转已经为从上到下排列的像素行。
共享的 `text_renderer_apple.h` 同时供 iOS 平台和 macOS 字形回归程序使用。

```bash
clang++ -std=c++23 -fobjc-arc -Iballisticakit-ios \
  tools/community-ios/test_text_renderer.mm \
  -framework Foundation -framework CoreText -framework CoreGraphics -framework ImageIO \
  -o /tmp/bscn-test-text-renderer
/tmp/bscn-test-text-renderer /tmp/bscn-text-renderer.png
```

该检查验证 F 的上横与左竖方向、gj 的下伸笔画，并可输出中英文字形预览；
它不代替手机上的实际显示与触屏验收。

本次修订已通过 iPhone ARM64 Release 编译、AppIcon 资源编译和开发签名验证。
保留用户在 Xcode 选择的 Team `3T73793UR3`；生成的 app 已核对显示名为“炸弹小分队”，
并包含 `CFBundleIconName=AppIcon` 与 `Assets.car`。
签名包路径为 `artifacts/ios/ballistica-community-arm64-signed.ipa`，
当前 SHA256 见同名 `.json` 构建记录。
真机上的触摸与最终文字显示仍待重新运行验收。


## iOS 游戏音频

SDL 宿主在启动 OpenAL 之前将 `AVAudioSession` 设为 `Playback`，允许和其他应用的声音混播。
这样静音开关不会静音游戏音效和音乐。没有开启后台音频能力，退到后台仍沿用引擎的音频暂停流程。
真机测试时，请在游戏播放音乐时调节控制中心的媒体音量，并检查静音开关、前后台切换和来电中断后的声音。

本次音频修改已通过 iPhone ARM64 Release 编译和开发签名验证，真机音量行为待确认。
