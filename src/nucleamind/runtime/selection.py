"""§10.1 步骤 8：从已冻结的 registry 里按配置挑出必需能力（`D44` 从 `bootstrap.py` 拆出）。

职责：模型供应商与模型标识、会话存储、长期记忆的召回——三项「配置指名一个、registry 里
找它、找不到就以稳定错误码拒绝启动」。
不负责：注册能力（`wiring.py`）、解析覆盖（`kernel/registry/`）、装 `OrchestratorDeps`
（`bootstrap.py::_assemble`）、只读诊断（`inspect.py`）。

**从 `bootstrap.py` 拆出来的理由**：那个文件贴着 800 行上限（`D29` 已经为它拆过两次：
只读查询归 `inspect.py`、改配置归 `config_edit.py`）。这三个函数是同一件事的三个实例，
放在一起比散在装配流程里更容易看出「必需能力缺失」这条判定一共有几处。

**它们都不发事件、不写盘**：只读 registry 与配置，要么返回实现体，要么抛
`CAPABILITY_MISSING` / `CONFIG_INVALID`。`inspect.py` 的只读查询因此可以跳过整个本模块
（它刻意不做步骤 8 的必需能力判定）。
"""

from __future__ import annotations

from nucleamind.contracts import ErrorCode, ModelInfo, ModelProvider, NucleaError, SessionStore
from nucleamind.kernel.config import NucleaConfig
from nucleamind.kernel.plugins import (
    memory_providers_from,
    model_providers_from,
    session_store_from,
)
from nucleamind.kernel.registry import CapabilityRegistry
from nucleamind.kernel.turn import MemoryRecall, select_memory

__all__ = ["missing_capability", "require_sessions", "select_model", "select_recall"]


def select_model(
    registry: CapabilityRegistry, config: NucleaConfig
) -> tuple[ModelProvider, str, ModelInfo | None]:
    """§10.1 步骤 8 的 MODEL 一项：选出生效的 provider 与模型标识。"""
    bindings = model_providers_from(registry)
    if not bindings:
        raise missing_capability("MODEL", "没有任何模型供应商，实例无法回答任何输入。")
    wanted = config.model.provider
    chosen = next((b for b in bindings if b.name == wanted), None) if wanted else bindings[0]
    if chosen is None:
        raise NucleaError(
            ErrorCode.CAPABILITY_MISSING,
            "配置里指定的模型供应商没有注册。",
            detail={
                "pointer": "/model/provider",
                "wanted": wanted,
                "available": [b.name for b in bindings],
            },
        )
    model_id = config.model.name
    if not model_id:
        raise NucleaError(
            ErrorCode.CONFIG_INVALID,
            "没有指定要用哪个模型。",
            detail={
                "pointer": "/model/name",
                "suggestion": '在 config.json 里写 {"model": {"name": "gpt-4o-mini"}}。',
            },
        )
    return chosen.value, model_id, chosen.value.describe(model_id)


def select_recall(registry: CapabilityRegistry, config: NucleaConfig) -> MemoryRecall | None:
    """按 `memory.provider` 挑一条 `MEMORY` 能力，装成 `MemoryRecall`（`D44`）。

    **`None`（没配）就是不启用**，这是默认。自动挑一个会让「装上一个记忆插件」悄悄改变
    每一轮请求的内容；配了却不存在是 `CAPABILITY_MISSING`（判定在
    `kernel/turn/memory.py::select_memory`，这里不重写一遍）。

    这是 `memory_providers_from()` 在生产路径上的**第一个**调用方：`D39` 交了 `MEMORY`
    能力与一个实现它的插件，但 kernel 里没有消费者，因此那条能力此前只是契约形状。
    """
    if config.memory.provider is None:
        return None
    candidates = [
        (binding.name, binding.owner, binding.value)
        for binding in memory_providers_from(registry)
    ]
    name, owner, provider = select_memory(candidates, config.memory.provider)
    return MemoryRecall(
        provider=provider,
        name=name,
        owner=owner,
        limit=config.memory.recall_limit,
        timeout_ms=config.memory.recall_timeout_ms,
        priority_floor=config.memory.fragment_priority,
        critical=config.memory.critical,
    )


def require_sessions(registry: CapabilityRegistry) -> SessionStore:
    binding = session_store_from(registry)
    if binding is None:
        raise missing_capability("SESSION_STORE", "没有会话存储，历史无处可写（SES-003）。")
    return binding.value


def missing_capability(kind: str, why: str) -> NucleaError:
    """必需能力缺失的统一形状。`bootstrap.py` 的 CLI 入口那一条也用它——
    四处各拼一遍消息会让「检查什么」的建议逐渐长得不一样。"""
    return NucleaError(
        ErrorCode.CAPABILITY_MISSING,
        f"必需能力缺失：{kind}。{why}",
        detail={"kind": kind, "suggestion": "检查 plugins.disable 与插件加载结果（nm 会打印）。"},
    )
