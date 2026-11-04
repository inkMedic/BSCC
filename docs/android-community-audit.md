# A01 源码及依赖审计

审计基线：`d89c2d90cae1593899bd17a1510fef2465acb437`（上游提交说明 v1.8.5）。
最初 `bscn` 为空目录，不是 Git 仓库；已克隆用户指定主项目，修改前无工作区变更。
此提交没有 `.gitmodules` 和仓库内 `AGENTS.md`。父目录检查也没有发现适用的 AGENTS.md。
iOS 参考项目的网页列出不同 Ballistica 子模块版本 `2ff3b4a`；未复制或混用。

## 固定标识

| 内容 | 值及源码位置 |
| --- | --- |
| 引擎版本 / build / Python API | 1.8.5 / 23079 / 9；`src/ballistica/shared/ballistica.cc` |
| 场景协议 | HostMin 56 / ClientMin 24 / Max 57；`scene_v1/scene_v1.h`，另有开发区间排除规则 |
| 工具 Python | 3.14；`tools/efrotools/pyver.py` |
| Android Python | CPython 3.14.7 / API 24；`tools/efrotools/python_build_android.py` |
| 内置资源 pin | `a-0.babuiltinassets.261028`；`pconfig/projectconfig.json` |
| 离线资源集合 | `store-mobile`，包含脚本声明的 11 个包、41 种语言及 builtin fallback 纹理 |

## 实际缺口及对应处理

| 缺口证据 | 处理位置 |
| --- | --- |
| 仓库只有 ballisticakit-cmake / ballisticakit-windows；没有 Gradle 工程、Manifest、Java Activity | 新增 `ballisticakit-android/`；Gradle 实际执行过 Manifest、Java 和 dex 编译 |
| `core/platform/platform.cc` 通用 Android 分支 include 不存在的 `platform_android.h` | 新增公开 PlatformAndroid；应用私有路径、安装 UUID、语言及 JNI 字体服务 |
| `base/support/base_build_switches.cc` include 不存在的 AppAdapterAndroid / AppPlatformAndroid | 社区 Android 选择公开 AppAdapterSDL；新增 AppPlatformAndroid 使用明确不可用的购买/平台登录默认行为 |
| 仅有 Android typed message bus，生成文件/私有宿主不完整 | 社区 target 不编译未使用的私有宿主 bus；使用 SDL/JNI 的完整 Activity/Surface/input 桥接 |
| `networking_sys.h` Android 分支引用缺失 ifaddrs_android_ext.h | API 24+ 使用系统 ifaddrs.h；保留旧 API 条件分支，社区 minSdk 为 24 |
| 上游 CMake 是桌面入口，依赖系统 SDL/OpenGL/Python，并无条件链接 prefablib/libballisticaplus.a | 新 Android CMake 复用固定上游源文件列表，独立定义 ARM64 依赖；不执行该桌面链接规则 |
| CPython Android 工具硬编码 `/home/ubuntu/.py314/bin/python3.14` | 新增 BA_ANDROID_BUILD_PYTHON；本机使用 Linux `/usr/bin/python3.14`；目标仍实际编译 3.14.7 |
| 初始仓库只有游戏脚本，无真实纹理、模型、地图、音频 CAS 文件 | 实际执行 `asset_bundle_build store --form-factor mobile`，取得完整固定资源集合 |
| `gui-minimal` 只提供启动基础，其他资源首次运行下载 | 打包完整 store-mobile；不以 minimal 当完整离线游戏 |
| SDL 适配器没有把 Android finger 事件转给 TouchInput | 新增指针 ID 映射、坐标转换、取消及失焦释放 |
| SDL 桌面适配器仅有可见性 active 状态，缺少手机后台 Suspend/Unsuspend 和 OpenAL 焦点处理 | 新增 Android lifecycle / audio focus 事件；复用引擎 suspend，EGL 错误恢复走现有 renderer reload |
| Android 系统字体服务缺失 | JNI Paint/Canvas 渲染，UTF-16/UTF-8 转换和 Unicode 行分割 |
| NDK Clang 暴露隐式析构时引用不完整类型 | EmptyAppMode、UIV1FeatureSet、ClassicAppMode、LightNode 使用源文件内定义的析构函数 |
| OggStream 与 SoundAsset 使用不同 Vorbis 后端条件 | OggStream 改为与既有 BA_USE_TREMOR_VORBIS 一致；社区定义为 0，链接可追溯 libvorbisfile |

构建中发现的解析、头文件、类型及原生目标错误均记录于 `artifacts/android/logs/history/`。
以最新构建与验收记录为准；历史失败记录不会被标成通过。

## 官方 Plus 的入口与本次隔离

* `Makefile` 的 prefab lib 规则包括 `libballisticaplus.a`、Windows Plus `.lib/.pdb`，经 efrocache 获取。
* `ballisticakit-cmake/CMakeLists.txt` 的两个目标链接 `prefablib/libballisticaplus.a`。
* `src/codegen/Makefile` 调用 `gen_monolithic_register_modules`；
  `tools/batools/pcommands2.py` 为 `_baplus` 生成 `DoPyInit__baplus` 转发。
* Python `baplus/_appsubsystem.py` 的原始实现将账号、购买等调用转发至 `_baplus`；
  公开 `_cloud.py` 只有可替换传输接口。
* `babase/_app.py` 在 Plus 存在时等待其初始登录判定完成通知。
  仅仅放一个空 `_baplus` 会使 Classic 缺少账号子系统或导致启动等待。
* `baclassic/_appmode.py` 和 `_appsubsystem.py` 要求 app.plus 非空；
  原生本地玩家的 `SceneV1InputDeviceDelegate::GetAccountID` 也直接调用 Plus。
* 原生 PlusSoftInterface 在生命周期、公共房间状态、账号 ID、成就、购买和旧版握手处被调用；
  本次逐项提供空账号、false 能力、无网络的本地通知或显式未实现错误，见构建文档行为表。

本工程自有 `native/community_plus.cc` 实现生成器要求的初始化符号，并安装 PlusSoftInterface。
Python `_community.py` 覆盖原始 PlusAppSubsystem 的在线调用面；
原始 `on_app_mode_activated` 只处理未加载的 console session，仍可沿用。
兼容名称保留给后续社区服务，不能作为“已登录”或“已联机”的证据。

## 环境审计与执行过的修复

初始 Windows PATH 中有 JDK 25.0.2、Python 3.13.13、CMake 4.3.3、ADB；
Windows SDK 已有 NDK 28.2.13676358。WSL2 Ubuntu 存在，最初缺 Linux Android SDK、uv、
clang-format、JDK 21、Ninja 和 zstd。现已建立独立 Linux SDK/NDK 并安装所需工具。
完整版本输出及实际 ADB 设备列表见 `artifacts/android/environment.json`。
当前设备列表为空；真机功能验收受到设备环境阻塞。

初始 Git 下载失败来自全局 localhost:10808 代理。单次 clone 使用空代理覆盖后成功；
没有改写用户全局 Git 配置。沙箱内 ADB/WSL 检查曾失败，在实际 Windows 环境中读取成功，
不能把沙箱错误误记为系统没有安装 WSL 或 ADB。
