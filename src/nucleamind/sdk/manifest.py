"""插件 manifest：声明式的数据与校验（技术方案 §7.2，需求 `PLG-001`、`SDK-005`、`CMP-001`）。

职责：定义 `CapabilityDecl` / `PermissionDecl` / `PluginManifest` 三个数据类型及其校验
规则，并提供把外部数据（`plugin.toml`、entry point 模块里的字面量）解析为 manifest 的
`parse_manifest()`。
不负责：发现插件、导入 `setup`、解析依赖拓扑、判定权限是否已被授权——那些在
`kernel/plugins/`（`D25`–`D27`）；本模块不读文件、不访问网络、不碰全局状态。

**导入本模块必须无副作用且廉价**（§7.2 硬约束）。阶段 A 校验要保持在毫秒级
（`NFR-401`、`NFR-403`），所以这里只有类型定义与纯函数，没有任何 import 时执行的逻辑。

错误面刻意收窄成一种异常：

- 语义校验（id 形状、PEP 440、覆盖目标、能力重名）直接抛 `NucleaError`。pydantic 只
  截获 `ValueError` / `AssertionError`，其他异常原样穿透，这一点是有意利用的。
- 结构错误（缺字段、类型不符、多余字段）由 pydantic 报 `ValidationError`；从外部数据
  进来的路径一律走 `parse_manifest()`，它把 `ValidationError` 转成带**字段路径**的
  `NucleaError(PLUGIN_MANIFEST_UNSUPPORTED)`。`CMP-001` 要的就是「列出字段路径而不是
  兜底猜测」。
"""

from __future__ import annotations

import string
import sys
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from typing import Final

from packaging.version import InvalidVersion, Version
from pydantic import (
    BaseModel,
    ConfigDict,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)

from nucleamind.contracts import (
    Builtin,
    CapabilityArity,
    CapabilityKind,
    CapabilityRef,
    ErrorCode,
    NucleaError,
    PermissionKind,
    Plugin,
    PluginId,
    ProviderId,
    parse_capability_target,
)

from .version import is_compatible, parse_sdk_range

__all__ = [
    "MANIFEST_MODEL_CONFIG",
    "CapabilityDecl",
    "PermissionDecl",
    "PluginManifest",
    "parse_manifest",
]

#: 插件 id 的字符集。比 `contracts` 的能力名更严（不含 `.` 与 `_`），与 §12.2
#: 「插件 id 小写短横线」一致：id 会出现在包名 `nucleamind-plugin-<id>`、状态目录名和
#: `plugin:<id>:<name>` 覆盖目标串里，多一种分隔符就多一处可以歧义的地方。
_ID_CHARS: Final[frozenset[str]] = frozenset(string.ascii_lowercase + string.digits + "-")

#: `setup` 字段的分隔符：`"pkg.module:function"`。
_SETUP_SEPARATOR: Final = ":"

#: 三个模型共用的配置。`extra="forbid"` 让拼错的字段成为错误而不是被静默丢弃——
#: 一个被忽略的 `permisions` 拼写错误等于插件带着未声明的权限意图上线。
MANIFEST_MODEL_CONFIG: Final = ConfigDict(extra="forbid", frozen=True)


def _fail(code: ErrorCode, message: str, **detail: object) -> NucleaError:
    """错误码作为第一个参数，与 `contracts.metadata._fail` 同形。

    manifest 的失败几乎都是 `PLUGIN_MANIFEST_UNSUPPORTED`（INCOMPATIBLE 类）：这份声明
    在当前 SDK 下不可用。逐次写出错误码是刻意的——`AGENTS.md` 禁止在 `contracts` 之外
    出现错误码字面量，`ErrorCode` 成员不是字面量，而藏进默认值会让「这里抛的是哪一类」
    要翻到函数定义才知道。
    """
    return NucleaError(code, message, detail=detail)


@contextmanager
def _at_field(field: str) -> Generator[None, None, None]:
    """把 `contracts` 抛出的形状错误重贴上 manifest 的字段路径。

    `CapabilityRef`、`Plugin`、`parse_capability_target` 报的是 `INPUT_MALFORMED` 且只
    知道自己那个值，不知道它在 manifest 里叫什么。不转换的话，「manifest 校验失败一律是
    `PLUGIN_MANIFEST_UNSUPPORTED` 且带字段路径」这条承诺就有三个漏洞，而调用方要为它们
    单独写分支（`CMP-001`）。原始 detail 挂在 `cause` 下，定位信息不丢。
    """
    try:
        yield
    except NucleaError as exc:
        raise _fail(
            ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
            exc.user_message,
            field=field,
            cause=dict(exc.detail),
        ) from exc


