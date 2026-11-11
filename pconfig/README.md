# BombSquad-Chinese-Community project configuration

这里保存 BSCC 的项目配置。部分配置字段沿用 Ballistica 上游名称，以便复用构建工具；实际
的版本、社区平台和发行配置以本仓库为准。

This directory contains overall configuration files for the project.

Noteworthy files:
- [projectconfig.json](projectconfig.json): Top level settings for the project.
  Various tools look for values here.
- [spinoffconfig.py](spinoffconfig.py): Configures how this project can be
  spun off into other projects and/or what it inherits from a parent project.
- **localconfig.json**: Optional file influencing behavior only at this
  location. This file should not be stored in git/etc.
