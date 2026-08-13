"""`nm permissions list|grant|revoke`：查看与修改权限账本（`NFR-301`、`NFR-307`）。

职责：把 `permissions.json` 印出来，并把用户的显式批准 / 撤销写回去。
不负责：判定授权（`kernel/plugins/permissions.py` 的 `PermissionLedger.decide()`）、
发现插件（`D25`）、构造受限运行时（`runtime/plugin_context.py`）。

**这条命令就是「用户显式操作」本身**（`NFR-307`）。TOFU 让首次见到的声明被自动记下，
而**扩权**——插件升级新增了一条权限、换了个实现——默认落在 `pending`，只有这里（或用户
直接编辑那个文件）能把它变成 `granted`。

**不取实例锁**，与 `nm config show` 同一条理由：看一眼授权不该与正在跑的实例互斥。
代价是 `grant` 与一个正在跑的实例并发时，改动要等对方重启才生效——账本在启动期读一次。
这条如实印在 `grant` / `revoke` 的输出里。
"""

from __future__ import annotations

import json
import sys

from nucleamind.contracts import ErrorCode, NucleaError
from nucleamind.kernel.config import InstanceLayout
from nucleamind.kernel.plugins import Decision, PermissionLedger, parse_permission

from ..main import Options

__all__ = ["permissions_command"]

_USAGE = """用法：nm permissions <子命令>

子命令：
  list [--json]                     列出全部授权记录
  grant  <插件 id> <权限> [理由]    批准一项权限
  revoke <插件 id> <权限>           撤销一项权限
  forget <插件 id>                  删掉一个插件的全部记录（下次启动重新走首次授予）

权限写成 fs:read / fs:write / net / shell / secret:<名字>。
"""

_DECISION_LABELS = {
    Decision.GRANTED: "已授予",
    Decision.PENDING: "待批准",
    Decision.REVOKED: "已撤销",
}


def permissions_command(options: Options) -> int:
    action = options.rest[0] if options.rest else ""
    if action in ("", "-h", "--help"):
        sys.stdout.write(_USAGE)
        return 0
    layout = InstanceLayout.resolve(instance_dir=options.instance_dir, instance=options.instance)
    ledger = PermissionLedger.load(layout.permissions_path)
    args = options.rest[1:]
    match action:
        case "list":
            return _list(ledger, args)
        case "grant":
            return _set(ledger, args, Decision.GRANTED)
        case "revoke":
            return _set(ledger, args, Decision.REVOKED)
        case "forget":
            return _forget(ledger, args)
        case _:
            raise NucleaError(
                ErrorCode.INPUT_MALFORMED,
                f"未知的 permissions 子命令 {action!r}。",
                detail={"known": ["list", "grant", "revoke", "forget"]},
            )


def _list(ledger: PermissionLedger, args: list[str]) -> int:
    unknown = set(args) - {"--json"}
    if unknown:
        raise NucleaError(
            ErrorCode.INPUT_MALFORMED, "未知选项。", detail={"unknown": sorted(unknown)}
        )
    if "--json" in args:
        sys.stdout.write(
            json.dumps(ledger.to_json(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        return 0

    sys.stdout.write(f"权限文件：{ledger.path}\n")
    providers = ledger.providers()
    if not providers:
        # 「文件不存在」与「文件里没有记录」对用户是同一件事：还没有任何插件被装过。
        sys.stdout.write("\n还没有任何授权记录——启动一次实例即可生成。\n")
        return 0
    for plugin_id in providers:
        sys.stdout.write(f"\n{plugin_id}\n")
        for entry in ledger.entries_for(plugin_id):
            label = _DECISION_LABELS[entry.decision]
            reason = f"  # {entry.reason}" if entry.reason else ""
            sys.stdout.write(f"  {label}  {entry.name}  （{entry.source}）{reason}\n")
    return 0


def _set(ledger: PermissionLedger, args: list[str], decision: Decision) -> int:
    if len(args) < 2:
        raise NucleaError(
            ErrorCode.INPUT_MALFORMED,
            "要给出插件 id 与权限名。",
            detail={"usage": "nm permissions grant <插件 id> <权限> [理由]"},
        )
    plugin_id, permission = args[0], parse_permission(args[1])
    reason = " ".join(args[2:])
    entry = ledger.set_decision(plugin_id, permission, decision, reason=reason)
    ledger.save()
    sys.stdout.write(
        f"{plugin_id}: {entry.name} -> {_DECISION_LABELS[entry.decision]}\n"
        "改动在实例下次启动时生效（账本在启动期读一次）。\n"
    )
    return 0


def _forget(ledger: PermissionLedger, args: list[str]) -> int:
    if len(args) != 1:
        raise NucleaError(
            ErrorCode.INPUT_MALFORMED,
            "要给出且只给出一个插件 id。",
            detail={"usage": "nm permissions forget <插件 id>"},
        )
    if not ledger.forget(args[0]):
        sys.stdout.write(f"{args[0]}: 没有记录可删。\n")
        return 3
    ledger.save()
    sys.stdout.write(f"{args[0]}: 记录已删除，下次启动按首次授予处理。\n")
    return 0
