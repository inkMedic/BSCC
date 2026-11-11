# BombSquad-Chinese-Community tools

这些工具服务于 BSCC 的构建、测试、资源准备和社区发行流程；它们可能继承上游 Ballistica
工具的名称或目录结构，但不代表本仓库与上游保持相同的构建和发行行为。

Code in this directory is used to build or test Ballistica projects but
(in most cases) is not available *from* a running Ballistica app.

Note that there are exceptions to this rule; some of the Python packages
here such as 'efro' or 'bacommon' are bundled with builds so can be used
from tools *and* app code.
