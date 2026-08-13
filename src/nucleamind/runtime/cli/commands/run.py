"""`nm run`：装配实例、安装信号处理、把进程交给 CLI 入口能力（§10.1、§10.3）。

职责：把 `bootstrap()` → `start()` → `cli_entry.run()` → `stop()` 串成一条命令，
并实现两次 `Ctrl-C` 的语义。
不负责：解析交互参数（那是 CLI 入口能力自己的事，`-p` 由它认）、渲染输出。

**两次 `Ctrl-C` 的语义**（`contracts.CliEntry.run` 的取消语义、§10.3）：
第一次在有 turn 在跑时**取消那些 turn**，会话继续；没有 turn 在跑时它是「退出」。
第二次（或退出那一次）请求入口的取消令牌，随后强制结束进程——读 stdin 的工作线程没有
可移植的唤醒方式（`builtins/cli_entry/entry.py::_readline` 如实写着这条），干等它只会
让用户按第三次。**强制退出前先跑一遍 `stop()`**，实例锁因此正常释放。
"""

from __future__ import annotations

import asyncio
import os
import sys

from nucleamind.contracts import CancelReason
from nucleamind.kernel.turn import CancelToken

from ...bootstrap import bootstrap
from ...instance import AgentInstance
from ..main import Options, install_cancel_handler

__all__ = ["run_command"]

#: 强制退出前留给 `stop()` 的时间。收尾只有取消任务与关文件，超过它多半是卡住了。
_STOP_GRACE_S = 3.0


def run_command(options: Options) -> int:
    """同步入口。`asyncio.run` 只在这里出现一次——`nm` 的其余命令都不需要事件循环。"""
    return asyncio.run(_run(options))


async def _run(options: Options) -> int:
    instance = await bootstrap(
        instance=options.instance,
        instance_dir=options.instance_dir,
        overrides=options.overrides,
    )
    cancel = CancelToken()
    interrupts = _Interrupts(instance, cancel)
    install_cancel_handler(asyncio.get_running_loop(), interrupts)
    try:
        await instance.start()
        return await instance.run_cli(options.rest, cancel)
    finally:
        await instance.stop()


class _Interrupts:
    """`Ctrl-C` 的状态机。在事件循环线程里被调用（信号回调只做转发）。"""

    def __init__(self, instance: AgentInstance, cancel: CancelToken) -> None:
        self._instance = instance
        self._cancel = cancel
        self._cancelling = False

    def __call__(self) -> None:
        live = self._instance.orchestrator.live_turns
        if live and not self._cancelling:
            self._cancelling = True
            for turn_id in live:
                self._instance.orchestrator.cancel(turn_id, CancelReason.USER)
            sys.stderr.write("\n已请求中断当前 turn；再按一次 Ctrl-C 退出。\n")
            return
        self._cancel.request(CancelReason.USER)
        asyncio.get_running_loop().create_task(self._quit())

    async def _quit(self) -> None:
        """收尾后结束进程。

        **只能用 `os._exit`**：读 stdin 的线程在 `input()` 上阻塞，而 `to_thread` 用的是
        非守护线程——正常退出会在解释器关闭时 join 它，表现为「按了 Ctrl-C 却要再敲一次
        回车才退出」。先跑 `stop()` 释放实例锁，再硬退出。
        """
        try:
            await asyncio.wait_for(self._instance.stop(), timeout=_STOP_GRACE_S)
        except (TimeoutError, Exception):  # noqa: B014 - 退出路径上不让收尾失败拦住退出
            pass
        sys.stderr.write("\n已退出。\n")
        sys.stderr.flush()
        sys.stdout.flush()
        os._exit(130)
