# Design Constraints

以下规则约束 NucleaMind 的架构决策。添加功能或修复 bug 时，优先选择尊重这些边界的路径。

## 核心保持小，能力在边缘扩展

新能力应通过 `channels/`、`agent/tools/`、skills、MCP server 或未来的插件包提供。
`agent/loop.py` 与 `agent/runner.py` 是核心路径，改动必须最小化且有充分理由。
如果某个能力可以放进 channel 适配器、tool、外部 MCP server 或插件，就不应该内联进 agent loop。

运行时状态扇出遵循同样边界。`AgentLoop` 可以发布 `nanobot.bus.runtime_events` 中的通用运行时事件
（turn/run/model/goal 状态变化），但 WebUI/WebSocket 的线上细节（`_turn_end`、`_goal_status`、
标题刷新、goal-state 同步）属于 `nanobot.session.webui_turns.WebuiTurnCoordinator` 或对应 channel 适配器。

## Kernel / 插件边界（NucleaMind 愿景）

NucleaMind 的目标是把能力从核心抽离为插件。判断标准：

> 这是 Agent Runtime 必须能力，还是用户需求能力？

用户需求能力应优先设计为插件。核心只提供接口与注册机制（Plugin Runtime、Capability Registry、Lifecycle）。

逐步插件化的候选：Memory、Channels（Telegram/Discord/...）、Browser、MCP、WebUI、Automation、Multi-Agent。

## 少结构，多智能

优先简单可读的代码，而非新的框架层和间接层。只有当下述情况才增加结构：
移除真实复杂度、保护重要边界、或匹配已有的本地模式。最好的修复往往是一个更小的 prompt、
一个更紧的 tool 契约、一个 channel 局部改动，或一个聚焦的回归测试。

## 优先重复而非过早抽象

Channels 和 providers 允许重复相似逻辑（发送重试、媒体处理、消息拆分）。
不要为了消除跨 channel 文件的重复而引入复杂基类或共享 helper。
每个 channel 文件应保持自包含、可独立阅读。providers 同理。

## 在边界类型化动态数据

Wire payload、持久化记录、第三方 SDK 对象是不可信的动态边界。
优先在拥有它们的边缘用 parser 或小型 normalizer，并用 `TypedDict` 固定字典形状，
使校验只发生一次，内部代码拿到具体类型。不要把原始动态字典或 SDK 对象散播到核心。

第一方稳定依赖必须在存储或传递处标注类型。不要把内部服务、上下文字段或回调结果声明为 `Any`
再在消费侧用 cast 恢复真实类型。使用具体类型或窄 `Protocol`；`Any` 只留给真正的动态边界。

`typing.cast` 不做运行时校验。每个新 cast 必须有同路径的运行时检查支撑，
或有从构造与控制流即可明确的不变式（不明显时在本地注释说明）。
如果输入可能违反声明的类型，先处理非法情况再 cast；不要仅为让 BasedPyright 闭嘴而使用 cast。

## 显式优于魔法

配置必须在 `config/schema.py` 的 Pydantic 模型中显式声明。
错误处理应抛出清晰异常，而非静默修正坏输入。
Provider 自动检测存在，但每条解析路径都必须能从 factory 追溯到具体 provider 类。
