# 社区 Android 工程：构建、安装与排错

本工程以 `efroemling/ballistica` 提交
`d89c2d90cae1593899bd17a1510fef2465acb437` 为唯一上游基线。
引擎 1.8.5，build 23079，Python API 9；场景协议 HostMin 56、ClientMin 24、Max 57。
未移入 iOS 仓库的代码、资源或二进制。

当前实际构建和验收状态见 `android-community-acceptance.md`。编译成功不代表真机对局已经通过。

## 工具链与目录

Windows 负责编辑、PowerShell 入口、ADB 和产物保存；所有编译均在 WSL2 Ubuntu 的 Linux 文件系统进行。

| 项目 | 选择 |
| --- | --- |
| WSL | Ubuntu，当前执行环境为 Ubuntu 26.04 / WSL2 |
| Linux JDK | OpenJDK 21；当前实际补丁版本见 `artifacts/android/environment.json` |
| Gradle / AGP | 8.13 / 8.9.2 |
| Android SDK | compile/target 35，min 24，Build Tools 35.0.0 |
| NDK | 28.2.13676358（r28c），Linux x86_64 宿主，arm64-v8a 目标 |
| Native CMake | SDK CMake 3.22.1；依赖构建宿主 CMake 4.2.3 |
| CPython | 目标 3.14.7 Debug / Py_DEBUG；上游源码交叉编译，扩展静态链接 |
| Python 构建工具宿主 | Linux CPython 3.14.4，uv 0.9.4，clang-format 21.1.0 |
| SDL | release-3.2.24，源码构建 |
| OpenAL Soft / Oboe | 1.25.2 / 1.11.0，沿用固定引擎提交中的补丁 |
| Ogg / Vorbis | 1.3.6 / 1.3.7，源码构建，浮点 Vorbis 后端 |
| 资源 | `a-0.babuiltinassets.261028`，及脚本声明的固定资源包；`store-mobile` 集合 |

Linux SDK 保存在 `$HOME/bscn-android-sdk`，构建副本在
`$HOME/bscn-android-d89c2d90`。Windows 工作区仅接收 APK、日志及审计记录。
脚本不使用 Windows JDK/NDK 交叉编译，也不共享 Windows 和 Linux 的 `.cxx`、Gradle 缓存或目标库。

CPython 依赖版本直接由 `tools/efrotools/python_build_android.py` 固定：
OpenSSL 3.0.22、zlib 1.3.2、xz 5.8.4、zstd 1.5.7、bzip2 1.0.8、
libffi 3.8.0、libuuid 2.42.4、SQLite 3.53.4。来源和下载文件摘要见构建依赖清单。

## Windows 命令

在仓库根目录用 PowerShell 执行。首次准备需要可用的 WSL2 Ubuntu 26.04；
`-InstallSystemPackages` 会通过 WSL root 安装 Linux 构建依赖。
SDK 初始化会接受 Android SDK 许可证，并下载上表选定的 Linux 组件。

```powershell
./tools/community-android/check-environment.ps1
./tools/community-android/setup.ps1 -InstallSystemPackages
./tools/community-android/build.ps1
```

已有 Linux 环境可省略系统软件安装开关。不同发行版名称使用 `-Distribution` 参数。
本机 Windows Python 3.13 和 JDK 25 不是 Android 编译宿主；不要用其生成目标运行时或 `.pyc`。

APK 位置：`artifacts/android/ballistica-community-arm64-debug.apk`。
Debug 包由 Gradle 的 debug signingConfig 签名；私钥留在 Linux 用户的 Android 调试密钥目录，
不进入源码交付。第一次构建会生成密钥；不同机器的 Debug 签名可能不同，不能直接覆盖安装。

```powershell
./tools/community-android/build.ps1 -Clean
./tools/community-android/verify.ps1
./tools/community-android/device.ps1 -Action Install
./tools/community-android/device.ps1 -Action Launch
./tools/community-android/device.ps1 -Action Collect
# 多台设备时给出 adb devices 中的真实序列号
./tools/community-android/device.ps1 -Action Install -Serial DEVICE_SERIAL
```

`-Clean` 清理 Gradle 与引擎原生目标后重新编译；可追溯的第三方静态依赖缓存保留。
若需要重建 CPython，移动 Linux 构建目录中的 `build/python_android_arm64_debug` 至备份位置后重建；
音频依赖对应 `build/openal-android/arm64_release` 和 `arm64_release_oboe`。
不要把这些目录复制到 Windows 再复用为 Linux 缓存。

构建入口检查固定 Git HEAD，但允许本项目的工作区源码修改；完整源码摘要用于区分移植修订。
普通 `make cmake` 仍属于上游桌面入口，会引用官方 Plus，**不是本工程构建命令**。
社区构建不执行 prefab / Plus 下载目标，也不链接 `libballisticaplus.a`。

## 原生宿主及资源布局

`CommunityActivity` 继承源码构建 SDL3 的 Activity。
SDL 管理 JVM 线程关联、Surface、EGL、原生事件线程和 Android IME。
Java 在 SDL 引擎线程上将 APK 内真实脚本、标准库和资源复制到应用私有目录，
成功后才写内容版本标记，再进入 `SDL_main` / `MonolithicMain`。
复制失败会保留错误并停止启动，不以空资源继续。

引擎逻辑、资源和音频线程仍由 Ballistica 创建；Java 主线程不直接操作引擎对象。
音频焦点变化使用 SDL 事件传到引擎线程；后台通知调用已有 SuspendApp/UnsuspendApp，
并取消触点与按键。EGL swap 失败时尝试重建上下文并调用现有 ReloadLostRenderer。
引擎完整退出后结束宿主进程，避免在同一进程二次初始化 monolithic 全局对象和 Python；
Activity 销毁事件会先恢复挂起逻辑线程，使关闭流程能够执行。
这些路径仍需要实际手机验证。

