"""工具契约测试（`D03`，需求 §10.5、`TOL-001`–`TOL-004`、`EDG-401`、`EDG-402`、`EDG-407`）。

两条不肯让步的规则各有一组用例：`side_effect` 没有默认值（构造点必须表态），
`ok=False` 必须带 `error`（错误不得伪装成普通成功文本）。
"""

from __future__ import annotations

import dataclasses

import pytest

from nucleamind.contracts import (
    ArtifactRef,
    Concurrency,
    Correlation,
    ErrorCode,
    InstanceId,
    NucleaError,
    PermissionKind,
    RiskLevel,
    SessionKey,
    SideEffect,
    ToolCall,
    ToolInvocation,
    ToolResult,
    ToolSpec,
    TurnId,
)
from nucleamind.contracts.tool import MAX_TOOL_RESULT_LENGTH

CORRELATION = Correlation(InstanceId("default"), SessionKey("cli", "local"), TurnId("t-1"))
SCHEMA = {"type": "object", "properties": {"path": {"type": "string"}}}


def spec(**overrides: object) -> ToolSpec:
    base: dict[str, object] = {
        "name": "fs.read",
        "description": "读取工作区内的文件。",
        "parameters": SCHEMA,
    }
    base.update(overrides)
    return ToolSpec(**base)  # pyright: ignore[reportArgumentType]


def result(**overrides: object) -> ToolResult:
    base: dict[str, object] = {
        "call_id": "c-1",
        "ok": True,
        "content": "file body",
        "truncated": False,
        "side_effect": SideEffect.NONE,
    }
    base.update(overrides)
    return ToolResult(**base)  # pyright: ignore[reportArgumentType]


def test_instances_are_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec().name = "x"
    with pytest.raises(dataclasses.FrozenInstanceError):
        result().ok = False


# ------------------------------------------------------------------ ToolSpec / TOL-001


@pytest.mark.parametrize("name", ["FS.Read", "fs-read", "1fs", "fs.", ".read", "fs read", ""])
def test_tool_name_shape_is_enforced(name: str) -> None:
    with pytest.raises(NucleaError) as exc:
        spec(name=name)
    assert exc.value.code is ErrorCode.INPUT_MALFORMED


@pytest.mark.parametrize("name", ["fs.read", "shell.exec", "a", "a.b.c", "web_search"])
def test_valid_tool_names_are_accepted(name: str) -> None:
    assert spec(name=name).name == name


def test_description_is_required() -> None:
    """模型只能靠描述决定是否调用，空描述等于把工具藏起来。"""
    with pytest.raises(NucleaError) as exc:
        spec(description="")
    assert exc.value.code is ErrorCode.INPUT_MALFORMED


def test_read_only_tool_must_be_safe() -> None:
    assert spec(read_only=True, risk=RiskLevel.SAFE).read_only
    with pytest.raises(NucleaError):
        spec(read_only=True, risk=RiskLevel.DESTRUCTIVE)


def test_read_only_tool_cannot_request_write_permission() -> None:
    with pytest.raises(NucleaError):
        spec(
            read_only=True,
            risk=RiskLevel.SAFE,
            permissions=frozenset({PermissionKind.FS_WRITE}),
        )


def test_permission_values_match_host_api() -> None:
    """技术方案 §7.5 的权限字符串是 manifest 的一部分，改名等于改插件接口。"""
    assert {kind.value for kind in PermissionKind} == {
        "fs:read",
        "fs:write",
        "net",
        "shell",
        "secret",
    }


def test_default_concurrency_is_parallel() -> None:
    assert spec().concurrency is Concurrency.PARALLEL


# ------------------------------------------------------------------ ToolCall / ToolInvocation


def test_tool_call_arguments_are_frozen_snapshot() -> None:
    args = {"path": "a.md"}
    call = ToolCall("c-1", "fs.read", args)
    args["path"] = "b.md"
    assert call.arguments["path"] == "a.md"


