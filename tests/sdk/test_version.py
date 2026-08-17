"""SDK 版本与兼容判定（技术方案 §7.6、`SDK-005`）。"""

from __future__ import annotations

import pytest
from packaging.version import Version

from nucleamind.contracts import ErrorCode, NucleaError
from nucleamind.sdk import SDK_VERSION, is_compatible


def test_sdk_version_is_a_valid_pep440_version() -> None:
    assert Version(SDK_VERSION)


def test_sdk_version_is_one_point_x() -> None:
    """§7.6 的兼容承诺已经起算（`D42` 发的 1.0.0，`D45` 起是 1.1.0）。

    原来这里断言的是 `major == 0`，并在 docstring 里写着「发 1.0 时本用例会失败——那是
    刻意的提醒」。它**真的按设计失败了一次**，`D42` 顺着它确认了承诺可兑现：十一个官方
    插件验证过这个表面，`D41`/`D42` 补齐了它们撞出来的四个缺口。

    往后 `major == 2` 时这条同样会失败，同样是刻意的：那意味着一次破坏性变更，
    需要有人确认 §7.6 的迁移与维护窗口都安排好了。
    """
    assert Version(SDK_VERSION).major == 1


@pytest.mark.parametrize(
    ("sdk_range", "version", "expected"),
    [
        (">=0.1,<0.2", "0.1.0", True),
        (">=0.1,<0.2", "0.1.7", True),
        (">=0.1,<0.2", "0.2.0", False),
        (">=0.1,<0.2", "0.0.9", False),
        (">=1.0", "0.1.0", False),
        # 预发布必须能被普通范围接纳，否则跑一遍 0.2.1rc1 就得先改所有插件的 manifest。
        (">=0.2,<0.3", "0.2.1rc1", True),
        # 但 `0.2.0rc1 < 0.2.0` 是 PEP 440 的排序事实，不是预发布策略：它确实不满足 `>=0.2`。
        (">=0.2,<0.3", "0.2.0rc1", False),
        ("", "0.1.0", True),
    ],
)
def test_is_compatible(sdk_range: str, version: str, expected: bool) -> None:
    assert is_compatible(sdk_range, sdk_version=version) is expected


def test_current_version_satisfies_its_own_major_range() -> None:
    major_minor = ".".join(SDK_VERSION.split(".")[:2])
    assert is_compatible(f"=={major_minor}.*")


@pytest.mark.parametrize("bad", [">>1", "not-a-range", "0.1"])
def test_invalid_range_is_rejected_rather_than_treated_as_compatible(bad: str) -> None:
    """「解析不了就当全兼容」正好会让最该被拦下的插件通过（`CMP-001`）。"""
    with pytest.raises(NucleaError) as excinfo:
        is_compatible(bad)
    assert excinfo.value.code is ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED
    assert "sdk_range" in str(excinfo.value.detail)


def test_invalid_version_is_rejected() -> None:
    with pytest.raises(NucleaError) as excinfo:
        is_compatible(">=0.1", sdk_version="not-a-version!")
    assert excinfo.value.code is ErrorCode.PLUGIN_MANIFEST_UNSUPPORTED
