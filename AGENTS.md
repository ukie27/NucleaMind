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
  阶段 2 Turn 内核收口；`D10` 已落地实例布局与配置加载（`kernel/config/` 九个模块），
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
  **阶段 5 进行中**，下一步 `D23`。
  遗留实现全部位于 `src/nucleamind/legacy/`，通过 `nm legacy` 可正常运行；
  `runtime/` 有 `wiring.py`、`introspection.py`、`plugin_context.py`、`bootstrap.py`、
  `instance.py` 与 `cli/`，`embed/` 已落地薄门面，`kernel/` 有
  `registry/`、`turn/`、`config/`、`observability/`、`routing/` 与 `plugins/`。
  `nm run` / `nm config show` / `nm session` 已可用。
- **长期目标**：不是继续堆功能，而是把 nanobot 改造成**轻量、模块化、可扩展的 Agent Kernel**——核心保持最小化（只保留 Agent 执行循环、LLM 抽象层、消息系统、Session 管理、Context 构建接口、Tool 注册机制、Plugin Runtime、基础配置），具体能力（Telegram/Discord/Memory/Browser/MCP/WebUI/Automation/Multi-Agent 等）逐步抽离为可选插件。
- 愿景与开发原则详见 [`docs/project/开发背景.md`](./docs/project/开发背景.md)。

> **命名（`D00` 已落地，技术方案 §4.5）**：Python 包为 `nucleamind`，发行名 `nucleamind`，
> CLI 命令只有 `nm`（不保留 `nanobot` 别名）。新层只读 `NUCLEAMIND_*`、
> `~/.nucleamind/<instance>/` 和 snake_case 配置，**不双读旧格式、不写长期兼容垫片**。
> `src/nucleamind/legacy/` 在被删除前继续使用 `NANOBOT_*`、`~/.nanobot/` 和 camelCase
> 配置别名——那是尚未改写完的实现，不是兼容承诺。

## 仓库结构（`D00` 已落地，技术方案 §4.1–§4.4）

```text
src/nucleamind/            # 唯一 Python 包（src 布局，强制 editable install）
├── contracts/             # 第 1 层：公开数据契约，纯类型，零内部依赖
├── kernel/                # 第 2 层：机制，只依赖 contracts
├── sdk/                   # 第 3 层：插件唯一依赖面，只 import contracts
├── builtins/              # 第 4 层：内建默认能力，与插件同等身份
├── runtime/               # 第 5 层：组装根 + `nm` 可执行程序
├── embed/                 # 第 5 层：嵌入式 Python SDK
└── legacy/                # 隔离区：nanobot 遗留代码，只出不进
plugins/                   # 一等公民：官方插件，各自独立发行
examples/plugins/          # 教学用最小示例插件
tests/                     # 镜像分层：architecture/ contracts/ kernel/ ... legacy/
                           # 是一个包（tests/__init__.py），否则 tests/builtins/ 与标准库撞名
                           # 外加 baseline/：旧实现行为基线，D31 随 legacy/agent/ 一并删除
deploy/                    # Dockerfile / compose / entrypoint
webui/                     # 前端源码（TypeScript）
```

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
写内建能力或插件时，先继承 `sdk.testing` 的 5 个契约测试基类。

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
  `TIMEOUT_TOOL_CANCEL` + `side_effect=UNKNOWN`。`jsonschema` 只在 `invoker._compile()`
  一处接触，惰性 import。

`kernel/config/`（`D10`、`D11`）是实例布局、分层配置、实例锁与 `${VAR}` 凭据引用的唯一
来源。写代码前记住六条：

- **配置的四层优先级只在 `sources.collect_layers()` 的返回顺序里定义一次**：
  `default < config.json < env < cli`。内置默认值是**一层**（`schema.defaults()`）而不是
  dataclass 兜底——`CFG-005` 要求每个生效值可追溯来源，「取自默认值」必须查得到。
- **字段只加在 `schema.SECTION_SPECS`**，那张表同时是默认值、类型与 `extra="forbid"` 的
  唯一依据。不要在别处另开一张表，也不要绕过 `validate_config()` 直接构造小节。校验积木
  （`FieldKind` / `FieldSpec` / `coerce_value`）在 `fields.py`，它**一个字段名都不认识**——
  分界线就是这个：加字段改 `schema.py`，加一种字段形状才改 `fields.py`。
- **`kernel/config/` 全包不写任何文件**（`EDG-501`）：`config.json` 只以 `"rb"` 打开且只在
  `sources.read_config_file` 一处。生成初始配置是 `D24`，写日志是 `D12`。
