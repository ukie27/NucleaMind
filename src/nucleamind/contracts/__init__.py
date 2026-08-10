"""第 1 层：公开数据契约。

职责：定义 Kernel、内建能力与插件之间传递的纯数据类型与窄 Protocol，并统一提供
递归类型别名 `JsonValue`。
不负责：实现任何行为、依赖 nucleamind 内的其他层、执行 IO。

三条不变量（技术方案 §5.1）：契约对象一律不可变；契约层不出现 `Any`；契约层不出现 IO。

当前已落地 `D02` 基础层（`ids` / `errors` / `events`）；领域层与能力层由 `D03`、`D04` 补齐。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeAlias, Union

#: JSON 可表达的全部值。契约层用它代替 `Any`——形状在边界固定，不向核心泄漏。
JsonValue: TypeAlias = Union[
    str,
    int,
    float,
    bool,
    None,
    Sequence["JsonValue"],
    Mapping[str, "JsonValue"],
]

#: JSON Schema 文档。语义上就是 `Mapping[str, JsonValue]`，单独命名只为签名可读。
JsonSchema: TypeAlias = Mapping[str, JsonValue]

# 子模块的注解引用上面的 `JsonValue`，因此定义必须先于导入；子模块只在
# `TYPE_CHECKING` 下反向导入它，运行时不成环。
from .errors import (  # noqa: E402
    CODE_CATEGORIES,
    ErrorCategory,
    ErrorCode,
    NucleaError,
    redact,
    scrub,
)
from .events import EventFamily, EventName, RuntimeEvent  # noqa: E402
from .ids import Correlation, InstanceId, PluginId, SessionKey, TurnId  # noqa: E402

__all__ = [
    "CODE_CATEGORIES",
    "Correlation",
    "ErrorCategory",
    "ErrorCode",
    "EventFamily",
    "EventName",
    "InstanceId",
    "JsonSchema",
    "JsonValue",
    "NucleaError",
    "PluginId",
    "RuntimeEvent",
    "SessionKey",
    "TurnId",
    "redact",
    "scrub",
]
