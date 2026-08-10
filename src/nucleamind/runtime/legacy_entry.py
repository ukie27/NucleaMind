"""`nm legacy` 到遗留 CLI 的过渡适配器。

职责：把 `nm legacy <args>` 的参数、退出码和标准流转发给 `legacy/cli/commands.py`。
不负责：承载任何新功能，也不做参数翻译、配置迁移或行为修正。

这是依赖规则 `R6`（新代码不 import legacy）在迁移期的**唯一例外**：
本模块不得被 runtime/cli/main.py 以外的任何模块导入，D01 用精确路径白名单约束，
D31 随 legacy/agent/ 与该白名单一并删除。
"""

from __future__ import annotations


def run_legacy(argv: list[str]) -> int:
    """运行遗留 CLI，返回其退出码。

    遗留 CLI 以 click 的 standalone 模式运行，正常退出路径是抛 `SystemExit`。
    这里**不捕获** `SystemExit`：让它带着原始退出码与错误消息穿透到解释器，
    才是真正的「转发退出码」。只有在遗留 CLI 正常返回时才由本函数给出 0。
    """
    # 局部导入：遗留 CLI 在导入期就会配置 loguru 与控制台编码，
    # 不能让这些副作用泄漏到 `nm` 的其他路径。
    from nucleamind.legacy.cli.commands import app as legacy_app

    legacy_app(args=list(argv), prog_name="nm legacy")
    return 0