- **不要在 `schema.py` 里 module-level import `kernel.turn.limits`**：那会执行
  `kernel/turn/__init__.py`，把 engine/scheduling/folding 与 asyncio 拖上配置路径
  （`NFR-405` 冷启动预算 300 ms），`kernel.routing` 同理。`to_limits()` 用函数内 import，
  turn 的六个默认值、routing 的五个默认值与 hooks/context 的三个超时都在两处各写一份、
  由对照测试钉住。同理**不要把 pydantic 引进 `kernel/config/`**，有子进程测试盯着。
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

`tests/baseline/` 是 `D07` 的一次性设施：它只锁 `legacy/agent/{loop,runner}.py` 的五类
可观察行为（迭代上限 / 工具失败·超时·参数非法 / 流式聚合 / 调度顺序 / 结果截断），
供 `D09` 的 Turn Engine 与 `D14` 的 Orchestrator 对照，**`D31` 删 `legacy/agent/` 时一并
删除**。用法是「换构造、不换断言」——断言改不动说明新旧语义有差异，要给结论而不是放宽断言；
也不要往里加与那五类无关的测试。

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

`kernel/plugins/`（`D16`）是能力注册的唯一通道。写内建或插件前记住四条：

- **`CapabilityHost` 是唯一的 `NucleaAPI` 实现**，内建与外部插件共用它（`SDK-007`、
  `BAS-005`）。它不继承 `NucleaAPI`（`R2` 禁止 `kernel/` import `sdk/`），一致性由
  `runtime/wiring.py` 里那句 `conformance: NucleaAPI = host` 静态证明——有 AST 测试盯着。
- **九个 kind 的注册载荷形状与取回函数全齐**（`D14` 四个 + `D16` 五个）。内建能力自己不
  构造它们，Host 会按 `register_*` 的参数替你构造；取回后的实现体在 `binding.value` 上。
- **未声明的注册与声明了却没注册都是 `PLUGIN_LOAD_FAILED`**，靠 `detail` 区分。manifest 的
  `capabilities` 是有约束力的全集，`overrides` 只能从那里来（`EDG-102`）。
- **manifest 里别写 `priority`**：默认值 100 会被原样采纳，而内建基准是 0
  （`to_declaration()` 用 `model_fields_set` 判断作者写没写）。

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
.venv\Scripts\python.exe -m pytest tests/legacy/test_openai_api.py::test_function -v
.venv\Scripts\python.exe -m ruff check src/ plugins/

# legacy/ 债务指标（只允许下降）
.venv\Scripts\python.exe scripts/legacy_debt.py
.venv\Scripts\python.exe scripts/legacy_debt.py --check          # CI 门禁形态
.venv\Scripts\python.exe scripts/legacy_debt.py --lower-baseline # 迁完模块后下调基线

# 架构守卫（R1–R6 / 模块头部 / 文件规模 / Any 边界 / 债务棘轮），CI 独立作业
.venv\Scripts\python.exe -m pytest tests/architecture -q
.venv\Scripts\python.exe scripts/check_startup_cost.py --check

# 严格类型检查（与 CI 一致）
uv sync --all-extras --dev
uv run --no-sync python -m scripts.install_channel_dependencies --all-channels
uv run --no-sync basedpyright

# WebUI：dev server（代理 API/WS 到 gateway :8765）/ build / test
# 构建产物输出到 ../src/nucleamind/legacy/web/dist（打进 Python wheel）
cd webui && bun run dev      # 或 NANOBOT_API_URL=... bun run dev
cd webui && bun run build
cd webui && bun run test

