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
- **`deliver()` 不抛**。契约 docstring 写的是「投递失败抛 `EXTERNAL_CHANNEL`」，但
  `emit_outbound` 没有 try/except，真抛出去会把一次**成功**的 turn 变成失败，而 `EDG-204`
  要的恰恰是「投递失败时 turn 继续到终态并完整持久化」。两个现存实现（`cli_entry`、
  `openai-api`）都选了不抛，这里跟随它们；那条矛盾记在 `contracts/protocols.py` 里等
  `channel.delivery_failed` 落地时一并解决。
- **`receive()` 里畸形消息丢弃并继续，不终止整个 Channel**（`MSG-004`）：一条看不懂的
  平台事件不该让 bot 下线。

**`deliver()` 可能被并发调用**（`D33` 的泵扇出之后），但**同一 conversation 内不会**——
`stream.py` 的缓冲表因此按 conversation 分片而不加锁。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Final

from nucleamind.contracts import InboundMessage, OutboundMessage, SecretStr, StreamState

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
        """投递一条出站消息。**不抛**，见模块 docstring。"""
        if not self._show_reasoning and message.metadata.get(_REASONING):
            return
        await self._quietly(self._relay.handle(message))
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

    @staticmethod
    # boundary: 任意 awaitable；这里只负责跑它并吞异常
    async def _quietly(awaitable: Any) -> None:
        """跑一件投递/清理，异常只吞不抛。`BaseException`（取消）放行。"""
        try:
            await awaitable
        except Exception:  # noqa: BLE001 - 见模块 docstring 的第二条
            return
