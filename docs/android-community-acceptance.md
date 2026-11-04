# Android 实际交付与验收记录

验收日期：2026-10-30（Asia/Shanghai）。

**已完成 ARM64 Debug APK 清洁构建、重复构建和静态验收；未完成真机功能验收。**
Windows ADB 实际枚举结果为 0 台授权设备，安装尝试已执行但受设备环境阻塞。
不能据此宣称已经显示菜单、完成一局或通过输入/音频/生命周期测试。

## 交付标识

| 项目 | 实际值 |
| --- | --- |
| 上游源码 | efroemling/ballistica，`d89c2d90cae1593899bd17a1510fef2465acb437` |
| 移植修订 | 当前工作区修改；逐文件摘要在 build-source-inventory.json 和源码包 SOURCE-STATE.json |
| 引擎 | 1.8.5 / build 23079 / API 9 |
| 协议 | HostMin 56 / ClientMin 24 / Max 57 |
| 目标 | ARM64，Android 7.0 / API24 起，GLES 3.0+，普通横屏手机 |
| APK | `artifacts/android/ballistica-community-arm64-debug.apk` |
| APK 大小 | 93,730,303 字节 |
| APK SHA256 | `61b4aaa3f7e272b180e923fb1941020f9b2e16a617f5c4f3f9c37029b96af7fa` |
| 应用 ID | `org.ballistica.community` |
| 签名 | Android Debug，APK v2 签名验证通过 |
| 手机型号 / Android 系统 | 无连接设备，未取得 |
| 自建测试服务器 | 未提供、未连接；未验证 UDP 直连 |

工程源码在 `ballisticakit-android/` 及相关引擎修改中；
完整源码归档为 `artifacts/android/ballistica-community-source.tar.gz`，
精确资源及依赖源码输入为 `ballistica-community-build-inputs.tar.gz`。
源码包不包含调试签名私钥。工具链及复现步骤见 `android-community-build.md`。

## 验证结论

| 验证项目 | 状态 | 实际证据与范围 |
| --- | --- | --- |
| 固定源码及环境审计 | 通过 | android-community-audit.md、environment.json |
| Windows → WSL 构建入口 | 通过 | 实际通过 build.ps1 / build.ps1 -Clean 调用 Linux 工具链 |
| 清洁构建 | 通过 | Gradle clean 与 externalNativeBuildCleanDebug 后，36 项任务执行成功；clean-build.log |
| 重复构建 | 通过 | 后续构建 exit=0，APK SHA256 一致；logs/gradle.log、apk-sha256.txt |
| 依赖哈希锁 | 通过 | 16 个源码/工具压缩包匹配；logs/dependency-lock.log、dependency-lock.json |
| ARM64 CPython 编译 | 通过 | 3.14.7 Py_DEBUG；libpython3.14d.a，_zstd 静态包含检查通过；Python 构建历史日志 |
| Python 及引擎原生模块内容 | 通过 | 导出 _babase、_bascenev1、_bauiv1、_baclassic、_baplus，以及 _ssl、_sqlite3、_ctypes、_zstd 等；native-exports.txt |
| APK 架构及布局 | 通过 | 3 个 ARM64 ELF，1352 个 Python 源文件；apk-verification.json |
| 游戏源码与交付一致 | 通过 | 416 个仓库游戏脚本逐字匹配 APK；apk-source-match.json |
| 真实资源打包 | 通过 | 11 个固定包、1762 个传递引用 blob/bucket，逐个 SHA256 匹配；apk-verification.json |
| 签名与 Manifest | 通过 | apksigner verify、aapt2 dump badging；apk-signature.txt、apk-badging.txt |
| 原生链接与 16KB 对齐 | 通过 | main ELF 的 LOAD 对齐 0x4000；native-elf.txt |
| Plus 二进制隔离 | 通过（静态） | 原生链接规则无官方 Plus archive，动态依赖无官方 Plus；plus-link-audit.txt、native-elf.txt；自有符号见 native-exports.txt |
| 离线 Plus 行为契约 | 通过（宿主单测） | 6 项单元测试通过；offline-unit-tests.txt。测试替代依赖，不能证明手机 native 初始化 |
| ADB 安装 | 受环境阻塞 | 已执行安装入口；授权设备数 0；device-status.json、device-install-attempt.txt |
| 真机原生库加载、Python 初始化/导入 | 受环境阻塞，未执行 | 无设备；导出符号只能作为静态证据 |
| 真实菜单可操作 | 受环境阻塞，未执行 | 无设备，未取得游戏画面 |
| 断网后启动及本地开局 | 受环境阻塞，未执行 | 无设备，未在飞行模式运行 |
| 完整本地一局及结算返回 | 受环境阻塞，未执行 | 无设备，没有对局记录 |
| 多点触控及取消释放 | 受环境阻塞，未执行 | 实现已编译，未在手机操作 |
| 中文组合输入、确认、取消、再次输入 | 受环境阻塞，未执行 | SDL IME / 系统字体桥接已编译，未取得输入法结果 |
| 游戏音效与音频焦点 | 受环境阻塞，未执行 | OpenAL/Oboe 已编译，未实际听测 |
| 连续三次后台恢复、Surface 重建及重启 | 受环境阻塞，未执行 | 实现已编译，未取得手机循环结果 |
| 手机运行日志无持续错误 | 受环境阻塞，未执行 | 无进程日志；不能把编译日志当运行日志 |
| 社区账号、目录、认证、UDP 联机 | 未执行；后台未实现 | 明确离线，不提供假登录/假服务器列表；接入位置见 integration 文档 |

