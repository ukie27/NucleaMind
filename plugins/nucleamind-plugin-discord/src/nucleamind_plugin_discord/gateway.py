"""**唯一**接触 `discord.py` 的模块（`MSG-004`，开发方案 `D33`）。

职责：连接与断开 gateway；把 `discord.Message` 拍成本插件自己的 `RawInbound`；
把发消息 / 编辑 / 反应 / typing 收敛成 `Platform` 与 `Reactions` 两个 Protocol 的实现。
不负责：判定该不该处理（`normalize.py`）、分段（`outbound.py`）、流式时机（`stream.py`）、
指示器的生命周期（`indicators.py`）。

**这个边界是整个测试计划的支点。** `discord` 只在这里出现，而且只在 `TYPE_CHECKING` 下
标注；其余模块只对 `RawInbound` 与两个 Protocol 编程，因此**不装 `discord.py` 也能跑
全部线格式与判定的用例**。legacy 的做法是在测试文件第 11 行写
`pytest.importorskip("discord")`——那意味着 CI 没装依赖时 52 个用例静默全跳。

**惰性 import**：`discord.py` 只在 `connect()` 里被 import。装了本插件却没装它时给一句能
照做的错误（`EXTERNAL_CHANNEL` + `detail.fix`），而不是在导入 manifest 时就炸掉整个实例
——`openai-api` 对 `aiohttp` 的同一条做法。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Sequence
from datetime import UTC, datetime
from io import BytesIO
from typing import Any, Final

from nucleamind.contracts import ErrorCode, NucleaError, SecretStr

from .normalize import RawAttachment, RawAuthor, RawInbound

__all__ = ["DiscordGateway", "MISSING_SDK_FIX", "to_raw"]

MISSING_SDK_FIX: Final = "pip install 'nucleamind-plugin-discord[gateway]'"

_MISSING_SDK: Final = "Discord Channel 需要 discord.py，但当前环境里没有装。"
_CONNECT_FAILED: Final = "无法连接 Discord gateway。"

#: 只有这两种消息带用户的 prompt；其余是系统消息。取值与 `normalize._USER_MESSAGE_TYPES`
#: 对应——那边按字符串判定，这边负责把 SDK 的枚举翻成同一批字符串。
_USER_TYPES: Final[frozenset[str]] = frozenset({"default", "reply"})


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _id_of(value: object) -> str:
    """把 SDK 对象或裸 id 变成稳定的字符串键。Discord 的 id 是 64 位整数。"""
    raw = getattr(value, "id", value)
    return "" if raw is None else str(raw)


def to_raw(message: Any) -> RawInbound:  # boundary: discord.Message，只在本模块解构
    """`discord.Message` → `RawInbound`。**这是 SDK 对象能走到的最后一步。**

    它是纯函数（不碰网络），因此用例可以用一个手写的假消息驱动它——那正是
    `tests/_fakes.py` 在做的事。
    """
    channel = message.channel
    reference = getattr(message, "reference", None)
    resolved = getattr(reference, "resolved", None) or getattr(reference, "cached_message", None)
    kind = getattr(getattr(message, "type", None), "name", "default")
    created = getattr(message, "created_at", None)
    return RawInbound(
        message_id=_id_of(message),
        channel_id=_id_of(channel),
        author=RawAuthor(
            id=_id_of(message.author),
            display_name=_text(getattr(message.author, "display_name", "")),
            is_bot=bool(getattr(message.author, "bot", False)),
        ),
        content=_text(getattr(message, "content", "")),
        timestamp=created if isinstance(created, datetime) else datetime.now(UTC),
        message_type=kind if kind in _USER_TYPES else str(kind),
        guild_id=_id_of(message.guild) or None if getattr(message, "guild", None) else None,
        parent_channel_id=_id_of(getattr(channel, "parent_id", None)) or None,
        reply_to=_id_of(getattr(reference, "message_id", None)) or None,
        reply_to_author_id=_id_of(getattr(resolved, "author", None)) or None,
        mention_ids=tuple(_id_of(user) for user in getattr(message, "mentions", ()) or ()),
        attachments=tuple(
            RawAttachment(
                filename=_text(getattr(item, "filename", "")),
                url=_text(getattr(item, "url", "")),
                size=int(getattr(item, "size", 0) or 0),
                content_type=_text(getattr(item, "content_type", "")),
            )
            for item in getattr(message, "attachments", ()) or ()
        ),
    )


class DiscordGateway:
    """gateway 连接 + `Platform` / `Reactions` 的实现。

    `on_message` 是注入的回调而不是被继承的方法：Channel 拥有那条消息路径，
    gateway 只负责把它交出去。
    """

    __slots__ = ("_client", "_intents", "_on_message", "_proxy", "_proxy_auth", "_task", "_token")

    def __init__(
        self,
        *,
        token: SecretStr,
        intents: int,
        # boundary: 回调收 discord.Message；`Coroutine` 的两个 Any 是 stdlib 的形状
        on_message: Callable[[Any], Coroutine[Any, Any, None]],
        proxy: str | None = None,
        proxy_auth: tuple[str, SecretStr] | None = None,
    ) -> None:
        self._token = token
        self._intents = intents
        self._on_message = on_message
        self._proxy = proxy
        self._proxy_auth = proxy_auth
        self._client: Any = None  # boundary: discord.Client
        self._task: asyncio.Task[None] | None = None

    @property
    def bot_user_id(self) -> str:
        """本 bot 自己的账号 id；`on_ready` 之前是空串。自环与 @ 门控都要它。"""
        user = getattr(self._client, "user", None)
        return _id_of(user) if user is not None else ""

    async def connect(self) -> None:
        """起 gateway。

        **异常约定**：SDK 没装或连接失败抛 `EXTERNAL_CHANNEL`；两者的 `detail` 分得开，
        因为补救动作不同（装依赖 vs 查 token/网络）。
        """
        client = self._build_client()
        self._client = client
        kwargs: dict[str, Any] = {}  # boundary: 传给 SDK 的关键字
        if self._proxy:
            kwargs["proxy"] = self._proxy
            if self._proxy_auth is not None:
                kwargs["proxy_auth"] = self._basic_auth(*self._proxy_auth)
        try:
            await client.login(self._token.reveal(), **kwargs)
        except Exception as exc:  # noqa: BLE001 - SDK 的原生异常不得逸出（`protocols.py`）
            raise NucleaError(
                ErrorCode.EXTERNAL_CHANNEL,
                _CONNECT_FAILED,
                detail={"exception": type(exc).__name__},
                retryable=True,
            ) from exc
        self._task = asyncio.create_task(client.connect(), name="discord:gateway")

    async def close(self) -> None:
        """断开。**约定不抛**（`Channel.stop()` 的契约），多次调用安全。"""
        task, self._task = self._task, None
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.close()
            except Exception:  # noqa: BLE001 - 停止路径上的失败不该盖住其余收尾
                pass
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    # ------------------------------------------------------------------ Platform

    async def send(
        self, conversation_id: str, content: str, *, reply_to: str | None
    ) -> Any:  # boundary: 返回 discord.Message，交给 `stream.SentMessage` 用
        channel = await self._channel(conversation_id)
        kwargs: dict[str, Any] = {"content": content}  # boundary: 传给 SDK 的关键字
        if reply_to:
            reference = self._partial(channel, reply_to)
            if reference is not None:
                kwargs["reference"] = reference
                # **不 ping 被回复的人**：turn 的回复本来就在他眼前，再 @ 一次是噪声。
                kwargs["allowed_mentions"] = self._no_reply_ping()
        return await channel.send(**kwargs)

    async def send_files(
        self, conversation_id: str, files: Sequence[tuple[str, bytes]], *, reply_to: str | None
    ) -> None:
        """上传附件（`D47`）。一条消息带多个文件，不是每个文件一条消息。

        **字节由调用方读好**（`channel.py` 经 `ctx.fs.read_bytes`）：本模块只负责平台 API，
        不同时承担 Workspace 文件读取。
        `discord.File` 收一个类文件对象，因此这里包一层 `BytesIO`——`discord.py` 会自己
        读完它，不需要我们关。
        """
        del reply_to  # 附件消息不带引用：它紧跟在正文之后，引用只会重复一次同样的上下文
        discord_module = self._import_sdk()
        channel = await self._channel(conversation_id)
        payload = [discord_module.File(BytesIO(data), filename=name) for name, data in files]
        await channel.send(files=payload)

    # ------------------------------------------------------------------ Reactions

    async def add_reaction(self, conversation_id: str, message_id: str, emoji: str) -> None:
        message = await self._message(conversation_id, message_id)
        await message.add_reaction(emoji)

    async def clear_reaction(self, conversation_id: str, message_id: str, emoji: str) -> None:
        message = await self._message(conversation_id, message_id)
        await message.remove_reaction(emoji, self._client.user)

    async def type_once(self, conversation_id: str) -> None:
        channel = await self._channel(conversation_id)
        await channel.typing()

    # ------------------------------------------------------------------ 内部

    def _build_client(self) -> Any:  # boundary: discord.Client
        discord_module = self._import_sdk()
        intents = discord_module.Intents(self._intents)
        client = discord_module.Client(intents=intents)

        @client.event
        # boundary: discord.Message，下一行的 `to_raw()` 就把它拍成 `RawInbound`
        async def on_message(message: Any) -> None:  # pyright: ignore[reportUnusedFunction]
            await self._on_message(message)

        return client

    @staticmethod
    def _import_sdk() -> Any:  # boundary: discord 模块本身
        try:
            import discord as discord_module
        except ImportError as exc:
            raise NucleaError(
                ErrorCode.EXTERNAL_CHANNEL,
                _MISSING_SDK,
                detail={"fix": MISSING_SDK_FIX},
            ) from exc
        return discord_module

    def _no_reply_ping(self) -> Any:  # boundary: discord.AllowedMentions
        return self._import_sdk().AllowedMentions(replied_user=False)

    @staticmethod
    def _basic_auth(username: str, password: SecretStr) -> Any:  # boundary: aiohttp.BasicAuth
        """代理认证。`aiohttp` 只为这一件事被 import（legacy 的同一条）。"""
        import aiohttp

        return aiohttp.BasicAuth(username, password.reveal())

    async def _channel(self, conversation_id: str) -> Any:  # boundary: discord 频道对象
        """取频道对象。缓存未命中时回落到一次 `fetch_channel`。"""
        client = self._client
        if client is None:
            raise NucleaError(ErrorCode.EXTERNAL_CHANNEL, "Discord gateway 尚未连接。")
        channel = client.get_channel(int(conversation_id))
        if channel is None:
            channel = await client.fetch_channel(int(conversation_id))
        return channel

    async def _message(self, conversation_id: str, message_id: str) -> Any:  # boundary: discord.Message
        channel = await self._channel(conversation_id)
        return await channel.fetch_message(int(message_id))

    @staticmethod
    def _partial(channel: Any, message_id: str) -> Any:  # boundary: discord 频道与 PartialMessage
        """回复引用。id 不是数字时**放弃引用而不是整条不发**——引用是装饰。"""
        try:
            return channel.get_partial_message(int(message_id))
        except (ValueError, AttributeError):
            return None
