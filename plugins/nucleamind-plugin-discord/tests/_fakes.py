"""`discord` 插件测试的假平台（供同目录的五个测试文件 import）。

职责：手写的 `discord.Message` 形状替身、`Platform` / `Reactions` / `FileReader` 的
记录式实现、可注入的时钟，以及 `RawInbound` / `OutboundMessage` 的构造助手。
不负责：任何断言——每条判定都写在对应的 `test_*.py` 里。

**它们不是 `discord.py` 的对象，只是长得像**：`gateway.to_raw()` 用 `getattr` 解构，
因此一个带对的属性的普通对象就够。这条正是「`gateway.py` 是唯一接触 SDK 的模块」
换来的东西——不装 `discord.py` 也能把归一化逐条钉住。

**不放在 `conftest.py`**：那个文件的职责是零网络闸门那条 autouse 夹具（`D32` 的先例）。
测试目录不是包，pytest 的 prepend 导入模式会把它加进 `sys.path`，因此 `import _fakes` 成立。
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from nucleamind_plugin_discord import DiscordSettings, RawAttachment, RawAuthor, RawInbound
from nucleamind_plugin_discord.normalize import InboundGate

from nucleamind.contracts import (
    ErrorCode,
    InstanceId,
    NucleaError,
    OutboundMessage,
    SecretStr,
    SessionKey,
    StreamState,
    TurnId,
)

CHANNEL_ID = "discord"
CONVERSATION = "555"
BOT_ID = "1"
USER_ID = "42"
TOKEN = SecretStr("discord-bot-token-0123456789")


# ------------------------------------------------------------------ 平台对象的形状替身


class FakeAuthor:
    def __init__(self, user_id: str = USER_ID, *, display_name: str = "", bot: bool = False) -> None:
        self.id = user_id
        self.display_name = display_name
        self.bot = bot


class FakeAttachment:
    def __init__(
        self,
        filename: str = "a.txt",
        *,
        url: str = "https://cdn.discordapp.test/a.txt",
        size: int = 10,
        content_type: str = "text/plain",
    ) -> None:
        self.filename = filename
        self.url = url
        self.size = size
        self.content_type = content_type


class FakeKind:
    """`discord.MessageType` 的形状：`to_raw()` 只读它的 `.name`。"""

    def __init__(self, name: str) -> None:
        self.name = name


class FakeChannel:
    def __init__(self, channel_id: str = CONVERSATION, *, parent_id: str | None = None) -> None:
        self.id = channel_id
        self.parent_id = parent_id


class FakeGuild:
    def __init__(self, guild_id: str = "900") -> None:
        self.id = guild_id


class FakeReference:
    def __init__(self, message_id: str, *, author: FakeAuthor | None = None) -> None:
        self.message_id = message_id
        self.resolved = _Resolved(author) if author is not None else None
        self.cached_message = None


class _Resolved:
    def __init__(self, author: FakeAuthor) -> None:
        self.author = author


class FakeMessage:
    """`discord.Message` 的形状替身。`to_raw()` 全靠 `getattr`，因此这样就够。"""

    def __init__(
        self,
        *,
        message_id: str = "1001",
        content: str = "在吗",
        author: FakeAuthor | None = None,
        channel: FakeChannel | None = None,
        guild: FakeGuild | None = None,
        kind: str = "default",
        mentions: tuple[FakeAuthor, ...] = (),
        attachments: tuple[FakeAttachment, ...] = (),
        reference: FakeReference | None = None,
    ) -> None:
        self.id = message_id
        self.content = content
        self.author = author or FakeAuthor()
        self.channel = channel or FakeChannel()
        self.guild = guild
        self.type = FakeKind(kind)
        self.mentions = mentions
        self.attachments = attachments
        self.reference = reference
        self.created_at = datetime.now(UTC)


# ------------------------------------------------------------------ Protocol 的记录式实现


class FakeSent:
    """一条已发出的消息。`edit()` 把每次编辑记下来。"""

    def __init__(self, content: str) -> None:
        self.content = content
        self.edits: list[str] = []

    async def edit(self, content: str) -> None:
        self.content = content
        self.edits.append(content)


class FakePlatform:
    """`stream.Platform`。`sent` 里是每次 `send()` 的 `(conversation, content, reply_to)`。"""

    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[tuple[str, str, str | None]] = []
        self.messages: list[FakeSent] = []
        #: 每次 `send_files()` 的 `(conversation, [(文件名, 字节), ...])`。
        self.uploads: list[tuple[str, list[tuple[str, bytes]]]] = []
        self.fail = fail

    async def send(self, conversation_id: str, content: str, *, reply_to: str | None) -> FakeSent:
        if self.fail:
            raise RuntimeError("send failed")
        self.sent.append((conversation_id, content, reply_to))
        message = FakeSent(content)
        self.messages.append(message)
        return message

    async def send_files(
        self, conversation_id: str, files: Sequence[tuple[str, bytes]], *, reply_to: str | None
    ) -> None:
        del reply_to
        if self.fail:
            raise RuntimeError("upload failed")
        self.uploads.append((conversation_id, list(files)))


class FakeWorkspace:
    """`ctx.fs` 读取面的替身（`D47`）。按 locator 给字节，找不到就抛。

    抛的是 `NucleaError`，因为 `channel.py::_read_attachment` 只折那一种——一个替身抛
    `KeyError` 会让那条 `except` 看起来是对的，而生产里门面抛的正是 `NucleaError`。
    """

    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self.files = dict(files or {})
        self.reads: list[str] = []

    async def read_bytes(self, path: str) -> bytes:
        self.reads.append(path)
        if path not in self.files:
            raise NucleaError(ErrorCode.PERSISTENCE_READ_FAILED, "没有这个文件。")
        return self.files[path]


class FakeReactions:
    """`indicators.Reactions`。可注入失败，用来验「指示器的失败不影响 turn」。"""

    def __init__(self, *, fail: bool = False) -> None:
        self.added: list[tuple[str, str, str]] = []
        self.cleared: list[tuple[str, str, str]] = []
        self.typed: list[str] = []
        self.fail = fail

    async def add_reaction(self, conversation_id: str, message_id: str, emoji: str) -> None:
        if self.fail:
            raise RuntimeError("reaction failed")
        self.added.append((conversation_id, message_id, emoji))

    async def clear_reaction(self, conversation_id: str, message_id: str, emoji: str) -> None:
        if self.fail:
            raise RuntimeError("reaction failed")
        self.cleared.append((conversation_id, message_id, emoji))

    async def type_once(self, conversation_id: str) -> None:
        if self.fail:
            raise RuntimeError("typing failed")
        self.typed.append(conversation_id)


class FakeClock:
    """可注入的单调时钟，毫秒。**节流与延迟因此是确定的**，用例不必真的等 0.8 秒。"""

    def __init__(self, start: int = 0) -> None:
        self.now = start

    def __call__(self) -> int:
        return self.now

    def advance(self, ms: int) -> None:
        self.now += ms


class FakeSleep:
    """记录每次 `sleep` 的秒数并**让出一次事件循环**。

    `Indicators` 的两处时间语义都经过它。**必须真的让出**：`_type_loop` 是
    `while True: 打字; await sleep(...)`，一个不让出的 `sleep` 会把它变成饿死事件循环的
    死循环——写这套用例时就是这么挂住的。生产里 `asyncio.sleep(8)` 当然会让出，
    因此这不是实现的问题，是替身必须诚实到这一步。
    """

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        await asyncio.sleep(0)


# ------------------------------------------------------------------ 构造助手
#
# 下面四个助手的 `**kwargs: Any` 都是同一件事：它们是**关键字转发器**，把用例写的那几个
# 覆盖项合进一份默认值再交给真正带类型的构造函数。类型检查落在被构造的那个 dataclass 上。


def gate(**kwargs: Any) -> InboundGate:  # boundary: 关键字转发，见上面那段
    """一个默认允许所有人的门控。用例按需收紧。"""
    defaults: dict[str, Any] = {  # boundary: 关键字转发，见上面那段
        "instance_id": InstanceId("test"),
        "channel_id": CHANNEL_ID,
        "bot_user_id": BOT_ID,
    }
    defaults.update(kwargs)
    return InboundGate(**defaults)


def raw(**kwargs: Any) -> RawInbound:  # boundary: 同上
    """一条默认可通过的私聊消息（DM 不受群聊 @ 门控约束）。"""
    defaults: dict[str, Any] = {  # boundary: 关键字转发，见上面那段
        "message_id": "1001",
        "channel_id": CONVERSATION,
        "author": RawAuthor(id=USER_ID),
        "content": "在吗",
        "timestamp": datetime.now(UTC),
    }
    defaults.update(kwargs)
    return RawInbound(**defaults)


def attachment(**kwargs: Any) -> RawAttachment:  # boundary: 同上
    defaults: dict[str, Any] = {  # boundary: 关键字转发，见上面那段
        "filename": "a.txt",
        "url": "https://cdn.discordapp.test/a.txt",
        "size": 10,
        "content_type": "text/plain",
    }
    defaults.update(kwargs)
    return RawAttachment(**defaults)


def outbound(
    content: str = "答案",
    *,
    state: StreamState = StreamState.FINAL,
    conversation: str = CONVERSATION,
    turn: str = "turn-1",
    **kwargs: Any,  # boundary: 同上
) -> OutboundMessage:
    key = SessionKey(channel_id=CHANNEL_ID, conversation_id=conversation)
    return OutboundMessage(
        session_key=key,
        channel_id=key.channel_id,
        conversation_id=key.conversation_id,
        turn_id=TurnId(turn),
        content=content,
        stream_state=state,
        **kwargs,
    )


def settings(**kwargs: Any) -> DiscordSettings:  # boundary: 同上
    defaults: dict[str, Any] = {  # boundary: 关键字转发，见上面那段
        "instance_id": InstanceId("test"),
        "channel_id": CHANNEL_ID,
        "allow_from": frozenset(),
        "allow_channels": frozenset(),
        "operators": frozenset(),
        "group_policy": "mention",
        "intents": 37377,
        "streaming": True,
        "stream_edit_interval_ms": 800,
        "read_receipt_emoji": "👀",
        "working_emoji": "🔧",
        "working_emoji_delay_ms": 2000,
        "typing_interval_ms": 8000,
        "max_attachment_bytes": 20 * 1024 * 1024,
        "proxy": None,
        "proxy_username": None,
    }
    defaults.update(kwargs)
    return DiscordSettings(**defaults)
