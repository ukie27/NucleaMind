"""`nm plugins list|enable|disable|uninstall|purge`（`D29`，技术方案 §10.4、§10.5）。

职责：列出插件与它们的状态，把启用 / 禁用写进 `config.json`，移除配置里的引用，
并在显式确认后删除插件的状态目录。
不负责：发现与阶段 A 判定（`runtime/inspect.py` → `inventory.py` / `plugin_plan.py`）、
改配置的文件操作（`runtime/config_edit.py`）、判定授权（`nm permissions`）。

**`enable` / `disable` 只改配置，不在当前进程生效**（首版不热更新，需求 §4.2、§10.4）。
这句印在每一次改动的输出里，与 `nm permissions grant` 一致。

**不取实例锁**，与 `nm config show` / `nm permissions` 同一条理由：看一眼装了什么、
或者改一行配置，不该与正在跑的实例互斥。代价是改动要等对方重启才生效——反正首版本来
就不热更新，这里没有多付出什么。

**`purge` 是本文件唯一会删用户数据的地方**（`EDG-505`）：默认**不删**，`uninstall` 更是
一个字节都不碰状态目录。要删就得先看见将要删掉什么——路径与体积在 `--confirm` 之前
就已经印出来了，那不是确认之后的回执。
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from nucleamind.contracts import ErrorCode, JsonValue, NucleaError
from nucleamind.kernel.config import InstanceLayout
from nucleamind.kernel.observability import PluginStatus

from ...config_edit import add_to_list, read_document, remove_from_list, write_document
from ...inspect import inspect_plugins
from ..main import Options

__all__ = ["plugins_command"]

_USAGE = """用法：nm plugins <子命令>

子命令：
  list [--json]              列出已发现的插件、状态、版本与能力
  enable <插件 id>           写入 plugins.enabled（下次启动生效）
  disable <插件 id>          写入 plugins.disable（对内建同样有效）
  uninstall <插件 id>        从配置里移除引用，保留插件的状态目录
  purge <插件 id> --confirm  删除插件的状态目录（先打印路径与体积）