历史构建曾失败于工具缺失、NDK 编译类型、Vorbis、Py_DEBUG 和链接配置，
均已修复至上述成功构建。失败日志保存在 logs/history，不计入当前通过项。

## A01–A13 对照

| 编号 | 本次交付状态 |
| --- | --- |
| A01 | 审计及证据已交付 |
| A02 | PowerShell 环境、准备、Debug/清洁构建、验签、ADB 入口已实际执行 |
| A03 | Gradle、Manifest、Activity、JNI、Debug 签名已构建；设备安装待验 |
| A04 | 目标 CPython/依赖已编译打包；手机导入待验 |
| A05 | 公开 Platform / AppPlatform / SDL 宿主已编译；系统服务行为待验 |
| A06 | 自有 PlusSoftInterface/Python 离线兼容实现已链接并通过宿主契约测试；手机启动待验 |
| A07 | 真实引擎与 GLES 渲染器完整编译链接；菜单/持续渲染待验 |
| A08 | 真实脚本、标准库及资源已打包并校验；手机资源装载待验 |
| A09 | 复用引擎触屏控件，事件/多指/取消接线已编译；手机操作待验 |
| A10 | SDL 系统 IME、JNI 字体、音频焦点与 OpenAL/Oboe 已编译；中文/听测待验 |
| A11 | 暂停、恢复、上下文恢复、退出重启处理已编译；三次循环待验 |
| A12 | 网络模块保留并构建；账号、目录、认证与 UDP 边界已记录，无联机成功声明 |
| A13 | 清洁构建、APK/签名/静态验证已完成；真机验收受硬件阻塞 |

## 尚未完成及已知限制

1. 设备验收是明确外部阻塞。本包是实际完整引擎构建，仍不能标为“手机游戏验收完成”。
2. 社区云、登录、购买、公开房间发布和入房认证未实现；在线入口显示不可用。
   原生旧版握手兼容方法主动报未实现，不能据此声称可连接官方或社区服务器。
3. 本次仅生成 ARM64 Debug APK；未做其他 ABI、Release、性能、耗电及广泛机型兼容验证。
4. 首次启动需要在应用私有存储展开 APK 内脚本/标准库/资源，慢速存储的实际时延未测。
5. Android 系统输入法、音频焦点和 EGL 恢复在不同手机上的差异尚未验证。
6. 第三方资源来自固定上游资源服务；交付的资源输入归档用于保留准确版本，原始美术制作文件未在公开仓库提供。

接入设备后执行 `device.ps1 -Action Install`，按构建文档逐项完成真实测试，
将这里的待验项依据日志、截图/录像和实际交互结果更新；不能仅因安装命令返回成功而改为全部通过。