def _validate_plugin_id(value: str, *, field: str) -> str:
    """插件 id 的形状。先过 `Plugin()`，因为 id 最终就是要变成 `ProviderId` 的那个串。"""
    with _at_field(field):
        Plugin(PluginId(value))
    if not value or value[0] == "-" or value[-1] == "-" or set(value) - _ID_CHARS:
        raise _fail(
            ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
            "插件 id 只能由小写字母、数字和中划线组成，且不以中划线开头或结尾。",
            field=field,
            value=value,
        )
    return value


class CapabilityDecl(BaseModel):
    """一项能力声明（§7.2）。

    `kind` + `name` 定位能力，`overrides` 是**唯一**的覆盖来源——覆盖永不由加载顺序
    决定（`EDG-102`）。`priority` 只对 MULTI 类能力（CONTEXT / HOOK）有意义，其余 kind
    的排序由 arity 语义决定，填了也不会被用来打破唯一性。

    **`namespace=True` 时 `name` 是前缀而不是能力名**（`D38-A`）：本条声明放行提供方注册
    任意多条 `<name>.<后缀>` 的能力。它是为「能力名要连上外部服务才知道」这类插件开的——
    MCP 的远端工具名只有 `list_tools` 之后才可知，而 manifest 是静态的。做成显式布尔而不是
    `name="mcp.*"` 这样的通配串，是因为后者会让「名字」这个字段有两种含义，
    而 `CapabilityRef` 的形状校验对通配串又不成立（原则 7「显式优于魔法」）。

    形状先例就在 `kernel/plugins/host.py::on()`：Hook 早就是「一条声明、N 次注册」
    （`<hook>.2` / `.3` 派生名按基名回查声明）。命名空间是同一形状的推广。

    两条限制（`_check_namespace`）：只允许 arity 为 MULTI_UNIQUE 的 kind，且不得同时声明
    `overrides`——一个前缀覆盖不到一个具体目标，`EDG-102` 的判定会无从进行。
    """

    model_config = MANIFEST_MODEL_CONFIG

    kind: CapabilityKind
    name: str
    overrides: str | None = None
    priority: int = 100
    namespace: bool = False

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        """能力名的形状由 `CapabilityRef` 定义，这里借它校验而不是另写一套。

        构造出来的引用随即丢弃：manifest 阶段还不知道自己的 `ProviderId`（那要等
        `PluginManifest.id` 一起才成立），但名字的合法性与 provider、与 kind 都无关。
        """
        with _at_field("capabilities.name"):
            CapabilityRef(kind=CapabilityKind.TOOL, name=value, provider=Builtin())
        return value

    @field_validator("overrides")
    @classmethod
    def _check_overrides(cls, value: str | None) -> str | None:
        """覆盖目标串只用 `parse_capability_target()` 解码，不在此另写正则。"""
        if value is not None:
            with _at_field("capabilities.overrides"):
                parse_capability_target(value)
        return value

    @field_validator("priority")
    @classmethod
    def _check_priority(cls, value: int) -> int:
        if value < 0:
            raise _fail(
                ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
                "能力优先级不得为负。",
                field="priority",
                priority=value,
            )
        return value

    @property
    def override_target(self) -> tuple[ProviderId, str] | None:
        """解码后的覆盖目标 `(提供方, 能力名)`；未声明覆盖时为 `None`。"""
        return None if self.overrides is None else parse_capability_target(self.overrides)

    @property
    def slot(self) -> tuple[CapabilityKind, str]:
        """同一 manifest 内的唯一性键。"""
        return (self.kind, self.name)

    @model_validator(mode="after")
    def _check_namespace(self) -> CapabilityDecl:
        """命名空间声明的两条限制。

        **只允许 arity 为 MULTI_UNIQUE 的 kind**：SINGLETON 的槽位按定义只有一个，
        给它开一个前缀等于让「唯一」失去判定对象；MULTI 类（CONTEXT / HOOK）本来就允许
        同一提供方注册多条同名能力，不需要这个机制。判据取自 `CAPABILITY_ARITY` 而不是
        一张手写的 kind 名单——那张表已经是**全部冲突语义的唯一来源**，在这里另写一份
        必然与它分叉。

        **不得与 `overrides` 并存**：`overrides` 指向一个具体的 `(提供方, 能力名)`，
        而一条声明能注册出任意多个名字——哪一个才是覆盖者无从判定，而静默挑一个正是
        `EDG-102`「覆盖永不由加载顺序决定」要堵的路。
        """
        if not self.namespace:
            return self
        if self.kind.arity is not CapabilityArity.MULTI_UNIQUE:
            raise _fail(
                ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
                "只有可并存且按名字唯一的能力才能声明命名空间。",
                field="namespace",
                kind=self.kind.value,
                arity=self.kind.arity.value,
            )
        if self.overrides is not None:
            raise _fail(
                ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
                "命名空间声明不能同时声明 overrides。",
                field="overrides",
                name=self.name,
            )
        return self


