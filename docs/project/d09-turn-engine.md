# D09 Turn Engine — 基线对照与语义差异

临时开发文档，`D09` 收口后删除。用途：把 `tests/baseline/` 的 33 个用例逐条落到
「新 engine 对应用例」或「移交 D14 / 不迁移」的结论上，并在收口时把 `E≠` / `✗` 的压缩版
写进技术方案 §6.2 新增小节「与旧实现的语义差异」。

分类记号：

| 记号 | 含义 | 产物 |
| --- | --- | --- |
| `E=` | engine 级、语义保留 | `tests/kernel/test_engine.py` 对应用例 |
| `E≠` | engine 级、语义**有意不同** | 新用例 + 一句差异结论 |
| `O→` | 编排策略，移交 `D14` | 本表只记「已移交」 |
| `✗` | 无后继机制 | 记「不迁移」+ 理由 |
| `L` | `test_loop_behavior.py`，本就属 `D14` | 不进对照 |

## `test_runner_behavior.py`（24 条）

| 基线用例 | 类别 | 新 engine 用例 | 差异与结论 |
| --- | --- | --- | --- |
| `test_max_iterations_stops_and_finalizes_without_tools` | `O→` | — | 「用完预算后再发一次不带 tools 的收尾请求」是编排策略且要渲染模板。engine 撞上限即 `TurnStoppedByLimit`；`D14` 若要保留收尾，就再调一次 `run_turn` |
| `test_max_iterations_falls_back_to_template_when_finalization_unusable` | `O→` | — | 模板文件是产品资产，引擎不渲染 |
| `test_max_iterations_without_finalization_makes_no_extra_request` | `O→` | — | 同上 |
| `test_unbounded_tool_calls_terminate_within_the_budget` | `E=` | `test_unbounded_loop_stops_by_iteration_limit` | 断言不变（有限步终止）；返回物从 `stop_reason=="max_iterations"` 换成 `TurnStoppedByLimit(breach.kind is MAX_ITERATIONS)`。另新增 `test_final_iteration_does_not_execute_tools_it_cannot_report`：最后一轮的工具**不执行**——结果无法再回给模型，执行只会白白产生副作用（详见该测试 docstring） |
| `test_tool_exception_is_reported_to_the_model_and_the_run_continues` | `E=` | `test_tool_invoke_error_does_not_fail_the_turn` | 断言「模型看到错误文本 + 本轮继续」不变；错误文本形态从 `"Error: RuntimeError: boom"` 换成 `NucleaError` 的 `user_message`（已脱敏），且新增 `side_effect=UNKNOWN` 维度 |
| `test_fail_on_tool_error_aborts_the_run_with_the_same_text` | `O→` | — | 谁设置 `fail_on_tool_error` 是编排策略；engine 的工具失败**永不**升级为 `TurnFailed`（见上一条） |
| `test_tool_error_result_gets_a_retry_hint` | `E≠` | 见 `test_tool_invoke_error_does_not_fail_the_turn` | 旧实现给部分失败追加 `[Analyze the error above...]` 提示；新实现**不追加**——「重试提示」是提示工程，不该由 engine 替所有模型厂商统一垫一句。差异结论：提示去掉，语义保留（错误仍以 tool 消息回给模型） |
| `test_unknown_tool_and_invalid_arguments_are_answered_conversationally` | `E≠` | `test_unknown_tool_becomes_error_result_not_turn_failure` | 拆成两条：未知工具仍由 engine 合成 tool 消息（保留）；**参数非法改由 `ToolInvoker` 判定**（§10.2 第 10 步把 schema 校验划给 invoker，engine 不认识 JSON Schema）。对模型可见行为一致，判定点上移 |
| `test_tool_timeout_reaches_the_model_as_a_tool_error` | `E≠` | `test_tool_timeout_is_clamped_to_remaining_turn_time` | 旧实现**没有** per-tool deadline（超时只是工具自己抛的 `TimeoutError`）；新实现有 `tool_timeout_ms` 预算（§6.4）并压到 turn 剩余时间。差异结论：这是净增能力，`D14` 需要另加一条「invoker 在宽限期后返回 `UNKNOWN`」的测试 |
| `test_model_wall_clock_timeout_ends_the_run_as_an_error` | `O→` | — | 旧实现把墙钟超时**伪造**成 `LLMResponse(finish_reason="error")` 并写占位 assistant 消息；新实现的终态是 `TurnCancelled(TIMEOUT)`，占位消息由 `D14` 生成 |
| `test_security_boundary_rejections_are_never_fatal` | `O→` | — | SSRF/工作区越界是错误**分类策略**（哪些非致命、哪些不可重试、加什么边界说明），在 `D14` 的 invoker 实现里；engine 只需要「工具失败不升级」这一条机制 |
| `test_stream_deltas_arrive_in_order_and_match_the_final_content` | `E=` | `test_stream_deltas_join_to_the_final_content` | 断言「增量按序 + 拼接等于最终内容 + reasoning 分离」逐字保留；事件名换成 `ModelTextDelta` / `ModelReasoningDelta` |
| `test_length_truncated_output_is_recovered_and_concatenated_in_order` | `O→` | — | `_MAX_LENGTH_RECOVERIES` 定为 `D14` 编排策略（不进 `TurnLimits`）；engine 对 `MAX_TOKENS` 一视同仁地正常收尾 |
| `test_length_recovery_is_capped` | `O→` | — | 同上 |
| `test_blank_replies_are_retried_then_finalized` | `O→` | — | `_MAX_EMPTY_RETRIES` 同理 |
| `test_persistently_blank_replies_end_with_a_stable_message` | `O→` | — | 空回复的收尾文案是产品决定 |
| `test_serial_mode_runs_tools_strictly_one_after_another` | `E=` | `test_exclusive_tool_is_not_overlapped` | 断言「EXCLUSIVE 不重叠」不变；验证手段从时序痕迹换成 `asyncio.Barrier` + 超时（串行会死锁，更强） |
| `test_concurrent_mode_overlaps_concurrency_safe_tools` | `E=` | `test_parallel_batch_really_overlaps` | 同上；结果顺序仍恒等于 `tool_calls` 顺序，见 `test_tool_result_enters_next_request_in_call_order` |
| `test_unsafe_tools_split_the_batch_and_run_alone` | `E=` | `test_scheduling.py::test_exclusive_tool_splits_surrounding_parallel_run` | 合批口径从 `concurrency_safe`（≈只读且非独占）换成 `ToolSpec.concurrency is PARALLEL` |
| `test_batch_partitioning_is_declarative` | `E≠` | `test_scheduling.py` 全部 | 旧实现私有方法 `_partition_tool_batches` 改为公开纯函数 `partition_tool_batches`（可测性不变，测试从私有方法解绑）。差异结论见上一条 |
| `test_oversized_result_is_truncated_with_a_stable_suffix_without_workspace` | `E≠` | `test_tool_result_is_truncated_by_limit` | 旧实现按**字符**截断并追加 `"\n... (truncated)"`；新实现按 **UTF-8 字节**截断（`tool_result_max_bytes`），**不追加后缀**，标记由 `ToolResult.truncated` 承载——截断后缀会让结果反过来超出上限。差异结论：截断是 budget 的职权，提示是渲染的职权 |
| `test_oversized_result_is_offloaded_to_a_file_when_a_workspace_exists` | `✗` + `O→` | — | `.nanobot/tool-results/` 是迁移期运行契约（新层不保留），engine 不做任何落盘；「超长结果如何呈现」归 `D14` |
| `test_read_file_results_are_exempt_from_offload_and_truncation` | `✗` | — | `read_file` 豁免是产品级名单（防 persist→read→persist 循环），engine 不认识工具名——豁免若需要，是 `D14` invoker 的策略 |
| `test_empty_tool_result_becomes_an_explicit_marker` | `E=` | `test_fold_tool_result_replaces_empty_content_in_message_only` | 占位文案同结论（`EMPTY_TOOL_RESULT_TEXT`），且只作用于消息、不改写 `ToolResult.content` 本身 |