# Gateway（迁移期遗留入口，D31 随 legacy/agent/ 一并删除）
nm legacy gateway
```

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

## 高层架构（`legacy/` 隔离区，源自 nanobot）

下列 `legacy/` 路径均在 `src/nucleamind/legacy/` 之下，描述的是**待迁移**的遗留实现。
新 Kernel 的目标分层见技术方案 §4.2；`legacy/` 的隔离规则见
[`src/nucleamind/legacy/README.md`](./src/nucleamind/legacy/README.md)。

### 核心数据流

消息通过异步 `MessageBus`（`legacy/bus/queue.py`）解耦聊天渠道与 agent 核心：

1. **Channels**（`legacy/channels/`）接收外部平台消息，向总线发布 `InboundMessage` 事件。
2. **`AgentLoop`**（`legacy/agent/loop.py`）消费入站消息，构建上下文，协调整个 turn。
3. **`AgentRunner`**（`legacy/agent/runner.py`）执行真正的 LLM 对话循环：发送消息、接收 tool calls、执行工具、流式返回。
4. 响应以 `OutboundMessage` 事件发布回对应渠道。

### 关键子系统

- **Agent Loop**（`legacy/agent/loop.py`、`runner.py`）：核心处理引擎。`AgentLoop` 管理 session keys、hooks、上下文构建；`AgentRunner` 执行带工具调用的多轮 LLM 对话。
- **LLM Providers**（`legacy/providers/`）：Anthropic、OpenAI 兼容、OpenAI Responses API、Azure、Bedrock、GitHub Copilot、Codex 等，基于公共基类（`base.py`），含图像生成（`image_generation.py`）与音频转录（`transcription.py`）。`factory.py` / `registry.py` 负责实例化与模型发现。
- **Channels**（`legacy/channels/`）：Telegram、Discord、Slack、Feishu、Matrix、WhatsApp、QQ、WeChat、WeCom、DingTalk、Email、MoChat、MS Teams、WebSocket、Mattermost。`manager.py` 通过 `pkgutil` 扫描自动发现，每个 channel 是自包含包。
- **Tools**（`legacy/agent/tools/`）：文件系统、shell（含沙箱后端）、web 搜索/抓取、MCP servers、cron、notebook、subagent、长任务/持续目标（`long_task.py`）、图像生成、自修改。`pkgutil` 扫描 + entry-point 插件自动发现。
- **Memory**（`legacy/agent/memory.py`）：会话历史持久化 + Dream 两阶段记忆整合，原子写（temp + fsync + rename）保证持久性。
- **Session Management**（`legacy/session/`）：会话历史、上下文压缩、TTL 自动压缩（`manager.py`）、持续目标状态（`goal_state.py`）。
- **Config**（`legacy/config/schema.py`、`loader.py`）：Pydantic 配置，从 `~/.nanobot/config.json` 加载（迁移期不变），支持 camelCase 别名。
- **WebUI**（`webui/`）：Vite + React SPA，通过 WebSocket 多路复用协议与 gateway 通信。
- **API Server**（`legacy/api/server.py`）：OpenAI 兼容 HTTP API（`/v1/chat/completions`、`/v1/models`）。
- **Command Router**（`legacy/command/`）：斜杠命令路由与内置命令处理。
- **Skills**（`legacy/skills/`）：内置技能定义（cron、github、image-generation 等），markdown + YAML frontmatter。
- **Security**（`legacy/security/`）：PTH 文件守卫等安全措施，CLI 入口激活。

### 入口点

- **`nm`（唯一命令）**：`src/nucleamind/runtime/cli/main.py`（最小骨架，真正的子命令在 `D23`）
- **遗留 CLI**：`nm legacy` -> `src/nucleamind/runtime/legacy_entry.py` -> `legacy/cli/commands.py`
- **遗留 Python SDK**：`legacy/nanobot.py`（新层门面 `embed/` 为重写，不移植旧实现）

## 架构约束与改造方向

改造时遵循以下边界（详见 [.agent/design.md](.agent/design.md)）；分层与依赖规则
`R1`–`R6` 见技术方案 §3.1、§4.2：

1. **核心保持小，能力在边缘扩展**：新代码写在最终位置——机制进 `kernel/`，能力进 `builtins/` 或 `plugins/`，公开类型进 `contracts/`，装配进 `runtime/`。**不允许往 `legacy/` 新增文件**（只出不进，`R6`）。
2. **接口优先于实现**：不绑定具体数据库、聊天平台、模型供应商、工作流框架，优先设计抽象接口（Memory Interface、Context Interface、Message Interface、Agent Provider Interface）。
3. **机制优先于功能**：核心提供 Extension Mechanism、Lifecycle、Registry、Interface，而不是堆积具体功能。
4. **少结构、多智能**：优先简单可读的代码，不要引入不必要的框架层和间接层。
5. **优先重复而非过早抽象**：channel/provider 之间允许重复逻辑（发送重试、媒体处理、消息拆分），不要为消除重复引入复杂基类。从 `legacy/` 复用实现时**把代码搬到新家并补测试**，不要 import 过来。
6. **在边界类型化动态数据**：wire payload、持久化记录、第三方 SDK 对象在拥有它们的边缘做解析/规范化，用 `TypedDict` 固定形状，不用 `Any` 向核心泄漏；`typing.cast` 必须有运行时检查支撑。
7. **显式优于魔法**：配置必须显式声明（新层在 `kernel/config/`，`legacy/` 仍在 `legacy/config/schema.py`）；错误处理抛清晰异常，不静默修正坏输入。
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
- `legacy/templates/AGENTS.md` 是运行时复制到用户 workspace 的 Agent 行为模板，不是仓库开发规范。
- 修改 `legacy/templates/`、`legacy/skills/` 中的说明会改变最终用户 Agent 的行为；不要把仓库开发流程、上游协作方式或当前重构任务写入这些运行时模板。

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
