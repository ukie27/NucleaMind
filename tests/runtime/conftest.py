"""装配根测试的公共闸门：断言它们不碰真实网络，也不看见开发环境里装了什么插件。

职责：两条 autouse 夹具——把出站连接与名字解析拦掉，以及把 entry point 发现清空。
`D23` 的用例装的是**真实**内建清单的一个变体（模型换成 Fake），前者是「装配一次实例
不会连出去」这件事的可执行断言。
不负责：限制文件访问（用例只写 `tmp_path`）。

**为什么不整体拦掉 `socket.socket` 的构造**：Windows 上 asyncio 的 `ProactorEventLoop`
自身要用 `socket.socketpair()` 做 self-pipe，而那是一对回环连接。拦构造会把事件循环一起
拦掉，测试就只能证明「起不来」。因此闸门放在**去哪儿**上：回环放行，其余一律失败并指名
道姓。与 `tests/integration/conftest.py` 同一条判据。
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any

import pytest

from nucleamind.kernel.plugins import ENTRY_POINT_GROUP

#: 允许的目标。事件循环的 self-pipe 只连这几个。
_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost", "", None})

_MESSAGE = "装配根的测试试图访问真实网络"


def _host_of(address: object) -> object:
    return address[0] if isinstance(address, tuple) and address else address


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """出站连接与 DNS 解析只允许打到回环地址。"""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def guard(target: object) -> None:
        host = _host_of(target)
        if host not in _LOOPBACK:
            raise AssertionError(f"{_MESSAGE}：{host!r}")

    def connect(self: socket.socket, address: Any) -> None:  # boundary: stdlib 的地址联合类型
        guard(address)
        return real_connect(self, address)

    def connect_ex(self: socket.socket, address: Any) -> int:  # boundary: 同上
        guard(address)
        return real_connect_ex(self, address)

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:  # boundary: 同上
        guard(host)
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    yield


@pytest.fixture(autouse=True)
def no_ambient_plugins(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """本层用例看到的 entry point 恒为空（`D30` 加）。

    `examples/plugins/` 的两个示例插件在开发环境里是**真的装着的**（`tests/e2e/` 那套
    里程碑用例要求如此），于是「没装任何插件」这个前提在这一层就不再成立——`nm plugins
    list` 会印出两条，`diagnostics.plugins()` 也不再是空元组。那不是回归，是这些用例
    一直依赖着一个它们没有声明的环境事实。

    **patch 的是 `importlib.metadata.entry_points`**：`installed_entry_points()` 在函数
    体内 import 它，因此换掉它就够了；而 `build_inventory` 的 `entry_points` 形参默认值
    在函数定义时就绑好了，改模块属性影响不到那条路。要在这一层验真实 entry point 的用例
    自己传 `entry_points=`，本夹具挡不住那条显式路径——那正是它可注入的理由。
    """
    import importlib.metadata

    real = importlib.metadata.entry_points

    def entry_points(**kwargs: Any) -> Any:  # boundary: stdlib 的重载签名
        if kwargs.get("group") == ENTRY_POINT_GROUP:
            return ()
        return real(**kwargs)

    monkeypatch.setattr(importlib.metadata, "entry_points", entry_points)
    yield