## `test_loop_behavior.py`（9 条，全部 `L`）

`test_loop_configures_the_run_from_its_own_limits`、`test_loop_limits_default_to_the_configured_agent_defaults`
（预算来源）、`test_completed_tool_turn_reports_content_tools_and_transcript`（返回契约）、
`test_tool_failure_does_not_end_the_users_turn`（`fail_on_tool_error=False` 的值侧）、
`test_budget_exhaustion_is_pushed_through_the_stream`（channel 契约）、
`test_model_error_is_surfaced_as_an_error_turn`（`NANOBOT_LLM_TIMEOUT_S` 是迁移期契约）、
`test_persisted_tool_results_are_truncated_again_on_save`、`test_orphan_tool_results_are_dropped_on_save`
（持久化边界）、`test_empty_assistant_messages_never_enter_history`（历史边界）——全部由 `D14`
的 orchestrator 承接，`D09` 不做。

## 移交 `D14` 时要求的验收项

1. invoker 实现必须有一条「不可取消工具在宽限期后返回 `side_effect=UNKNOWN` 并登记孤儿」
   的独立测试（`EDG-407`、`EDG-104`；`ToolInvoker.invoke` 的 docstring 写死了
   「必须在 `timeout_ms + grace` 内返回」）。
2. `D14` 不得在调用 `run_turn` 前再分发一次 `BEFORE_MODEL_REQUEST`——第一轮会触发两遍。
   验收断言 `dispatch(BEFORE_MODEL_REQUEST)` 次数 == 迭代数。
3. 续写（长度截断）用「同一个 `ledger` 再调一次 `run_turn`」实现；验收建议加一条
   「重放持久化历史得到的 messages 与本轮 engine 发出的 message 序列逐条相等」。
4. `turn.stopped_by_limit` 没有 `EventName`（见 `TurnStoppedByLimit` docstring）：
   `D12` 按 `NFR-104` 评审新增，或 `D14` 显式论证用 `turn.completed` 承载。
5. 写内建/插件工具时，声明 `FS_WRITE` 或 `SHELL` 权限的工具必须显式给出
   `concurrency=EXCLUSIVE`（默认 `PARALLEL` 与旧行为相反，见 `scheduling.py` docstring）。
