"""第 5 层：组装根。

职责：把 kernel 机制与 builtins / plugins 能力装配成可运行实例，并提供 `nm`
可执行程序；本层是唯一允许同时 import kernel 与 builtins 的地方。
不负责：实现机制或能力本身。

除 `cli/main.py` 与 `legacy_entry.py` 外当前为空骨架，
组装逻辑由开发方案 D23 落地。
"""