触摸按指针 ID 分流到引擎 PushTouchEvent，坐标由左上原点转换为归一化左下原点。
菜单鼠标语义、摇杆及动作键由上游 TouchInput 处理；关闭 SDL 合成鼠标事件以免重复点击。
系统输入法只将提交文本送入现有 SDL 文本输入路径；组合态由 SDL/Android 保存。
Android Paint/Canvas 提供中文字体测量、纹理和 UTF-8 换行偏移。

应用数据在 `files/game-23079/`；配置、用户脚本分别在其 `config/`、`mods/` 中，
缓存使用 `getCacheDir()`。安装 UUID 仅标识本地安装，不代表登录账号。
本包使用 `.py` 源码，不携带宿主生成的 `.pyc` 或宿主 ELF 扩展。
Python 标准库来自目标 CPython 的安装输出；纯 Python 第三方模块取自上游哈希锁定的构建环境。

资源构建采用 `store --form-factor mobile`。普通 `gui-minimal` 不满足离线完整对局要求。
APK 静态检查会遍历清单中的每个 bucket 和 blob，验证 SHA256、11 个资源包及 ARM64 ELF。
资源由上游构建服务取得，仅作为构建输入；运行时离线 Plus 不建立官方账号或云传输。
资源的适用授权沿用上游 README；本地构建不等于取得公开再分发授权。

交付另含 `ballistica-community-build-inputs.tar.gz`：固定资源 CAS 文件、清单和第三方源码压缩包。
在 Linux 构建副本根目录解压可恢复这些输入；SDK/NDK、JDK、Gradle 和 Python 构建工具仍按上述步骤准备。
`tools/community-android/dependency-lock.json` 固定本次实际使用的 16 个源码/工具压缩包 SHA256，
构建在原生 APK 编译前验证这些摘要。上游 Python 包使用其自带的 requirements_build_lock.txt 哈希锁。

## 离线 Plus 的明确行为

`native/community_plus.cc` 提供本工程的 `_baplus` 初始化符号和 PlusSoftInterface，
`baplus/_community.py` 提供 Python 子系统；兼容名称不代表使用官方闭源库。

| 能力 | 本次行为 |
| --- | --- |
| 初始账号判定 | 在逻辑线程异步通知一次“判定完成”，状态始终为 signed_out |
| 本地账号 ID / 主账号 | 空字符串 / None，不伪造账号 |
| 云请求 | 回调获得 CommunicationError，future/async 抛出错误 |
| 旧版事务 | 不上传；有回调时异步返回 None（旧协议失败值） |
| 购买、登录 | 明确不可用；菜单显示中文提示 |
| 广告 | 不可用；本地游戏继续流程可以直接执行 |
| 分析、远端成就上报、商品价格 | 不发送、不持久化云状态 |
| 官方 blessing | false，无官方完整性背书 |
| 房间凭据、握手、客户端认证查询 | 原生方法明确抛出未实现错误 |

`_env.py` 在社区模式下跳过官方 bootstrap ping。
原生网络模块、LAN 查询和 UDP 连接代码保留编译；主菜单联机入口在本次离线构建中显示不可用。
六项宿主单元测试覆盖初始通知、失败回调和离线状态，不代替 Android 原生运行测试。

## 排错

* 日志：`artifacts/android/logs/`；重试前日志归档到 `history/`。
* Windows Git 若配置不可达的 localhost 代理，可对单次 clone 使用 `git -c http.proxy= -c https.proxy= clone ...`；无需修改全局代理。
* 不要在 Windows 工作区直接执行上游 Linux Makefile；入口负责同步到 WSL 文件系统。
* `android_sdk_utils` 要求 Linux SDK 内有 platform-tools，即使设备操作使用 Windows ADB。
* `ADB unauthorized`：手机解锁并接受调试授权后重试；无设备时命令会失败，不生成通过记录。
* 原生加载错误：检查 APK 中的 ARM64 库和手机 `ro.product.cpu.abilist`，收集 crash buffer。
* 启动或资源错误：保留 `logcat.txt`、APK SHA256、清单、源码摘要；不要用旧版本资源覆盖当前包。
* 调试证书冲突：先备份应用数据，再决定卸载旧包或使用原签名密钥；安装脚本不会自动卸载。

## 真机验收步骤

安装脚本只执行安装、启动和日志采集，不自动把交互项目记为通过。

1. 核对设备为 ARM64、Android API 24+、GLES 3.0+，保存设备信息和 APK SHA256。
2. 启动观察真实引擎菜单；确认无 Python 初始化错误及关键资源缺失。
3. 手机手动开启飞行模式，关闭 Wi-Fi；强停并重启应用，确认仍可进入菜单及本地玩法。
4. 选择本地玩法，例如合作模式的基础关卡；加入触屏玩家，完成胜负结算并返回菜单。
5. 同时按住摇杆和动作键，移动、抬起、系统取消触摸后确认无卡键。
6. 在玩家名字/资料文字字段输入英文、中文组合文本，分别提交、取消、再次输入；确认无乱码与重复字符。
7. 连续三次 HOME → 恢复，每次检查场景、输入、音效；再测试锁屏、返回、重新启动。
8. 使用其他音频应用/系统事件造成焦点丢失与恢复，确认音频正确暂停恢复。
9. 执行 `device.ps1 -Action Collect` 保存日志，记录每项“通过/失败/未执行/受环境阻塞”。
