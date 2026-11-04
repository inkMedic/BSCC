# 本次工作基线（2026-10-30）

源码 HEAD：`d89c2d90cae1593899bd17a1510fef2465acb437`，上游 1.8.5；构建号 23079，Python API 9，内嵌 Python 3.14.7。
场景协议最大 57，HostMin 56，ClientMin 24；社区流程固定 57 / 社区协议 1 / assets 23079，默认不接受其他组合。
原 APK SHA256：`198a32d88bc8fb833f72ebaf145159ab265b9b0b84e1d14ca4cc11d525ccd7e6`。
Android 工具链沿用 NDK 28.2.13676358、SDK 35、Gradle 8.13、JDK 21。
本次开始时已有 22 个已修改文件以及 Android、artifacts、文档等未跟踪成果；未回退、清理或提交这些用户修改。
仓库及项目父目录未发现 AGENTS.md。

原生离线 Plus 位于 `ballisticakit-android/native/community_plus.cc`；本次把可复用实现移至 `src/ballistica/plus/community_plus.cc`，Android 和可选 CMake COMMUNITY_PLUS 共同编译该源。
原离线 Python 子系统保留，在线子类继承本地资料处理与明确不可用的商城/广告能力。