"""

#: 改完配置后统一的那句话。首版不热更新，说清楚比让用户困惑地敲 `/plugins` 强。
_RESTART_HINT = "改动在实例下次启动时生效（首版不热更新）。"

_PLUGINS = "plugins"
_ENABLED = "enabled"
_DISABLE = "disable"


def plugins_command(options: Options) -> int:
    action = options.rest[0] if options.rest else ""
    if action in ("", "-h", "--help"):
        sys.stdout.write(_USAGE)
        return 0
    layout = InstanceLayout.resolve(instance_dir=options.instance_dir, instance=options.instance)
    args = options.rest[1:]
    match action:
        case "list":
            return _list(options, args)
        case "enable":
            return _enable(layout, args)
        case "disable":
            return _disable(layout, args)
        case "uninstall":
            return _uninstall(layout, args)
        case "purge":
            return _purge(layout, args)
        case _:
            raise NucleaError(
                ErrorCode.INPUT_MALFORMED,
                f"未知的 plugins 子命令 {action!r}。",
                detail={"known": ["list", "enable", "disable", "uninstall", "purge"]},
            )


def _plugin_id(args: Sequence[str], usage: str, *, flags: Sequence[str] = ()) -> str:
    """摘出唯一的位置参数。选项在 `flags` 里的允许出现，其余一律拒绝。"""
    positional = [item for item in args if not item.startswith("-")]
    unknown = [item for item in args if item.startswith("-") and item not in flags]
    if len(positional) != 1 or unknown:
        raise NucleaError(
            ErrorCode.INPUT_MALFORMED,
            "要给出且只给出一个插件 id。",
            detail={"usage": usage, "unknown": sorted(unknown)},
        )
    return positional[0]


# ------------------------------------------------------------------------ list


def _list(options: Options, args: Sequence[str]) -> int:
    unknown = set(args) - {"--json"}
    if unknown:
        raise NucleaError(
            ErrorCode.INPUT_MALFORMED, "未知选项。", detail={"unknown": sorted(unknown)}
        )
    inspection = inspect_plugins(
        instance_dir=options.instance_dir,
        instance=options.instance,
        overrides=options.overrides,
    )
    if "--json" in args:
        payload: dict[str, JsonValue] = {
            "instance_dir": str(inspection.loaded.layout.root),
            "plugins": [status.to_json() for status in inspection.statuses],
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return 0

    sys.stdout.write(f"实例目录：{inspection.loaded.layout.root}\n")
    statuses = inspection.statuses
    if not statuses:
        # 「没有插件」是 `EDG-101` 要求的可用形态，说一句确认比印一张空表清楚。
        sys.stdout.write("\n没有发现任何外部插件（内建能力见 nm capabilities）。\n")
        return 0
    sys.stdout.write(f"\n已发现插件（{len(statuses)}）：\n")
    for status in statuses:
        sys.stdout.write(_render(status))
    return 0


def _render(status: PluginStatus) -> str:
    """一条插件记录。

    `reason` 直接印 `inventory._SKIP_REASONS` 那张表里的原话——`D25` 定死跳过原因的文案
    只有一份，CLI 侧再写一份会让「为什么没加载」有两种说法。
    """
    version = f"  {status.version}" if status.version else ""
    lines = [f"  {status.plugin_id}{version}  [{status.state.value}]\n"]
    if status.reason:
        lines.append(f"      原因：{status.reason}\n")
    if status.capabilities:
        lines.append(f"      能力：{', '.join(status.capabilities)}\n")
    if status.failure is not None:
        phase = f"（{status.failed_phase}）" if status.failed_phase else ""
        lines.append(f"      失败{phase}：{status.failure.user_message}\n")
        for key, value in sorted(status.failure.detail.items()):
            lines.append(f"        {key}: {value}\n")
    return "".join(lines)


# ------------------------------------------------------- enable / disable / uninstall


def _enable(layout: InstanceLayout, args: Sequence[str]) -> int:
    """写入 `plugins.enabled`，并把它从 `plugins.disable` 里摘掉。

    **摘掉是必须的，不是顺手**：`disable` 压过 `enabled`（`D25`），不摘就等于让一条明确
    的「启用」静默失效。摘掉了什么会印出来——这条命令不做用户看不见的事。
    """
    plugin_id = _plugin_id(args, "nm plugins enable <插件 id>")
    document = read_document(layout.config_path)
    added = add_to_list(document, _PLUGINS, _ENABLED, plugin_id)
    undisabled = remove_from_list(added.document, _PLUGINS, _DISABLE, plugin_id)
    if not added.changed and not undisabled.changed:
        sys.stdout.write(f"{plugin_id}: 本来就已启用。\n")
        return 3
    write_document(layout.config_path, undisabled.document)
    if added.changed:
        sys.stdout.write(f"{plugin_id}: 已写入 plugins.enabled。\n")
    if undisabled.changed:
        sys.stdout.write(f"{plugin_id}: 同时从 plugins.disable 移除（禁用会压过启用）。\n")
    sys.stdout.write(_RESTART_HINT + "\n")
    return 0


def _disable(layout: InstanceLayout, args: Sequence[str]) -> int:
    """写入 `plugins.disable`。**不动 `enabled`**——那样 `enable` 才是它的逆操作。

    对内建同样有效（`plugins.disable` 是按提供方禁用）。唯一被拒的是 CLI 入口，
    那条判定在装配根（`EDG-108`），启动时才报——这里不抄一遍，否则两份判定会分叉。
    """
    plugin_id = _plugin_id(args, "nm plugins disable <插件 id>")
    document = read_document(layout.config_path)
    edit = add_to_list(document, _PLUGINS, _DISABLE, plugin_id)
    if not edit.changed:
        sys.stdout.write(f"{plugin_id}: 本来就已禁用。\n")
        return 3
    write_document(layout.config_path, edit.document)
    sys.stdout.write(f"{plugin_id}: 已写入 plugins.disable。\n{_RESTART_HINT}\n")
    return 0


def _uninstall(layout: InstanceLayout, args: Sequence[str]) -> int:
    """从两张表里移除引用，**保留状态目录**（`EDG-505`）。

    **不碰已安装的发行包**：那是 pip 的事，一条 CLI 子命令去卸别人装的包只会在权限、
    虚拟环境与卸载失败三件事上各留一个坑。这句印在输出里，免得用户以为包已经没了。
    """
    plugin_id = _plugin_id(args, "nm plugins uninstall <插件 id>")
    document = read_document(layout.config_path)
    from_enabled = remove_from_list(document, _PLUGINS, _ENABLED, plugin_id)
    from_disable = remove_from_list(from_enabled.document, _PLUGINS, _DISABLE, plugin_id)
    state_dir = layout.plugins_dir / plugin_id
    if not from_enabled.changed and not from_disable.changed:
        sys.stdout.write(f"{plugin_id}: 配置里本来就没有它。\n")
        _write_state_note(state_dir, plugin_id)
        return 3
    write_document(layout.config_path, from_disable.document)
    sys.stdout.write(f"{plugin_id}: 已从配置里移除引用。\n")
    sys.stdout.write("发行包本身不受影响（要卸载请用 pip）。\n")
    _write_state_note(state_dir, plugin_id)
    sys.stdout.write(_RESTART_HINT + "\n")
    return 0


def _write_state_note(state_dir: Path, plugin_id: str) -> None:
    """状态目录仍在哪、怎么删掉它。没有目录时不提，免得指向一个不存在的路径。"""
    if state_dir.is_dir():
        sys.stdout.write(
            f"状态目录仍保留：{state_dir}\n"
            f"  要一并删除：nm plugins purge {plugin_id} --confirm\n"
        )


# ----------------------------------------------------------------------- purge


def _purge(layout: InstanceLayout, args: Sequence[str]) -> int:
    """删除插件的状态目录。**没有 `--confirm` 就只打印，不删任何东西。**

    路径与体积在确认之前打印（`EDG-505`）：一句「确定吗」不足以让用户知道自己将要失去
    什么，而这是本命令唯一不可撤销的动作。
    """
    plugin_id = _plugin_id(args, "nm plugins purge <插件 id> --confirm", flags=["--confirm"])
    state_dir = layout.plugins_dir / plugin_id
    if not state_dir.is_dir():
        sys.stdout.write(f"{plugin_id}: 没有状态目录可删（{state_dir}）。\n")
        return 3
    files, total = _measure(state_dir)
    sys.stdout.write(f"将删除：{state_dir}\n  {files} 个文件，共 {_human(total)}\n")
    if "--confirm" not in args:
        sys.stdout.write("未删除任何东西。确认后重跑：nm plugins purge "
                         f"{plugin_id} --confirm\n")
        return 3
    try:
        shutil.rmtree(state_dir)
    except OSError as exc:
        raise NucleaError(
            ErrorCode.PERSISTENCE_WRITE_FAILED,
            "无法删除插件状态目录。",
            detail={"path": str(state_dir), "errno": exc.errno},
        ) from exc
    sys.stdout.write(f"{plugin_id}: 状态目录已删除。\n")
    return 0


def _measure(root: Path) -> tuple[int, int]:
    """`(文件数, 字节数)`。

    读不动的条目按 0 计而不是让整条命令失败：这段数字是给人看的量级参考，
    为一个权限不足的文件放弃打印，用户就连「大概多大」都不知道了。
    """
    files = 0
    total = 0
    for path in root.rglob("*"):
        try:
            if not path.is_file():
                continue
            total += path.stat().st_size
        except OSError:  # pragma: no cover - 平台相关的防御分支。
            continue
        files += 1
    return files, total


def _human(size: int) -> str:
    """人读的体积。`EDG-505` 要的是「打印体积」，而 `13421772 字节` 不是给人读的。"""
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"  # pragma: no cover - 上面的循环已经覆盖了全部出口。
