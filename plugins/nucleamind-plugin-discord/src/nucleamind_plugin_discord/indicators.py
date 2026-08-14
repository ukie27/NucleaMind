"""typing 指示器与反应 emoji 的生命周期（开发方案 `D33`）。

职责：收到消息时立刻打一个「已读」反应、延迟一段时间再打「工作中」反应、并在整条 turn
期间维持 typing 指示器；终态时全部清理。
不负责：判断什么是终态（由 `channel.py` 传进来）、发消息（`stream.py`）、
接触 `discord.py`（`Indicators` 对注入的 `Reactions` Protocol 编程）。

**legacy 把这套东西和流式生命周期缠在一起，那是它最容易写错的地方**
（`legacy/channels/discord/runtime.py:479`：只有**非 progress** 的出站消息才清理指示器）。
这里拆开的全部理由就是让「谁在什么时候拆掉指示器」只有一处答案：`stop()`，
由 `channel.py` 在**终态**出站消息上调用一次。一条 `DELTA` 永远不该拆掉它——
模型还在说话，而用户会看到指示器闪一下又回来。

**注入时钟与 sleep**：延迟 emoji 与 typing 循环是本模块仅有的两处时间语义。注入之后
用例不必真的等 2 秒，也不会在慢机器上假阳性（`stream.py` 的同一条做法）。

**每一个平台调用都可能失败，而失败一次都不该影响 turn**：反应可能因为消息被删、权限
不足或频道归档而失败，那是装饰不是内容。因此本模块**全部动作都吞异常**——它没有任何
调用方需要知道的失败。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Protocol

__all__ = [
    "DEFAULT_TYPING_INTERVAL_MS",
    "DEFAULT_WORKING_DELAY_MS",
    "Indicators",
    "Reactions",
]

#: 「工作中」反应的延迟。legacy 的 `working_emoji_delay: float = 2.0` 原值，只换了单位。
DEFAULT_WORKING_DELAY_MS: int = 2000

#: typing 指示器的续期间隔。legacy 的 `TYPING_INTERVAL_S = 8` 原值。
DEFAULT_TYPING_INTERVAL_MS: int = 8000


class Reactions(Protocol):
    """本模块需要的全部平台能力。`gateway.py` 提供实现。"""

    async def add_reaction(self, conversation_id: str, message_id: str, emoji: str) -> None: ...

    async def clear_reaction(self, conversation_id: str, message_id: str, emoji: str) -> None: ...

    async def type_once(self, conversation_id: str) -> None: ...


@dataclass(slots=True)
class _Session:
    """一条 conversation 上正在显示的指示器。"""

    message_id: str
    typing: asyncio.Task[None] | None = None
    working: asyncio.Task[None] | None = None
    shown: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Indicators:
    """按 conversation 维护指示器。`start()` / `stop()` 各调用一次。"""

    reactions: Reactions
    # boundary: `Coroutine[Any, Any, None]` 的两个 Any 是 stdlib 的形状，不是我们的类型
    sleep: Callable[[float], Coroutine[Any, Any, None]] = asyncio.sleep
    read_receipt_emoji: str = "👀"
    working_emoji: str = "🔧"
    working_delay_ms: int = DEFAULT_WORKING_DELAY_MS
    typing_interval_ms: int = DEFAULT_TYPING_INTERVAL_MS
    _sessions: dict[str, _Session] = field(default_factory=dict)

    def active(self) -> int:
        """当前有指示器的 conversation 数。"""
        return len(self._sessions)

    async def start(self, conversation_id: str, message_id: str) -> None:
        """收到一条消息：立刻打已读反应、派出 typing 循环与延迟的工作中反应。

        同一 conversation 再次 `start()` 会先把上一次清干净——否则一条消息接一条消息时
        会在频道里堆出一串没人清理的反应。
        """
        await self.stop(conversation_id)
        session = _Session(message_id=message_id)
        self._sessions[conversation_id] = session
        if self.read_receipt_emoji:
            await self._quietly(
                self.reactions.add_reaction(conversation_id, message_id, self.read_receipt_emoji)
            )
            session.shown.append(self.read_receipt_emoji)
        if self.typing_interval_ms > 0:
            session.typing = asyncio.create_task(
                self._type_loop(conversation_id), name=f"typing:{conversation_id}"
            )
        if self.working_emoji:
            session.working = asyncio.create_task(
                self._delayed_working(conversation_id, session), name=f"working:{conversation_id}"
            )

    async def stop(self, conversation_id: str) -> None:
        """终态：取消循环、清掉已经打出去的反应。**只在终态调用。**

        一条 `DELTA` 调它就会让指示器在模型说话的中途闪一下又回来——legacy 那条坑的新家
        就在这里，因此判断留给调用方而不是本模块猜。
        """
        session = self._sessions.pop(conversation_id, None)
        if session is None:
            return
        for task in (session.typing, session.working):
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task
        for emoji in session.shown:
            await self._quietly(
                self.reactions.clear_reaction(conversation_id, session.message_id, emoji)
            )

    async def shutdown(self) -> None:
        """把所有 conversation 的指示器清干净。Channel 停止时调用一次。"""
        for conversation_id in list(self._sessions):
            await self.stop(conversation_id)

    # ------------------------------------------------------------------ 内部

    async def _type_loop(self, conversation_id: str) -> None:
        """周期性重打 typing。平台侧的 typing 只维持几秒，不续期就会消失。"""
        while True:
            await self._quietly(self.reactions.type_once(conversation_id))
            await self.sleep(self.typing_interval_ms / 1000)

    async def _delayed_working(self, conversation_id: str, session: _Session) -> None:
        """延迟之后打「工作中」反应。

        延迟的意义是**只对慢 turn 显示**：一条秒回的消息不该在频道里留下两个反应。
        终态先到时这个任务会被 `stop()` 取消，因此那个反应根本不会出现——
        它也就不需要被清理。
        """
        await self.sleep(self.working_delay_ms / 1000)
        await self._quietly(
            self.reactions.add_reaction(conversation_id, session.message_id, self.working_emoji)
        )
        session.shown.append(self.working_emoji)

    @staticmethod
    # boundary: 同上，stdlib `Coroutine` 的形状
    async def _quietly(awaitable: Coroutine[Any, Any, None]) -> None:
        """跑一个平台动作，失败只吞不抛。见模块 docstring：指示器是装饰不是内容。"""
        with suppress(Exception):
            await awaitable