class PermissionDecl(BaseModel):
    """一项权限声明（§7.5、`NFR-301`、`NFR-307`）。

    `reason` 必填：授予是用户的显式操作，用户得知道自己在批准什么。它会出现在授权提示
    与 `permissions.json` 的审计记录里，因此「因为需要」这种废话在评审阶段就该被打回。

    `target` 把权限收窄到具体对象（`secret` 的密钥名、`fs:read` 的相对路径前缀）。
    `secret` 必须带 target——`secret:*` 等于「给我全部凭据」，那不是最小权限。
    """

    model_config = MANIFEST_MODEL_CONFIG

    kind: PermissionKind
    reason: str
    target: str = ""

    @field_validator("reason")
    @classmethod
    def _check_reason(cls, value: str) -> str:
        if not value.strip():
            raise _fail(
                ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
                "权限声明必须写明用途，它会直接展示给授权的用户。",
                field="reason",
            )
        return value

    @model_validator(mode="after")
    def _check_secret_target(self) -> PermissionDecl:
        if self.kind is PermissionKind.SECRET and not self.target:
            raise _fail(
                ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
                "secret 权限必须指明密钥名——不带 target 等于申请全部凭据。",
                field="target",
            )
        return self

    @property
    def grant_key(self) -> tuple[PermissionKind, str]:
        """授权记录的键。同 kind 不同 target 是两条独立授权。"""
        return (self.kind, self.target)


