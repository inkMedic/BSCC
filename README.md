# BombSquad-Chinese-Community

BombSquad-Chinese-Community（简称 **BSCC**）是
[Ballistica](https://github.com/efroemling/ballistica) 的社区分支版本，面向中文社区的
客户端、服务器和配套服务开发。它会持续吸收上游的引擎更新，但产品功能、账号体系、
服务端和发行方向由本项目独立维护。

本仓库不是 `efroemling/ballistica` 的镜像，也不是官方 BombSquad 发行仓库。上游代码、
第三方依赖和资源仍按各自的许可证与授权要求使用；BSCC 新增的社区代码和服务配置以本仓库
的提交记录为准。

## 项目内容

- 中文社区客户端和本地离线 Plus 实现
- 独立的账号、服务器目录、联机准备和单人进度后端
- Android 社区 APK、iOS 社区构建入口和 Linux Headless 服务端
- 中文界面、社区活动、排行榜及移动端适配

主要入口：

| 内容 | 位置 |
| --- | --- |
| 社区后端 | [`community-backend/`](community-backend/) |
| 社区客户端逻辑 | [`src/assets/ba_data/python/baplus/`](src/assets/ba_data/python/baplus/) |
| 社区原生 Plus | [`src/ballistica/plus/community_plus.cc`](src/ballistica/plus/community_plus.cc) |
| Android 工程 | [`ballisticakit-android/`](ballisticakit-android/) |
| iOS 工程与构建脚本 | [`ballisticakit-ios/`](ballisticakit-ios/)、[`tools/community-ios/`](tools/community-ios/) |
| 社区文档 | [`docs/community/`](docs/community/) |

## 构建与发行

移动端构建说明：

- [Android 社区构建](docs/android-community-build.md)
- [iOS 社区构建与真机验收](docs/ios-community-build.md)

推送 `v*` 标签会触发 GitHub Actions，构建并发布桌面、服务器、Android 和 iOS 社区产物。
iOS 云端产物默认未签名，Android 云端产物为 ARM64 Debug APK；签名和真机验收仍需使用对应
平台的账号、证书和设备。

## 与上游同步

上游项目地址：<https://github.com/efroemling/ballistica>

同步上游时应先评估协议、资源、Plus 接口和社区后端的兼容性。BSCC 的功能变更不要求与上游
保持相同的产品路线；涉及社区账号、联机协议或移动端宿主的修改，应同时更新
[`docs/community/`](docs/community/) 中的设计和验收记录。

## 许可与贡献

仓库内代码的许可信息见 [`LICENSE`](LICENSE) 及各目录中的说明。请不要重新分发未获授权的
官方资源、预构建库或完整商业发行包。

欢迎通过本仓库的 Issue 和 Pull Request 提交中文社区相关的问题与改进。提交前请确认改动
针对 BSCC 的功能方向，并在描述中注明是否需要同步上游。
