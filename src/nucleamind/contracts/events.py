"""运行时事件契约（技术方案 §6.8、需求 `OBS-001`–`OBS-005`）。

职责：定义冻结的事件名清单、事件族，以及带 `Correlation` 与单调 `sequence`、
构造时即完成脱敏的不可变 `RuntimeEvent`。
不负责：分配 `sequence`、发布与扇出、写 sink、决定订阅者——那些都在
`kernel/observability/`（`D12`）；本模块不含任何 IO。

事件必带实例标识与单调序号，因此单个 turn 的执行过程可以按序完整重放（`OBS-002`）。
脱敏在构造时完成而不是在 sink 端（`OBS-003`）：新增一个 sink 不应重新引入泄漏面。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

from .errors import ErrorCode, NucleaError, redact
from .ids import Correlation, InstanceId

if TYPE_CHECKING:  # pragma: no cover - 仅为注解。
    from . import JsonValue

__all__ = ["EventFamily", "EventName", "RuntimeEvent"]

#: 空 payload 的共享只读默认值。MappingProxyType 不可变，可以安全地当默认值用。
_EMPTY_PAYLOAD: Mapping[str, "JsonValue"] = MappingProxyType({})


class EventFamily(StrEnum):
    """事件族。事件名的第一段必须是其中之一（`OBS-002`）。"""

    INSTANCE = "instance"
    PLUGIN = "plugin"
    CAPABILITY = "capability"
    SESSION = "session"
    TURN = "turn"
    MODEL = "model"
    TOOL = "tool"
    CHANNEL = "channel"


class EventName(StrEnum):
    """首版冻结的事件名清单。新增事件名视为公开表面变化，须按 `NFR-104` 论证。

    `TURN_STOPPED_BY_LIMIT` 是 `D12` 按 `NFR-104` 评审后补入的（`D09` 的
    `TurnStoppedByLimit` 在此原本没有落点）：用 `TURN_COMPLETED` 承载会让「模型自己
    说完了」与「撞上预算上限被拦下」在事件流里不可区分，而 `EDG-304` 要求终态可区分。

    `INSTANCE_INPUT_DROPPED` 是 `D33` 补入的：Channel 泵按 conversation 扇出之后，
    一条消息可能在**进 orchestrator 之前**就因为 lane 队列或并发上界满而被拒。
    它刻意**不是** `TURN_REJECTED`——那条消息从未进过 orchestrator，而 turn 事件只有
    orchestrator 一个发布点；给它发一条 turn 事件等于在事件流里凭空造一条 orchestrator
    没见过的 turn，`OBS-002` 的按序重放随之作废。背压是**实例级**现象，因此落 INSTANCE 族。

    `CHANNEL_DELIVERY_FAILED` 是 `D43` 补入的，用来消解一条真实存在的契约矛盾：
    `Channel.deliver` 的 docstring 说投递失败抛 `EXTERNAL_CHANNEL`，而 `EDG-204` 要求
    投递失败时 turn 仍然走到终态并完整持久化。四个现存实现因此**全都选了不抛**——一条
    写在契约上却没人遵守的约定比没有约定更坏。有了这个事件，投递失败就有了「既不吞掉、
    也不毁掉 turn」的第三条出路：实现方照约定抛，路由点捕获并发这条事件，turn 继续。

    它**不是** `TURN_FAILED`：投递是 turn 的最后一步，那一轮的模型输出与历史都已经正确
    产生了；记成 turn 失败会让「答案没算出来」与「答案没送出去」不可区分，而这两件事的
    处置完全不同（前者重跑，后者重发）。也**不是** `PLUGIN_FAILED`：内建 `cli_entry` 的
    投递失败与插件无关，而它此前正是被折进那条事件里的。
    """

    INSTANCE_STARTING = "instance.starting"
    INSTANCE_READY = "instance.ready"
    INSTANCE_STOPPING = "instance.stopping"
    INSTANCE_STOPPED = "instance.stopped"
    INSTANCE_INPUT_DROPPED = "instance.input_dropped"

    PLUGIN_DISCOVERED = "plugin.discovered"
    PLUGIN_LOADED = "plugin.loaded"
    PLUGIN_LOAD_FAILED = "plugin.load_failed"
    PLUGIN_ACTIVATED = "plugin.activated"
    PLUGIN_DEACTIVATED = "plugin.deactivated"
    PLUGIN_FAILED = "plugin.failed"

    CAPABILITY_REGISTERED = "capability.registered"
    CAPABILITY_SHADOWED = "capability.shadowed"
    CAPABILITY_DISABLED = "capability.disabled"
    CAPABILITY_RESOLVED = "capability.resolved"
    CAPABILITY_PERMISSION_GRANTED = "capability.permission_granted"

    SESSION_STARTED = "session.started"
    SESSION_LOADED = "session.loaded"
    SESSION_COMPACTED = "session.compacted"
    SESSION_CLOSED = "session.closed"

    TURN_STARTED = "turn.started"
    TURN_REJECTED = "turn.rejected"
    TURN_COMPLETED = "turn.completed"
    TURN_FAILED = "turn.failed"
    TURN_CANCELLED = "turn.cancelled"
    TURN_STOPPED_BY_LIMIT = "turn.stopped_by_limit"

    MODEL_REQUEST_STARTED = "model.request_started"
    MODEL_RESPONSE_RECEIVED = "model.response_received"
    MODEL_REQUEST_FAILED = "model.request_failed"

    TOOL_CALL_STARTED = "tool.call_started"
    TOOL_CALL_COMPLETED = "tool.call_completed"
    TOOL_CALL_BLOCKED = "tool.call_blocked"
    TOOL_CALL_FAILED = "tool.call_failed"

    CHANNEL_DELIVERY_FAILED = "channel.delivery_failed"

    @property
    def family(self) -> EventFamily:
        """事件名首段即事件族。"""
        return EventFamily(self.value.split(".", 1)[0])


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    """一条不可变的运行时事件。

    - `sequence` 由 `EventBus` 单调递增分配，实例内全局唯一，用于按序重放。
    - `correlation` 在实例级事件（启动、插件加载）中为 None：那时还没有会话与 turn。
      它非 None 时，其 `instance_id` 必须与事件自身一致，否则关联链会指向别的实例。
    - `payload` 构造时脱敏并冻结为只读映射，直接交给任何 sink 都安全。
    """

    name: EventName
    sequence: int
    occurred_at: datetime
    instance_id: InstanceId
    correlation: Correlation | None = None
    payload: Mapping[str, JsonValue] = _EMPTY_PAYLOAD
    error: NucleaError | None = None

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise NucleaError(
                ErrorCode.KERNEL_INVARIANT_VIOLATED,
                "事件序号必须非负且单调递增。",
                detail={"sequence": self.sequence, "event": self.name.value},
            )
        if self.occurred_at.tzinfo is None:
            raise NucleaError(
                ErrorCode.KERNEL_INVARIANT_VIOLATED,
                "事件时间必须带时区，否则跨实例排序无意义。",
                detail={"event": self.name.value},
            )
        if self.correlation is not None and self.correlation.instance_id != self.instance_id:
            raise NucleaError(
                ErrorCode.KERNEL_INVARIANT_VIOLATED,
                "事件的实例标识与关联标识不一致。",
                detail={
                    "event": self.name.value,
                    "instance_id": self.instance_id,
                    "correlation_instance_id": self.correlation.instance_id,
                },
            )

        redacted, _ = redact(self.payload)
        object.__setattr__(self, "payload", MappingProxyType(dict(redacted)))

    @property
    def family(self) -> EventFamily:
        """所属事件族，等价于 `name.family`。"""
        return self.name.family
