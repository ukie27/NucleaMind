# 旧实现行为基线（D07）

本目录用测试的形式记录 `src/nucleamind/legacy/agent/loop.py` 与
`src/nucleamind/legacy/agent/runner.py` 在重构前的**可观察行为**。
它不是回归测试，也不是新架构的验收标准，而是 M2「基线测试 → 新实现 →
单点切换并删除旧实现」中的第一步（技术方案 §13 M2、开发方案 `D07`）。

## 为什么需要它

`loop.py` + `runner.py` 合计约 3900 行，`D09` 要把它拆成
`kernel/turn/engine.py`（≤400 行的纯循环）与 `D14` 的 `orchestrator.py`。
拆分过程中最大的风险不是写不出新循环，而是**不知道旧循环到底做了什么**——
迭代上限用完之后到底返回什么、工具抛异常时模型看到的字符串长什么样、
并发批次里第二个工具是不是真的和第一个重叠。这些行为散落在几十个分支里，
靠读代码复述必然失真。这里把它们写成断言，让 `D09` 的差异是**决定**而不是**意外**。

## 锁定了哪些行为

按开发方案 `D07` 的五条：

| 编号 | 行为 | 位置 |
| --- | --- | --- |
| `B1` | 迭代上限触发后的终止方式与返回内容 | `test_runner_behavior.py` |
| `B2` | 工具失败、超时、参数非法时模型收到什么 | `test_runner_behavior.py` |
| `B3` | 流式增量的聚合顺序与最终内容一致性 | `test_runner_behavior.py` |
| `B4` | 并发／串行工具调度的实际顺序 | `test_runner_behavior.py` |
| `B5` | 工具结果超长时的截断行为 | `test_runner_behavior.py` |

`test_loop_behavior.py` 补的是 `AgentLoop` 对这次运行**做的决定**（预算、
工具错误策略、超长结果的持久化处理），这部分归 `D14` 的 orchestrator 继承，
而不是 `D09` 的 engine。

几个值得单独记住的结论：

- 用户可见的一轮对话 **不** 设 `fail_on_tool_error`（取默认 `False`），
  尽管 `AgentDefaults.fail_on_tool_error` 是 `True`——那个默认值只作用于 subagent。
- 工具超长结果有两条路径：无 workspace 时按 `max_tool_result_chars` 截断并追加
  `"\n... (truncated)"`；有 workspace 时落盘到
  `<workspace>/.nanobot/tool-results/<session>/<call_id>.txt` 并把引用串交给模型。
  `read_file` 是唯一豁免工具。
- SSRF／工作区越界是**对模型不可重试、对本轮不致命**：即使
  `fail_on_tool_error=True` 也不会中止这一轮。
- 并发只在**连续的** `concurrency_safe` 工具之间发生，非安全工具是屏障；
  无论是否并发，工具结果进入消息列表的顺序始终等于 tool_calls 的顺序。

## 怎么用

- **`D09`**：新 `engine.py` 落地后，把本目录中**行为断言的部分**在新实现上重跑
  （换掉 `AgentRunner` 与 spec 的构造，断言本身尽量不动）。断言改不动的地方，
  说明新旧语义不同——要在 `D09` 的文档里给出结论，而不是悄悄放宽断言。
  逐条对照表在 `docs/project/d09-turn-engine.md`（临时文档）；`E≠` / `✗` 结论的
  永久落点是技术方案 §6.2.1「与旧实现的语义差异」。
- **`D14`**：`test_loop_behavior.py` 的决定项由 orchestrator 承接，同样处理。
- 这些测试**不联网**，不依赖真实模型或真实工具：`_support.py` 里的
  `ScriptedProvider` 按脚本回放 `LLMResponse`，`FakeTool` 提供可控的结果、
  异常与并发类别。

## 什么时候删除

**在 `D31` 删除 `legacy/agent/` 的同一个 PR 内一并删除本目录。**
到那时它锁定的实现已经不存在，留着只会让人误以为新 Kernel 承诺了同样的行为
（比如 `.nanobot/` 目录名、`NANOBOT_LLM_TIMEOUT_S` 这类迁移期运行契约，
新层一律不保留）。

在此之前不要往本目录加与上述五类行为无关的测试：它越像通用测试套件，
`D31` 就越难整体删除。
