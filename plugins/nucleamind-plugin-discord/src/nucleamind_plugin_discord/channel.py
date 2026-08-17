"""`contracts.Channel` 的 Discord 实现（开发方案 `D33`）。

职责：`channel_id` / `start` / `stop` / `receive` / `deliver` 五个成员，以及把
gateway、归一化、流式与指示器组装到一起。
不负责：归一化（`normalize.py`）、分段（`outbound.py`）、编辑时机（`stream.py`）、
指示器生命周期（`indicators.py`）、接触 SDK（`gateway.py`）。

**它很薄，那是刻意的**（`openai-api` 的 `channel.py` 只有 116 行）：Channel 是接缝而不是
实现，把判定写进这里会让每一条都需要一个真的 gateway 才测得到。

三条契约约定，逐条兑现：

- **`stop()` 幂等且不抛**（`EDG-104`：Kernel 对每个能力的停止有独立超时，一个抛异常的
  `stop()` 只会让别的收尾也做不完）。
- **`deliver()` 照约定抛 `EXTERNAL_CHANNEL`**（`D43` 起）。出站路由点
  （`runtime/instance.py::outbound_router`）捕获它、发一条 `channel.delivery_failed`，
  turn 照样走到自己的终态（`EDG-204`）。在此之前这里把投递故障整个吞掉，于是「答案发不
  出去」这件事在事件流里一个字都没有——用户看到的现象是 bot 不说话，而日志一片正常。
  **只有正文的投递会抛；指示器的启停仍然静默**（`_quietly`）：一个没清掉的「正在输入」
  是外观问题，而一条没发出去的答案不是。
- **`receive()` 里畸形消息丢弃并继续，不终止整个 Channel**（`MSG-004`）：一条看不懂的
  平台事件不该让 bot 下线。

**`deliver()` 可能被并发调用**（`D33` 的泵扇出之后），但**同一 conversation 内不会**——
`stream.py` 的缓冲表因此按 conversation 分片而不加锁。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Final

from nucleamind.contracts import (
    ErrorCode,
    InboundMessage,
    NucleaError,
    OutboundMessage,
    SecretStr,
    StreamState,
)

from .gateway import DiscordGateway, to_raw
from .indicators import Indicators
from .normalize import normalize
from .settings import DiscordSettings
from .stream import StreamRelay

__all__ = ["DiscordChannel"]

#: 这些状态表示「这条 turn 说完了」，指示器该清掉。**`DELTA` 不在其中**——模型还在
#: 说话时拆掉指示器会让它闪一下又回来（legacy `runtime.py:479` 那条坑的新家）。
_TERMINAL: Final[frozenset[StreamState]] = frozenset(
    {StreamState.FINAL, StreamState.CANCELLED, StreamState.FAILED}
)

#: 投递失败的用户可见文案。定义成模块级常量：`ruff` 的 `TRY003` 不允许在 `raise`
#: 处写多词消息。
_DELIVERY_FAILED: Final = "出站消息投递失败。"

#: 推理增量的元数据标记。`show_reasoning` 关掉时整条丢弃（`openai-api` 的同一条）。
_REASONING: Final = "reasoning"


class DiscordChannel:
    """一条 Discord Channel。`setup()` 构造它，装配根负责 `start()` / `stop()`。"""

    __slots__ = (
        "_gateway",
        "_indicators",
        "_inbox",
        "_relay",
        "_settings",
        "_show_reasoning",
        "_started",
    )

    def __init__(
        self,
        settings: DiscordSettings,
        *,
        token: SecretStr,
        proxy_password: SecretStr | None = None,
        gateway: DiscordGateway | None = None,
        show_reasoning: bool = False,
    ) -> None:
        self._settings = settings
        self._show_reasoning = show_reasoning
        self._inbox: asyncio.Queue[InboundMessage | None] = asyncio.Queue()
        self._started = False
        auth = (
            (settings.proxy_username, proxy_password)
            if settings.proxy_username and proxy_password is not None
            else None
        )
        self._gateway = gateway or DiscordGateway(
            token=token,
            intents=settings.intents,
            on_message=self._on_platform_message,
            proxy=settings.proxy,
            proxy_auth=auth,
        )
        self._relay = StreamRelay(
            platform=self._gateway,
            now_ms=lambda: int(asyncio.get_running_loop().time() * 1000),
            edit_interval_ms=settings.stream_edit_interval_ms,
            streaming=settings.streaming,
        )
        self._indicators = Indicators(
            reactions=self._gateway,
            read_receipt_emoji=settings.read_receipt_emoji,
            working_emoji=settings.working_emoji,
            working_delay_ms=settings.working_emoji_delay_ms,
            typing_interval_ms=settings.typing_interval_ms,
        )

    # ------------------------------------------------------------------ 契约成员

    @property
    def channel_id(self) -> str:
        """稳定标识，构成 `SessionKey.channel_id`（`SES-001`）。

        它也是装配根 `by_channel` 的路由键——改它等于把这条 Channel 的历史换一批。
        """
        return self._settings.channel_id

    async def start(self) -> None:
        """连接 gateway。**异常约定**：失败抛 `EXTERNAL_CHANNEL`（见 `gateway.py`）。"""
        if self._started:
            return
        self._started = True
        await self._gateway.connect()

    async def stop(self) -> None:
        """断开并结束入站流。**幂等且不抛**。"""
        if not self._started:
            self._inbox.put_nowait(None)
            return
        self._started = False
        await self._quietly(self._indicators.shutdown())
        await self._quietly(self._gateway.close())
        self._inbox.put_nowait(None)

    async def receive(self) -> AsyncIterator[InboundMessage]:
        """入站流。`stop()` 之后结束。

        **拉模型**（契约原文）：平台事件由 gateway 的回调塞进队列，这里只负责取。
        """
        while True:
            message = await self._inbox.get()
            if message is None:
                return
            yield message

    async def deliver(self, message: OutboundMessage) -> None:
        """投递一条出站消息。

        **正文失败抛 `EXTERNAL_CHANNEL`**（`D43`，见模块 docstring 第二条）；指示器的清理
        仍然静默——它在正文之后，而一次失败的清理不该盖掉「正文已经送到了」。
        """
        if not self._show_reasoning and message.metadata.get(_REASONING):
            return
        await self._relayed(message)
        if message.stream_state in _TERMINAL:
            # 只在终态清指示器。判断留在这里而不是 `Indicators` 里——那个模块不该猜
            # 什么算「说完了」。
            await self._quietly(self._indicators.stop(message.conversation_id))

    # ------------------------------------------------------------------ 内部

    # boundary: discord.Message；`to_raw()` 在下一行就把它拍成 `RawInbound`
    async def _on_platform_message(self, raw_message: Any) -> None:
        """gateway 的回调。**一条消息炸掉不该让 bot 下线**（`MSG-004`）。"""
        try:
            raw = to_raw(raw_message)
            gate = self._settings.gate(bot_user_id=self._gateway.bot_user_id)
            message = normalize(raw, gate)
        except Exception:  # noqa: BLE001 - 畸形消息丢弃并继续
            return
        if message is None:
            return
        # 指示器在**进队列之前**打上：用户按下回车之后看到的第一个反馈不该等到 turn
        # 真的开始跑（那可能要排队）。
        await self._quietly(self._indicators.start(message.conversation_id, raw.message_id))
        self._inbox.put_nowait(message)

    async def _relayed(self, message: OutboundMessage) -> None:
        """把正文交给 relay，失败折成 `EXTERNAL_CHANNEL`。

        **只放异常类型名不放消息**：平台 SDK 的异常文本可能带着 webhook URL 或令牌
        （`web.search` 的同一条理由）。`retryable=True`——投递失败几乎总是网络或限流，
        而重发一条聊天消息的代价是可能重复，不是不可逆。
        """
        try:
            await self._relay.handle(message)
        except NucleaError:
            raise
        except Exception as exc:
            raise NucleaError(
                ErrorCode.EXTERNAL_CHANNEL,
                _DELIVERY_FAILED,
                detail={"conversation": message.conversation_id, "cause": type(exc).__name__},
                retryable=True,
            ) from exc

    @staticmethod
    # boundary: 任意 awaitable；这里只负责跑它并吞异常
    async def _quietly(awaitable: Any) -> None:
        """跑一件投递/清理，异常只吞不抛。`BaseException`（取消）放行。"""
        try:
            await awaitable
        except Exception:  # noqa: BLE001 - 见模块 docstring 的第二条
            return
