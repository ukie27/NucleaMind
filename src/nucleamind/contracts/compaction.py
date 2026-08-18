"""上下文压缩契约：插件输入与输出的纯数据形状（D51）。

职责：定义 Kernel 交给 `ContextCompactor` 的请求，以及插件返回的压缩水位与摘要正文。
不负责：决定何时压缩、校验或持久化结果、选择具体插件实现。
"""

from __future__ import annotations

from dataclasses import dataclass

from .ids import Correlation
from .session import SessionSnapshot

__all__ = ["CompactionRequest", "CompactionResult"]


@dataclass(frozen=True, slots=True)
class CompactionRequest:
    """一次持久化上下文压缩请求。"""

    snapshot: SessionSnapshot
    target_tokens: int
    correlation: Correlation
    user_input: str


@dataclass(frozen=True, slots=True)
class CompactionResult:
    """插件建议的压缩水位与摘要正文。"""

    through: int
    content: str
