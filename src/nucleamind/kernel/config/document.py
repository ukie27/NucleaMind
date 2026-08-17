"""把一份已校验的 `NucleaConfig` 渲染成诊断用的 JSON 文档（`D33` 从 `schema.py` 拆出）。

职责：`NucleaConfig` → `dict[str, JsonValue]`，元组转列表，保证真能被 `json.dumps` 编码。
不负责：定义有哪些字段（`schema.SECTION_SPECS`）、校验（`fields.py` / `schema.py`）、
读取任何来源（`sources.py`）。

**它是那张字段表的派生物，不是第二份真相来源**——与 `json_schema.py` 同一档：一个渲染给
编辑器看，一个渲染给 `/config` 与 `nm config show` 看。拆出来的直接原因是 `schema.py` 又
撞上了 `kernel/` 的 500 行上限（`D13` → `fields.py`、`D24` → 六个 `*_at()`、
`D28` → `defaults.py` 之后同一条规则的第四次应用）：先被挪走的应当是「只是把已有结构换个
形状」的那部分，而不是字段表本身。

加字段时**两处都要改**：`schema.SECTION_SPECS` 与这里的渲染。`tests/kernel/test_config.py`
有一条「渲染出来的键集合 == 字段表的键集合」的对照测试盯着这件事。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from nucleamind.contracts import JsonValue

from . import plugin_blocks as blocks

if TYPE_CHECKING:  # pragma: no cover - 仅为注解；运行期反向 import 会成环。
    from .schema import NucleaConfig

__all__ = ["config_to_json"]


def config_to_json(config: NucleaConfig) -> dict[str, JsonValue]:
    """诊断视图。元组转列表，保证真能被 `json.dumps` 编码。"""
    return {
        "turn": {
            "max_iterations": config.turn.max_iterations,
            "max_tool_calls_per_turn": config.turn.max_tool_calls_per_turn,
            "tool_timeout_ms": config.turn.tool_timeout_ms,
            "tool_result_max_bytes": config.turn.tool_result_max_bytes,
            "turn_timeout_ms": config.turn.turn_timeout_ms,
            "context_max_tokens": config.turn.context_max_tokens,
        },
        "workspace": {"root": config.workspace.root},
        "routing": {
            "command_prefix": config.routing.command_prefix,
            "session_concurrency": config.routing.session_concurrency,
            "queue_max_size": config.routing.queue_max_size,
            "dedup_capacity": config.routing.dedup_capacity,
            "dedup_ttl_ms": config.routing.dedup_ttl_ms,
            "channel_concurrency": config.routing.channel_concurrency,
            "channel_queue_max_size": config.routing.channel_queue_max_size,
        },
        "hooks": {
            "observer_timeout_ms": config.hooks.observer_timeout_ms,
            "interceptor_timeout_ms": config.hooks.interceptor_timeout_ms,
        },
        "context": {"provider_timeout_ms": config.context.provider_timeout_ms},
        "memory": {
            "provider": config.memory.provider,
            "recall_limit": config.memory.recall_limit,
            "recall_timeout_ms": config.memory.recall_timeout_ms,
            "fragment_priority": config.memory.fragment_priority,
            "on_failure": config.memory.on_failure,
        },
        "plugins": {
            "enabled": list(config.plugins.enabled),
            "disable": list(config.plugins.disable),
            "search_paths": list(config.plugins.search_paths),
            "stop_timeout_ms": config.plugins.stop_timeout_ms,
            **blocks.entries_to_json(config.plugins.entries),
        },
        "model": {"provider": config.model.provider, "name": config.model.name},
        "logging": {"level": config.logging.level, "file_enabled": config.logging.file_enabled},
    }