def test_tool_call_rejects_non_json_arguments() -> None:
    with pytest.raises(NucleaError):
        ToolCall("c-1", "fs.read", {"handle": object()})  # pyright: ignore[reportArgumentType]


def test_invocation_timeout_must_be_positive() -> None:
    """`KER-009`：缺省配置下不存在无界执行路径，因此没有「永不超时」这个选项。"""
    with pytest.raises(NucleaError) as exc:
        ToolInvocation(ToolCall("c-1", "fs.read"), CORRELATION, timeout_ms=0)
    assert exc.value.code is ErrorCode.INPUT_MALFORMED


def test_auto_retry_requires_idempotency_key() -> None:
    """`EDG-402`：可能重复提交的工具要么带幂等键，要么禁止自动重试。"""
    call = ToolCall("c-1", "fs.read")
    assert ToolInvocation(call, CORRELATION, 1000).auto_retry_allowed is False
    assert ToolInvocation(call, CORRELATION, 1000, idempotency_key="k-1").auto_retry_allowed


# ------------------------------------------------------------------ ToolResult / §10.5


def test_side_effect_has_no_default() -> None:
    """必填三态：每个构造点都必须显式表态（`EDG-401`、`EDG-407`）。"""
    field = next(f for f in dataclasses.fields(ToolResult) if f.name == "side_effect")
    assert field.default is dataclasses.MISSING
    assert field.default_factory is dataclasses.MISSING


def test_side_effect_unknown_is_a_first_class_state() -> None:
    """取消宽限期用尽时写入的正是这个组合（技术方案 §6.4）。"""
    cancelled = result(
        ok=False,
        content="",
        side_effect=SideEffect.UNKNOWN,
        error=NucleaError(ErrorCode.TIMEOUT_TOOL_CALL, "工具未在宽限期内返回。"),
    )
    assert cancelled.side_effect is SideEffect.UNKNOWN


def test_failure_must_carry_error() -> None:
    with pytest.raises(NucleaError) as exc:
        result(ok=False, content="出错了")
    assert exc.value.code is ErrorCode.KERNEL_INVARIANT_VIOLATED


def test_success_must_not_carry_error() -> None:
    with pytest.raises(NucleaError) as exc:
        result(error=NucleaError(ErrorCode.KERNEL_UNEXPECTED, "boom"))
    assert exc.value.code is ErrorCode.KERNEL_INVARIANT_VIOLATED


def test_oversized_content_is_rejected() -> None:
    """`TOL-003`：截断在执行器侧完成，契约只拦「截断没做」。"""
    with pytest.raises(NucleaError) as exc:
        result(content="x" * (MAX_TOOL_RESULT_LENGTH + 1))
    assert exc.value.code is ErrorCode.INPUT_TOO_LARGE


def test_negative_duration_is_rejected() -> None:
    with pytest.raises(NucleaError):
        result(duration_ms=-1)


def test_data_is_normalized() -> None:
    assert result(data={"lines": 3}).data == {"lines": 3}
    with pytest.raises(NucleaError):
        result(data={"raw": object()})


def test_error_detail_is_already_redacted() -> None:
    """堆栈不进这里；`NucleaError` 在构造时已完成脱敏（§10.5 末段）。"""
    failure = NucleaError(
        ErrorCode.EXTERNAL_MODEL_PROVIDER,
        "调用失败",
        detail={"api_key": "sk-abcdefghijklmnop0123"},
    )
    assert result(ok=False, content="", error=failure).error is failure
    assert "sk-" not in repr(failure)


def test_artifact_requires_media_type() -> None:
    assert ArtifactRef("artifacts/out.png", "image/png").media_type == "image/png"
    with pytest.raises(NucleaError) as exc:
        ArtifactRef("artifacts/out.png", "")
    assert exc.value.code is ErrorCode.INPUT_UNSUPPORTED_MEDIA
