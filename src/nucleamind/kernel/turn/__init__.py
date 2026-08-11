"""Turn 执行机制：取消、预算，以及后续的引擎与编排（技术方案 §6.2、§6.4）。

职责：re-export `cancel`（`CancelToken` 与 6 个命名检查点）与 `limits`（`TurnLimits`
六项预算与 `BudgetLedger` 账本）的公开表面。
不负责：执行模型循环、调度工具、读写 session——那些在 `engine.py`（`D09`）与
`orchestrator.py`（`D14`）；本包不读文件、不访问网络。

两个模块之间没有依赖：取消是「有人要求停下」，预算是「已经用掉多少」，
把它们缝在一起会让「撞上迭代上限」和「用户中断」共用一条判定路径，
而这两件事的 turn 终态不同（`STOPPED_BY_LIMIT` 对 `CANCELLED`），必须分别可判定。
唯一的交点在 `LimitBreach.cancel_reason`：`turn_timeout_ms` 是预算项，触发时以
`CancelReason.TIMEOUT` 走取消路径，由 `D09` 把这个 reason 交给 `CancelToken.request()`。
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

__all__ = [
    "CANCEL_REASON_CODES",
    "CHECKPOINT_OWNERS",
    "DEFAULT_MAX_ITERATIONS",
    "DEFAULT_MAX_TOOL_CALLS_PER_TURN",
    "DEFAULT_TOOL_CANCEL_GRACE_MS",
    "DEFAULT_TOOL_RESULT_MAX_BYTES",
    "DEFAULT_TOOL_TIMEOUT_MS",
    "DEFAULT_TURN_TIMEOUT_MS",
    "FALLBACK_CONTEXT_MAX_TOKENS",
    "LIMIT_OUTCOMES",
    "BudgetLedger",
    "CancelToken",
    "Checkpoint",
    "CheckpointOwner",
    "LimitBreach",
    "LimitKind",
    "TurnLimits",
]