class PluginManifest(BaseModel):
    """插件的全部声明（§7.2）。

    manifest 是数据不是代码：读它**不需要**导入插件实现。这是「发现与启用分离」
    （§7.1）成立的前提——未启用的插件只被读 manifest，不产生任何导入开销。
    """

    model_config = MANIFEST_MODEL_CONFIG

    id: str
    version: str
    sdk_range: str
    setup: str
    capabilities: tuple[CapabilityDecl, ...]
    dependencies: tuple[str, ...] = ()
    permissions: tuple[PermissionDecl, ...] = ()
    # 语义上就是 `contracts.JsonSchema`，但值类型用 **pydantic 的** `JsonValue`：
    # `contracts.JsonValue` 是带前向引用的普通递归 Union，pydantic 为它生成 schema 时会
    # 无限递归。两者互相兼容（pydantic 的 list/dict 是我们的 Sequence/Mapping 的子类型），
    # 因此 `config_schema` 可以原样喂给任何接受 `JsonSchema` 的调用方。
    # 不再包一层 MappingProxyType：pydantic 在校验时已经深拷贝，调用方事后改自己那份
    # dict 影响不到这里，快照语义已经成立，浅冻结只是装样子。
    config_schema: Mapping[str, JsonValue] | None = None
    state_version: int = 1
    critical: bool = False
    platforms: tuple[str, ...] = ()
    runtime_requires: tuple[str, ...] = ()

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        return _validate_plugin_id(value, field="id")

    @field_validator("version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        try:
            Version(value)
        except InvalidVersion as exc:
            raise _fail(
                ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
                "插件版本不符合 PEP 440。",
                field="version",
                version=value,
            ) from exc
        return value

    @field_validator("sdk_range")
    @classmethod
    def _check_sdk_range(cls, value: str) -> str:
        parse_sdk_range(value)
        return value

    @field_validator("setup")
    @classmethod
    def _check_setup(cls, value: str) -> str:
        module, separator, attribute = value.partition(_SETUP_SEPARATOR)
        parts = module.split(".")
        shaped = separator and attribute.isidentifier() and all(p.isidentifier() for p in parts)
        if not shaped:
            raise _fail(
                ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
                'setup 必须形如 "pkg.module:function"。',
                field="setup",
                setup=value,
            )
        return value

    @field_validator("capabilities")
    @classmethod
    def _check_capabilities(cls, value: tuple[CapabilityDecl, ...]) -> tuple[CapabilityDecl, ...]:
        if not value:
            raise _fail(
                ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
                "manifest 必须至少声明一项能力——不注册任何能力的插件没有作用点。",
                field="capabilities",
            )
        slots = [decl.slot for decl in value]
        duplicates = sorted(
            {f"{kind.value}:{name}" for kind, name in slots if slots.count((kind, name)) > 1}
        )
        if duplicates:
            raise _fail(
                ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
                "同一 manifest 内出现重复的 (kind, name)；跨插件的冲突另由覆盖解析处理。",
                field="capabilities",
                duplicates=duplicates,
            )
        return value

    @field_validator("dependencies", "platforms", "runtime_requires")
    @classmethod
    def _check_string_tuples(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise _fail(ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED, "列表项不得为空串。", value=list(value))
        if len(set(value)) != len(value):
            raise _fail(ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED, "列表项不得重复。", value=list(value))
        return value

    @field_validator("state_version")
    @classmethod
    def _check_state_version(cls, value: int) -> int:
        if value < 1:
            raise _fail(
                ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
                "state_version 必须为正。",
                field="state_version",
                state_version=value,
            )
        return value

    @model_validator(mode="after")
    def _check_dependencies(self) -> PluginManifest:
        for dependency in self.dependencies:
            _validate_plugin_id(dependency, field="dependencies")
        if self.id in self.dependencies:
            raise _fail(
                ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
                "插件不得依赖自身。",
                field="dependencies",
                id=self.id,
            )
        grants = [decl.grant_key for decl in self.permissions]
        if len(set(grants)) != len(grants):
            raise _fail(
                ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
                "权限声明重复；同 kind 同 target 只写一条。",
                field="permissions",
                permissions=[f"{kind.value}:{target}" for kind, target in grants],
            )
        return self

    @property
    def sdk_compatible(self) -> bool:
        """当前 SDK 是否落在 `sdk_range` 内（`SDK-005`）。不兼容即拒绝加载。"""
        return is_compatible(self.sdk_range)

    def matches_platform(self, platform: str | None = None) -> bool:
        """当前平台是否在 `platforms` 内。空 `platforms` 表示全平台。

        `platform` 默认取 `sys.platform`，但作为参数暴露出来——平台矩阵测试需要在
        Linux 上断言一个 Windows-only 插件会被跳过，而不是只能在 Windows 上跑。
        """
        return not self.platforms or (platform or sys.platform) in self.platforms


def _format_location(location: Sequence[str | int]) -> str:
    """pydantic 的 `loc` 元组转成人类可读的字段路径：`capabilities.1.kind`。"""
    return ".".join(str(part) for part in location) or "<root>"


def parse_manifest(data: Mapping[str, object], *, origin: str) -> PluginManifest:
    """把外部数据解析为 manifest。这是**唯一**应当用于不可信输入的入口。

    直接 `PluginManifest(...)` 也能用（插件作者在自己的模块里就该那样写），但那条路径
    上的结构错误是 pydantic 的 `ValidationError`。外部数据走本函数，调用方只需要处理
    `NucleaError`：`detail.errors` 是 `[{"field": ..., "message": ...}]`，
    `detail.origin` 说明这份数据来自哪个文件或 entry point（`CMP-001`）。
    """
    try:
        return PluginManifest.model_validate(dict(data))
    except ValidationError as exc:
        raise _fail(
            ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED,
            "插件 manifest 校验失败。",
            origin=origin,
            errors=[
                {"field": _format_location(error["loc"]), "message": error["msg"]}
                for error in exc.errors()
            ],
        ) from exc
