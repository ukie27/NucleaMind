"""Turn 执行机制：取消、预算、事件、依赖面、折叠、调度与引擎（技术方案 §6.2、§6.4）。

职责：re-export `kernel/turn/` 六个模块的公开表面，使调用方只需要
`from nucleamind.kernel.turn import ...` 一条导入路径。
不负责：session 读写、context 组装、命令分流、事件发布——那些在 `orchestrator.py`（`D14`）；
本包不读文件、不访问网络。

包内依赖是单向的，没有环：

```text
cancel ─┐
        ├─> events ─> engine
limits ─┘      ↑        ↑
   └─> folding ─┘   scheduling
        deps ───────────┘
```

`cancel` 与 `limits` 之间**没有**依赖：取消是「有人要求停下」，预算是「已经用掉多少」。
把它们缝在一起会让「撞上迭代上限」与「用户中断」共用一条判定路径，而这两件事的 turn 终态
不同（`STOPPED_BY_LIMIT` 对 `CANCELLED`），必须分别可判定。唯一的交点在
`LimitBreach.cancel_reason`：`turn_timeout_ms` 是预算项，触发时以 `CancelReason.TIMEOUT`
走取消路径，由 `engine._terminal_for_breach()` 把这个 reason 交给 `CancelToken.request()`。
"""

from __future__ import annotations

from .cancel import (
    CANCEL_REASON_CODES,
    CHECKPOINT_OWNERS,
    DEFAULT_TOOL_CANCEL_GRACE_MS,
    CancelToken,
    Checkpoint,
    CheckpointOwner,
)
from .deps import ENGINE_HOOKS, EngineDeps, HookDispatcher, ToolInvoker
from .engine import run_turn
from .events import (
    TERMINAL_EVENTS,
    ModelReasoningDelta,
    ModelResponseCompleted,
    ModelTextDelta,
    TerminalEvent,
    ToolCallCompleted,
    ToolCallStarted,
    ToolDisposition,
    TurnCancelled,
    TurnCompleted,
    TurnEvent,
    TurnFailed,
    TurnStoppedByLimit,
    terminal_from_error,
)
from .folding import (
    EMPTY_TOOL_RESULT_TEXT,
    StreamFolder,
    assistant_message,
    blocked_result,
    escaped_result,
    fold_tool_result,
    skipped_result,
    unknown_tool_result,
)
from .limits import (
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_MAX_TOOL_CALLS_PER_TURN,
    DEFAULT_TOOL_RESULT_MAX_BYTES,
    DEFAULT_TOOL_TIMEOUT_MS,
    DEFAULT_TURN_TIMEOUT_MS,
    FALLBACK_CONTEXT_MAX_TOKENS,
    LIMIT_OUTCOMES,
    BudgetLedger,
    LimitBreach,
    LimitKind,
    TurnLimits,
)
from .scheduling import execute_batch, partition_tool_batches

__all__ = [
    "CANCEL_REASON_CODES",
    "CHECKPOINT_OWNERS",
    "DEFAULT_MAX_ITERATIONS",
    "DEFAULT_MAX_TOOL_CALLS_PER_TURN",
    "DEFAULT_TOOL_CANCEL_GRACE_MS",
    "DEFAULT_TOOL_RESULT_MAX_BYTES",
    "DEFAULT_TOOL_TIMEOUT_MS",
    "DEFAULT_TURN_TIMEOUT_MS",
    "EMPTY_TOOL_RESULT_TEXT",
    "ENGINE_HOOKS",
    "FALLBACK_CONTEXT_MAX_TOKENS",
    "LIMIT_OUTCOMES",
    "TERMINAL_EVENTS",
    "BudgetLedger",
    "CancelToken",
    "Checkpoint",
    "CheckpointOwner",
    "EngineDeps",
    "HookDispatcher",
    "LimitBreach",
    "LimitKind",
    "ModelReasoningDelta",
    "ModelResponseCompleted",
    "ModelTextDelta",
    "StreamFolder",
    "TerminalEvent",
    "ToolCallCompleted",
    "ToolCallStarted",
    "ToolDisposition",
    "ToolInvoker",
    "TurnCancelled",
    "TurnCompleted",
    "TurnEvent",
    "TurnFailed",
    "TurnLimits",
    "TurnStoppedByLimit",
    "assistant_message",
    "blocked_result",
    "escaped_result",
    "execute_batch",
    "fold_tool_result",
    "partition_tool_batches",
    "run_turn",
    "skipped_result",
    "terminal_from_error",
    "unknown_tool_result",
]
