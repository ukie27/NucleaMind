# NucleaMind 项目指南（AGENTS.md）

本文件为本仓库中的 AI 编码代理提供开发指引。

## 项目概述

NucleaMind 是基于 [HKUDS/nanobot](https://github.com/HKUDS/nanobot)（MIT 协议）
独立开发的个人 AI Agent 项目，仓库与上游 Git 历史及协作流程均已分离。

- **当前状态**：`D00` 已把仓库搬到目标结构（`src/` 布局 + 新层空骨架 + `legacy/` 隔离区），
  `D01` 已立起架构守卫与 CI 门禁，`D02`–`D04` 已落地完整契约层
  （`contracts/` 十二个模块），`D05` 已落地 SDK 表面（`sdk/` 与 `sdk/testing/`），
  `D06` 已落地 Capability Registry 与覆盖解析（`kernel/registry/`），阶段 1 收口；
  `D07` 已落地旧实现行为基线（`tests/baseline/`），`D08` 已落地取消与预算
  （`kernel/turn/{cancel,limits}.py`），`D09` 已落地 Turn Engine
  （`kernel/turn/{engine,events,deps,scheduling,folding}.py`，纯循环，≤400 行），
  阶段 2 Turn 内核收口；`D10` 已落地实例布局与配置加载（`kernel/config/`，`D24`/`D28`
  之后共十三个模块），
  `D11` 已落地 Secret 与凭据（`kernel/config/secrets.py`，`SecretStr` 下沉到
  `contracts/errors.py`），`D12` 已落地可观测性（`kernel/observability/` 五个模块），
  阶段 3 支撑设施收口；`D13` 已落地输入分流与 Session 并发
  （`kernel/routing/{dispatcher,session_lock,dedup}.py`），`D14` 已落地 Turn Orchestrator
  （`kernel/turn/` 再加六个模块：`orchestrator` / `orchestration` / `hooks` /
  `context_builder` / `invoker` / `transcript` / `translation`），`D15` 已落地骨架集成验收
  （`tests/integration/`，28 个用例），**阶段 4 收口**；`D16` 已落地内建加载路径与契约测试
  套件（`kernel/plugins/` 四个模块 + `builtins/registry.py` + `runtime/wiring.py`），
  `D17` 已落地内建 Session（`builtins/session_jsonl/`），`D18` 已落地内建 Context
  （`builtins/context_basic/`），`D19` 已落地内建 Model（`builtins/model_openai/`），
  `D20` 已落地内建文件工具（`builtins/tools_fs/`），`D21` 已落地内建 shell 工具
  （`builtins/tools_shell/`，§8.2 冻结清单六件套至此交齐），`D22` 已落地内建命令集
  （`builtins/commands_core/` + `runtime/introspection.py`，并为此扩了 `PluginContext`），
  `D23` 已落地内建 CLI 能力、装配根与 `nm` 入口（`builtins/cli_entry/` +
  `runtime/{bootstrap,instance,plugin_context}.py` + `runtime/cli/` + `embed/`），
  **阶段 5 收口**；`D24` 已落地首次运行体验与开箱可用验收
  （`kernel/config/{scaffold,json_schema}.py` + `runtime/first_run.py` + `nm init` +
  `tests/e2e/`），**阶段 6 收口、需求 §16.1 达成**；`D25` 已落地插件发现
  （`kernel/plugins/discovery.py` + `runtime/inventory.py` + `plugins.enabled`），
  `D26` 已落地权限门面与生产级 `PluginContext`
  （`kernel/plugins/{permissions,permission_codec}.py` + `runtime/access/` +
  `nm permissions`），`D27` 已落地两阶段加载与事务性注册
  （`kernel/plugins/loader.py` + `runtime/plugin_plan.py`，外部插件与内建合并进同一次
  `wire_capabilities()`），`D28` 已落地插件生命周期（`kernel/plugins/lifecycle.py`：
  六阶段状态机、停止顺序、每插件停止预算；镜像常量拆出 `kernel/config/defaults.py`），
  `D29` 已落地插件 CLI 与诊断输出（`runtime/{config_edit,inspect}.py` +
  `runtime/cli/commands/{plugins,capabilities}.py`，`nm plugins` / `nm capabilities`），
  `D30` 已落地示例插件与 Plugin Runtime 验收（`examples/plugins/` 两个独立发行包 +
  `tests/e2e/{test_plugin_runtime,test_plugin_docs}.py` + `docs/plugin-development.md`，
  并把 `on_disable` 从「留给以后」变成真的判定：`runtime/plugin_disable.py` +
  registry 的按能力抑制），**阶段 7 收口、需求 §16.2 达成**；`D31` 已落地遗留 Agent 路径
  的删除与替代（删 `legacy/{agent,cli,webui,gateway,api,sdk,triggers}` 与 `nanobot.py`、
  `nm legacy`、`runtime/legacy_entry.py` 与 `R6` 的唯一白名单例外、`tests/baseline/`；
  新增官方插件 `plugins/nucleamind-plugin-openai-api/` 与通用无头命令 `nm serve`），
  **阶段 8 收口**；`D32` 已落地能力插件化的第一项——官方插件
  `plugins/nucleamind-plugin-anthropic/`（Anthropic 原生 Messages API 的 `MODEL` 能力，
  raw httpx，与内建 `model-openai` 并存），同 PR 删掉
  `legacy/providers/anthropic_provider.py` 及三条 `backend="anthropic"` 的 `ProviderSpec`，
  并把 `anthropic` 从根 `pyproject.toml` 的依赖里摘掉；`D33` 已落地 M5 的第 4 项——
  **放开 Channel 泵的串行限制**（`kernel/routing/fanout.py` 的按 conversation 扇出）
  与官方插件 `plugins/nucleamind-plugin-discord/`，同 PR 删掉 `legacy/channels/discord/`；
  `D34` 已落地官方 Feishu Channel 插件（`plugins/nucleamind-plugin-feishu/`）；
  **`D35` 删掉了整个 `legacy/`、`tests/legacy/` 与 `webui/`**，`R6` 守卫、
  `scripts/legacy_debt.py` 与债务棘轮一并退休——**项目范围本轮收窄**：Model Provider
  止步于内建 `model-openai` + `anthropic` 插件，Channel 只做 `feishu`，WebUI 不做。
  `D36`–`D38` 已交齐 **M5 的「扩展 Tool」**：官方插件 `web`
  （`plugins/nucleamind-plugin-web/`，`web.fetch` + `web.search`）、`image`
  （`plugins/nucleamind-plugin-image/`，`image.generate`）、`mcp`
  （`plugins/nucleamind-plugin-mcp/`，把 MCP server 的工具桥接进来），
  外加一次机制扩展 **`D38-A` `CapabilityDecl.namespace`**（`sdk/manifest.py` +
  `kernel/plugins/{declarations,host}.py` + `runtime/wiring.py`）与一个新错误码
  `EXTERNAL_TOOL_SERVER`。
  `D39` 已落地 **M5 的「Memory」**：官方插件 `memory`
  （`plugins/nucleamind-plugin-memory/`，一份 manifest 四类能力：`MEMORY:jsonl` 存储本体 +
  `CONTEXT:memory` 每轮自动召回 + 三条 `TOOL:memory.*` + `COMMAND:memory`），
  外加一次冻结表面变更 **`sdk.testing.MemoryProviderContract`**（第 6 个契约基类）。
  **`D40` 已落地 M5 的最后一项「Cron / Automation」**：官方插件 `cron`
  （`plugins/nucleamind-plugin-cron/`，一份 manifest 五条能力：`CHANNEL:cron` 调度器本体 +
  三条 `TOOL:cron.*` + `COMMAND:cron`），**Kernel 一行未改、零新依赖**。
  **M5 至此交齐，`references/nanobot/` 的迁移清单清空**；
  `runtime/` 有 `wiring.py`、`introspection.py`、`plugin_context.py`、`bootstrap.py`、
  `first_run.py`、`inventory.py`、`plugin_plan.py`、`plugin_disable.py`、`instance.py`、
  `inspect.py`、`config_edit.py`、`access/` 与 `cli/`，
  `embed/` 已落地薄门面，`kernel/` 有 `registry/`、`turn/`、`config/`、`observability/`、
  `routing/` 与 `plugins/`。
  `nm init` / `nm run` / `nm serve` / `nm config show` / `nm session` / `nm permissions` /
  `nm plugins` / `nm capabilities` 已可用。
- **长期目标**：不是继续堆功能，而是把 nanobot 改造成**轻量、模块化、可扩展的 Agent Kernel**——核心保持最小化（只保留 Agent 执行循环、LLM 抽象层、消息系统、Session 管理、Context 构建接口、Tool 注册机制、Plugin Runtime、基础配置），具体能力（Telegram/Discord/Memory/Browser/MCP/WebUI/Automation/Multi-Agent 等）逐步抽离为可选插件。
- 愿景与开发原则详见 [`docs/project/开发背景.md`](./docs/project/开发背景.md)。

> **命名（`D00` 已落地，技术方案 §4.5）**：Python 包为 `nucleamind`，发行名 `nucleamind`，
> CLI 命令只有 `nm`（不保留 `nanobot` 别名）。新层只读 `NUCLEAMIND_*`、
> `~/.nucleamind/<instance>/` 和 snake_case 配置，**不双读旧格式、不写长期兼容垫片**。
> `D35` 删掉 `legacy/` 之后，仓库里已经没有第二套命名——`NANOBOT_*` / `~/.nanobot/` /
> camelCase 只存在于 `references/nanobot/` 那份只读上游副本里。

## 仓库结构（`D00` 已落地，技术方案 §4.1–§4.4）

```text
src/nucleamind/            # 唯一 Python 包（src 布局，强制 editable install）
├── contracts/             # 第 1 层：公开数据契约，纯类型，零内部依赖
├── kernel/                # 第 2 层：机制，只依赖 contracts
├── sdk/                   # 第 3 层：插件唯一依赖面，只 import contracts
├── builtins/              # 第 4 层：内建默认能力，与插件同等身份
├── runtime/               # 第 5 层：组装根 + `nm` 可执行程序
└── embed/                 # 第 5 层：嵌入式 Python SDK
plugins/                   # 一等公民：七个官方插件（openai-api、anthropic、discord、
                           # feishu、web、image、mcp）
examples/plugins/          # 教学用最小示例插件
tests/                     # 镜像分层：architecture/ contracts/ kernel/ sdk/ builtins/ runtime/
                           # 是一个包（tests/__init__.py），否则 tests/builtins/ 与标准库撞名
                           # 外加 integration/（骨架集成，Fake 在能力边界）与
                           # e2e/（开箱可用里程碑，只有传输层是替身）
deploy/                    # Dockerfile / compose / entrypoint
```

`D35` 之后**包里只有这六层**：`legacy/` 隔离区、`tests/legacy/` 与 `webui/` 全部删除，
`R6`（新层禁止 import legacy/）随之退休——没有隔离区了，规则没有可判定的对象。

`contracts/` 三层（基础 / 领域与执行 / 能力）已齐，`sdk/` 已冻结公开表面，
`kernel/registry/` 已落地；`builtins/` 有 `registry.py` 与七个内建子包（`session_jsonl/`、
`context_basic/`、`model_openai/`、`tools_fs/`、`tools_shell/`、`commands_core/`、
`cli_entry/`），`runtime/` 与 `embed/` 已落地（见上），按开发方案逐个填充。
**新代码直接写在最终位置**，不要放临时目录。

契约层已冻结、后续模块必须复用而不是另起炉灶的三样东西：

- `SessionKey.storage_id()`：可逆且无碰撞的编码，**已发布即为持久化契约**，不得更改。
- `ErrorCode` + `CODE_CATEGORIES`：全部错误码集中登记，禁止在其他模块写错误码字面量；
  `NucleaError` 的 `category` 由码推导，不接受调用方传入。
- `contracts.errors.redact` / `scrub`：脱敏在**构造时**完成，不依赖日志或 sink 层。
- `contracts.SecretStr`（`D11` 从 `sdk/api.py` 迁来）：**全项目唯一的密钥包装类型**。
  刻意不是 dataclass（`dataclasses.asdict()` 会抖出明文），`str` / `repr` / `format` 恒为
  `MASK`，明文只经 `reveal()` 取出；它不在 `sdk.__all__` 里，插件按 `R4` 直接从
  `contracts` 导入。要再写一个密钥类型之前先想清楚哨兵测试要多扫一遍哪些输出路径。

`sdk/` 同样已冻结：`sdk.__all__` 与 `sdk.testing.__all__` 是规范性清单，有字面量快照测试；
`NucleaAPI` 的 9 个注册方法与 `CapabilityKind` 的 9 个取值一一对应；契约类型不从 `sdk`
转发（插件按 `R4` 直接 import `contracts`）；`sdk/manifest.py` 导入即不得有副作用。
写内建能力或插件时，先继承 `sdk.testing` 的 6 个契约测试基类
（`D39` 补上了 `MemoryProviderContract`）。**契约基类挡不住签名不一致**——它只在你自己
传的实参下跑，`isinstance` 又只查属性存在性，见下方 `plugins/nucleamind-plugin-memory/`
那条。那条 `inspect.signature` 守卫在 `D40` 的 `cron` 里已经照抄了一遍
（`test_cron_plugin.py`，并扩到 `Channel` 的四个方法），**新插件继续照抄**。

**`D22` 给 `PluginContext` 加了 `instance` 与 `turns`**（类型是 `contracts` 的
`InstanceView` / `TurnControl`，`sdk.__all__` 因此一个字都没变）。它们是插件读取实例自身
状态、取消在跑 turn 的**唯一**通道——`/plugins`、`/capabilities` 这类命令本来就该是插件
能写的东西，把它们做成 `runtime/` 特权就是在给「内建是特殊的」找借口（`BAS-005`）。
两个门面**不需要权限声明**（只读可观测性不是资源访问，与 `ctx.events` 同一档），
分成两个 Protocol 是因为一个是只读、一个是控制动作，`D26` 可以分别授予。
生产实现在 `runtime/introspection.py`，一致性靠返回类型标注静态证明（`wiring.py` 的先例）。
往 `PluginContext` 加成员要同时改**两处**快照：`tests/contracts/test_protocols.py`
（`SUPPORT_PROTOCOLS` 现在 3 条，`CAPABILITY_PROTOCOLS` 仍恒为 9）与
`tests/sdk/test_public_surface.py`（`API_PROTOCOLS` + 只读属性豁免名单）。

`kernel/registry/` 是**全项目冲突语义的唯一来源**：能力冲突、覆盖与遮蔽的判定只在
`resolution.py` 里，注册点一律不判冲突（`EDG-102`：覆盖永不由加载顺序决定）。注册必须走
`RegistrationBatch`（`EDG-103`：`setup` 中途抛异常整批丢弃），内建与插件走同一条分派，
不存在内建专用注册 API。`kernel/` 不 import `sdk/`，因此 manifest 的 `overrides` 以**原始串**
跨层传递，两侧共用 `contracts.parse_capability_target()` 解码。

`kernel/turn/` 是 turn 执行的全部机制。取消一律用 `CancelToken` 而不是
`asyncio.CancelledError`（后者无法保证「保存已产生内容再退出」），检查点一律用
`token.checkpoint(Checkpoint.X)`——`CHECKPOINT_OWNERS` 已经定死 engine 拿 2/3/5/6、
orchestrator 拿 1/4。预算只有 `TurnLimits` 那**六项**，取值与 `LimitKind` 的名字相同，
越界后的终态只查 `LIMIT_OUTCOMES`，不要在 engine 或编排里另写一份判断；记账用
per-turn 的 `BudgetLedger`（判定必须在发起工具**之前**）。`D09` 已落地 engine 事件流：
`run_turn(request, deps, cancel, *, ledger=None)` 以 `ModelRequest` 为种子、产出恰好一个
终态事件结尾的事件流；`EngineDeps` 只有四个槽（model/tools/hooks/limits），engine 的
import 白名单与 ≤400 行各有测试盯着；engine 只分发 4 个 Hook
（`ENGINE_HOOKS`），`turn_start`/`context_assemble`/`turn_end` 归 orchestrator；
续写 = 用同一个 `ledger` 再调一次 `run_turn`。新旧语义差异见技术方案 §6.2.1。

`D14` 的编排层（`orchestrator` / `orchestration` / `hooks` / `context_builder` /
`invoker` / `transcript` / `translation`）再记七条：

- **turn 事件只有一个发布点**（`orchestrator.py`），翻译表只有一份（`translation.py`）。
  engine 不发 `RuntimeEvent`；`model.request_started` 由 `orchestration.EventTap` 在
  `before_model_request` 分发时补上。想让 engine 直接拿一个 bus，就是在给 `EngineDeps`
  开第五个槽。
- **`before_model_request` 由 engine 每轮分发，编排层不得再分发一次**（有一条
  「分发次数 == 迭代数」的测试）。
- **准入顺序 去重 → 并发 → 分流**：`turn_id` 分配与去重在 `turn.started` **之前**，
  `turn.started` 在拿到 session 槽位**之后**。被去重或被拒的消息只发 `turn.rejected`——
  给它一个 `turn.started` 就会留下永远等不到终态的 turn。
- **注册载荷的形状定死四个**：`RegisteredHook` / `RegisteredContextProvider` /
  `RegisteredTool`（`kernel/turn/`）与 `RegisteredCommand`（`kernel/routing/`）。
  `critical` 由注册方从 manifest 带进来，kernel 不认识 manifest。
- **`trust=SYSTEM` 是进入系统指令位置的唯一凭据**，`kind` 不参与判定；`UNTRUSTED` 的包裹
  由契约层的 `as_model_text()` 完成，组装器不许自己拼字符串。
- **裁剪丢弃顺序**：priority 逆序，同优先级先丢片段再丢历史（从最旧）；裁到只剩系统段与
  当前输入仍超预算就抛 `INPUT_TOO_LARGE`，**不要**伪装成「压缩过了」。
- **`ToolInvoker.invoke` 必须在 `timeout_ms + grace` 内返回**且约定不抛。超时后不要
  `task.cancel()`——请求子令牌取消、等宽限期，仍不回来就登记孤儿并写
  `TIMEOUT_TOOL_CANCEL` + `side_effect=UNKNOWN`。`jsonschema` 在 turn 这条路上只在
  `invoker._compile()` 一处接触，惰性 import（全项目另一处是 `D27` 的
  `kernel/plugins/loader._compile()`，同样惰性）。

`kernel/config/`（`D10`、`D11`）是实例布局、分层配置、实例锁与 `${VAR}` 凭据引用的唯一
来源。写代码前记住六条：

- **配置的四层优先级只在 `sources.collect_layers()` 的返回顺序里定义一次**：
  `default < config.json < env < cli`。内置默认值是**一层**（`schema.defaults()`）而不是
  dataclass 兜底——`CFG-005` 要求每个生效值可追溯来源，「取自默认值」必须查得到。
- **字段只加在 `schema.SECTION_SPECS`**，那张表同时是默认值、类型与 `extra="forbid"` 的
  唯一依据。不要在别处另开一张表，也不要绕过 `validate_config()` 直接构造小节。校验积木
  （`FieldKind` / `FieldSpec` / `coerce_value` 与六个 `*_at()` 收窄器）在 `fields.py`，
  它**一个字段名都不认识**——分界线就是这个：加字段改 `schema.py`，加一种字段形状才改
  `fields.py`。`json_schema.py` 是那张表的**派生物**（给编辑器用），不是第二份真相。
  **默认值常量写进 `defaults.py`**（`D28` 从 `schema.py` 拆出，它撞上了 500 行上限）：
  那里只有镜像自 `kernel.turn` / `kernel.routing` / `kernel.plugins` 的字面量，每一组都有
  一条逐项对照测试；`schema.py` 从它 import 再原样再导出，因此既有引用一个都没变。
- **`kernel/config/` 全包不写任何文件**（`EDG-501`）：`config.json` 只以 `"rb"` 打开且只在
  `sources.read_config_file` 一处。`D24` 的 `scaffold.py` / `json_schema.py` 也不例外——
  它们只**渲染**，落盘在 `runtime/first_run.py`（`O_CREAT|O_EXCL`，没有 `--force`，
  既有配置一个字节都不动）。**修改**既有 `config.json` 只有 `runtime/config_edit.py`
  一处（`D29`，`nm plugins enable` 用）：只读写 `config.json` 那一层、从不解析 secret、
  原子替换。写日志是 `D12`。
- **顶层 `$schema` 是 `validate_config()` 唯一放行的非小节键**（`schema.IGNORED_TOP_LEVEL_KEYS`）。
  它必须是**具名的一条**，不是「`$` 开头就放行」——后者会让拼错成 `$turn` 的小节静默消失。
  这是全项目第二处对未知键让路的地方，第一处是 `plugins` 小节里的插件 id。
- **不要在 `kernel/config/` 里 module-level import `kernel.turn.limits`**：那会执行
  `kernel/turn/__init__.py`，把 engine/scheduling/folding 与 asyncio 拖上配置路径
  （`NFR-405` 冷启动预算 300 ms），`kernel.routing` 与 `kernel.plugins` 同理。
  `to_limits()` 用函数内 import，turn 的六个默认值、routing 的五个默认值、hooks/context
  的三个超时与插件停止预算都在两处各写一份（本层那份在 `defaults.py`）、由对照测试钉住。
  同理**不要把 pydantic 引进 `kernel/config/`**，有子进程测试盯着。
- **判断 PID 是否存活一律用 `process.process_is_alive()`**，绝不用 `os.kill(pid, 0)`：
  Windows 上 CPython 把非 CTRL 信号映射到 `TerminateProcess`，那个「探测」会杀掉目标进程。
  返回值是**三态**，`UNKNOWN` 不得用来回收锁。
- **`${VAR}` 解析后的明文不进配置文档**（`secrets.py`，`CFG-003`）：`resolve_secrets()`
  返回按 JSON Pointer 索引的 `SecretMap`，配置树自始至终持有 `${VAR}` 字面量，写回因此
  「没有别的东西可写」。要落盘一份配置前先过 `prepare_for_write()`。任何位置的引用都算
  密钥（整串或内嵌），没有 `${VAR:-默认值}` 回退、没有 `$${VAR}` 转义、空变量按缺失处理。

`kernel/observability/`（`D12`）是事件发布与诊断的唯一来源。写代码前记住五条：

- **发事件只走 `bus.publish(name, correlation=…, payload=…, error=…)`**，不要自己构造
  `RuntimeEvent`：`sequence` 由 bus 分配，绕过它就有两个真相来源，`OBS-002` 的按序重放
  随之失效。载荷不必自己脱敏，`prepare_payload()` 在事件构造**之前**已经做完。
- **`publish()` 同步、绝不抛出、绝不 await 订阅者**，别去 `await` 它。订阅者签名是
  `Callable[[RuntimeEvent], None]`，要异步处理就在回调里塞进自己的有界队列。连续 5 次
  失败、或单次投递超过 50 ms 达 5 次，订阅者会被**自动退订**——查 `bus.health()`。
- **脱敏规则只有一份**：`redaction.prepare_payload()` 先调 `contracts.errors.redact`
  再按条数上界收敛，顺序不可颠倒（先截断会把长令牌切成不再匹配已知形状的明文前缀）。
  不要在 sink 或调用点补第二道脱敏，也不要新写敏感键名规则。
- **sink 只是普通订阅者，Bus 不认识它们**（`OBS-005`）。`JsonlFileSink` 接一个
  `Callable[[date], Path]`，不 import `kernel.config`，也不自己拼
  `events-<date>.jsonl`——那个文件名只在 `layout.py` 里有一份。
- **`write_config_error()` 不是 sink**，是给 `EDG-501` 用的独立写函数：配置解析失败时
  bus 还没建起来。`D23` 必须在配置解析的 `except` 里调它一次。

`kernel/routing/`（`D13`）是准入路径：一条入站消息在进 engine 之前要过的三道关。写代码前
记住五条：

- **顺序是去重 → 并发 → 分流**，写在 `routing/__init__.py` 的 docstring 里。去重必须在最
  前面：重复投递的消息不该占队列名额，更不该在 `MERGE` 下被并进下一批，否则「重复投递不
  产生第二次副作用」（`EDG-201`）就失效了。
- **单写者不变量只有一条实现**（`session_lock.py`）：`run` 只在持有槽位时被调用，同一
  session 同时至多一个。`queue` / `merge` / `reject` 的差别**只在「拿不到槽位时怎么办」**，
  不要为某个策略另写一条执行路径。用显式 FIFO 票据而不是 `asyncio.Lock`——后者的唤醒顺序
  是 CPython 的实现细节，而 `EDG-202` 要断言的恰好是严格 FIFO。
- **命令名冲突在启动期判**（`build_command_index()`，`CMD-002`）。registry 的 MULTI_UNIQUE
  只保证 `name` 唯一，**别名撞车它看不见**；别名与命令名在同一个命名空间里。
- **dispatcher 不发任何事件、不分配 `turn_id`**：turn 事件的唯一发布点是 `D14` 的
  orchestrator（`Correlation` 由它传进来）。两个发布点会让命令类 turn 与模型类 turn 的
  事件序列各有一套口径，`OBS-002` 的按序重放随之作废。
- **命令 handler 的异常一律折成 `REJECTED`**（`CMD-003`），但**只捕 `Exception`**：
  `BaseException`（取消、Ctrl-C）要放行。折出来的错误里**不放异常消息**，只放类型名——
  第三方命令的异常文本可能带着凭据。

`tests/integration/`（`D15`）是骨架集成验收，写进去或改到它之前记住四条：

- **Fake 只在能力边界上**（模型 / 会话存储 / 工具 / Context Provider / 命令 handler），
  能力**之间**一律生产实现（registry + 覆盖解析、`HookRouter`、`ToolExecutor`、
  `Dispatcher`、`SessionScheduler`、`DedupCache`、`EventBus`、`TurnOrchestrator`）。
  往里挪一层，这套测试就退化成 `tests/kernel/` 的重复。
- **能力经 `RegistrationBatch` 注册、再由 `*_from(registry)` 取回**，不要把列表直接塞进
  `OrchestratorDeps`——`D14` 定死的四个注册载荷形状只有走这条路才会被核对。
- **一次 turn 的事件名序列（9 条）与 7 个 Hook 的触发顺序都以字面量钉在
  `test_skeleton_turn.py` 里**，改编排顺序会让它们失败，那是刻意的评审闸门。
- **「不触碰真实网络」是 `conftest.py` 的 autouse 夹具**：拦 `connect` / `connect_ex` /
  `getaddrinfo` 的**目标**、回环放行。别改成拦 `socket.socket` 的构造——Windows 的
  `ProactorEventLoop` 用 `socketpair()` 做 self-pipe，那样只会证明事件循环起不来。

`kernel/plugins/`（`D16`、`D25`、`D27`）是能力注册、插件发现与加载计划的唯一通道。
写内建或插件前记住九条：

- **`CapabilityHost` 是唯一的 `NucleaAPI` 实现**，内建与外部插件共用它（`SDK-007`、
  `BAS-005`）。它不继承 `NucleaAPI`（`R2` 禁止 `kernel/` import `sdk/`），一致性由
  `runtime/wiring.py` 里那句 `conformance: NucleaAPI = host` 静态证明——有 AST 测试盯着。
- **九个 kind 的注册载荷形状与取回函数全齐**（`D14` 四个 + `D16` 五个）。内建能力自己不
  构造它们，Host 会按 `register_*` 的参数替你构造；取回后的实现体在 `binding.value` 上。
- **未声明的注册与声明了却没注册都是 `PLUGIN_LOAD_FAILED`**，靠 `detail` 区分。manifest 的
  `capabilities` 是有约束力的全集，`overrides` 只能从那里来（`EDG-102`）。
- **manifest 里别写 `priority`**：默认值 100 会被原样采纳，而内建基准是 0
  （`to_declaration()` 用 `model_fields_set` 判断作者写没写）。
- **发现（`discovery.py`）不认识 manifest 类型**，它只交出 `object`：manifest 的解析与
  判定在 `runtime/inventory.py`（`R5`），`kernel/` 里没有第二套 manifest 校验。加一种
  **来源**改前者，加一条**校验规则**改后者。
- **「未启用即不导入」靠「候选 id 先于 manifest 可知」成立**（entry point 的 name /
  目录名 / `.py` 文件名），启用判定发生在 `read_candidate()` 之前。因此 entry point 的
  name 必须等于 manifest 的 `id`，对不上即失败；未启用候选的 `version` 是空串。
  `plugins.enabled` 是外部插件的总开关，`plugins.disable`（按提供方，对内建也有效）压过它。
- **阶段 A 的分界线与发现完全相同**（`D27`）：排序与校验的**机制**在 `loader.py`
  （它只认识 `(id, dependencies, critical)` 与一份 JSON Schema），**manifest 判定**在
  `runtime/plugin_plan.py`。加一种机制改前者，加一条判定改后者。A6 权限不在这两处——
  `runtime/bootstrap.py::approve()` 仍是唯一调用点。
- **加载顺序只有一个来源**：`plan_load_order()` 的 `LoadPlan.order`（同层按 id 字典序，
  依赖可指向内建）。它保证「被依赖者先 `setup`」，**不决定谁覆盖谁**（`EDG-102`）。
  `D28` 的停止顺序取它的逆序，不要另算一遍。三种落榜理由要分得开：`missing` / `cycle`
  （整条环，`PLG-003`）/ `blocked_by`。
- **`state_version` 变化即拒绝加载，升与降都是**：P0 没有迁移机制，静默改写版本号或让
  插件带着为另一个版本写的状态跑，都是拿用户数据赌一把（`EDG-503` 要的是保住旧状态）。
  标记文件 `.nucleamind-state.json` **只在状态目录已存在时**才读写——不为一个从未写盘的
  插件建目录。`jsonschema` 在这里是全项目第二个接触点（另一处 `turn/invoker._compile`），
  两处都惰性 import。
- **停止顺序是加载顺序的逆序，只有 `stop_order(LoadPlan.order)` 一条路**（`D28`、
  `PLG-005`）。装配根交给 `units_for()` 的顺序表就是 `contexts` 的顺序，它源自
  `all_manifests`（内建在前、外部按拓扑序在后）——停止侧不重排一遍拓扑。
- **阶段是判定口径、`PluginState` 是显示口径**：`PluginPhase` 与那张唯一的
  `PHASE_TRANSITIONS` 在 `lifecycle.py`，非法转换是 `KERNEL_INVARIANT_VIOLATED` 而不是
  被静默接受；诊断要的粗粒度状态由 `PHASE_STATES` 投影，不要另写一份映射（`D12` 的
  「不发明第二套生命周期 taxonomy」就是靠这个投影兑现的）。**`FAILED` 不是终态**——
  `setup()` 中途失败的插件可能已经订阅过事件或派生过任务，它欠一次清理。
- **停止超时是放弃等待而不是等它结束**（`EDG-104`）：那个协程可能仍在跑，
  `StopOutcome.timed_out` 与 `TIMEOUT_PLUGIN_STOP` 如实标着。预算是
  `plugins.stop_timeout_ms`（默认 5000），**按插件各算一份**；`RuntimePluginContext`
  自己不设第二个超时，两处各判一次会让「等了多久」取决于两个数的最小值。
- **`EDG-105` 的三项落在两处**：取消订阅与取消任务在 `RuntimePluginContext.shutdown()`；
  「注销能力」**不在运行期**——registry 解析后只读（`NFR-403`）且首版不热更新（§10.4），
  被禁用的提供方在下一次启动时连 `setup()` 都不跑。别为了让一条测试好写而给冻结的
  registry 开一个 `unregister()`：已经被 `ToolExecutor` 取走的实现体它也收不回来。

`plugins/nucleamind-plugin-openai-api/` + `nm serve`（`D31`）是遗留 OpenAI 接口的替代，六条：

- **HTTP 服务是一条 `CHANNEL` 能力，不是 `instance.submit()` 的包装**。这条是硬的：
  出站增量只经 `OrchestratorDeps.deliver` 按 `channel_id` 路由回**注册过的** Channel，
  而 `submit()` 要等整条 turn 跑完才返回 `TurnReceipt`——用它做不出 SSE。想加第二个网络
  接口就照这条路走，别去给装配根开一个「投递回调」的口子。
- **它落在 `plugins/` 而不是 `builtins/`**：§7.3 的内建默认能力集不该因为一次清理而变长，
  而 `plugins.enabled` 天然就是「默认不开一个监听端口」的闸门——不需要给 `CHANNEL`
  再加一层 `keep` 过滤。开发方案原本就写着 `api/server.py` 在 `D32+` 迁为插件，
  这里直接落到终局形态。
- **`nm serve` 是通用无头模式**（bootstrap → `start()` → 等信号 → `stop()`），
  不把进程交给 CLI 入口。`D32+` 的 Telegram / Discord Channel 插件用的是同一条命令，
  不要为某个插件写第二条。它的 `Ctrl-C` 只有一档（没有阻塞在 `readline()` 的线程），
  因此不需要 `nm run` 那个 `os._exit`。
- **用量的唯一公开出口是 `model.response_received` 的载荷**（`D31` 给
  `kernel/turn/orchestrator.py` 那**唯一**的发布点补了 `input_tokens` / `output_tokens`）。
  `TurnOutcome` 与 `TurnReceipt` 都不带它，旧实现读的是 `AgentLoop._last_usage` 这个私有
  属性。报出来的是**整条 turn 之和**（含工具往返），拿不到时**省略 `usage` 字段而不是报零**。
- **不支持的东西显式拒绝，采样参数接受并忽略**。`system` 消息、客户端 `tools`、多模态
  content 部件一律 400——静默丢掉它们会让客户端相信自己设了一个没生效的东西；而
  `temperature` / `max_tokens` 这类归模型配置与 `TurnLimits` 管，为它们报错会让现成客户端
  全都不可用。**只提交最后一条 user 消息**，历史归会话存储。
- **一条如实记着的边界**（原来的两条，第一条已被 `D33` 消除）：五种权限里**没有
  「监听端口」**这一种（`net` 判的是出站），因此这个插件声明不出与它实际行为对应的权限。
  默认只绑回环，绑非回环地址时没配 `api_key` 直接以 `CONFIG_INVALID` 拒绝启动。
  ~~同一 Channel 的 turn 是串行的~~——`D33` 起泵按 conversation 扇出，只有打同一个
  `conversation` 的客户端才排队，而那是 `EDG-202` 要求的严格 FIFO 不是限制。

`kernel/routing/fanout.py` + `runtime/instance.py::_fanout_for`（`D33`）是 Channel 泵的
按 conversation 扇出，四条：

- **同一 conversation 一条 lane，lane 内严格按到达顺序串行、lane 之间并发。**
  `EDG-202` 因此逐字成立而不是「大概成立」：在一条 Channel 上 `channel_id` 与 `scope`
  都是常量，`conversation_id ↔ SessionKey` 是**双射**，「每 conversation 一个 worker」
  与「每 session 一个 worker」是同一句话。
- **刻意不是「每条消息 `create_task`」。** 那样同会话两条消息进 `SessionScheduler` 的顺序
  取决于事件循环 ready 队列的排空顺序——那与 `Lock` 的唤醒顺序是同一档的 CPython 实现
  细节，而 `session_lock.py` 的 docstring 已经为拒绝依赖它付过一次钱。
- **lane 队列空即退出，没有 idle TTL**（`SessionScheduler._discard_if_idle` 的同一条
  判据）：`lanes()` 恒等于此刻有活儿的 conversation 数，没有后台计时器也没有泄漏。
  两个上界（`routing.channel_concurrency` 64 / `channel_queue_max_size` 32）**不与
  scheduler 的 `queue_max_size` 串联**——lane 串行意味着同 session 在 scheduler 里至多
  一个来自泵的等待者，因此 lane 队列是 Channel 流量唯一生效的界，没有 `D28` 那个
  「等了多久取决于两个数的最小值」的陷阱。
- **被扇出拒掉的消息发 `instance.input_dropped` 而不是 `turn.rejected`**：它从未进过
  orchestrator，而 turn 事件只有那一个发布点。回音仍走**未改动的** `_rejection()`，
  因此两条背压路径在 Channel 侧长得一模一样。**`Channel.deliver` 因此可能被并发调用**
  （同 conversation 内仍不会），这条已写进 `contracts/protocols.py`。

`plugins/nucleamind-plugin-discord/`（`D33`，第一个 Channel 插件，**后续十几个照它写**）六条：

- **`gateway.py` 是唯一 import `discord` 的模块**，其余全是纯函数或对 `Platform` /
  `Reactions` 两个 Protocol 编程。这不是洁癖，是测试计划的支点：**106 个用例里只有一条
  需要碰 SDK**（而且是验「没装它时说什么」）。legacy 的做法是在测试文件第 11 行写
  `pytest.importorskip("discord")`——CI 没装依赖时 52 个用例静默全跳。**下一个 Channel
  插件从第一天就按这个形状切。**
- **平台 SDK 对象在 `to_raw()` 之后就不存在了**（`MSG-004`）。判定与归一化只认识本插件
  自己的 `RawInbound` frozen dataclass；`Any` 只出现在 `gateway.py` 与那两个回调签名上，
  每一处都带 `# boundary:`。
- **入站判定顺序本身是行为**：自环 → 系统消息 → `allow_from` → `allow_channels` →
  群聊 @ 门控 → 归一化，写在 `normalize.py` 的 docstring 里。**只丢自己账号的消息，
  不丢其它 bot 的**（上游 issue #3217，有一条用例名里写着它）——改成
  `if author.bot: return` 会静默毁掉多 bot 编排。
- **thread 天然是独立会话**：`conversation_id` 取频道 id 而 thread 有自己的 id，因此
  `SessionKey(channel_id, conversation_id)` 已经把它表达完了，不需要 legacy 那个自造的
  `f"{name}:{parent}:thread:{id}"`。**入站附件不下载**（契约只存引用，Discord CDN 给
  直链），本插件因此一条 `fs:*` 权限都不需要。
- **`EDG-304` 的标记是文本且与 `cli_entry.TERMINAL_MARKERS` 逐字相同**：文本能逐字节
  断言、复制粘贴不会丢，而两处同一句话意味着「被中断」在所有 Channel 上读起来一样。
  标记与半截答案在**同一条消息**里，分开发会让半截答案孤零零留着看起来像完整回答。
- **`stream.py` 与 `indicators.py` 都注入时钟**，用例不真的等 0.8s / 2.0s。写替身时注意
  **注入的 `sleep` 必须真的让出事件循环**——`_type_loop` 是 `while True` + `await sleep`，
  一个不让出的替身会把它变成饿死事件循环的死循环（本轮的用例就是这么挂住过一次）。
  **只在终态清指示器**（`channel._TERMINAL` 三个状态，`DELTA` 不在其中）：legacy
  `runtime.py:479` 那条坑的新家在 `channel.py`，而不是 `indicators.py` 自己猜。

`plugins/nucleamind-plugin-anthropic/`（`D32`，M5 五步法的第一次完整应用）六条：

- **迁移不是移植。** 旧实现有四张按模型名版本号 gating 的表
  （`_ADAPTIVE_ONLY_MIN_VERSIONS` / `_THINKING_DISABLE_MIN_VERSIONS` /
  `_SAMPLING_DEPRECATED_MODELS` + 那个版本号正则），**一张都没搬**——`D19` 拒过同类的
  `max_tokens_field` slug 表，理由不变：表只会越滚越大，用户换新模型要等我们发版。
  四种 thinking 形状改由 `thinking.mode` 直接选，采样禁用改由 `supports_temperature` 表达。
  旧实现的**重试引擎也没搬**：重试是编排层策略，provider 只如实标 `retryable`。
- **工具名必须编码，这是与内建 `model_openai` 最大的一处线格式差异。** 契约工具名是点分
  命名空间（`fs.read`），Anthropic 的 `tools[].name` 只收 `^[a-zA-Z0-9_-]{1,64}$`。契约名
  恒不含 `-`，因此 `.` ↔ `-` 是**无碰撞双射**（`wire.encode_tool_name` / `decode_tool_name`）。
  内建那句「`parameters` 已是 JSON Schema，原样透传」在这里对参数成立、对名字不成立。
- **`StopReason.STOP_SEQUENCE` 在这里第一次可达。** `model_openai/wire.py` 的注释写着
  OpenAI 对自然结束与撞上 stop 序列都回 `"stop"`、分不出来；Anthropic 明确回
  `stop_sequence`。`refusal` 同理走 `CONTENT_FILTER`，且它是 **HTTP 200 上的正常响应**。
- **usage 的输入侧必须三项相加**（`input_tokens + cache_creation + cache_read`）：线格式里的
  `input_tokens` 只是**未命中缓存的余量**，不加就少报一大截。`reasoning_tokens` **恒为 0**
  且**不估算**——Anthropic 不单独报它，猜出来的数字会被当成实测值写进事件日志。
- **能力声明与开关同源**：`describe()` 交出的是「配置基线 ∪ thinking 开着时的 `reasoning`
  ∪ 缓存开着时的 `prompt_caching`」，反过来**声明了却没开开关是 `CONFIG_INVALID`**。
  两个方向都判死，`MOD-005` 才真的成立（与 `D20` 的 `enabled_tool_names(config)` 同一种做法）。
- **thinking 块无法多轮回放，这是相对旧实现的真实能力回退。** Anthropic 要求续写时把
  `thinking` 块（含 `signature`）原样回传，而 `ModelMessage` 没有放 provider 私有块的槽位，
  `signature_delta` 因此被吞掉。写在插件 docstring 与 README 里，**不当成没发生**；
  要修得先给 `contracts/model.py` 加一个 opaque 块槽位（`NFR-104` 的冻结表面变更）。
  图像输入同理（`ModelMessage.content` 是纯 `str`），旧实现的 `_convert_image_block` 没有
  搬运源。

`CapabilityDecl.namespace`（`D38-A`，`sdk/manifest.py` + `kernel/plugins/{declarations,host}.py`
+ `runtime/wiring.py`）是「能力名要连上外部服务才知道」的唯一出路，六条：

- **它只作用在「声明↔注册」这一道核对上。** registry 的冲突语义、覆盖判定与权限模型
  一个字都没改：仍按精确 `(kind, name)` 判，`nm capabilities` 印的是**实际注册的**名字。
- **形状先例是 `host.py::on()`**（Hook 早就是「一条声明、N 次注册」）。做成显式布尔而不是
  `name="mcp.*"` 通配串：后者会让「名字」这个字段有两种含义，而 `CapabilityRef` 的形状
  校验对通配串又不成立。
- **只放行 `<前缀>.<后缀>`**，前缀本身与 `mcpx.read` 都不在内——比较落在分隔符边界上
  （`WorkspaceGuard` 的路径前缀同一条道理）。这条规则**只有一条**：`_declared` 里根本
  没有命名空间声明，它们单列一张 `_namespaces`。
- **精确声明优先；两条命名空间同时匹配是 `PLUGIN_LOAD_FAILED`**——静默择一等于让加载
  顺序说了算，那正是 `EDG-102` 要堵的。
- **零注册合法**（`finish()` 结构性豁免）：远端服务连不上时插件注册零条能力，那是它如实
  反映外部状态。**但同一份 manifest 里的精确声明仍然必须兑现。**
- **只允许 arity 为 `MULTI_UNIQUE` 的 kind，且不得与 `overrides` 并存。** 前者的判据取自
  `CAPABILITY_ARITY` 而不是一张手写 kind 名单——那张表已经是全部冲突语义的唯一来源。
  翻译只在 `runtime/wiring.py` 一处（`R2`），漏掉那个字段的后果是插件注册第一条能力时
  就被判成「未声明」。

`plugins/nucleamind-plugin-web/`（`D36`）与 `plugins/nucleamind-plugin-image/`（`D37`）
是两个工具插件，四条**对下一个工具插件同样成立**的事实：

- **走不走 `ctx.net` 的判据是「谁决定了那个 URL」**，不是「要不要出网」。`web.fetch` 的
  URL 整个来自模型 → 必须过 SSRF 守卫（`EDG-406`），插件不写第二份；`web.search` 与
  `image.generate` 的端点来自运维配置（自托管 SearXNG / 本地 ollama 常在私有网段，
  守卫会按设计拒掉）→ raw httpx + 如实声明 `net`，与内建 `model_openai` 同一条先例。
- **外部插件用不上 `runtime/bootstrap.py` 的 `keep` 声明过滤**（`_ENABLED_NAMES` 按**内建
  id** 索引），因此 manifest 声明几条就必须注册几条。想让一条能力「默认可用」，就得让它
  在零配置下真的可用——`web` 的默认搜索后端因此必须不要凭据。
- **`PLUGIN_LOAD_FAILED` 是提供方级的**：一份 manifest 里的两条能力共命运。`web` 因此把
  凭据解析推迟到第一次调用（缺 `api_key` 只让 `web.search` 那一次失败，不牵连
  `web.fetch`），代价是配置里少一个凭据不会在启动时报出来。
- **工具结果没有 trust 字段**：`contracts/context.py::as_model_text` 的
  `UNTRUSTED_DATA_PREFIX` 包裹只作用于 `ContextFragment`。`web.fetch` 的横幅是**提醒不是
  隔离**，README 与 docstring 里都这么写着——**别改成「已隔离」**。`FileAccess` 没有
  `read_bytes` / `write_bytes`（`image` 因此如实声明 `fs:write` 直接用 `pathlib`），
  `HttpAccess` 不能流式（`web.fetch` 因此只能先下完再截断）。三条都是冻结表面的缺口。

`plugins/nucleamind-plugin-memory/`（`D39`，M5 的 Memory）六条：

- **`CapabilityKind.MEMORY` 至今没有 kernel 消费者。** `memory_providers_from()` 除测试外
  没有调用方、`runtime/bootstrap.py` 从不取它、`kernel/turn/context_builder.py` 只认
  `ContextProvider`——因此**只注册一条 `MEMORY` 能力，记忆永远进不了模型**。本插件的记忆
  靠自己那条 `CONTEXT:memory` 进上下文，`MEMORY:jsonl` 注册的意义是**契约形状**
  （第三方换后端的对照目标）。下一个想用 `MEMORY` 的人先读这条，别以为它已经接上了。
- **契约的 `MemoryProvider` 三个方法一个 `SessionKey` 都不带**，因此经那条接口只能服务
  `agent` 级范围；`session` / `workspace` 由插件自己的四条通路（Context Provider /
  三条工具 / 一条命令）承担，它们分别从 `SessionSnapshot.session_key` 与
  `Correlation.session_key` 拿身份。**`CommandInvocation` 也只能走 `correlation`**——
  `InboundMessage` 只有 `channel_id + conversation_id`，缺 `scope`，拼不出 `SessionKey`。
- **`FragmentScope.USER` 落不了地**：召回路径拿不到发送者身份（`SessionMessage` 一个
  sender 字段都没有），折成「按 conversation 存」会让群聊里 A 的用户记忆被召回给 B。
  拒绝它并说明原因，不静默降级。
- **召回片段的 `priority` 必须 > 0 且一条记录一个片段。** `HISTORY_TRIM_PRIORITY` 是 0
  而组装器按 priority **逆序**丢弃，因此记忆排在历史之前被丢——记忆下一轮还能重新召回，
  历史丢了就是丢了。拼成一大块就只能整块留或整块丢，`dropped` 的记账也失去精度。
- **写入侧统一 `trust=UNTRUSTED` 并忽略调用方声明的 trust**（`record.from_fragment`）。
  `/memory add` 敲进来的内容与模型写的一样不可信——群聊里任何人都能敲那条命令。
  `sensitivity=SECRET` 直接拒绝写入：组装器本来就不会把它送进模型，存进去只是一条永远
  召不回来、却躺在明文文件里的记录。
- **`CommandHandler.handle` 收 `(invocation, cancel)` 两个参数。** 本轮第一版只写了一个，
  49 个命令用例**全绿**——它们直接用一个实参调 `handle()`，测的是「我自己写的那个签名」
  而不是「kernel 会怎么调」，真实表现是 `nm run` 下一条 `kernel.unexpected` + `TypeError`。
  `isinstance` 对 `runtime_checkable` Protocol 只查属性存在性，而 basedpyright 的 `include`
  只覆盖 `src/nucleamind`（**插件全都不在类型检查范围内**）。因此
  `test_memory_plugin.py` 有一条 `inspect.signature` 逐个比对注册实现与契约 Protocol 的
  守卫，**下一个插件照抄它**。

`plugins/nucleamind-plugin-cron/`（`D40`，M5 的 Cron / Automation）七条：

- **调度器就是一条 `CHANNEL`，`receive()` 本身是调度循环。** Channel 的入站是拉模型，
  因此 `receive()` 可以直接是「睡到下一个到期时刻 → yield 一条消息」的异步生成器：
  `AgentInstance.start()` 已经会 `channel.start()` 并派生泵，而泵把消息投进 lane 之后
  **立即回来接着拉**（`_fanout_for`），一条跑十分钟的 turn 不会堵住调度。于是本插件
  **既不需要 `ctx.spawn_task` 也不需要 Hook**——开发方案里那条「依赖后台任务与 Hook」的
  备注写在 `D33` 扇出落地之前。**下一个「要自己发起 turn」的能力照这条走**，
  别去给装配根开新口子。
- **到期任务注入的是「原会话」的消息**，即创建它时那个 `channel_id + conversation_id`
  （`job.Origin`；`scope` 不存——它是实例级常量 `deps.scope`）。出站按 `message.channel_id`
  路由回对应 Channel 是 Kernel 既有行为，因此「每天 9 点在这个群里提醒我」不需要新机制。
  **代价如实记着**：原 Channel 没加载时那条出站消息被 `deliver` 静默丢弃（既有行为，
  那是 `embed.submit()` 的正常情形），turn 仍然跑完并入库。插件**不试图检测**——
  能力名与 `channel_id` 不是一回事（`cli_entry` 注册名是 `CHANNEL_NAME` 而 `channel_id`
  来自它自己的配置），检测会给出错误的把握；改为把 origin 印在 `/cron list all` 里。
- **cron 表达式自己解析**（`expr.py`，5 字段，零依赖）。不引入 `croniter`：CI 用
  `--no-deps` 装插件，依赖它会让所有涉及表达式的用例在 CI 里跑不起来。
  **时区名的解析只在 `settings.py` 一处且可注入**，`expr.py` / `schedule.py` 只接受已解析
  的 `tzinfo`——因此**整棵测试树不依赖 tzdata**（Windows 上没有系统时区库），DST 用例用
  手写的 `tzinfo` 子类驱动，验的是真的跳表行为。
  **`datetime.astimezone(tz)` 在 `tz is self.tzinfo` 时直接返回自身**（CPython 短路），
  因此「这个墙钟时刻存在吗」的往返判据**必须绕一次 UTC**，否则它恒真。
- **`due_decision` 的容差与补跑窗口是两件事。** `catch_up_window_ms`（默认 0）说的是停机
  之后补不补，`DUE_TOLERANCE_MS`（5s）说的是本次唤醒晚了多少——**没有后者，默认配置会把
  每一次正常触发都判成过期，任务永远不跑**。窗口判的是「错过了多久」而不是「错过了几次」：
  停机一小时的每分钟任务补跑一遍，不是六十遍。
- **运行历史记的是「派发」不是「turn 的成败」。** 泵吞掉 `TurnReceipt`
  （`_fanout_for` 只在 `admitted=False` 时回音），而按 `session_key` 关联 turn 事件分不清
  同会话的并发 turn。`RunStatus.DISPATCHED` 因此只说「消息已交给 Kernel」，
  README 与 `/cron show` 的输出里都这么写着——**不假装看得到结局**。
- **任务表损坏时进降级态而不是抛异常。** `AgentInstance.start()` 里的
  `await channel.start()` 没有 try/except，在那里抛会连 CLI 一起带走，而 `BAS-009` 要求
  任何配置下都有本地交互入口。因此 `load()` 读不出来时：零任务、不调度、任何改动都以
  `PERSISTENCE_READ_FAILED` 拒绝并指向那份 `.corrupt-<时间戳>` 备份。
  **`/cron list` 必须说出降级**——一个空列表在这里是误导。
- **时钟只有一个出口**（`CronScheduler.now()`）。第一版让工具自己调 `datetime.now()`，
  于是注入的时钟只管调度循环，而「排一条一分钟后的一次性任务」跑去和真实墙钟比——
  用例因此在真实日期越过某条线之后才开始失败。**插件里凡是有注入时钟的，
  就不该再有第二处 `datetime.now()`。**

`plugins/nucleamind-plugin-mcp/`（`D38-B`）是第一个桥接类插件，五条：

- **连接必须由一条后台任务拥有**（`supervisor.py`）。`mcp` 的三种传输都建在 anyio 的任务组
  上，而**任务组必须在进入它的那个任务里退出**——在 `setup()` 里 `enter_async_context`、
  再由停止路径 `aclose()`，会炸出 `Attempted to exit cancel scope in a different task`。
  而 manifest **没有 teardown 字段**：`ctx.spawn_task()` 派生的任务是唯一的清理通道
  （`EDG-105`）。任何用 `AsyncExitStack` 持有第三方 async 上下文的插件都照这个形状写。
- **`setup()` 可以是 `async` 的**（`builtin_loader.py:40` 早就写着），而外部插件的
  `setup()` 跑在 `wire_capabilities` 里、**有运行中的事件循环**，因此 `ctx.spawn_task()`
  在那里可用。registry 解析后只读（`NFR-403`），发现远端能力没有第二个时机。
- **`side_effect` 恒为 `UNKNOWN`、`read_only` 恒为 `False`**：MCP 不报告副作用，远端的
  `readOnlyHint` 是**它自己说的**。失败分两档——发起**之前** `NONE`、发起之后 `UNKNOWN`；
  谎报 `NONE` 会让编排层以为可以安全重试一次可能已经生效的写操作。
- **归一化撞车的各方都不生效**（`get-file` 与 `get_file` 撞成一个名字），与 registry 对
  同名冲突的判定一致。**这与 `D32` anthropic 那条「`.` ↔ `-` 编码」结论相反**——那是无碰撞
  双射，这里的归一化会丢信息。
- **权限模型对它基本失效**：声明的 `shell` 与 `net` 挡不住任何东西（stdio 要长驻子进程与
  管道而 `ctx.shell` 是一次性 exec、HTTP 由 SDK 自己开连接）。**真正的边界是「你配了哪些
  server」**，这句如实写在 README 里。

`runtime/plugin_disable.py` + `examples/plugins/`（`D30`）是插件体系的收口，五条：

- **`on_disable` 是拒绝隐式恢复的那道判定**（`BAS-004`、§10.4）。禁用一个声明过
  `overrides` 的插件时，`plugins.<id>.on_disable` **必须**显式写 `restore_builtin` 或
  `leave_missing`，不写即 `CONFIG_INVALID` 并指向那一个键。默认值是刻意没有的——不做
  判定的话被禁用的插件根本不注册、覆盖关系不存在，内建就自动复活了，而那正是 `BAS-004`
  禁止的隐式恢复。**没声明过覆盖的插件不要求表态**，否则这个键会变成噪声。
- **`leave_missing` 走 registry 的按能力抑制**（`resolve(suppressed=...)`），不是
  `keep`。分界线是「作用在解析还是注册上」：被抑制的能力**照常注册**、照常出现在
  `ResolutionReport.disabled` 段里，只是不生效——`nm capabilities` 因此答得出「它为什么
  不在」，而一项从未注册过的能力在报告里连一行都没有。按提供方禁用（`disabled=`）与按
  能力抑制（`suppressed=`）在 `_partition_disabled` 一处合并判定，后果完全相同。
- **被 `disable` 关掉的插件仍然读一次 manifest，前提是它在 `enabled` 里**
  （`inventory._disabled`）。读它只为知道它覆盖过什么。§7.1 的「未启用即零导入开销」
  一个字没松动：`plugins.enabled` 仍是「会不会被读」的唯一闸门，`disable` 只决定
  「读了之后跑不跑」。读不出来时记进 `failures` 并按禁用处理，不为一个已经被关掉的插件
  让实例起不来。
- **示例插件必须真的装进环境**（entry point 没有第二条发现路径）。因此
  `tests/runtime/conftest.py` 有一条 autouse 夹具把 entry point 清空——那一层的用例
  一直依赖着「开发环境里没装任何插件」这个它们没有声明的前提，`D30` 把它显式化了。
  要在那一层验真实 entry point 的用例自己传 `entry_points=`。
- **`docs/plugin-development.md` 的代码块由 `tests/e2e/test_plugin_docs.py` 直接执行**
  （Python `exec`、JSON/TOML 解析），外加「文档列出的 9 个注册方法 == `NucleaAPI` 上真有
  的那 9 个」。比对片段挡不住这类漂移：复制粘贴来的文档在实现改名之后仍然长得一模一样。

`runtime/inspect.py`（`D29`）是全部只读诊断的入口，四条：

- **只读查询不走 `bootstrap()`**：`inspect_plugins()` / `inspect_capabilities()` /
  `open_session_store()` 共用同一套承诺——不取实例锁、不 `save()` 权限账本、不装
  orchestrator、不做步骤 8 的必需能力判定、不 `raise_if_failed()`。它们复用装配根的
  `select_manifests` / `plan_external` / `wire_all`，**不重写装配逻辑**。
- **两个诊断专用旋钮**：`plan_external(strict=False)`（关键插件阶段 A 失败只记不抛）与
  `wire_capabilities(halt_on_critical=False)`（关键提供方 `setup()` 失败只记不抛）。
  两者都**不改 manifest 里的 `critical`**，启动路径的默认值仍是 `True`——那是
  `PLG-004`「失败的后果由装配根决定」的应用。
- **`/plugins` 的状态 = 清单 + `lifecycle.state` 投影**（`bootstrap._plugin_statuses`），
  已记下的失败不被覆盖，内建不进这张表。跳过原因的文案只有 `inventory._SKIP_REASONS`
  一份，CLI 侧直接印 `PluginStatus.reason`。
- **`bootstrap.py` 贴着 800 行上限**：只读查询归 `inspect.py`、改配置归 `config_edit.py`，
  往装配根加东西之前先确认它真的属于「装配」。

`kernel/plugins/permissions.py` + `runtime/access/`（`D26`）是权限的唯一来源。六条：

- **授权 = manifest 声明 ∩ 账本批准**，判定只在 `runtime/bootstrap.py::approve()` 一处
  被调用（`D27` 的外部插件走同一条路，不要在 loader 里另判一次）。manifest → `Grant`
  的翻译同样只在 `declared_grants()` 一处——`R2` 禁止 kernel 认识 `PermissionDecl`，
  与 `D25` 的「发现在 kernel、manifest 判定在 runtime」是同一条分界线。
- **批准模型是 TOFU + 扩权需显式**：首见即按声明整份授予并记 `permissions.json`
  （`source="first_use"`），此后声明**扩大**时新增项默认落 `pending`（拒绝），撤销是显式
  操作且压过声明。「首见」看的是有没有被 `decide()` 见过（`source` 是 `first_use` /
  `declared`），**用户预先批准留下的 `user` 记录不算**——否则一个更宽松的动作会换来更严的
  结果。读不懂账本是**启动失败**，静默当成空账本等于一次静默的全部重新授予。
- **账本按 plugin id 索引而不是 `ProviderId`**（全部内建共用一个 `Builtin()`）。
  加一条判定规则改 `permissions.py`，改文件长什么样改 `permission_codec.py`——分界线是
  「认不认识判定」。
- **三个门面在 `runtime/access/` 而不是 `kernel/`**：`HttpResponse` / `ShellResult` 在
  `sdk/`，`R2` 够不着。因此 workspace 双重校验是**第三份实现**（另两份在 `tools_fs` /
  `tools_shell`），shell 的环境白名单基线也是第二份——两处都有逐条对照测试，改一边要改多边。
- **`ctx.fs` 读写分别判定**（`NFR-302`），`fs:read` / `fs:write` 各自收窄 `target`；
  **认不出的 `target` 收窄成「什么都不许」而不是「整个根」**。`ctx.net` 判的是**解析之后**
  的地址且**手动跟随重定向**（`EDG-406`），httpx 惰性 import；`ctx.shell` 走 `exec`
  不经 shell、超时不抛、起不来折成 `exit_code=-1`。三者挡不住什么（TOCTOU、DNS 重绑定、
  cwd 之外的绝对路径）各自如实写在 docstring 里，**别删掉那几段**。
- **应用级权限 ≠ 进程隔离**（技术方案 §13.7）：同进程插件可以绕过全部门面直接
  `import os`。这句写在 `sdk/api.py`、`runtime/access/__init__.py` 与 `docs/permissions.md`
  里，是必须保留的诚实声明而不是免责套话。

`builtins/`（`D17` 起）的落地形态只有一种：一份 `PluginManifest` 追加进
`builtins/registry.py::BUILTIN_MANIFESTS`，加一个 `setup(api)`。五条通用约束：

- **内建拿不到实例布局**（`R4`），要写盘就只能让装配根把路径经 `ctx.config` 交下来。
  `session_jsonl` 用 `dir` 键，没配时退回 `ctx.state_dir`；`D23` 装配时必须真的填上，
  否则数据会安静地写到插件私有目录去。
- **不要在 `builtins/` 里写注册辅助函数**：`R4` 拦得住 import，拦不住自建通道，
  `tests/architecture/test_builtin_no_privilege.py` 的符号扫描是为此存在的。
- **格式一旦发布就是契约**（`SES-006`）：`docs/session-storage.md` 里的示例由
  `tests/builtins/test_session_jsonl.py` 直接解析，改 `codec.py` 的字段就得改文档。
  `committed_bytes` 提交水位是整批原子性的全部机制，读只认水位内的字节，写最后才换
  `meta.json`；文件比水位**短**是损坏，不是「就这些了」。
- **声明为只读的内建连持久化的语法途径都不许有**（`D18`）：`context_basic` 在
  `test_builtin_no_privilege.py::_READ_ONLY_BUILTIN_PACKAGES` 里，因此它不得出现
  `os` / `pathlib` / `socket` / 裸 `open` 之类的名字，manifest 的 `permissions` 必须为空。
  要写盘的内建（`tools_fs` / `tools_shell`）**不进**那张表，走 `session_jsonl` 那条路
  ——如实声明权限，而不是绕道。
- **一份 manifest 里的多条能力声明可以按配置少注册几条，但只有一条路**（`D20`）：
  `runtime/wiring.py` 的 `keep: CapabilityFilter` 裁掉声明，内建导出一个只看配置的
  `enabled_tool_names(config)` 决定注册谁，两者**同源于同一份配置**。`D16` 的
  「声明 ⊆ 注册」不变量一条也不放松——忘了传 `keep` 就会被 `CapabilityHost.finish()` 以
  `PLUGIN_LOAD_FAILED` 挡下，那个报错是对的。别改用「注册一个总是失败的桩工具」来糊弄
  `TOL-006`：那正是「声明了但不可用」。
- **`tools_fs` 的路径守卫是 `NFR-302` 的唯一防线**（`builtins/tools_fs/paths.py`）：逻辑
  校验（`normpath`，挡 `..`）与 realpath 校验（`resolve()`，挡符号链接与重解析点）**缺一
  不可**，两次比较都过 `os.path.normcase`。不做 `expanduser()`、绝对路径接受但过同一道门、
  Windows 保留设备名两个平台一律拒绝。TOCTOU 挡不住，docstring 里如实写着，别删掉那段。
  越界错误的 `detail` 只放原始串——宿主机绝对路径进模型可见的错误就是泄漏。
- **失败发生在落盘之前才敢标 `SideEffect.NONE`**：`tools_fs` 的写走「临时文件 → `fsync`
  → `os.replace`」，替换成功后没有可失败的步骤，因此它一次 `UNKNOWN` 都不产出，
  `base.FsTool` 把折出来的失败一律标 `NONE`。**`D21` 的 `shell.exec` 没有照抄这一句**：
  三档判定在 `tools_shell/executor.py::_fold` 一处——执行**之前**失败（参数 / cwd / 入口
  取消）→ `NONE`；进程自己退出或宽限期内被终止 → `OCCURRED`；**宽限期用尽被强杀 →
  `UNKNOWN`**（`EDG-407`，全项目唯一的产出点）。判据是「失败发生在副作用可能已经发生
  **之后**，且无法确认做完没有」。
- **`tools_shell` 的取消是三步，不是一步**（`process.py::_supervise`）：终止信号 → 等宽限期
  → 强杀 + 收尸。直接 `kill()` 会让一条 `rm -rf` 写了一半就停，那不叫取消成功。
  `CancelSignal` 只有 `requested` 可轮询（`CancelToken.wait()` 属 kernel 扩展面，`R4` 够
  不着），因此每 50 ms 看一次——等到 `timeout_ms` 才响应取消等于不支持取消。
  `DEFAULT_GRACE_MS` 与 kernel 那份各写一份，有对照测试。
- **Windows 起子进程必须走 `create_subprocess_shell`**（`tools_shell/command.py` 的模块
  docstring 是唯一出处）：`cmd.exe` 接在 `/c` 后的是原始命令行尾巴，而 `subprocess` 用
  `list2cmdline()` 把 argv 拼回字符串时会把内层引号转义成 `\"`，`cmd` 不认识——任何带引号
  的命令当场残掉。代价是 Windows 拿不到 `/d`、`shell` 配置项不生效，两条都写在那里了。
  平台分派只在 `process._spawn` 一处，有测试数 `os.name` 的出现次数。
- **`tools_shell` 的子进程环境是白名单**（`environ.py`，`NFR-307`）：父进程的环境默认一个
  字节都不进子进程，只有平台基线与运维在 `pass_env` 里点名的才转发。别改成「过滤掉像密钥的
  变量名」的黑名单——那要求名单穷举所有会泄漏的变量，漏一个就把凭据交给模型写的命令。
  哨兵用例走真实子进程打印自己的环境，因为「函数是对的」不等于「调用它的路径是对的」。
- **cwd 守卫是 `tools_fs.WorkspaceGuard` 的第二份实现**（`tools_shell/paths.py::CwdGuard`），
  刻意不 import 它：两者是独立 manifest、可各自被禁用或被第三方覆盖的提供方。判定逐条相同，
  由 `test_cwd_guard_matches_the_fs_workspace_guard` 钉住，改一边要改两边。另外**守住 cwd
  不等于守住命令能碰到的文件**（`cat /etc/shadow` 与 cwd 无关），那句如实写在 docstring 里。
- **非零退出码不是工具失败**（`shell.exec` 返回 `ok=True`）：`grep` 没匹配返回 1 是正常产出，
  模型要靠退出码和 stderr 继续工作。`ok=False` 只留给「这次调用没能给出结论」（起不来 /
  超时 / 被强杀）。进程起不来折成 `exit_code=-1`（不在 0–255 内），诊断因此分得开。
- **自报的 `estimated_tokens` 要和组装器同一把尺**：`R4` 逼得公式在
  `builtins/context_basic/instructions.py` 与 `kernel/turn/context_builder.py` 各写一份
  （都是 `ceil(len/3)`），由一条逐字符对照测试钉住。自报偏小会让请求真的超出模型窗口，
  偏大则白丢内容。运维配置的自定义指令是 `TrustLevel.OPERATOR` 而不是 `SYSTEM`，
  它因此进不了 system 消息位置——那是 `CMD-005` 的分级，不是可以顺手改掉的实现细节。
- **命令的数据只从 `ctx.instance` / `ctx.turns` 来**（`D22`）：`commands_core` 的六个命令
  没有一条走特权通道，`/help` 因此能列出自己，第三方也能写 `/status`。`handle()` 的
  「约定不抛」只在 `_Handler.handle` 一处实现——`NucleaError` 原样带出，其余异常折成
  `KERNEL_INVARIANT_VIOLATED` 且**只放类型名不放异常消息**（第三方命令的异常文本可能带着
  凭据）。`operator_only` 与参数个数由 dispatcher 前置校验，命令自己**不要**再抄一遍；
  带自由文本的命令要声明 `repeated=True` 的尾参，否则会被按「参数过多」拒掉。
  **`/cancel` 显式拒绝取消自己所在的 turn**（它正持有 session 槽位，取消自己会让输出发不
  出去），不带参数时只列出而不是取消全部。`/config` 的脱敏是**结构性**成立的（配置树只有
  `${VAR}` 字面量），`redact()` + `scrub()` 是纵深防御而不是唯一防线。

## 开发命令

```bash
# Python：单测 / lint
.venv\Scripts\python.exe -m pytest tests/kernel/test_engine.py::test_function -v
.venv\Scripts\python.exe -m ruff check src/ plugins/ examples/

# 插件（D30 的两个示例 + D31 的 openai-api + D32 的 anthropic + D33 的 discord
# + D34 的 feishu + D36–D38 的 web / image / mcp + D39 的 memory + D40 的 cron）：
# 经 entry point 发现，因此必须真的装进环境才跑得起来。
# tests/e2e/ 与各插件自己的 tests/ 都要求它们在位。
# **--no-deps 是刻意的**：平台 SDK（discord.py / lark-oapi / mcp）因此不在 CI 环境里，
# 而那三个插件的测试树仍须全绿。cron 的 tzdata 同理——它整棵测试树都不依赖时区数据库。
.venv\Scripts\python.exe -m pip install --no-deps -e examples/plugins/nucleamind-plugin-echo-tool
.venv\Scripts\python.exe -m pip install --no-deps -e examples/plugins/nucleamind-plugin-session-memory
.venv\Scripts\python.exe -m pip install --no-deps -e plugins/nucleamind-plugin-openai-api
.venv\Scripts\python.exe -m pip install --no-deps -e plugins/nucleamind-plugin-anthropic
.venv\Scripts\python.exe -m pip install --no-deps -e plugins/nucleamind-plugin-discord
.venv\Scripts\python.exe -m pip install --no-deps -e plugins/nucleamind-plugin-feishu
.venv\Scripts\python.exe -m pip install --no-deps -e plugins/nucleamind-plugin-web
.venv\Scripts\python.exe -m pip install --no-deps -e plugins/nucleamind-plugin-image
.venv\Scripts\python.exe -m pip install --no-deps -e plugins/nucleamind-plugin-mcp
.venv\Scripts\python.exe -m pip install --no-deps -e plugins/nucleamind-plugin-memory
.venv\Scripts\python.exe -m pip install --no-deps -e plugins/nucleamind-plugin-cron

# 架构守卫（R1–R5 / 模块头部 / 文件规模 / Any 边界），CI 独立作业
.venv\Scripts\python.exe -m pytest tests/architecture -q
.venv\Scripts\python.exe scripts/check_startup_cost.py --check

# 严格类型检查（与 CI 一致）
uv sync --all-extras --dev
uv run --no-sync basedpyright

# 无头模式：启动已启用的 Channel 插件并常驻（D31）
nm serve
```

**沙箱下跑 pytest 要加 `--basetemp=.pytest-tmp`**：系统临时目录不可写时
`tmp_path` 夹具会以 `PermissionError` 报错，而那与被测代码无关。
`.pytest-tmp/` 已在 `.gitignore` 里。

## Python 环境与沙箱

- 项目本地开发和测试统一使用仓库中的 `.venv`，所有 Python 命令均通过
  `.venv\Scripts\python.exe` 执行，例如
  `.venv\Scripts\python.exe -m pytest` 和
  `.venv\Scripts\python.exe -m pip install -e ".[dev]"`。
- 不要使用裸 `pip`、`pytest` 或系统 `python` 代替项目虚拟环境；只有在明确确认
  `.venv` 不存在时，才可以使用系统 Python 创建或修复虚拟环境。
- Python 虚拟环境与执行沙箱是两套独立机制：`.venv` 负责固定 Python 解释器和依赖，
  沙箱负责限制进程可访问的文件、目录和网络。沙箱不会提供或替代 Python 环境。
- 如果 `.venv` 在普通终端可用，但 Agent 执行时出现基础解释器不存在、访问被拒绝、
  依赖下载失败等问题，应先检查沙箱的文件或网络权限。不要仅凭沙箱内的失败判断
  `.venv` 已损坏，也不要因此绕过 `.venv` 改用系统 Python。
- 测试或开发命令确实需要访问工作区之外的基础解释器、缓存目录或网络时，应申请
  对应的沙箱权限，并在获得授权后继续使用 `.venv\Scripts\python.exe`。

## 剩余工作与迁移参考（`D40` 之后）

`legacy/` 已经不存在。**M5 至此全部交齐**，项目范围本轮收窄成：

| M5 项 | 范围 |
| --- | --- |
| 额外 Model Provider | **止步**：内建 `model-openai` + `anthropic` 插件已够 |
| Memory | **已交**：`memory` 插件（`D39`） |
| 扩展 Tool | **已交**：`web`（`D36`）、`image`（`D37`）、`mcp`（`D38`） |
| Channel | **只做 `feishu`**（`D34` 已交），其余 13 个放弃 |
| Cron / Automation | **已交**：`cron` 插件（`D40`） |
| WebUI | **不做**，前端源码已删 |

「扩展 Tool」里**刻意没做的两样**：参考实现的 `agent/tools/search.py` 是**文件搜索**，
已被内建 `tools_fs` 的 `fs.grep` / `fs.list` 覆盖；`providers/transcription.py`
（语音转写）是另一类能力（音频输入），而契约层今天没有多模态输入位置。
「Cron」里刻意没做的两样：**heartbeat**（`HEARTBEAT.md`，用一条普通任务加一句「没有要紧的
就回一个字」就能表达）与 **local trigger**（`nanobot trigger <id>`，它要一个进程外的入队
通道与至少一次投递语义，是另一件事）。

**`references/nanobot/`**（本地只读的上游副本，被 Git 忽略）从此只是历史对照，
不再有待迁移项。它比原来的 `legacy/` 更全，但未改名、没有通过的测试，
因此**只能读不能搬**：按下方原则 5，复用实现时把代码写到新家并补测试。

`D32`–`D40` 已经把 M5 的五步法跑通九遍，**下一轮做别的模块时照它们的形状写**：
a 步不新写基线，b 步在 `plugins/` 里新写而不是搬运，c/d/e 步同 PR 完成。

### 入口点

- **`nm`（唯一命令）**：`src/nucleamind/runtime/cli/main.py`，子命令 `init` / `run` /
  `serve` / `config show` / `session` / `permissions` / `plugins` / `capabilities`
  （全部延迟导入）
- **嵌入式 Python SDK**：`src/nucleamind/embed/`（`open_instance()` / `run()`）
- **OpenAI 兼容 HTTP API**：官方插件 `plugins/nucleamind-plugin-openai-api/` + `nm serve`
- **Anthropic 原生模型**：官方插件 `plugins/nucleamind-plugin-anthropic/`（一条 `MODEL` 能力）
- **Discord bot**：官方插件 `plugins/nucleamind-plugin-discord/` + `nm serve`
- **飞书 / Lark bot**：官方插件 `plugins/nucleamind-plugin-feishu/` + `nm serve`
- **抓网页 / 搜网**：官方插件 `plugins/nucleamind-plugin-web/`（`web.fetch` + `web.search`）
- **图像生成**：官方插件 `plugins/nucleamind-plugin-image/`（`image.generate`）
- **MCP 工具桥接**：官方插件 `plugins/nucleamind-plugin-mcp/`（一条命名空间声明）
- **长期记忆**：官方插件 `plugins/nucleamind-plugin-memory/`（`/memory` 命令 + 三条工具 + 每轮自动召回）
- **定时任务**：官方插件 `plugins/nucleamind-plugin-cron/`（`/cron` 命令 + 三条工具 + `CHANNEL:cron` 调度循环）+ `nm serve`

## 架构约束与改造方向

改造时遵循以下边界（详见 [.agent/design.md](.agent/design.md)）；分层与依赖规则
`R1`–`R5` 见技术方案 §3.1、§4.2：

1. **核心保持小，能力在边缘扩展**：代码写在最终位置——机制进 `kernel/`，能力进 `builtins/` 或 `plugins/`，公开类型进 `contracts/`，装配进 `runtime/`。**不要再开隔离区**：`D35` 之后没有「先放着以后再清」的地方。
2. **接口优先于实现**：不绑定具体数据库、聊天平台、模型供应商、工作流框架，优先设计抽象接口（Memory Interface、Context Interface、Message Interface、Agent Provider Interface）。
3. **机制优先于功能**：核心提供 Extension Mechanism、Lifecycle、Registry、Interface，而不是堆积具体功能。
4. **少结构、多智能**：优先简单可读的代码，不要引入不必要的框架层和间接层。
5. **优先重复而非过早抽象**：channel/provider 之间允许重复逻辑（发送重试、媒体处理、消息拆分），不要为消除重复引入复杂基类。从 `references/nanobot/` 借鉴实现时**把代码写到新家并补测试**，那份副本不在包里、也不可 import。
6. **在边界类型化动态数据**：wire payload、持久化记录、第三方 SDK 对象在拥有它们的边缘做解析/规范化，用 `TypedDict` 固定形状，不用 `Any` 向核心泄漏；`typing.cast` 必须有运行时检查支撑。
7. **显式优于魔法**：配置必须显式声明（字段表只在 `kernel/config/schema.py` 一处）；错误处理抛清晰异常，不静默修正坏输入。
8. **新模块首个 docstring 含「职责/不负责」两行**（技术方案 §4.6）：`contracts/`、`kernel/`、`sdk/`、`runtime/` 强制，由 `D01` 的架构守卫检查。

## 常见坑与安全边界

- 常见坑（`${VAR}` 语义、Windows 兼容、prompt 模板、上下文污染、原子写等）：[.agent/gotchas.md](.agent/gotchas.md)
- 安全边界（工作区路径解析、SSRF 防护、shell 沙箱，不可绕过）：[.agent/security.md](.agent/security.md)

## 参考项目读取规范

`references/` 是本地只读参考源码目录，默认被 Git 忽略。当前约定的参考项目及其导航文档位于 [`docs/references/`](./docs/references/README.md)。

- 不要全量读取 `references/`，先阅读 `docs/references/README.md` 和对应项目导航文档。
- 先按主题定位候选目录、文件和符号，再使用 `rg` 或索引查询缩小范围。
- 只有在需要确认具体实现、调用关系、生命周期或兼容性契约时，才读取相关源码和测试。
- `references/nanobot` 用于确认原始 nanobot 行为；`references/openclaw` 用于插件、SDK 和生态兼容研究；`references/pi` 用于极简 Agent、扩展点和运行时设计研究。
- 参考项目中的 `AGENTS.md` 只约束对该参考项目源码的阅读和解释，不覆盖 NucleaMind 的开发规则。
- 参考源码不是 NucleaMind 的实现目录。借鉴设计时，必须记录采用的边界和不采用的部分，避免直接复制与当前目标冲突的功能。
- 索引由 `scripts/reference_index.py` 生成，属于导航辅助数据，不是架构事实的唯一来源；索引过期时先重新生成。

## 项目文档规范

[`docs/project/README.md`](./docs/project/README.md) 是项目当前状态和开发进度的交接文档。
每次新会话开始较大开发任务前应先阅读；完成一个大模块、项目阶段或架构调整后必须更新。

- `docs/project/开发背景.md` 只维护相对稳定的项目愿景、目标和原则，不记录阶段性进度。
- `docs/project/` 保持扁平，不按方案、计划、决策等类型继续拆分子目录；长期文档使用
  中文原名，临时开发文档文件名优先使用小写英文和短横线。
- 开发模块时，可在 `docs/project/` 直接创建临时 Markdown 文档，记录目标、技术方案、
  任务拆分、风险和验收方式。
- 模块完成后，先把当前状态、关键结果和下一步工作更新到 `docs/project/README.md`，
  再将仍然有效的架构或使用说明更新到正式文档，最后删除对应临时开发文档。
- 参考项目导航资料放在 [`docs/references/`](./docs/references/README.md)，不要写入被
  Git 忽略的 `references/`。

## 指令文件边界

- 根目录 `AGENTS.md` 是本仓库 AI 编码代理的开发指引，`CLAUDE.md` 仅引用本文件。
- 运行时复制到用户 workspace 的 Agent 行为模板随 `legacy/templates/` 一并删除；新 Kernel 的
  同位物是 `builtins/context_basic/` 的基线指令与运维可配的自定义指令（`TrustLevel.OPERATOR`）。
  改那里会改变最终用户 Agent 的行为——**不要**把仓库开发流程或当前重构任务写进去。

## 代码风格

- Python 3.11+，全 asyncio。
- 行宽 100。
- Lint：`ruff`（规则 E, F, I, N, W，忽略 E501）。
- 测试：pytest，`asyncio_mode = "auto"`。
- **不要运行 `ruff format`**（会对历史代码生成大面积无关 diff），只用 `ruff check`。

## 开发流程（本项目自主）

- 本项目独立开发，不向上游 nanobot 提交代码。
- 提交保持小且单一意图，便于回溯（commit message 用简洁中文或英文均可）。
- 仓库已重新 init，与上游 git 历史完全脱离；是否持续跟踪上游修复由项目自行决定。
