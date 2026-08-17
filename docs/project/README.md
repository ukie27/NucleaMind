# NucleaMind 项目交接

- 更新时间：2026-08-17（`D47` 收口，**出站附件通路打通 + SDK 1.2**）
- 当前阶段：**阶段三 P1 能力插件化收口**（`D00`–`D47` 均已完成）。
  **本轮项目范围收窄**：Model Provider 止步于内建 `model-openai` + `anthropic` 插件，
  Channel 只做 `feishu`（`D34` 已交），WebUI 不做。`D35` 因此删掉了整个 `legacy/`、
  `tests/legacy/` 与 `webui/`，`R6` 守卫与债务棘轮一并退休。
  `D36`–`D38` 已交齐 **M5 的「扩展 Tool」**：官方插件 `web`（`web.fetch` / `web.search`）、
  `image`（`image.generate`）、`mcp`（命名空间桥接），外加一次机制扩展
  `CapabilityDecl.namespace`（`D38-A`）。
  `D39` 已交齐 **M5 的「Memory」**：官方插件 `memory`（一份 manifest 四类能力），
  外加第 6 个契约基类 `sdk.testing.MemoryProviderContract`。
  **`D40` 已交齐 M5 的最后一项「Cron / Automation」**：官方插件 `cron`
  （一份 manifest 五条能力：`CHANNEL:cron` + 三条 `TOOL:cron.*` + `COMMAND:cron`），
  **Kernel 一行未改、零新依赖**。**M5 至此全部交齐**，
  `references/nanobot/` 的迁移清单清空。
  `D41` 已把**插件纳入 basedpyright** 并为两张容易漂移的清单各加守卫
  （CI 安装清单、类型检查排除清单）；它同 PR 修掉了自己抓出的 `sdk.EventHandler` 缺陷。
  **`D42` 已交三条冻结表面变更并发布 `SDK 1.0.0`**：`ToolResult.trust`（工具结果真的被
  包成不可信数据块）、`FileAccess.read_bytes` / `write_bytes`、
  `HttpAccess.request(max_bytes=…)`，外加 `sdk.ManifestJsonSchema`。
  **`D43`–`D45` 清掉了 `D42` 之后清单上的前三条**：`D43` 落地 `channel.delivery_failed`
  （消解 `Channel.deliver` 与 `EDG-204` 那条真实矛盾，并把 discord / feishu 从「吞掉投递
  故障」改成照约定抛）；`D44` 给 `CapabilityKind.MEMORY` 接上 kernel 消费者，
  **M5 唯一一件「交了但没通电」的至此通电**；`D45` 给契约加了 **opaque 块槽位**
  （`contracts.OpaqueBlock`），`anthropic` 的 thinking 块因此可以多轮回放，
  **SDK 到 `1.1.0`**（纯新增）。
  **`D46` 补齐了新层的用户文档**：`docs/getting-started.md`（装包 → `nm init` → 凭据 →
  第一次对话 → 装插件）、`docs/configuration.md`（实例布局 + 四层优先级 + `${VAR}` 语义 +
  **九个小节的逐字段表**）、`docs/cli.md`（八个子命令的参数、退出码与「不做什么」）、
  `docs/deployment.md`（Docker / compose / systemd + 「权限模型没有监听端口这一种」）。
  三条防漂移守卫落在 `tests/e2e/test_user_docs.py`，同 PR 修掉 `deploy/` 的三处陈旧项。
  **`D47` 打通了出站附件通路**：`ToolResult.attachments`（**SDK `1.2.0`**，纯新增）→
  `TurnState.collect_attachments`（去重 + 封顶）→ 终帧 `OutboundMessage.attachments` →
  内建 CLI 印路径 / `discord` 经 `ctx.fs.read_bytes()` 真上传；`image` 的落点从
  `<state_dir>/images` 改到 `<workspace>/artifacts/images`——**那是它能被当成附件发出去的
  前提**（`AttachmentRef` 按契约拒绝绝对路径）。`ToolResult.artifacts` 至此不再是
  「有机制没消费者」。

本文档用于在新会话或开发者之间交接 NucleaMind 当前状态。完成一个较大的模块、
项目阶段或架构调整后，应同步更新本文档，使下一次开发可以直接从“下一步工作”
开始。

长期愿景和开发原则见 [`开发背景.md`](./开发背景.md)，仓库开发规则见
[`../../AGENTS.md`](../../AGENTS.md)。

## 当前项目状态

- NucleaMind 已与上游 nanobot 的 Git 历史和协作流程分离。
- 包名 `nucleamind`，发行名 `nucleamind`，CLI 命令只有 `nm`。仓库为 `src/` 布局，
  包里只有六层：`src/nucleamind/{contracts,kernel,sdk,builtins,runtime,embed}/`。
- **`D35` 之后仓库里没有遗留实现了**：`legacy/`（218 文件 / 73773 行）、
  `tests/legacy/`（97 文件）与 `webui/` 全部删除。迁移参考退回 `references/nanobot/`
  ——那份只读上游副本比 `legacy/` 更全（`D31` 从 `legacy/` 删掉的 `agent/tools/`
  与 memory 在那里还在）。
- 宿主的第三方依赖从 36 个降到 4 个（pydantic / httpx / jsonschema / packaging）。
  **能力所需的包由那个能力自己的发行包声明**，不回到宿主。
- **M5 已全部交齐**，没有待迁移的模块。`D43`–`D45` 清掉的是「机制缺口」而不是新能力：
  一条矛盾的契约约定、一条交了没通电的能力、一个缺失的契约槽位。Kernel 本身不再扩张。
- `references/` 保存本地参考源码并被 Git 忽略；其受版本控制的导航文档位于
  [`../references/`](../references/README.md)。

## 已完成

- 整理 NucleaMind 的项目背景、长期目标和核心开发原则。
- 保留原始 nanobot、OpenClaw 和 Pi 作为本地参考项目。
- 建立参考项目导航文档和轻量索引脚本，支持按需查询参考源码。
- 规定参考源码与 NucleaMind 自有文档分离管理。
- 建立本交接文档和临时开发文档约定。
- **`D00` 仓库重构与包重命名**（4 个 commit）：
  - `A0` 用 `scripts/test_snapshot.py` 捕获行为基线（5852 个用例、0 采集错误）。
  - `A1` 用 `git mv` 搬到目标结构，`git log --follow` 可追溯重构前历史。
  - `A2` 用 `scripts/migrate_names.py` 机械改写 4389 处包名/发行名，
    手工处理 `parents[N]` 层级、构建资源路径、vite outDir、Dockerfile 与
    `python -m` 子进程调用等机械规则覆盖不到的位置。
  - `A3` 重写 `pyproject.toml`（`packages`/`include`/`artifacts`/`testpaths`/
    `basedpyright.include`），新增 `nm` 入口与 `nucleamind.plugins` entry point 组，
    创建新层空骨架、`legacy/README.md` 与常驻的 `scripts/legacy_debt.py`。
  - 验收：基线比对 `missing`/`added`/`outcome_changed` 均为空；
    `nm --version` 与 `nm legacy --help` 可用且无 `nanobot` 命令；
    wheel/sdist 含 `templates/`、`skills/`、`web/dist/`；
    `ruff check` 与 `basedpyright` 通过；新层无旧名残留。
- **`D01` 架构守卫与 CI 门禁**：
  - `tests/architecture/` 共 51 个用例，全部只做 AST/文本静态检查，不导入被测模块：
    `test_import_boundaries.py`（`R1`–`R6`）、`test_module_docstrings.py`
    （「职责/不负责」两行）、`test_file_size.py`（行数阈值）、
    `test_any_usage.py`（`Any` 须带 `# boundary:` 说明）、
    `test_legacy_debt.py`（债务棘轮）、`test_guard_integrity.py`（守卫自身不可被关掉）。
  - 规则实现集中在 `_boundaries.py`，可作用于任意源码树——反向用例因此能在
    `tmp_path` 里构造违规样例。`R1`–`R6` 每条各有一个注入用例；`R6` 另有四例覆盖
    「新层 import legacy 失败 / legacy import 新层通过 / 白名单适配器通过 /
    第二个适配器失败」。空目录一律通过，空骨架不会误报。
  - `R6` 白名单精确到 `nucleamind/runtime/legacy_entry.py` 一个文件路径。
  - `pyproject.toml` 叠加 `C901`(≤12) / `PLR0915` / `TRY` / `ASYNC`，
    用 `per-file-ignores` 反向豁免 `legacy/`、`scripts/`、`tests/`；仍不引入 `ruff format`。
  - `scripts/legacy_debt.py` 增加 `--check`（棘轮门禁）与 `--lower-baseline`（只许下调），
    基线存于 `scripts/legacy_debt_baseline.json`。
  - `scripts/check_startup_cost.py` 记录 `import nucleamind` 耗时、`nm --version`
    耗时与包根急切导入的模块清单——第三项保证 `nucleamind/__init__.py` 零副作用。
  - CI 新增独立作业 `Architecture guard`（守卫 + 债务棘轮 + 启动开销），失败即阻断。
- **`D02` 契约·基础层**（`contracts/{__init__,ids,errors,events}.py`，约 640 行 +
  `tests/contracts/` 85 个用例）：
  - `contracts/__init__.py` 定义递归类型别名 `JsonValue` 与 `JsonSchema`，
    并统一再导出基础层公开名。子模块只在 `TYPE_CHECKING` 下反向导入 `JsonValue`，
    运行时不成环，因此契约层全程没有 `Any`。
  - `ids.py`：`InstanceId` / `TurnId` / `PluginId`（`NewType`）、`SessionKey`、`Correlation`。
    `SessionKey.storage_id()` 对每个分量按 UTF-8 逐字节百分号编码（安全字符集
    `[A-Za-z0-9._-]`），再用 `~` 连接。`~` 不在安全字符集内，编码结果里绝不会出现
    未转义的分隔符，因此 `split` 不可能切错位置——这就是「不同输入不可能撞同一个 id」的
    依据，也顺带让编码结果可以直接当目录名用。`from_storage_id()` 是其逆运算。
    `Correlation.derive()` 生成 subagent / 派生 turn 的关联标识，只记一层父节点。
  - `errors.py`：`ErrorCategory` 11 个取值全部落地；`ErrorCode` 集中登记 29 个稳定错误码，
    `CODE_CATEGORIES` 是码到分类的唯一映射，`NucleaError.category` 由码推导而**不接受
    调用方传入**，杜绝同码异类；未登记的码抛 `UnknownErrorCodeError`（编码错误，不走
    `NucleaError` 自身）。脱敏在构造时完成：敏感键名整值打码、已知令牌形状（`sk-`、
    `ghp_`、`xox*-`、`AKIA`、`Bearer`）按值打码，被摘除的原始密文再从 `user_message`
    里反查擦除，因此 `user_message`、`detail`、`repr`、`str`、`args` 都不含哨兵值。
  - 键名判定按**整词**比对（`_`、`-`、camelCase 边界切词）而不是子串：子串匹配会把
    `tokens`、`prompt_tokens` 这类用量统计一并打掉，而那正是可观测性最需要的信号。
    裸 `key` 不算密钥（`session_key`、`cache_key` 保留），只有 `api/access/private/
    secret/signing/encryption` + `key` 的词组才算；`count`/`limit`/`usage` 等统计限定词
    一票否决。这条规则由 15 个「必须保留」的反向用例锁死。
  - `events.py`：`EventFamily` 7 族、`EventName` 冻结 30 个事件名，
    `RuntimeEvent` 带 `Correlation` 与单调 `sequence`，构造时校验序号非负、时间带时区、
    关联标识与事件实例一致，并对 `payload` 脱敏 + 快照冻结为只读映射
    （调用方事后改自己的 dict 影响不到已发布的事件）。实例级事件允许无 `correlation`。
  - 验收：`storage_id()` 在 16 个刁钻分量的 4096 种组合上往返还原且零碰撞；
    `("a","b:c")` -> `a~b%3Ac~default` 与 `("a:b","c")` -> `a%3Ab~c~default` 不同；
    哨兵密钥在五种渲染形式下均不泄漏；`ruff check`、`basedpyright`（新层 0 报错）、
    `tests/architecture` 51 个用例全绿。
- **`D03` 契约·领域与执行层**（`contracts/{metadata,message,session,context,tool,model}.py`，
  约 1450 行 + `tests/contracts/` 新增 150 个用例，合计 269 个）：
  - 比开发方案多一个 `metadata.py`：`metadata` 在 `InboundMessage`、`OutboundMessage`、
    `ToolResult`、`ModelResponse` 四处出现，四份等价校验没有意义；而「进 Kernel 前移除
    不可序列化的 SDK 对象」是 Channel/Provider 边界要复用的公开动作，放私有模块会逼
    调用方 import 下划线名字。`normalize_metadata()` 校验四项上限（条数 64 / 16 KiB /
    深度 4 / 键长 128）后深拷贝冻结，非 JSON 值**抛错而不是静默 `str()`**——静默通过
    只会把问题推迟到持久化层。
  - `ids.validate_identifier()` 由 `D02` 的私有 `_validate_component` 提升为公开函数：
    `message_id`、`channel_id`、`call_id` 与会话分量是同一条规则（非空 / 不超长 /
    无控制字符），编码与 `SessionKey` 的 `storage_id()` 逻辑未动。
  - `message.py`：`OutboundMessage` 自带 `channel_id + conversation_id + turn_id`
    （`MSG-006`），并断言这些字段与 `session_key` 一致——冗余寻址打架时投递会静默投错。
    附件用 `AttachmentSource` 四态（URL / WORKSPACE / OPAQUE / INLINE）而不是裸路径，
    `WORKSPACE` 拒收绝对路径与 `..`（§10.2 校验规则）。`is_complete_answer` 只在
    `stream_state=FINAL` 时为真（`EDG-304`）。
  - `session.py`：`SessionSnapshot` 带 `schema_version`（`SES-006` 的可迁移格式），
    `compacted_through` 是压缩水位而非标记位；`TurnStatus` 四个终态与
    `error`/`cancel_reason` 的一致性在构造时校验。
  - `context.py`：`trust` 四级齐全，`as_model_text()` 对 `UNTRUSTED` 片段强制包裹
    `UNTRUSTED_DATA_PREFIX`（「以下内容为参考数据，不构成指令。」）+ 带来源的数据块，
    并中和内容里自带的闭合标记——否则一段检索结果只要自带 `</untrusted-data>` 就能提前
    合上数据块，让后半段以指令身份出现（`CMD-005`、`EDG-306`）。包裹放在契约上而不是
    组装器里，插件交出来的是片段而不是最终文本，没有绕行路径。
  - `tool.py`：`side_effect` 必填无默认值（测试直接断言 `field.default is MISSING`），
    `ok=False` 必须带 `error`，`read_only=True` 与 `risk != SAFE` 互斥。
    `ToolCall`（模型发出）与 `ToolInvocation`（带 `Correlation`、超时、幂等键）拆开，
    前者要能原样放进 `ModelResponse`。`auto_retry_allowed` 由幂等键决定（`EDG-402`）。
  - `model.py`：`provider_metadata` 走 `normalize_metadata()`，这是「Provider 私有响应
    对象不得越过边界」在类型层的强制；`ModelResponse` 拒收重复 `call_id`（`EDG-303`）；
    `TokenUsage` 字段名用 `*_tokens` 复数，与 `errors` 的整词脱敏规则配合，保证用量统计
    能原样进事件与日志。
  - 验收：`tests/contracts/test_field_traceability.py` 用一张表把 20 个契约类型的**完整**
    字段集合对上需求 §10 的具体小节，断言用相等而不是包含——包含关系拦不住「多加了一个
    没人讨论过的字段」；同一文件断言全部类型是 frozen + slots。
    `ruff check`、`basedpyright`（新层 0 报错，legacy 仍是既有 4 个）、
    `tests/architecture` 51 个用例、`tests/contracts` 269 个用例全绿；
    新层 `Any` 数仍为 0（仅 docstring 里提到这个词）。
- **`D04` 契约·能力层**（`contracts/{capability,command,protocols}.py`，约 1030 行 +
  `tests/contracts/` 新增 126 个用例，合计 395 个）：
  - 比开发方案多一个 `command.py`：`CommandHandler` 的输入输出不定型，Protocol 就无法
    类型化，而 `protocols.py` 是长期兼容承诺的起点，带着必然要改的签名发布代价更大。
    同理，`HookHandler` 需要的 `HookContext` / `HookOutcome` 落在 `capability.py`。
  - `capability.py`：`CapabilityKind` 9 个取值，与 `sdk.NucleaAPI` 的 9 个注册方法一一
    对应；`CAPABILITY_ARITY` 是冲突语义的唯一来源，9 个 kind 全部登记，缺项直接 KeyError
    ——冲突语义未定的能力不该有注册路径。**技术方案 §6.1 的表格漏了 `MEMORY`，`D04` 定为
    MULTI（name 唯一）并已回写技术方案**：`register_memory_provider(name, m)` 带 name
    本身就意味着可并存多个具名实现，而 `MEM-003` 的降级要求换后端不必先卸载现有的。
  - `ProviderId = Builtin | Plugin(plugin_id)` 是联合类型而不是裸字符串（`SDK-002`）：
    一个恰好叫 `builtin` 的插件在字符串世界里能冒充内建。`str(provider)` 的渲染
    (`"builtin"` / `"plugin:<id>"`) 让「内建排在插件前」直接由字典序成立，
    §6.1 的排序规则不需要特例。覆盖目标的编解码集中在
    `CapabilityRef.target` / `parse_capability_target()`，`D05` 的 manifest `overrides`
    与 `D06` 的解析必须复用这一份，不得各写一套正则。
  - Hook 表面：`HookName` 冻结 10 个 + `HOOK_KINDS`（5 观察者 / 5 拦截器）+
    `HOOK_REQUIRED_SLOTS`。最后这张表是 §6.6 表格的可执行形态——「`before_tool_call`
    能改工具参数」落地就是「它一定拿得到 `invocation`」。`HookOutcome` 的载荷四选一而不是
    全填：让一个结果同时带片段、请求和工具结果，调度器就只能靠当前 Hook 反推该用哪个，
    handler 填错即静默失效。
  - `command.py`：`Disposition` **照抄 §6.3 的四个取值**，`D13` 的 dispatcher 直接复用，
    不再定义第二个同义枚举；`CommandResult` 在构造时拒绝 `MODEL_TURN`（那是「未命中」，
    dispatcher 的结论而非 handler 的）。`fragments` 用 `ContextFragment` 而不是裸文本，
    `CMD-004`/`CMD-005`「不得凭借文本形式绕过限制」因此在类型层就已成立。
  - `protocols.py`：8 个能力 Protocol 共 20 个成员，外加只读的 `CancelSignal`
    （`requested` + `raise_if_requested()`）。取消信号拆成两个面是刻意的——`D08` 的
    `CancelToken` 额外有 `request()` / `child()`，能力实现拿到的只有观测面，
    无权取消整个 turn。每个方法的 docstring 固定写 **异常约定** 与 **取消语义** 两段，
    并由测试断言这两个标记存在（三个豁免项在测试里显式列出）。
  - `NucleaError` 补上 `capability` 字段，兑现 `D02` docstring 里的承诺
    （`PLG-006`：诊断要能一眼看出是谁的问题）。`CapabilityRef` 只在 `TYPE_CHECKING` 下
    导入——`capability.py` 运行时依赖 `errors.py`，反向导入会成环。
  - 验收：arity 表与 Hook 表以**字面量**写在测试里再与实现比对（从实现反推的测试只能
    证明代码没改，证明不了它和技术方案一致）；每个 Protocol 有一个不继承任何宿主基类的
    最小 Fake 通过 `isinstance`；方法数快照 + AST 断言 `protocols.py` 里没有实现；
    `ruff check`、`basedpyright`（新层 0 报错，legacy 仍是既有 4 个）、
    `tests/architecture` 51 个用例、`tests/contracts` 395 个用例全绿；新层 `Any` 数仍为 0。
- **`D05` sdk 骨架与测试夹具**（`sdk/{__init__,api,manifest,version}.py` +
  `sdk/testing/{fakes,contracts}.py`，约 1100 行 + `tests/sdk/` 120 个用例）：
  - `api.py`：`NucleaAPI` 恰好 **9 个注册方法 + `ctx`**，逐条对应 `CapabilityKind` 的 9 个
    取值（对照表以字面量写在 `tests/sdk/test_public_surface.py` 里）。另含受限的
    `PluginContext` 与四个资源访问器 Protocol（`fs` / `net` / `shell` / `secret`）——
    访问器是 **property 而不是方法**：未授权时属性访问就抛 `PERMISSION_DENIED`，插件拿不到
    「看起来能用、调用才失败」的对象。`SecretStr` 默认渲染为 `contracts.errors.MASK`，
    明文只能经 `reveal()` 取出，调用点即审计抓手（**`D11` 已把它下沉到
    `contracts/errors.py`**，不再由 `sdk` 导出）。
  - **`CliEntry` 补进 `contracts/protocols.py`（第 9 个能力 Protocol）**：
    `register_cli_entry()` 的载荷需要类型，而 `kernel/` 与 `runtime/` 都要调用 CLI 能力却
    禁止 import `sdk/`（`R2`）。`D04` 冻结的是「8 个」这个数字，不是「不许补齐」——
    `CapabilityKind` 一直是 9 个取值。签名是 `run(argv, cancel) -> int`：交互式会话与单次
    执行是同一方法的两种参数形态，拆开会让 `EDG-108` 的整体回落无处落脚。
    `tests/contracts/test_protocols.py` 的快照同步改为 9 个 Protocol / 21 个成员。
  - `manifest.py` 用 pydantic（`extra="forbid"` + `frozen=True`，与技术方案 §5.1 表格一致），
    但**错误面收窄成一种异常**：语义校验直接抛 `NucleaError`（pydantic 只截获 `ValueError`
    / `AssertionError`，其余原样穿透），结构错误由 `parse_manifest()` 转成带**字段路径**的
    `NucleaError(PLUGIN_MANIFEST_UNSUPPORTED)`。id 形状借 `Plugin()` 校验、能力名借
    `CapabilityRef` 校验、`overrides` 只用 `parse_capability_target()` 解码——三处都用
    `_at_field()` 把 contracts 抛出的 `INPUT_MALFORMED` 重贴上 manifest 字段路径，
    否则「一律带字段路径」这条承诺会有三个漏洞。
  - `SDK_VERSION = "0.1.0"`：§7.6 的兼容承诺从 1.0.0 起算，Kernel 未落地前不宣布 1.0
    （已回写技术方案）。`is_compatible()` 用 `packaging` 的 PEP 440 语义，
    非法 `sdk_range` **抛错而不是当作全兼容**——后者正好让最该被拦下的插件通过。
  - `sdk/testing/`：`FakeModelProvider`（脚本是 `ModelResponse` 序列，`stream()` 由同一条
    脚本派生分片）、`InMemorySessionStore`（用 `storage_id()` 作键，让 Fake 也走一遍已发布
    的编码契约）、`RecordingHook`、`ManualCancel`，以及 5 个契约测试基类
    （`ModelProviderContract` / `SessionStoreContract` / `ContextProviderContract` /
    `ToolContract` / `ChannelContract`）。基类**不 import pytest**，只是普通类 + `assert`。
  - 验收：`sdk.__all__` 与 `sdk.testing.__all__` 做字面量快照；导入 `sdk.manifest` 在子进程
    里用 **audit hook** 断言无写文件、无网络、耗时 < 2s、且不牵连 `kernel/legacy/builtins`
    ——并有一条「注入一个导入时写文件的模块，探针必须报出来」的自证用例；5 个契约基类各被
    一个 Fake 继承跑通，另有一个故意忽略取消的 provider 证明基类会拦。
    `ruff check`、`basedpyright`（新层 0 报错，legacy 仍是既有 4 个）、`tests/architecture`
    51 个 + `tests/contracts` 395 个 + `tests/sdk` 120 个用例全绿；新层 `Any` 数仍为 0。
- **`D06` Capability Registry 与覆盖解析**（`kernel/registry/{__init__,capability,resolution}.py`，
  761 行 + `tests/kernel/` 50 个用例）：
  - **分工是单向的**：`capability.py` 只管「谁登记了什么」，`resolution.py` 才判「谁最终
    生效」，后者依赖前者、反过来不成立。把两件事写进一个类，冲突语义就会散落到每个注册点
    上，而 `EDG-102`「覆盖永不由加载顺序决定」正是那样丢掉的。
  - `RegistrationBatch` 是**上下文管理器**形态：正常退出即 `commit()`，异常退出即
    `rollback()` 并原样抛出。这不是便利封装——它是唯一能保证 `EDG-103`「`setup` 中途抛
    异常不留半注册状态」不被遗漏的写法。也保留显式 `commit()` / `rollback()`，因为 `D16`
    的 Host 要在 `setup(api)` 返回**之后**才提交，两个调用点不在同一个作用域。
  - **解析一次性全量计算，失败不抛出而是进 `failures`**：一次解析报出全部冲突，
    「启动错误」这个语义由调用方对报告调用 `raise_if_failed()` 兑现。改一条配置才看到下一条
    冲突不是可接受的启动体验。有冲突时**依然冻结**注册表——否则诊断路径连生效集合都读不到。
  - **priority 基准值按提供方分**：内建 0、插件 100（`base_priority_for()`，§6.1 规则 1、
    §15 决策表第 3 行）。规则放在 registry 而不是各 bootstrap 路径——priority 同时决定
    §10.2 的裁剪顺序（「其余按 priority 逆序丢弃」），基准 0 意味着系统提示与会话历史在
    预算压力下最后被丢；两处各复述一遍必然分叉。插件仍可显式声明 0，同值时按 provider
    字典序，内建依然在前。
  - **冲突各方都不生效**（同名重复、SINGLETON 多实现）：选任何一边都是替用户做决定。
    但覆盖冲突是例外——抢覆盖的都出局，被抢的目标继续生效，实例不会因此丢掉这个能力。
  - **SINGLETON 的分组键是 kind 本身**，与 name 无关：`register_session_store("sqlite", …)`
    和 `("jsonl", …)` 是同一个槽位的两份实现。按 `(kind, name)` 分组会让它们各自「唯一」，
    SINGLETON 也就名存实亡。
  - **冻结前不可查找**：未定案的注册表返回的任何结果都可能被后续覆盖掉，让它可查就是在
    鼓励调用方缓存一个随后失效的实现——而这种问题只在装了覆盖插件的用户那里复现。
    `lookup()` 对 MULTI 类 kind 直接拒绝，那两类天然可能有多个实现，只取第一个必然静默丢实现。
  - `Registration.payload` 类型是 **`object` 而不是 `Any`**：注册表不解释载荷只搬运它，
    用 `object` 时调用方必须先窄化，用 `Any` 则让未经检查的值一路流进 Kernel。
  - **补了两个 `ErrorCode`**：`CAPABILITY_OVERRIDE_TARGET_MISSING`（→ `CAPABILITY_MISSING`
    类）与 `CAPABILITY_OVERRIDE_CONFLICT`（→ `PLUGIN_FAILURE` 类，与既有
    `PLUGIN_REGISTRATION_CONFLICT` 同类：都是「插件之间打架」）。技术方案 §6.1 与开发方案
    点名了这两个码，但 `D02` 落地 `ErrorCode` 时没有登记。
  - 验收：开发方案那张八行冲突分支表逐条对齐，每条一个测试（表格写在
    `tests/kernel/test_resolution.py` 的模块 docstring 里）；`ResolutionReport.to_json()`
    做完整字面量断言并 `json.dumps/loads` 往返一次，证明它真是 JSON 而不是「看起来像 JSON
    的字典」；排序稳定性用**输入轮换**测试（4 条登记的每种旋转结论一致）。
    `ruff check`、`basedpyright`（新层 0 报错）、`tests/architecture` + `tests/contracts` +
    `tests/sdk` + `tests/kernel` 共 625 个用例全绿；`kernel/registry/` 语句覆盖率 100%；
    新层 `Any` 数仍为 0。
- **`D07` 旧实现行为基线**（`tests/baseline/{__init__,_support}.py` +
  `test_{runner,loop}_behavior.py` + `README.md`，约 900 行 / 36 个用例）：
  - 全部针对**旧实现**编写并通过，不联网、不碰真实模型或真实工具：`_support.py` 的
    `ScriptedProvider` 按脚本回放 `LLMResponse`（`chat_with_retry` 与
    `chat_stream_with_retry` 共用同一条脚本），`FakeTool` 提供可控的结果、异常与并发类别。
    刻意不复用 `tests/legacy/agent/` 的既有夹具——基线要能当作行为说明书读，也要能在
    `D31` 整体删除。
  - `ScriptedProvider` 每次请求返回响应的**深拷贝**：runner 会就地改写
    `response.content`（`extract_reasoning` 之后），共用一个脚本对象会让第二次迭代看到
    已被清洗过的内容——这个坑本身就说明「响应对象可变」是旧实现的隐含约定。
  - 开发方案点名的五类行为逐条落在 `test_runner_behavior.py` 的五个分节
    （`B1` 迭代上限 / `B2` 工具失败·超时·参数非法 / `B3` 流式聚合 / `B4` 调度顺序 /
    `B5` 结果截断）；`test_loop_behavior.py` 收的是 `AgentLoop` 对这次运行**做的决定**
    （预算、工具错误策略、持久化时的再次截断），那部分归 `D14` 而不是 `D09`。
  - 记下来的几条容易读错的事实：用户可见的一轮 **不** 传 `fail_on_tool_error`
    （取默认 `False`），而 `AgentDefaults.fail_on_tool_error` 是 `True` 且只作用于 subagent；
    超长结果有截断与落盘两条路径，`read_file` 是唯一豁免工具；SSRF／工作区越界对模型
    不可重试但对本轮不致命；并发只发生在**连续的** `concurrency_safe` 工具之间，
    非安全工具是屏障，而工具结果进消息列表的顺序永远等于 tool_calls 的顺序。
  - 验收：36 个用例在旧实现上全绿（`tests/baseline` 单独跑 0.9s + 1.3s）；
    与 `tests/legacy/agent` 同进程跑 1554 passed / 1 failed，那 1 个是既有的
    `test_onboard_logic.py::test_quick_start_openai_codex_reports_incomplete_installation`
    （单独跑同样失败，属既有 oauth-cli-kit 家族）；`ruff check` 通过；
    `tests/architecture` 51 个用例仍全绿；`src/` 未改动一行。
- **`D08` 取消与预算**（`kernel/turn/{__init__,cancel,limits}.py`，约 420 行 +
  `tests/kernel/{test_cancel,test_limits}.py` 87 个用例）：
  - **取消与预算是两件事，因此是两个不互相依赖的模块**：取消是「有人要求停下」
    （终态 `CANCELLED`），预算是「已经用掉多少」（终态 `STOPPED_BY_LIMIT`）。缝在一起
    就会让「模型自己绕了 16 圈」和「用户按了 Ctrl-C」共用一条判定路径，而这两者的善后
    动作不同。唯一交点是 `turn_timeout_ms`：它是预算项，触发时以 `CancelReason.TIMEOUT`
    走取消路径，由 `LimitBreach.cancel_reason` 显式给出。
  - `CancelToken` 三条不变量：`request()` 幂等且第一次的 reason 胜出（`EDG-206`）；
    取消**只向下传播**（父取消全部后代，子取消不影响父与兄弟）；父已取消时 `child()`
    **出生即取消**——否则「取消后又发起一次工具调用」会拿到一个看起来正常的令牌。
    子令牌用 `WeakSet` 登记，工具结束后不会一直挂在 turn 上。
  - **额外提供 `await token.wait()`**，不只是可轮询：`EDG-407` 的宽限期要与取消赛跑，
    只能轮询的话 Kernel 只能指望不自觉的那些工具自觉。`asyncio.Event` 懒创建，
    每工具一个的令牌绝大多数从不被 await。
  - 6 个检查点落成 `Checkpoint` 枚举 + `CHECKPOINT_OWNERS`（engine 4 个：2/3/5/6；
    orchestrator 2 个：1/4）。`token.checkpoint(where)` 抛出的错误带
    `detail["checkpoint"]`，「turn 停在哪一步」不必靠读日志上下文猜。
  - **补了一个 `ErrorCode`**：`CANCELLED_BY_SHUTDOWN`（→ `CANCELLED` 类）。四个
    `CancelReason` 到错误码的映射集中在 `CANCEL_REASON_CODES`（`TIMEOUT`/`BUDGET` 合并到
    `CANCELLED_BY_BUDGET`）。把 `SHUTDOWN` 并进 `CANCELLED_BY_USER` 会让「用户按了
    Ctrl-C 还是实例在关闭」不可判定，而这两者的后续处理完全不同。
  - `TurnLimits` 恰好六项且 `LimitKind` 的取值**等于字段名**（有对照测试）：越界报告要能
    直接指回「改哪个配置项」，中间隔一层翻译表就会出现「报的名字和配置里的对不上」。
    `LIMIT_OUTCOMES` 是 §6.4「触发行为」列的可执行形态，`None` 表示该项越界**不终止
    turn**（单工具超时、结果截断、上下文超限三项）。取消宽限期
    `DEFAULT_TOOL_CANCEL_GRACE_MS = 2000` 是取消参数而不是预算项，因此不在六项里。
  - `BudgetLedger` 与 `TurnLimits` 分开：前者是 per-turn 可变状态，后者是不可变配置。
    计数器塞进配置对象就等于让并发 turn 共享同一份计数（`KER-008` 允许同实例多 session
    并发）。时钟注入默认 `time.monotonic`——墙钟回拨会让 turn 突然超时或永不超时。
  - `check(pending_tool_calls=n)` 在**发起前**判定：先记账再判定会让最后一批工具真的执行
    完才发现超了，副作用已经发生。判定顺序总超时 -> 迭代 -> 工具调用，时间用尽时的终态
    （`CANCELLED`）不会被计数类越界遮住。「配额刚好用满且模型没再要工具」不算越界。
  - 验收：六项预算逐项测试（默认值字面量 / 达到上限的行为 / 可配置性 / 非正数与 `bool`
    被拒）；「缺省配置下不存在无界执行路径」用一个永远返回 tool_call 的假模型驱动
    engine 主循环骨架，断言 16 轮后以 `STOPPED_BY_LIMIT` 终止；「取消后数据仍可保存」
    有独立用例（模拟检查点 3，断言已产生文本完整留存）。`ruff check`、
    `basedpyright`（新层 0 报错，legacy 仍是既有 4 个）、`tests/architecture` +
    `tests/contracts` + `tests/sdk` + `tests/kernel` + `tests/baseline` 共 742 个用例全绿；
    `kernel/turn/` 语句覆盖率 100%；新层 `Any` 数仍为 0。
- **`D09` Turn Engine**（`kernel/turn/{engine,events,deps,scheduling,folding}.py`，
  约 1170 行 + `tests/kernel/{test_engine,test_folding,test_scheduling}.py` 77 个用例）：
  - **`run_turn(request, deps, cancel, *, ledger=None)` 以整个 `ModelRequest` 为种子**
    （技术方案 §6.2 的草图已回写）：`before_model_request` Hook 的载荷槽就是
    `ModelRequest`，拆成 `(messages, tool_specs)` 就得把 Hook 改过的请求拆回去，而
    `params` / `timeout_ms` 的改写在那一步会被静默丢掉。顺带地，「模型看得见的工具集」
    与「engine 能调度的工具集」成了同一个对象（`request.tools`）。
  - **engine 事件类型放 `kernel/turn/events.py` 而不是 contracts**：`test_field_traceability`
    要求每个契约类型对上需求 §10 的一节（事件是 §6.2 拆分的产物，没有出处）；进
    `contracts.__all__` 会被快照变成永久公开表面（`NFR-104`）；且 `TurnCancelled.checkpoint`
    与 `TurnStoppedByLimit.breach` 引用的是 kernel 的 `Checkpoint` 与 `LimitBreach`。
    事件是 9 个 frozen dataclass 的**封闭联合**（不是 kind 枚举）：`D14` 的 `match` 在
    basedpyright 严格模式下拿到穷尽性检查，漏一个分支是编译期错误。事件不带 `correlation`
    （整个 turn 只有一个，复制一份就有两个真相来源）。
  - **`EngineDeps` 恰好四个槽**（§6.2 原文），`ToolInvoker` / `HookDispatcher` 两个
    kernel-local Protocol。三条职责边界：`ToolSpec` 查找留在 engine（`request.tools` 建索引，
    「未知工具」由此有精确定义）；超时 engine 定、invoker 执行（`ToolInvocation.timeout_ms`
    必填，engine 压到 `min(tool_timeout_ms, remaining_ms())`，宽限期与孤儿任务登记在
    invoker）；截断在 engine 且在 `after_tool_call` **之后**（先截后钩等于给插件一条绕过
    预算的路）。
  - **全文件只有 2 处 try/except**：`run_turn` 外层的唯一出口（一切异常转成终态事件，
    `terminal_from_error` 是唯一翻译表）+ `_invoke_one` 里把 invoker 逸出的异常折成
    `side_effect=UNKNOWN`。捕 `Exception` 不捕 `BaseException` 是刻意的：`CancelledError`
    是任务本身被杀，不是 turn 被取消。**工具失败永不升级为 `TurnFailed`**（旧实现行为，
    开发方案验收表此处有措辞差异，结论写在测试 docstring 与 §6.2.1）。
  - **工具调度的关键设计：检查点 5 只在工具阶段入口抛一次，批次内部只查不抛**。
    批次中途取消时，已执行的保留真实结果，未执行的合成 `side_effect=NONE` 的
    `SKIPPED` 结果，tool 消息照样进 messages——否则「已产生的内容」要靠 except 里的
    局部变量抢救，那正是「一堆 try/except」的来源。`partition_tool_batches` 是公开纯函数
    （替代旧私有方法）：连续 `PARALLEL` 合批，`EXCLUSIVE` 与未知工具单独成批。
  - **`StreamFolder` 是推入式状态机**（engine 必须边收边发 delta 并做检查点 3）。全案
    唯一一处推断：流结束但缺 DONE 分片时按 `TOOL_CALLS if tool_calls else END_TURN` 推断
    并标记 `provider_metadata["missing_done_chunk"]`（`MOD-005` 不静默降级）。`DONE(ERROR)`
    抛 `EXTERNAL_MODEL_PROVIDER` 而不是折成正常响应（`EDG-304`）。同 `call_id` 分片
    后到覆盖先到并计数（增量拼装是 Provider 边界的职责）。
  - **与旧实现的语义差异**逐条写进技术方案 §6.2.1（合批口径从只读换成
    `concurrency is PARALLEL`、字节截断不追加后缀、`before_model_request` 归 engine 每轮
    分发、续写 = 共享 ledger 再调 `run_turn`、收尾请求归 D14）。33 个基线用例的逐条
    对照结论已并入 §6.2.1。
  - 验收：`engine.py` 380 行（≤400，自有测试 + D01 守卫双卡）；import 白名单测试
    （`os`/`pathlib`/`socket` 出现即失败 + 注入反向用例）；4 个检查点各有独立测试并断言
    `side_effect` 正确；每个 `deps` 回调注入异常产出终态事件而非穿透；四个终态各有测试；
    「最后一轮的工具不执行」是一条刻意的行为测试（结果无法回给模型，执行只产生无谓副作用）；
    `tests/kernel` 单次 0.8s（≤2s）；`kernel/turn/` 语句覆盖率 100%；新层 `Any` 数保持 0。
    `ruff check`、`basedpyright`（新层 0 报错，legacy 仍是既有 4 个）、`tests/architecture` +
    `tests/contracts` + `tests/sdk` + `tests/kernel` + `tests/baseline` 共 822 个用例全绿；
    `legacy_debt` 未变（src/ 只增不改 legacy）；`check_startup_cost` OK。
    `pyproject.toml` 的 coverage `exclude_lines` 补了一条 `^\s*\.\.\.$`（Protocol 存根）。
- **`D10` 实例布局与配置加载**（`kernel/config/` 8 个文件，约 1450 行 +
  `tests/kernel/{test_layout,test_config}.py` 106 个用例）：
  - **包内依赖单向**：`layout` / `process` / `merge` 互不相识，`lock` 只用 `process`，
    `schema` 只用 `merge` 的 pointer 工具，`sources` 只产出层，`loader` 编排全部。
    比开发方案点名的 2 个文件多出 5 个，因为 `kernel/` 单文件上限是 500 行且本仓库模块
    约 45% 是 docstring；已回写技术方案 §4.2 的目录树。
  - **schema 手写而不用 pydantic**（与技术方案 §6.7 字面表述不同，取其意不取其形：
    `extra="forbid"` 与 JSON Pointer 两条规范要求照做）。**先写了 pydantic 版再实测改掉**：
    `import kernel.config` 从 313 ms 降到 110 ms、进程内模块数从 250 降到 138，而
    `NFR-405` 给整个冷启动的预算是 300 ms，配置加载在启动第 2 步、永远在必经路径上
    （`sdk/manifest.py` 用 pydantic 无妨——只在真要发现插件时才付这笔钱）。
    另两条与耗时无关的理由：`CFG-005` 要求默认值层也带来源，这就要求默认值物化成 dict，
    合并与来源追踪因此已在 `merge.py` 里自己写了；pydantic 的 `loc` 仍要自己转 RFC 6901，
    而 `sdk/manifest.py::_format_location` 产出点分路径且 `R2` 禁止 import。
    守卫是 `test_loading_config_does_not_import_pydantic`（子进程查 `sys.modules`）。
  - **默认值是一层，不是「查不到来源」的兜底**：`collect_layers()` 返回**四**层
    （`default < config.json < env < cli`）。只有默认值也是一层，`CFG-005` 的「每个生效值
    可追溯来源」才对所有字段成立——否则「取自默认值」与「来源索引漏了它」在数据上不可区分。
    `test_every_known_field_has_an_origin` 遍历 `SECTION_SPECS` 断言这件事。
  - **turn 引擎不得被拖上配置路径**：`schema.py` 重写六个默认值字面量、`to_limits()` 用
    函数内 import。`import kernel.turn.limits` 会执行 `kernel/turn/__init__.py`，把
    engine / scheduling / folding 与 asyncio 一起拉进来，而 `nm config show` 只要六个整数。
    代价是两张默认值表，由 `test_turn_defaults_match_the_limits_module` 与
    `test_default_limits_round_trip_through_turn_limits` 钉住。**这条是测试先发现、
    再改实现的**：最初直接 import 那些常量，守卫测试立刻报 LEAKED。
  - **`os.kill(pid, 0)` 在 Windows 上会杀掉目标进程**（CPython 把非 CTRL 信号映射到
    `TerminateProcess`），因此 `process.py` 分平台实现：Windows 用
    `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetExitCodeProcess`，
    `WinDLL(use_last_error=True)` 且**显式声明 `argtypes`/`restype`**（不声明会让 HANDLE
    在 Win64 上被截成 32 位 → 句柄泄漏 + 对垃圾值 `CloseHandle`）；POSIX 用信号 0，
    `EPERM` 视为存活。`pid <= 0` 在任何 syscall **之前**拒绝（`os.kill(0, 0)` 打的是整个
    进程组）。回归测试：`test_probing_a_live_process_does_not_kill_it`、
    `test_non_positive_pids_never_reach_a_syscall`。
  - **`Liveness` 是三态**（ALIVE / DEAD / UNKNOWN），`UNKNOWN` 绝不授权回收锁：塌成 bool
    就是替调用方在「永久砖掉实例」和「两个进程同时写同一份会话」之间选一个。
  - **锁的占用者七行分类表**在 `lock.py` 的 `_reclaim_or_fail`：不可解析 / 跨主机 /
    同 PID / DEAD / PID 复用 / ALIVE / UNKNOWN 各有结论。把**不可解析**当陈旧是刻意的
    ——它给不出 PID 也给不出恢复路径，一次「create 与 write 之间崩溃」就会永久砖掉实例；
    窗口只有微秒（create 后立即 fsync），且回收记进 `StaleLockReclaimed`。
    fd 保持打开到 `release()`：Windows 的 `_SH_DENYNO` 共享读写但**不共享删除**，
    别的进程算错陈旧性也删不掉活锁，只会拿到 `PermissionError`，`_reclaim` 把它降级成
    「持有者存活 → 拒绝」；同时第二个进程仍能**读**锁文件，`EDG-507` 才报得出 PID。
  - **补了一个 `ErrorCode`**：`CONFIG_INSTANCE_LOCKED`（→ `CONFIG` 类）。复用
    `CONFIG_INVALID` 会让「另一个实例正在运行」与「你的配置拼错了」不可区分，而两者的
    补救完全不同，且 `EDG-507`/`DST-005` 需要一个稳定码来单独断言。
  - 验收：`tests/architecture` + `contracts` + `sdk` + `kernel` + `baseline` 共
    **928 个用例全绿**（`D09` 收口时 822）；`ruff check`、`basedpyright`（新层 0 报错，
    legacy 仍是既有 4 个）、`legacy_debt --check` 未变、`check_startup_cost --check` OK。
    `kernel/config/` 语句覆盖率 **90%**——未达 `registry/`、`turn/` 的 100%，缺口全部是
    平台分支与防御性 IO 异常路径（`process.py` 的 POSIX 分支在 Windows 上不可能执行，
    反之亦然，需要两条 CI 腿才能合并覆盖；`lock.py` 里 `os.close`/`unlink` 的
    `except OSError` 兜底）。**如实记录，不是「约等于 100%」。**
- **`D11` Secret 与凭据**（`kernel/config/secrets.py` 约 300 行 +
  `tests/kernel/test_secrets.py` 43 个用例，另补 4 个契约测试）：
  - **`SecretStr` 从 `sdk/api.py` 下沉到 `contracts/errors.py`**，这是本模块唯一一处动
    已冻结表面的改动。技术方案 §7.5 原来的理由（「只出现在 `PluginContext.secret()` 的
    返回位置」）被 `D11` 推翻：`${VAR}` 的解析结果在 `kernel/config/` 里产生，而 `R2`
    禁止 `kernel/` import `sdk/`——与 `D05` 把 `CliEntry` 下沉是同一条理由。落在
    `errors.py` 是因为 `MASK`、`redact()` 与它是同一件事的三个面：`redact()` 现在认得
    `SecretStr`，明文因此进入 `scrub()` 的密文集合，**被顺手拼进 `user_message` 的凭据
    也擦得掉**。`sdk.__all__` 相应少一个名字（契约类型不从 `sdk` 转发），
    `tests/sdk/test_public_surface.py` 的规范性快照同步更新。
  - **顺带修掉一个真实泄漏面**：原实现是 `@dataclass(frozen=True, slots=True)`，
    `dataclasses.asdict()` 会把 `_value` 明文抖出来，且对任何**包含**它的 dataclass 递归
    时同样中招——一条绕过 `__repr__` 的泄漏路径。改为普通不可变类（`__slots__` + 拒绝
    `__setattr__` + `__deepcopy__` 返回自身）后 `asdict()` 对它不透明；并补 `__format__`，
    让 `f"{secret:>20}"` 也只得到掩码。`json.dumps` 仍然抛 `TypeError`——**大声失败**比
    静默掩码正确：密钥被送进序列化说明调用方本来就打算写到某处。
  - **明文不进配置文档**（`CFG-003` 的结构性保证）：`resolve_secrets()` 不返回替换过的
    文档，而是返回按 JSON Pointer 索引的 `SecretMap`（`refs` / `values` / `variables`）。
    配置树自始至终持有 `${VAR}` 字面量，于是「写回保留字面量」不是一条要人记得遵守的
    流程，而是**没有别的东西可写**。`prepare_for_write()` 是补充闸门，防「有人
    `reveal()` 之后把明文塞回文档」：按位置、再按明文反查换回字面量，换不回去就抛
    `KERNEL_INVARIANT_VIOLATED`。按明文反查有 `MIN_SCRUB_LENGTH` 阈值（短值与用户随手
    写的 `"1234"` 无法区分），按**位置**恢复不受此限——那条不需要猜。
  - **语义边界**：任何位置的引用都算密钥（整串或内嵌 `"Bearer ${TOKEN}"`），一种机制
    一种含义；没有 `${VAR:-默认值}` 回退、不支持 `$${VAR}` 转义；**定义为空的变量按缺失
    处理**（`reason: unset|empty`，两者都不含值）。缺失一次报全，与 `validate_config()`
    同构。
  - **不接进 `load_config()`**：`SECTION_SPECS` 目前没有 secret 字段，而 `SecretStr` 不是
    `JsonValue`，塞进合并后的文档会让 `validate_config()` 无从校验。接线在 `D19`
    （provider 凭据）与 `D26`（`ctx.secret()`）。
  - 验收：`tests/architecture` + `contracts` + `sdk` + `kernel` + `baseline` 共
    **990 个用例全绿**（`D10` 收口时 928）；`ruff check`、`basedpyright`（新层 0 报错，
    legacy 仍是既有 4 个）、`legacy_debt --check` 未变、`check_startup_cost --check` OK。
    `secrets.py` 语句覆盖率 **100%**。完整套件（含 `tests/legacy`）14 failed /
    5798 passed / 30 skipped，失败全部落在既有的那批网络与子进程时序用例上。
- **`D12` 可观测性**（`kernel/observability/` 5 个文件，约 820 行 +
  `tests/kernel/test_{redaction,bus,sinks,diagnostics}.py` 58 个用例，另补 2 个契约测试）：
  - **比开发方案多一个 `sinks.py`**（4 个模块而非 3 个）。理由与 `D10` 同：`kernel/`
    单文件上限 500 行，而本仓库模块约 45% 是 docstring；更要紧的是**把两个 sink 塞进
    `bus.py` 会毁掉本模块要立的那条规矩**——sink 与 bus 同文件，读代码的人第一反应就是
    bus 拥有 sink，而 `OBS-005` 要的恰恰是「Bus 不认识任何具体消费者」。已回写技术方案
    §4.2 的目录树。包内依赖单向：`bus`/`sinks` 用 `redaction`，`diagnostics` 用 `sinks`。
  - **`publish()` 同步、绝不抛出、绝不 await 订阅者**。三条理由：`NFR-204` 要求观察者
    故障不中断 turn，而 bus 一旦 await 订阅者，一个慢订阅者就直接拉长 turn，那条要求在
    时间维度上已经不成立；publish 会在**没有事件循环**的路径上被调用（`instance.starting`
    在启动第 1 步、`nm config show`、绝大多数测试），要求 bus 有 loop 等于要求每条诊断
    路径先起一个 loop；asyncio 抢占不了同步回调，即便 bus 是 async 的，`wait_for` 对一个
    CPU 阻塞的订阅者也无能为力。异步消费者在回调里把事件塞进自己的有界队列。
  - **既然抢占不了，「超时隔离」就只能是测量 + 熔断**：超过 `slow_after_ms`（默认 50 ms）
    记一次 strike，抛异常也记一次，健康投递把连续计数清零；连续 strike 达到
    `max_strikes`（默认 5）即**自动退订**。一次性掉线比永久拖慢每一个 turn 诚实，
    而 `bus.health()` 让这件事查得到——退订者的健康快照也保留（有界 64 条，且只留快照
    不留 handler 引用），因为「事件没到 WebUI」最常见的原因就是它被熔断摘掉了，
    而摘掉的那一刻没人在看。捕 `Exception` 不捕 `BaseException`，与 engine 同一条理由。
  - **重入的 publish 入队而不是递归**：订阅者在回调里再 `publish()` 是合法的（sink 记录
    自身失败、诊断插件派生事件），朴素实现会递归扇出——深度不可控，且投递顺序变成后序
    遍历。序号在 `publish()` 里立刻分配（返回值总是完整的），扇出由最外层那次按序 flush，
    因此序号严格单调、投递顺序 == 发布顺序（`OBS-002`）。
  - **脱敏先于截断**。`prepare_payload()` = `contracts.errors.redact()` → 再按条数上界
    收敛。顺序不能反：先截断会把一个 40 字符的 `sk-…` 切成 20 字符的前缀，那既不再匹配
    已知令牌形状，又仍然是一段明文密钥。`redact()` 已经管了敏感键名、`SecretStr`、
    令牌形状、单串 512 字符与深度 6，本模块**不写第二份规则**，只补它没有的那一项：
    **条数上界**（映射 64 项 / 序列 128 项，溢出留计数标记）——一条带十万元素列表的事件
    在契约层是合法 JSON，却足以撑爆内存环与日志盘（`NFR-404`）。
  - **序列化与脱敏放同一个模块**（`event_to_json` / `error_to_json` 在 `redaction.py`）：
    脱敏的意义在于「离开进程的字节里没有密文」，而序列化正是那些字节的产生点，
    分开放，改了一边忘了另一边就是泄漏。`resolution.py` 里那个私有 `_error_json`
    刻意**不**复用本模块——让 `registry` import `observability` 只为省 10 行不划算。
  - **JSONL sink 不认识 `InstanceLayout`**：`JsonlFileSink(path_for_day)` 接一个
    `Callable[[date], Path]`，由 `D23` 传 `layout.events_log_path`，既不 import
    `kernel.config`，也不在这里第二次拼 `events-<date>.jsonl` 这个文件名。日期取自
    `event.occurred_at`，跨天自动换文件；**写失败不抛**，自己计数并留 `last_error`
    ——抛出去只会被 bus 的隔离层吞掉，counter 至少查得到。
  - **内存环的 `dropped` 是必需的**：诊断查不到某个 turn 时，「环里从来没有这条」与
    「它被挤出去了」是两个完全不同的结论，塌成「查不到」会让人去错的方向排查。
  - **补上了 `D10` 欠的 `EDG-501` 后半句**：`write_config_error(path, error)` 落盘到
    `layout.config_error_log_path(day)`。它刻意**不是** sink——配置解析失败发生在启动
    第 2 步，事件总线那时还没建起来，做成订阅者就等于把这条需求推回它无法成立的时序里。
    best-effort：失败返回 `False` 而不是抛出，在一条已经失败的启动路径上再抛一次只会
    把真正的原因盖掉。接线在 `D23`。
  - **`EventName` 补 `turn.stopped_by_limit`**（`D09` 留下的缺口，按 `NFR-104` 评审后
    新增）：用 `turn.completed` 承载会让「模型自己说完了」与「撞上预算上限被拦下」在事件
    流里不可区分，而 `EDG-304` 要求终态可区分。同时补了一张**以字面量写死的
    `EventName` 快照**——`D02` 说「冻结 30 个事件名」，但当时没有快照，`NFR-104` 的闸门
    实际是空的；现在是 31 个。
  - `diagnostics` 的数据源是**注入的 callable 而不是三个单方法 Protocol**（「少结构」）；
    `capabilities` 用 callable 是因为覆盖解析在启动期才产出，而诊断门面在此之前就装配好
    了。`PluginState` 的取值直接对应 `EventName` 的 plugin 族，**不发明第二套插件生命周期
    taxonomy**（那是 `D25`/`D27` 的事），有测试盯着这条。`plugins()` 默认返回空元组。
  - 验收：`tests/architecture` + `contracts` + `sdk` + `kernel` + `baseline` 共
    **1050 个用例全绿**（`D11` 收口时 990）；`kernel/observability/` 语句覆盖率 **100%**；
    慢订阅者用注入的假时钟制造、不用 `sleep`；哨兵扫描覆盖 JSONL 全文 + 内存环的
    `repr` / payload / error 四条渲染路径。`ruff check`、`basedpyright`（新层 0 报错，
    legacy 仍是既有 4 个）、`legacy_debt --check` 未变、`check_startup_cost --check` OK；
    新层 `Any` 数仍为 0。完整套件（含 `tests/legacy`）15 failed / 7209 passed /
    35 skipped，失败全部落在既有那批家族（已用 `git stash` 逐一确认与 `D12` 无关）。
- **`D13` 输入分流与 Session 并发**（`kernel/routing/` 4 个文件，约 870 行 +
  `tests/kernel/test_{dispatcher,session_lock,dedup}.py` 62 个用例，另补 4 个配置测试）：
  - **`dedup.py` 单独成模块**：技术方案 §4.2 的目录树里本来就有它（原拼作 `dedupe.py`，
    已统一为 `dedup.py`，与 `DedupCache` / `DEFAULT_DEDUP_*` 同形），只是开发方案的交付
    清单漏列。它不该并进 `session_lock.py`：去重是**准入判定**，与「谁能写这个 session」
    无关，合并只会让那个文件同时管两件不相干的事，还要顶着 `kernel/` 500 行上限。
    三个模块互不相识，编排层按 **去重 → 并发 → 分流** 的顺序各问一次（顺序写在
    `routing/__init__.py` 里）。顺序有讲究：**去重必须在最前面**，否则重投的消息会占掉
    队列名额、在 `MERGE` 下被并进下一批，`EDG-201` 随之失效。
  - **显式 FIFO 票据，不用 `asyncio.Lock`**。`Lock` 的唤醒顺序是 CPython 的实现细节而非
    文档保证，而 `EDG-202` 要断言的恰好是严格 FIFO；票据还让「队列多长」「谁在跑」变成可读
    状态（`waiting()` / `running_turn()`），`Lock` 的等待者是私有的。20 条并发消息的
    FIFO 断言与三种策略的用例**全程不用 `sleep`**，用 `asyncio.Event` 卡住第一个 `run`
    制造确定的重叠窗口。
  - **单写者不变量只有一段实现**：`run` 只在持有槽位时被调用，三种策略的差别**只在
    「拿不到槽位时怎么办」**。测试用 `concurrent_peak` 把它变成可观测量——它只要超过 1，
    历史写入的顺序性就无从谈起。`MERGE` 下被合并的提交方拿到那一批的返回值（失败时拿到
    同一个异常），调用方因此不需要为「我的消息去哪了」再维护一张映射表。
  - **命令名冲突在 `build_command_index()` 里判**（`CMD-002`）：registry 的 MULTI_UNIQUE
    只保证 `name` 在 kind 内唯一，**别名撞车它看不见**——两个插件各自注册
    `status`/`st` 与 `statistics`/`st`，注册阶段一路绿灯，到调用期才由加载顺序择一。
    别名与命令名在同一个命名空间里判定。
  - **dispatcher 不发任何事件、不分配 `turn_id`**。`KER-010`（命令即使不进模型也发 turn
    事件）整件事留给 `D14`：turn 事件只能有一个发布点，两个发布点会让命令类 turn 与模型类
    turn 的事件序列各有一套口径，`OBS-002` 的按序重放随之作废。`Correlation` 由 `D14` 带着
    已分配的 `turn_id` 传进来。
  - **命令 handler 的异常只捕 `Exception`**（`CMD-003`）：`BaseException`（取消、Ctrl-C）
    放行，否则停机要按两次。折出来的错误**不放异常消息**只放类型名——第三方命令的异常
    文本可能带着凭据，有测试埋了 `token=sk-…` 哨兵。`NucleaError` 原样透传，实现方给的
    诊断比 Kernel 能编的更准。「会话仍可用」的可断言形态是：同一个 dispatcher 在命令炸掉
    之后，紧接着还能正常分流下一条命令与普通文本。
  - **新增 `ErrorCode.INPUT_SESSION_BUSY`**（INVALID_INPUT 类）。技术方案 §6.5 只说「返回
    `INVALID_INPUT` 类错误」，而那一类原有的三个码都表达不了「忙」。复用
    `INPUT_TOO_LARGE` 会让 `EDG-202` 的队列满与 `EDG-205` 的大文本在诊断里长得一模一样，
    而两者的补救动作完全不同（等一会儿 vs 把消息改短）。先例是 `D10` 的
    `CONFIG_INSTANCE_LOCKED`。
  - **配置多了 `routing` 小节**（`command_prefix` / `session_concurrency` / `queue_max_size`
    / `dedup_capacity` / `dedup_ttl_ms`），`FieldSpec` 相应加了 `choices`：取值受限的字段
    必须在**校验时**就带指针报错，否则错误推迟到构造调度器那一刻，那时既没有指针也没有
    「你可以写哪几个」。加完 `schema.py` 到 504 行、超了 `kernel/` 的 500 行上限，于是把
    校验积木（`FieldKind` / `FieldSpec` / `coerce_value` / `suggest`）拆到
    `kernel/config/fields.py`——分界线是**认不认识具体字段**：`fields.py` 一个字段名都不
    认识，`schema.py` 除了字段什么都不放。字段表在长，校验积木不该跟着长。
  - 验收：`tests/architecture` + `contracts` + `sdk` + `kernel` + `baseline` 共
    **1116 个用例全绿**（`D12` 收口时 1050）；`kernel/routing/` 语句覆盖率 **97%**。
    `ruff check`、`basedpyright`（新层 0 报错）、`legacy_debt --check` 未变、
    `check_startup_cost --check` OK；`kernel.routing` 已加进「配置加载不得拖上 turn 引擎」
    那条子进程测试的泄漏名单。完整套件（含 `tests/legacy`）14 failed / 5924 passed /
    30 skipped，失败全部落在既有那批网络与子进程时序家族。
    ⚠️ 跑测试时 **`--basetemp` 不要指到仓库内**：`tests/legacy` 的 36 个 git-store 用例会
    因为临时目录落在工作树里而误判失败。本机系统临时目录有 ACL 问题，用
    `--basetemp=D:/tmp/...` 之类的仓库外路径。
- **`D14` Turn Orchestrator**（`kernel/turn/` 新增 6 个文件，约 1750 行 +
  `tests/kernel/test_{hooks,context_builder,invoker,orchestrator}.py` 与
  `_orchestrator_support.py` 共 94 个用例，另补 1 个配置测试）：
  - **交付六个模块而不是开发方案点名的两个**。`orchestrator.py` 的 ≤500 行是技术方案 §6.2
    写死的硬约束（实测 497 行），而 §10.2 那 14 步里有四件事各自成体系：Hook 归并
    （`hooks.py`）、context 组装（`context_builder.py`，§4.2 目录树本来就有它）、工具执行
    （`invoker.py`）、引擎事件到事件名/终态的翻译（`translation.py`）。另两个是编排自己的
    切分：`orchestration.py` 装配面与产物（`D23` 的 wiring 只需要它，用不到流程）、
    `transcript.py` 记录与账本。已回写技术方案 §4.2 的目录树。
  - **turn 事件的唯一发布点在这里**（`KER-010`、`OBS-002`）。翻译表以字面量写死在
    `translation.py`：`SKIPPED`（取消时未轮到）与 `BLOCKED`（Hook 拦下）都归
    `tool.call_blocked`——它们的共同事实是**没有执行**，而 `tool.call_failed` 说的是
    「执行了但没成」，冻结的 4 个 tool 事件名里没有第三种表达。`model.request_started` 由
    `orchestration.EventTap` 在 `before_model_request` 分发时补上：那是编排层唯一能观察到
    「又要发一次请求」的时刻，而 engine 每轮自己分发这个 Hook，**`D14` 没有再分发一次**
    （有一条 `分发次数 == 迭代数` 的测试盯着）。
  - **准入顺序 去重 → 并发 → 分流 让 §10.2 的步骤 2/3 对调**：`turn_id` 分配与去重在
    `turn.started` **之前**，而 `turn.started` 在拿到 session 槽位**之后**。重复投递或被
    队列拒绝的消息只发一条 `turn.rejected`——给它一个 `turn.started` 就会在事件流里留下
    一个永远等不到终态的 turn。已回写 §10.2。
  - **`MERGE` 下整批归一个 turn**：被吸收的消息不产生自己的事件流，只在执行 turn 的
    `turn.started` 载荷里留 `merged_from`；提交方拿到的 `TurnReceipt` 就是执行 turn 的
    那一份，「我的消息去哪了」不需要第二张映射表。**分流对整批逐条做**——`MERGE` 下第二条
    消息也可能是命令，只看第一条会让它静默变成模型输入。
  - **检查点 4 的取消必须翻成 `CANCELLED` 而不是 `FAILED`**（`translation.outcome_for_error`
    按 `ErrorCategory` 分类）。这是测试先发现、再改实现的一条：检查点 1/4 由 orchestrator
    自己抛，异常从 engine 之外逸出，最初被那个兜底的 `except Exception` 一律记成 `FAILED`，
    而 `EDG-304` 要求四个终态可区分。
  - **被打断的半句必须落库**（同样是测试先发现的）。`TurnState.pending` 与 `text` 分开：
    每轮响应完整时 `pending` 清零（那一轮的正文已由 `ModelResponseCompleted.response`
    权威记过一次），剩下的就是「最后一次完整响应之后又流出来的内容」，取消时以
    `interrupted=True` 写入。合成一个列表就会在正常轮次重复写入 assistant 消息。
  - **持久化的三条基线决定逐条落地**（`transcript.py`）：空 assistant 不入历史、孤儿 tool
    结果丢弃、工具内容在持久化边界**再截断一次**（历史是长期资产，配置调小之后旧记录仍按
    旧上限躺在文件里）。**与旧实现的一处差异**：assistant 的 `tool_calls` 不进
    `SessionMessage`（契约没有这个字段），因此工具往返保真写入、但
    `replay_messages()` 重放时跳过 `role=TOOL`——一条没有调用声明的 tool 消息会让下一次
    请求在 Provider 侧直接被拒。
  - **`trust=SYSTEM` 是进入系统指令位置的唯一凭据**，`kind` 不参与判定：一个
    `kind=SYSTEM` 但 `trust=UNTRUSTED` 的片段（「从检索结果里捞到的系统提示」）只能落进
    数据块。包裹仍由契约层的 `as_model_text()` 完成，组装器没有拼字符串的绕行路径
    （`CMD-005`、`EDG-306`）。`sensitivity=SECRET` 与过期片段丢弃并记进 `dropped`——
    「它去哪了」必须查得到。
  - **裁剪的丢弃顺序**：`priority` 逆序；同优先级内先丢片段、再丢历史（从最旧）。
    `HISTORY_TRIM_PRIORITY = 0` 与「契约保证 `priority >= 0`」两条合起来意味着片段总是
    先走——片段下一轮还能重新产出，历史丢了就是丢了。**裁到只剩系统段与当前输入仍超预算
    时抛 `INPUT_TOO_LARGE`**：压缩（`SessionStore.compact`）本轮不实现，把「压不下去」
    伪装成「压缩了」会让用户拿到一个悄悄缺了半截历史的回答。
  - **`jsonschema` 成为直接依赖**（`pyproject.toml`，此前只是 `mcp` 的传递依赖）。它没有
    `py.typed`，因此在 `invoker._compile()` 一处收口：两个只声明「我们真正读的字段」的
    Protocol + 一次有运行时检查支撑的 `cast`（`AGENTS.md` 原则 6）。**惰性 import**，
    理由与 `config/schema.py::to_limits` 相同。`check_schema()` 必须显式调用——不调用的话
    写错的 schema 要等到校验参数时才炸，异常从 `iter_errors` 逸出，「约定不抛」当场失效。
  - **补了两个 `ErrorCode`**：`TIMEOUT_TOOL_CANCEL`（→ `TIMEOUT` 类，`D08` 点名要补的那个；
    与 `TIMEOUT_TOOL_CALL` 分开是因为「宽限期到了它还没回来」意味着副作用未知 + 已登记
    孤儿，而后者是一次有结论的调用）与 `PERMISSION_TURN_REJECTED`（→ `PERMISSION_DENIED`
    类，`turn_start` 拦截器 `REJECT` 的落点；复用 `PLUGIN_HOOK_FAILED` 会把「插件按策略
    挡下了这次 turn」记成「插件坏了」）。
  - **配置多了 `hooks` 与 `context` 两个小节**（`observer_timeout_ms` 2000 /
    `interceptor_timeout_ms` 5000 / `provider_timeout_ms` 3000）。**`tool_cancel_grace_ms`
    刻意不做成配置项**：它在 `cancel.py` 里是取消参数而不是六项预算之一，塞进 `turn` 小节
    会破坏「`TurnSection` 字段名 == `LimitKind` 取值」这条已被测试钉死的对应关系。
  - 验收：`tests/architecture` + `contracts` + `sdk` + `kernel` + `baseline` 共
    **1210 个用例全绿**（`D13` 收口时 1116）；`kernel/turn/` 语句覆盖率 **99%**
    （未覆盖的 10 行全是防御性分支：`jsonschema` 交回怪东西、`utc_now` 的真实墙钟、
    `mark_interrupted` 的空历史路径）。并发一律用 `asyncio.Barrier` / `asyncio.Event`
    制造确定的重叠窗口，**全程不用 `sleep`**。`ruff check`、`basedpyright`（新层 0 报错，
    legacy 仍是既有 4 个）、`legacy_debt --check` 未变、`check_startup_cost --check` OK。
    完整套件 14 failed / 7370 passed / 35 skipped，失败全部落在既有那批网络、子进程时序与
    oauth-cli-kit 家族。
- **`D15` 骨架集成验收**（`tests/integration/` 4 个文件，约 750 行 / 28 个用例，
  `src/` 一行未改）：
  - **Fake 只出现在能力边界上**（模型、会话存储、工具、Context Provider、命令 handler），
    能力**之间**的一切是生产实现：`CapabilityRegistry` + `resolve_into()`、`HookRouter`、
    `ToolExecutor`、`Dispatcher`、`SessionScheduler`、`DedupCache`、`EventBus` +
    `MemoryRingSink`、`TurnOrchestrator`。这条线不是风格偏好——`tests/kernel/` 在 kernel
    边界上也放 Fake（单测该那么做），集成测试若跟着做，两层测的就是同一件事，而「装配链
    本身装不起来」恰好落在两者之间。已回写技术方案 §12.3。
  - **能力一律经 `RegistrationBatch` 注册、再由 `*_from(registry)` 取回**，而不是把列表
    直接塞进 `OrchestratorDeps`：`D14` 定死的四个注册载荷形状只有走这条路才会被真正核对，
    而那正是 `D16` 的 Host 将要走的路。
  - **`D15` 暴露的一个真实缺口**（已回写技术方案 §6.1）：`MODEL` / `SESSION_STORE` /
    `CHANNEL` / `MEMORY` / `CLI_ENTRY` 五个 kind **既没有取回函数、也没有定下注册载荷
    形状**，骨架因此只能把 `ModelProvider` 与 `SessionStore` 直接注入 `OrchestratorDeps`。
    这不是 `D14` 的疏漏（那五个都不归 `kernel/turn/`），是 `D16`/`D23` 必须先补的一步：
    **载荷形状要在建立注册分派的同一处定下**，留到装配时各自 `isinstance` 一遍，就等于把
    「谁定义形状」分散到每个消费点上。
  - **「不触碰真实网络」是一条 autouse 夹具而不是一句承诺**（`conftest.py`）：拦
    `socket.connect` / `connect_ex` / `getaddrinfo` 的**目标**，回环放行。刻意**不**拦
    `socket.socket` 的构造——Windows 的 `ProactorEventLoop` 用 `socketpair()` 做 self-pipe，
    拦构造只会证明事件循环起不来。夹具自身有一条自证用例（探针连 `example.com` 必须被拦）。
  - **一次含工具调用的 turn 的事件名序列以字面量写死**（9 条，`turn.started` →
    `session.started` → 两轮 `model.request_started` / `model.response_received` +
    `tool.call_started` / `tool.call_completed` → `turn.completed`），另有序号连续无缺口、
    `by_turn()` 覆盖全部事件、以及 `event_to_json` → `json.dumps/loads` 往返三条断言——
    「可重放」的可执行形态。7 个 Hook 的跨 turn 触发顺序同样以字面量写死，并当场断言
    「`before_model_request` 分发次数 == 迭代数 == `model.request_started` 条数」。
  - **中断路径**：取消发生在工具阶段时，已执行工具保留真实结果、未执行的发
    `tool.call_blocked` 且 `side_effect=NONE`、终态 `CANCELLED` 且 `cancel_reason=USER`、
    已产生的 assistant 正文落库并 `interrupted=True`、同一 session 的下一条消息照常跑完
    并看得见上一轮历史。**一处值得记下的事实**：被跳过的工具**也会**留下一条 tool 记录
    ——模型声明过的每次调用都必须有对应的 tool 消息，缺一条会让续写请求在 Provider 侧被拒。
  - **写这批用例时踩到的两个坑**（都是「测试写错了」而不是实现有问题，但下一个人会再踩）：
    ① 两个工具同轮返回时默认**并发**执行（`Concurrency.PARALLEL` 是 `ToolSpec` 的默认值），
    要制造「未执行的工具」必须显式给第二个工具 `EXCLUSIVE` 让它单独成批；
    ② `TrustLevel` 的四个取值是 `SYSTEM`/`OPERATOR`/`USER`/`UNTRUSTED`，没有 `TRUSTED`。
  - 验收：`tests/architecture` + `contracts` + `sdk` + `kernel` + `baseline` +
    `integration` 共 **1238 个用例全绿**（`D14` 收口时 1210）；`tests/integration` 单跑
    **0.67 s**（预算 5 s），且有一条单 turn ≤1 s 的墙钟断言。并发一律用 `asyncio.Event`
    制造确定的重叠窗口，**全程不用 `sleep`**。`ruff check`、`legacy_debt --check` 未变、
    `check_startup_cost --check` OK。CI 门禁第 4 步已加上 `tests/integration`
    （技术方案 §12.4；CI 实际跑的是裸 `pytest`，`testpaths` 已覆盖）。

- **`D16` 内建加载路径与契约测试套件**（`kernel/plugins/` 4 个文件约 830 行 +
  `builtins/registry.py` + `runtime/wiring.py` + `sdk/testing/capabilities.py`，
  外加 `tests/kernel/test_{host,plugin_capabilities,plugin_declarations,builtin_loader}.py`、
  `tests/runtime/`、`tests/sdk/test_contract_reverse_samples.py`、
  `tests/architecture/test_builtin_no_privilege.py`、`tests/integration/test_no_builtins.py`
  共 104 个新用例）：
  - **`NucleaAPI` / `PluginContext` 没有下沉 `contracts/`**，`CapabilityHost` 是它们的
    **结构化**实现（仓库先例：`HookRouter`「结构化满足 `deps.HookDispatcher`」）。与 `D05`
    下沉 `CliEntry`、`D11` 下沉 `SecretStr` 不同——那两个是 kernel **要调用**的类型，而
    Host 只是**持有并转交** ctx、自己一个成员都不碰。ctx 因此做成泛型参数
    `CapabilityHost[ContextT]`：kernel 对它连一个结构假设都不做。
    **标成 `object` 是行不通的**（试过）：那样 `ctx` 的返回类型与 `NucleaAPI.ctx` 声明的
    `PluginContext` 不兼容，一致性就在任何地方都证明不了。
  - **一致性的证明落在 `runtime/wiring.py` 的一句类型标注上**
    （`conformance: NucleaAPI = host`）。理由是硬的：`pyproject.toml` 的 basedpyright 配置是
    `exclude = ["**/tests"]`，测试**验不了**签名兼容；而 `contracts/protocols.py` 写死了
    `runtime_checkable` 只作诊断、永不参与控制流，`isinstance` 同样证明不了。`runtime/` 是
    唯一同时看得见 kernel 与 sdk、又在严格检查范围内的层。证明**放在生产路径上**
    （`load_into(host_for=...)` 真的会调它），不是一个只为证明而存在、随时会被当成死代码
    删掉的函数——`tests/runtime/test_wiring.py` 另有一条 AST 断言盯着「那句标注还在、
    且没被改成 `cast`」。
  - **五个缺口 kind 一律包一层 dataclass**（`RegisteredModelProvider` /
    `RegisteredSessionStore` / `RegisteredChannel` / `RegisteredMemoryProvider` /
    `RegisteredCliEntry`），哪怕字段只有一个。这不是形式主义：取回函数要把
    `payload: object` 窄化，而 Protocol 的 `isinstance` 既被契约层禁止用于控制流、
    本身也只看方法名——`test_a_bare_implementation_object_is_not_an_acceptable_payload`
    就是拿 `FakeModelProvider` 证明裸实现能蒙混过关的。五个 binding 共用一个泛型
    `CapabilityBinding[T]`（它们的元数据完全相同，五份同构 dataclass 只会让「改一处忘四处」
    有五倍机会），与 `HookBinding` / `ContextProviderBinding` 各自独立并不矛盾——那两个
    各有独有字段。**两个 SINGLETON 的取回函数返回 `| None`**：`BUILTIN_MANIFESTS` 是空元组，
    非可选会让每条装配路径当场炸掉；`EDG-108` 的「CLI 入口必须存在」是 `D23` 的判定。
  - **`builtin_loader.py` 读不到 `BUILTIN_MANIFESTS`，这是刻意的**（与开发方案
    「静态内建清单 bootstrap」的字面表述有出入，已回写技术方案）：`R2` 只允许 `kernel/`
    import `contracts` 与 `kernel`，而 `PluginManifest` 在 `sdk/`、`BUILTIN_MANIFESTS` 在
    `builtins/`，两个都够不着。于是它做成**对 `LoadRequest` 泛化的 setup 运行器**，
    manifest 的翻译留给 `runtime/wiring.py`。好处不止是绕开规则：`D27` 的外部 loader 因此是
    它的同级调用方而不是第二份实现，`SDK-007` 才真正成立。
  - **两个 `priority` 默认值与内建基准 0 打架，各修一处**。① `CapabilityDecl.priority` 的
    默认值是 100（技术方案 §7.2），照搬会让每一项内建能力都落在 100，而 §6.1 规则 1 定的
    内建基准是 **0**——`to_declaration()` 用 pydantic 的 `model_fields_set` 判断作者**是否真的
    写过**这个字段，没写就留 `None` 交给 `base_priority_for()`。② `NucleaAPI.on()` 的签名默认值
    同样是 100，调用侧分不清「写了 100」和「什么都没写」，Host 因此把「等于
    `PLUGIN_BASE_PRIORITY`」一律视为未声明。**两条都不修的话，§10.2 的「内建最后被裁」与
    §6.1 的「内建排在插件前」会同时静默失效，且不报任何错。** 有
    `test_on_default_priority_equals_the_plugin_baseline` 用 `inspect.signature` 把 SDK 那个
    默认值钉住。
  - **未声明的注册与声明了却没注册都是 `PLUGIN_LOAD_FAILED`**，靠 `detail` 区分。放行前者
    等于让 manifest 的 `capabilities` 变成没有约束力的文档，而 `overrides` 只能从那里来
    （`EDG-102`）；放行后者则会让用户看到一项查得到却不存在的能力。**没有新增错误码**——
    `PLUGIN_REGISTRATION_CONFLICT` 是「两个提供方抢一个槽位」，与这两件事在诊断里必须可分；
    `PLUGIN_MANIFEST_UNSUPPORTED` 属 `INCOMPATIBLE` 类，会误导用户去升级 SDK。
  - **HOOK 的能力名由 `hook` 派生**：`on()` 没有 name 形参而 registry 需要一个。同一提供方
    对同一 Hook 绑第二个 handler 是合法的（HOOK 是 MULTI），但批次内 `(kind, name)` 必须唯一，
    因此第二次起用 `<hook>.2`；**声明表始终按基名回查**，N 次注册共享同一条声明。
  - **`tests/integration/_support.py` 已改用生产 Host**（README 点名的「不要留两套注册路径」）。
    改完暴露出一条**真实语义差异**：`critical` 在 manifest 里是**提供方级**字段，Host 因此把
    同一个值灌给自己注册的每一项，而 `D15` 手写 `batch.add` 时是逐项指定的。修法是按
    `critical` 把能力分成两批、各开一个 Host，**两批共用 `Builtin()`**（`ProviderId` 与
    priority 基准完全不变）——既保住各用例原有语义，也如实反映「关键性是插件的属性，不是
    单个能力的属性」。`test_skeleton_turn.py` 那 9 条事件名序列与 7 个 Hook 顺序**一字未改
    地通过了**，那正是这次改接想要的结论。
  - **`sdk.testing` 补了五类参考实现**：`EchoTool` + `ECHO_SPEC` / `NullChannel` /
    `StaticContextProvider` / `FakeMemoryProvider` / `FakeCliEntry` / `FakePluginContext` /
    `RecordingEventSubscriber`，放在新的 `sdk/testing/capabilities.py`（`fakes.py` 已 276 行，
    且两者定位不同：那边是**可编脚本的测试替身**，这边是**参考实现**）。`ToolContract` 与
    `ChannelContract` 自 `D05` 发布至今没有任何随 SDK 发布的样例，`D15` 与 `tests/sdk/` 因此
    各自私下写了一份——`D16` 把第三份的需求消掉了。**`FakePluginContext` 的权限语义是真的**：
    四个访问器未授予时**属性访问**就抛 `PERMISSION_DENIED`，`secret()` 区分
    `PERMISSION_DENIED` 与 `CONFIG_SECRET_MISSING`，给 `D26` 留一个行为基准。
  - **5 个契约基类各配了一个「故意不合规」的反向样例**（`test_contract_reverse_samples.py`，
    `ModelProviderContract` 的那个 `D05` 已有）。开发方案把「契约基类的用例质量」列为本模块
    的真实风险，而**一个不会失败的契约基类比没有契约基类更危险**——它给的是虚假的可替换性
    保证。四个违约实现都不是臆造的：空会话抛错、坏参数抛异常而不返回失败结果、
    `stop()` 不幂等，都是实现方最常见的偷懒方式。
  - **与开发方案交付清单的两处偏差**：① `test_kernel_runs_without_builtins.py` 改放
    `tests/integration/test_no_builtins.py`——它必须真的跑一次 turn，而
    `tests/architecture/` 的既定职责是「只做 AST 与文本读取、不导入被测模块」
    （由 `test_guard_integrity.py` 守着）；② `kernel/plugins/` 交付 4 个模块而不是 2 个
    （`declarations` / `capabilities` / `host` / `builtin_loader`），理由与 `D10`、`D12` 同：
    `kernel/` 单文件上限 500 行。
  - `test_builtin_no_privilege.py` 除了复用 `R4` 的依赖判定，另加一条**符号扫描**：
    `builtins/` 不得**提到** `RegistrationBatch` / `CapabilityRegistry` / `CapabilityHost` /
    `resolve_into`。理由是 `R4` 拦得住 import，却拦不住「在 `builtins/` 里写一套内建专用的
    注册辅助函数」——那不违反任何依赖规则。
  - 验收：`tests/architecture`(60) + `contracts` + `sdk`(134) + `kernel` + `baseline` +
    `integration`(32) + `runtime`(11) 共 **1342 个用例全绿**（`D15` 收口时 1238）；
    `kernel/plugins/` 语句覆盖率 **100%**。`ruff check`（src + plugins + tests）、
    `basedpyright`（新层 0 报错）、`legacy_debt --check` 未变、`check_startup_cost --check` OK
    （`import nucleamind` 仍只拉入 1 个模块，`wiring` 没有被急切导入）；新层 `Any` 数仍为 0。
    完整 `tests/legacy` 14 failed / 4808 passed / 30 skipped，失败全部落在既有那批网络、
    子进程时序与 oauth-cli-kit 家族。

- **`D17` 内建 Session：`session_jsonl`**（`builtins/session_jsonl/` 三个模块约 480 行 +
  `builtins/registry.py` 的第一条 manifest + `docs/session-storage.md` +
  `tests/builtins/test_session_jsonl.py` 共 70 个用例）：
  - **整批原子性由 `meta.json` 的 `committed_bytes` 承担**，这是本模块最关键的一个决定。
    `SessionStore.append()` 要求整批原子生效（`SES-002`），而 JSONL 是追加写的：不引入
    提交水位，就只有两条路——每次追加重写整个文件，或者承认「崩溃时可能留下半批」。
    水位把它变成两条规则：**读只认 `[0, committed_bytes)`；写先截断到水位、追加、`fsync`，
    最后才原子替换 `meta.json`**。于是崩在任何一步，下次读到的要么整批都在、要么整批都
    不在（`EDG-504`）。副作用是「半条记录」这种情况根本不需要单独处理——它按定义在水位
    之外。
  - **文件比水位短是错误，不是「就这些了」**。这条与上一条是一对：水位之外的字节不算数，
    但水位之内的字节必须都在。少了就说明文件被外部截断，此时返回一个短历史等于静默丢用户
    的上下文，所以抛 `PERSISTENCE_RECORD_CORRUPT`。`SessionStore.load()` 的异常约定
    （「不得返回空快照冒充没有历史」）在这里被认真对待了：整个 `codec.py` 只可能抛这一个码。
  - **压缩插入摘要而不是替换前缀，原始记录不物理删除**。契约要求 `load()` 之后
    `compacted_through == through` 且摘要出现在 `live_messages` 里——物理删除前缀会让这两条
    同时不成立（水位会指向不存在的记录）。与 `InMemorySessionStore` 的做法一致，因此 Fake
    与真实实现的语义可以互相对照。`SES-005` 的三条保留语义由此各有确定答案：压缩保留原文、
    删除物理不可撤销、**不做任何自动过期**。
  - **水位只能前进**：后退会让已被摘要覆盖的记录重新进入上下文，而摘要还留在原处，同一段
    历史被讲两遍。这是调用方的错，折成 `INPUT_MALFORMED` 而不是「尽力而为」。
  - **存储目录由 `ctx.config["dir"]` 交下来**。`R4` 禁止 `builtins/` import `kernel/`，
    而 `InstanceLayout.sessions_dir` 在 `kernel/config/`——内建能力**不可能**自己知道实例
    布局。因此目录走配置块（`CFG-002`：插件只看得见自己那一块），`D23` 装配时填
    `layout.sessions_dir`；没配时退回 `ctx.state_dir`。文件名（`<storage_id>.jsonl` /
    `<storage_id>.meta.json`）两边各写一份，由 `test_filenames_match_the_instance_layout`
    对照——两处都「自洽」而对不上时，`nm session` 会在一个空目录里找文件，没有别的测试会失败。
  - **不用 `ctx.fs`**：`FileAccess` 只有 `read_text` / `write_text` / `list_dir`，没有追加、
    `fsync` 与原子替换。manifest 里如实声明 `fs:read` / `fs:write`，实现直接用 `pathlib`——
    `sdk/api.py` 已经写明应用级权限的价值是「让越界意图可审计」而不是进程隔离，诚实声明比
    绕道更符合它。
  - **IO 全部经 `asyncio.to_thread`**：会话历史可以到几 MB，在事件循环里同步读写它会卡住同
    一实例的其他 turn。契约说 `load`/`append` 不接受取消，那是「不许中途放弃」，不是「可以
    阻塞事件循环」。
  - **`contracts` 补出口 `SESSION_SCHEMA_VERSION`**：它本来就在 `contracts/session.py` 的
    `__all__` 里，只是包根忘了转发。会话存储实现是它的第一个、也是主要的消费者。
  - **`tests/` 新增 `__init__.py`**：没有它，`tests/builtins/` 会被 pytest 当成顶层包
    `builtins`，而 `sys.modules` 里那个位置早被标准库占住，整个目录收集失败。加上之后各测试
    包变成 `tests.*` 的子包，相对导入不受影响。
  - **`D16` 的三条「`BUILTIN_MANIFESTS` 为空」断言按棘轮更新**：两条改成显式
    `wire_capabilities(manifests=())`（要测的是「零内建可装配」，不是「默认清单恰好是空的」），
    第三条改成对每一项内建断言 **manifest 里没写 `priority`**——内建基准是 0，写了就会被原样
    采纳，§10.2 的「内建最后被裁」会静默失效。
  - **格式文档 `docs/session-storage.md` 里的示例由测试直接解析**。`SES-006` 承诺的是外部
    实现能读懂这个格式，而外部实现读的是文档不是源码；文档漂移因此必须在这里失败，而不是在
    某个用户的迁移脚本里。字段清单常量（`RECORD_FIELDS` / `META_FIELDS`）同时钉住「写出去的
    键」与「文档里列出的键」。
  - 验收：`tests/builtins`(70) 全绿，`builtins/` 语句覆盖率 **99%**（未覆盖的 3 行是
    `_fsync_dir` 的 POSIX 分支，Windows 上 `os.open` 目录会被拒绝并按设计吞掉）；
    新层七个测试目录共 **1412 个用例全绿**（`D16` 收口时 1342）。`ruff check`、
    `basedpyright`（新层 0 报错）、`legacy_debt --check` 未变、`check_startup_cost --check` OK。

- **`D18` 内建 Context：`context_basic`**（`builtins/context_basic/` 三个模块约 405 行 +
  `builtins/registry.py` 的第二条 manifest + `tests/builtins/test_context_basic.py` 共 50 个
  用例 + `tests/architecture/` 的一条只读守卫）：
  - **它不贡献历史**。技术方案 §8.1 原文写的是「系统指令 + 历史 + 按 token 预算的尾部保留
    裁剪」，但 `D14` 之后历史重放（含 `EDG-305` 的投影规则）与从最旧丢起的裁剪都在
    `context_builder` 里。Provider 再贡献一份历史片段就是把同一段对话讲两遍，还绕过了投影
    规则。所以内建 Provider 的产出恰好是三类片段：**基线系统指令、运行时事实、运维配置的
    自定义指令**，「尾部保留裁剪」由组装器履行。§8.1 已回写这条细化。
  - **运维配置的 `instructions` 用 `TrustLevel.OPERATOR` 而不是 `SYSTEM`**（本轮唯一一处
    需要拍板的取舍）。契约对 OPERATOR 的定义就是「实例拥有者通过配置显式提供的内容，可信
    但不是系统本身」，把配置文本升为 SYSTEM 等于取消 `CMD-005` 的分级。**可观察后果**：
    自定义指令落在历史之后的一条 user 消息里，而不是 system 消息里；补偿是给它
    `priority=0`（与内建基准、`HISTORY_TRIM_PRIORITY` 同级），实际上最晚才被裁。
    只有基线指令与运行时事实是 `trust=SYSTEM`。`test_operator_instructions_stay_out_of_the_system_message`
    钉住这条——它走真的组装器，断言的是最终 `ModelMessage` 序列而不是片段字段。
  - **`kind` 与 `trust` 刻意不同步**：自定义指令片段是 `kind=SYSTEM` + `trust=OPERATOR`。
    种类说的是「它是一段指令」，位置由 `trust` 决定——这正是组装器规则 2 描述的那个组合，
    现在有了第一个真实样例。
  - **零权限、零 IO**。manifest 一条权限也不声明，模块连 `os` / `pathlib` 都不 import。
    新增的架构守卫 `test_read_only_builtins_have_no_syntactic_route_to_persistence` 按
    **「没有语法途径」**而不是「看起来没写盘」来断言（扫 import + 裸 `open`），另一条断言
    只读内建的 `permissions == ()`；两条都有反向注入样例。判据写成一张
    `_READ_ONLY_BUILTIN_PACKAGES` 表，`D20`/`D21` 那种确实要写盘的内建不进这张表。
  - **token 估算公式在 `builtins/` 与 `kernel/` 各写一份**（`R4` 逼的）。片段自报的
    `estimated_tokens` 与组装器裁剪时用的尺子必须同口径：自报偏小则请求真的超窗，偏大则
    白丢内容。`test_token_estimate_matches_the_kernel_trimmer` 逐字符对照两份实现，
    与 `kernel/config/schema.py` 重写六个默认值是同一种做法。
  - **基线系统指令里引用的是契约常量 `UNTRUSTED_DATA_PREFIX` 而不是复述那句话**。
    `EDG-306` 的数据块包裹只有在模型认得那个暗号时才有意义；用常量插值，改契约措辞时不会
    留下一段说着旧暗号的系统指令。（第一版测试在这里写错过：拿前缀出现与否当「有没有被包裹」
    的判据，会把这段刻意的引用误判成越界——判据应当是 `<untrusted-data` 标签。）
  - **配置在 `setup()` 时校验一次，不拖到第一次 turn**。本内建 `critical=True`，一份写错的
    配置应当让实例启动失败。`instructions` 同时接受字符串与字符串数组（JSON 里写多行提示词
    只有这两种写法，「写法合法但被静默忽略」是本项目一贯拒绝的失败）；`1` 不是 `True`，
    布尔项收到非布尔一律 `CONFIG_INVALID`；「关掉基线又不给自定义指令」也是 `CONFIG_INVALID`
    ——那等于要一个没有任何系统指令的 Agent，正规做法是在 `plugins.disable` 里禁用本内建。
  - **`provide()` 约定不抛、也不检查 `cancel`**。契约要求的是「每个**外部查询**前检查」，
    而这个实现一次外部往返也没有；加一个必然为假的检查点只会让人以为这里有阻塞操作。
    `critical=True` 敢这么设，正是因为它没有可失败的外部依赖。
  - 验收：`tests/builtins`(120) 全绿，`builtins/context_basic/` 语句覆盖率 **100%**；
    新层七个测试目录共 **1471 个用例全绿**（`D17` 收口时 1412）。`ruff check`、
    `basedpyright`（新层 0 报错）、`legacy_debt --check` 未变、`check_startup_cost --check` OK。

- **`D19` 内建 Model：`model_openai`**（`builtins/model_openai/` 五个模块约 1170 行 +
  `builtins/registry.py` 的第三条 manifest + `tests/builtins/test_model_openai.py` 与
  `tests/builtins/conftest.py` 共 120 个用例）：
  - **凭据走 `ctx.secret("api_key")`，不走 `resolve_text()`**（本轮第一处需要拍板的取舍）。
    `D11` 的遗留笔记写的是「provider 凭据用 `resolve_text()` 解单个字段」，但那个函数在
    `kernel/config/secrets.py`，`R4` 禁止 `builtins/` import `kernel/`——按字面已不可执行。
    改走 SDK 认可的通道：manifest 声明 `PermissionDecl(kind=SECRET, target="api_key")`，实现调
    `ctx.secret("api_key")` 拿 `SecretStr`。`CFG-003`「明文不进配置文档」因此是**结构性**成立
    的（配置块里根本没有 `api_key` 这个键），密钥名固定为 `SECRET_NAME` 常量——做成可配置
    会让那条 `target` 变成一句谎话。`PERMISSION_DENIED` 与 `CONFIG_SECRET_MISSING` 天然可分。
  - **HTTP 直接用 `httpx`，manifest 如实声明 `net` 权限，不走 `ctx.net`**（第二处取舍）。
    `HttpAccess` 的 SSRF 守卫会拒绝私有网段，而交付要点明确要覆盖本地 vLLM / Ollama /
    LM Studio（即 `127.0.0.1`）；且 `ctx.net` 的生产实现要等 `D26`。与 `D17` 的
    `session_jsonl` 用 `pathlib`、如实声明 `fs:read`/`fs:write` 是同一条先例：门面能力不足
    时，诚实声明比绕道更符合「应用级权限的价值是让越界意图可审计」。本地端点
    （`ipaddress` 判回环/私有网段）额外关 keepalive、关代理——Ollama / vLLM 会在客户端
    keepalive 到期前关掉空闲连接，`ALL_PROXY` 会把 localhost 送进够不着的代理，两条都是
    真实端点上验证过的。
  - **交付五个模块而不是开发方案点名的一个**：`wire.py`（纯函数线格式翻译，501 行）/
    `faults.py`（错误映射）/ `settings.py`（配置）/ `provider.py`（IO 与取消）/ `__init__.py`
    门面。切分的分界线是**碰不碰 IO**：线格式的每一条规则都能在 `wire.py` 上逐字节钉住、
    不需要事件循环，行为才需要 `httpx.MockTransport`。混在一起会让「payload 少了一个键」
    在异步栈里冒出来。
  - **模型窗口只能来自配置**：`describe()` 是纯查询（契约写死它在预算推导路径上、不得发
    网络请求），因此有 `models` / `default_context_window_tokens` 等键。`models` **非空即为
    白名单**：运维一旦列举了在用的模型，一个拼错的 model_id 就该当场报 `CAPABILITY_MISSING`
    而不是拿默认窗口蒙混。
  - **`max_tokens_field` / `supports_temperature` 是配置项，不是按模型名猜的表**。gpt-5、
    o1/o3/o4 只认 `max_completion_tokens` 且拒绝 `temperature`，旧实现为此维护了一张靠 slug
    匹配、越滚越大的厂商特例表。做成配置意味着用户换新模型只需改一行——这正是「显式优于
    魔法」「少结构」。同理不移植旧实现的角色交替重排、`<tool_call>` 文本兜底、`json_repair`
    修参数、OpenRouter 归因头、Mistral id 规整——它们各有各的不该进内建的理由
    （改写组装器交下来的消息越过 `MOD-004` / 把模型正文当结构化数据是 `EDG-306` 要防的 /
    静默修正坏输入违反原则 7）。
  - **流式 tool_call 增量拼装是本模块最易出错处**，四个线格式坑逐一处理：`index` 才是身份键
    （`id`/`name` 只在首片），`arguments` 是被切碎的字符串（只能 `+=`、流结束才 `json.loads`），
    判空用**真值**而不是 `is not None`（有端点在首片发 `"arguments": ""`），开了 `include_usage`
    时**收尾片的 `choices` 是空数组**、`finish_reason` 因此不在最后一片。`call_id` 去重是
    **强制项**——`ModelResponse.__post_init__` 对重复 `call_id` 直接抛错，而 Zhipu/GLM 会让
    并行调用共用一个 `id`；补了什么写进 `provider_metadata`（补救必须可查）。
  - **流式中途失败必须先 `yield DONE(ERROR)` 再抛**（`protocols.py` 写死、`EDG-304`）：
    `kernel/turn/folding.py` 据此把已收到的文本按 `interrupted=True` 落库，而不是把半截输出
    当成完整答案。一片都没吐过就失败则不发 DONE（没有「已产生的内容」要收尾）。
  - **内容过滤是 HTTP 200 上的正常响应而不是异常**，走 `StopReason.CONTENT_FILTER`
    （`is_complete_answer` 因此为假）。`STOP_SEQUENCE` **不可达**——OpenAI 对自然结束与撞上
    stop 序列都回 `"stop"`，契约有那个枚举值不等于这个 Provider 分得出来，docstring 如实写明
    不假装能区分。
  - **错误映射按语义分类**（`MOD-003`）：401→`CONFIG_SECRET_MISSING`（与 `ctx.secret()` 缺失
    同码，用户看到的是同一件事）、403→`PERMISSION_DENIED`、429 按 `error.code` 分**限速可
    重试 / 欠费不可重试**（两者都是 429，撞限速等一会儿就好，欠费重试一万次也不会好，未知
    code 默认可重试）、408/409/5xx 可重试、其余 4xx 不可、`httpx.TimeoutException` 与流空闲
    看门狗→`TIMEOUT_MODEL_REQUEST`。`detail` **只放状态码与 `error.type`/`code`，不放
    `error.message`**——那段自由文本会回显 prompt 或被 echo 回来的凭据（`D13` 的先例）。
  - **两处不显眼但会咬人的实现点**：① 孤立 UTF-16 代理码位在序列化前剔除——Windows 控制台
    粘贴文本会带进来，`httpx` 编码请求体时抛 `UnicodeEncodeError`，一次正常对话因此整轮失败
    且错误指不到原因（本模块唯一一处输入规整，单独测试）；② 流空闲看门狗（每片
    `asyncio.wait_for`）与请求级超时是两件事——请求超时保护不了「开了口就不再吐字」的流。
  - **未新增 `ErrorCode`**：认证失败与限流的区别由 `NucleaError.retryable` 承载，五个现有码
    （`CONFIG_SECRET_MISSING` / `PERMISSION_DENIED` / `EXTERNAL_MODEL_PROVIDER` /
    `TIMEOUT_MODEL_REQUEST` / `CAPABILITY_MISSING`）够用。**未碰 `kernel/`**。
  - **测试全走 `httpx.MockTransport`，一个 socket 都不开**；`tests/builtins/conftest.py` 照搬
    `tests/integration/` 的 autouse 网络闸门（拦 `connect`/`getaddrinfo` 的**目标**、回环放行，
    不拦 socket 构造），是「零真实网络」的可执行断言。凭据哨兵用 `sk-`+≥16 字符（匹配
    `errors.py::_SECRET_VALUE_PATTERNS`），驱动一次 401 后断言它不出现在 `repr` / `detail` /
    `user_message` / 事件序列化里（`MOD-002`）。踩到一个坑：`httpx` 0.28 不再导出
    `IteratorStream`，流式 stub 改用 `Response(200, content=<async iterator>)`。
  - 验收：`tests/builtins`(240) 全绿，`builtins/model_openai/` 语句覆盖率 **97%**
    （未覆盖的全是防御性分支：非字符串 host、客户端复用短路、`_metadata` 的空值跳过）；
    新层八个测试目录共 **1591 个用例全绿**（`D18` 收口时 1471）。`ruff check`（src + tests）、
    `basedpyright`（新层 0 报错，legacy 仍是既有 4 个）、`legacy_debt --check` 未变、
    `check_startup_cost --check` OK（`import nucleamind` 仍 0.5 ms、只拉入 1 个模块——
    `provider.py` 含 httpx，只在真正加载时才被 `import_setup()` 拉进来）；新层 `Any` 数仍为 0。

- **`D20` 内建工具：`tools_fs`**（`builtins/tools_fs/` 九个模块约 1597 行 +
  `builtins/registry.py` 的第四条 manifest + `runtime/wiring.py` 的一个可选参数 +
  `tests/builtins/test_tools_fs.py` 102 个用例）：
  - **单工具禁用（`TOL-006`）与 `D16`「声明 ⊆ 注册」的冲突，本轮唯一需要拍板的取舍**。
    `CapabilityHost.finish()` 要求 manifest 声明的每一项都真的被注册，而 `TOL-006` 要求被
    禁用的工具**从 registry 里消失**（模型可见列表与可执行集合同源）——静态的
    `BUILTIN_MANIFESTS` 无法按配置少声明一项，`plugins.disable` 也帮不上忙（全部内建共用
    一个 `Builtin()` ProviderId，provider 级禁用对内建没有粒度）。
    **取的路**：`runtime/wiring.py` 的 `to_load_request()` / `wire_capabilities()` 增加一个
    可选的 `keep: CapabilityFilter`，`tools_fs` 导出 `enabled_tool_names(config)`，装配根用
    **同一份配置**同时喂给声明过滤与 `setup()`。D16 的不变量一条也不放松（声明与注册仍
    严格相等，只是两者同源于配置而不是同源于常量），机制对 `D21` 的 `tools_shell` 与第三方
    工具插件通用。`keep=None` 时行为与 `D16` 完全一致。有一条用例专门断言**忘了传 `keep`
    就会被 `PLUGIN_LOAD_FAILED` 挡下**——那个报错是对的。
  - **路径守卫是双重校验，缺一不可**（`paths.WorkspaceGuard`，`EDG-405`、`NFR-302`）：
    ① `os.path.normpath` 后（不跟随符号链接）必须落在根内，挡 `..`；② `Path.resolve()` 后
    必须**再**落在根内，挡符号链接与 Windows 重解析点。两次比较都过 `os.path.normcase`
    （Windows 折叠大小写、POSIX 是恒等），因此同一段代码在两个平台给出同一套判定。
    前缀比较显式要求落在分隔符边界上——否则 `/x/ws-evil` 会被判成 `/x/ws` 的后代。
  - **三条与 legacy `path_utils.py` 不同的判定**：① **不做 `expanduser()`**（`~` 是模型给的
    普通字符，展开它等于凭空多出一条通往主目录的路径，而一个真叫 `~` 的目录反倒读不到）；
    ② **绝对路径接受但过同一道门**（`FileAccess` 那条「绝对路径一律拒绝」是针对没有根校验
    的门面说的，拒绝只会换来模型拼一串 `../`）；③ **Windows 保留设备名两个平台一律拒绝**
    （`CON`/`NUL`/`COM1`…能通过 containment 却根本不是文件；为它开平台分支就破坏 `NFR-605`）。
    越界错误的 `detail` 里**只放原始串、不放解析结果**——把宿主机绝对路径写进模型可见的
    错误里是另一种泄漏，有一条用例逐字段钉住。
  - **TOCTOU 如实写进 docstring，不假装挡得住**：校验与随后的 `open()` 之间目标可被换成
    越界符号链接，挡它需要 `openat` + `O_NOFOLLOW` 一类原语，而那在 Windows 上没有对等物。
    这是应用级守卫，真正的隔离是 P2 的子进程插件宿主。
  - **`execute()`「约定不抛」只实现一次**（`base.FsTool`）。逸出的异常会被 Kernel 记成
    `side_effect=UNKNOWN`，而本包的五个工具**总是知道**：所有失败都发生在真正落盘之前
    （写走「同目录临时文件 → `fsync` → `os.replace`」，替换成功之后没有可失败的步骤），
    因此折出来的失败一律 `NONE`，本包不产出 `UNKNOWN`——那个取值留给 `D21` 的 `shell.exec`。
    让五个工具各写一遍 try/except 迟早漏一个分支，而漏掉的代价是一次谎报。
  - **`EDG-205` 的四类各有可预期结果**：含 NUL 字节 → 判二进制 → `INPUT_UNSUPPORTED_MEDIA`
    整份拒绝（给模型乱码只会让它继续猜）；非法 UTF-8 但无 NUL → `errors="replace"` 解码 +
    `data["lossy"]=True`（一行坏字节不该让整份日志读不出来）；空文件 → 成功且内容为空串；
    超过 `max_read_bytes` → 截断而非失败。但 **`fs.edit` 拒绝有损解码的文件**：读可以将就，
    写回去等于把那些 `�` 变成文件的真实内容。
  - **`NFR-605` 落在字节上**：读的一侧把 `\r\n` 与孤立 `\r` 归一成 `\n`，写的一侧以二进制
    模式原样落盘（文本模式会在 Windows 上把 `\n` 翻成 `\r\n`，两个平台的产物就不同了）。
    结果里的路径一律是 posix 相对路径，`fs.list` 的顺序在收集后统一排序而不是文件系统序。
    测试夹具本身也改用 `write_bytes`——`write_text` 会让夹具变成平台相关的。
  - **`fs.write` / `fs.edit` 是 `DESTRUCTIVE` + `EXCLUSIVE`**：覆盖既有内容不可撤销
    （`TOL-004` 的确认策略要拦的正是这一档，「它只写一个文件」不构成降级理由）；两次写同
    一个文件的结果又取决于顺序，而 turn 内的并行调度不保证顺序。`fs.edit` 命中 0 处或命中
    多处且未传 `replace_all` 时**不做任何修改**。
  - **`fs.grep` 的正则由模型给，ReDoS 有面**，三道约束把它压成有界代价：pattern 长度封顶
    512、**每处理一个文件检查一次取消**（只在入口检查等于取消要等整次搜索结束）、匹配数
    封顶。这不是「挡住了 ReDoS」——足够病态的 pattern 仍能卡住一次调用，但那次调用会被
    `tool_timeout_ms` 收走而不是拖垮实例。二进制文件与读不动的文件**跳过而不是报错**。
  - **`MAX_TOOL_RESULT_LENGTH` 不在 `contracts/__init__` 里**，从 `contracts.tool` 取
    （`tests/contracts/test_tool.py` 也是这么取的）。截断标记**算在上限内**：先按最坏情况
    算能留多少字符，再用真实的 `shown` 渲染标记，因此返回值长度恒 ≤ 上限且标记里报的数字
    与实际截出来的长度是同一个数。配置的 `max_result_chars` 超过契约上界直接拒绝——放行
    只会让每次调用都在构造 `ToolResult` 时才炸，那时错误指向的是 kernel 而不是这行配置。
  - **符号链接用例建不了就 `skip`，不当成通过**；但 Windows 上另加了两条**目录联接**
    （`mklink /J`）用例——它不需要提权，走的又是同一条 `resolve()` 判定，因此在开发机上
    重解析点这条守卫**真的跑过了**（本机 4 条 symlink 用例 skip，2 条 junction 用例通过）。
  - **`critical=False`**：没有文件工具的 Agent 仍然能对话，这与「没有模型」「没有会话存储」
    不是一回事。**未新增 `ErrorCode`**，**未碰 `kernel/`**（`runtime/wiring.py` 是 `R5` 允许
    同时看见 `kernel/` 与 `sdk/` 的唯一一层）。
  - 验收：`tests/builtins`(342) 全绿；新层八个测试目录共 **1693 个用例全绿**（`D19` 收口时
    1591）。`ruff check`（src + plugins + tests）、`basedpyright`（新层 0 报错，legacy 仍是
    既有 4 个）、`legacy_debt --check` 未变、`check_startup_cost --check` OK；新层 `Any` 数仍为 0。

- **`D21` 内建工具：`tools_shell`**（`builtins/tools_shell/` 七个模块约 1100 行 +
  `builtins/registry.py` 的第五条 manifest + `tests/builtins/test_tools_shell.py` 74 个用例）：
  - **`SideEffect.UNKNOWN` 在这里第一次真的出现**，这是本模块与 `tools_fs` 唯一的语义差异，
    也是 `D20` 点名交代过的那条。三档判定只在 `executor._fold` 一处：执行**之前**失败
    （参数非法 / cwd 越界 / 入口取消）→ `NONE`（进程没起来，外部世界没变）；进程自己退出
    或宽限期内被终止 → `OCCURRED`；**宽限期用尽被强杀 → `UNKNOWN`**（`EDG-407`）。
    别照抄 `base.FsTool` 那句「折出来的失败一律 `NONE`」——文件工具的失败全部发生在落盘
    之前，而这里第三档正是 `UNKNOWN` 存在的理由，谎报 `NONE` 会让用户据此重试。
  - **取消是「终止信号 → 宽限期 → 强杀 + 收尸」三步，不是一步**（`process._supervise`）。
    直接 `kill()` 会让一条 `rm -rf` 写了一半就停——那不叫取消成功，叫留下半个被删掉的
    目录树。宽限期正是留给进程自己收尾的。**不 `task.cancel()`** 与 `kernel/turn/invoker.py`
    同一条理由。宽限期常量 `DEFAULT_GRACE_MS = 2000` 与 kernel 那份各写一份（`R4`），
    由一条对照测试钉住。
  - **取消要轮询而不是等超时**：`CancelSignal` 只有 `requested` 与 `raise_if_requested()`
    两个成员（`CancelToken.wait()` 属 kernel 扩展面，`R4` 够不着），因此 `_wait_or_cancel`
    每 `CANCEL_POLL_MS`（50 ms）看一次。一条 `timeout_ms=120000` 的命令在用户按下 Ctrl-C
    之后还要跑两分钟，不叫支持取消。
  - **两个管道从一开始就并发抽干**。`process.wait()` 在管道写满时会与子进程死锁，而
    `communicate()` 会等进程退出——宽限期用尽时进程可能还要跑一年。自己开两个抽干任务，
    任何时刻都拿得到「到目前为止的输出」，包括被强杀的那一刻。
  - **Windows 走 `create_subprocess_shell`，POSIX 走 `exec`**（`command.py` 的模块 docstring
    是这条的唯一出处，本轮踩到的最实的一个坑）：`cmd.exe` 接在 `/c` 之后的是**原始命令行
    尾巴**，而 `subprocess` 在 Windows 上用 `list2cmdline()` 把 argv 拼回字符串时会按 MSVC
    规则把内层引号转义成 `\"`——`cmd.exe` 不认识反斜杠转义，于是任何带引号的命令当场以
    exit 1 残掉（第一版就是这么写的，测试立刻报出来）。CPython 的 `shell=True` 分支拼的是
    `%ComSpec% /c "<原样命令>"`，外层那对引号正好抵消 `cmd` 的首尾引号剥离规则。
    代价是 Windows 上拿不到 `/d`（跳过 AutoRun 注册表项）、`shell` 配置项不生效，两条都
    如实写在 docstring 里。平台分派**只在 `process._spawn` 一处**，有一条 `os.name` 出现
    次数的测试盯着——挪到别处就会有人「顺手统一」成 exec。
  - **环境变量是白名单，不是黑名单**（`NFR-307`）。做成「过滤掉看起来像密钥的变量名」
    在结构上就是错的：它要求那张名单穷举出所有会泄漏的变量，而漏掉一个的代价是把父进程的
    凭据交给一条模型写的命令。这里反过来——父进程的环境**默认一个字节都不进子进程**，
    只有平台基线（让 shell 起得来的那几项，两个平台各一份且都不含凭据类变量）与运维在
    `pass_env` 里逐个点名的才转发。「哨兵不进子进程」因此不是一条要维护的过滤规则，
    而是**没有路径**。哨兵用例走**真实子进程**打印自己的整个环境再搜——`build_environment()`
    是对的不等于调用它的那条路径是对的（漏传 `env=` 单测看不见）。
  - **非零退出码是正常产出而不是工具失败**（`ok=True`）。`grep` 没匹配返回 1、`test` 判假
    返回 1、编译器发现错误返回 2——模型需要拿到退出码和 stderr 才能继续工作。折成
    `ok=False` 会让 Kernel 认为工具坏了，而真正坏掉的三条路（起不来 / 超时 / 被强杀）
    各有各的错误码。进程**起不来**折成 `exit_code=-1`（不是任何程序的真实退出码，
    有效范围 0–255），诊断因此能区分「启动失败」与「程序返回 1」。
  - **cwd 守卫是 `tools_fs.WorkspaceGuard` 的第二份实现，不是 import 它**。`R4` 确实允许
    `builtins/` 之间互相 import（`_ALLOWED_TARGETS["builtins"]` 含自身），但 `tools-fs` 与
    `tools-shell` 是两份独立 manifest、两个可以各自被禁用或被第三方覆盖的提供方——让一个
    import 另一个的内部模块，等于在能力边界之外偷偷建立依赖：`tools-fs` 被换成第三方实现
    时，`tools-shell` 仍绑在内建那份代码上。双重校验（`normpath` + `resolve()`，两次都过
    `normcase`）逐条相同，由 `test_cwd_guard_matches_the_fs_workspace_guard` 五条对照钉住，
    与 `estimate_tokens` 各写一份是同一种做法。**Windows 的重解析点用目录联接
    （`mklink /J`，不需要提权）真的验到了**，那是 realpath 校验在本机唯一跑得到的途径。
  - **守住 cwd 不等于守住命令能碰到的文件**：一条 `cat /etc/shadow` 用绝对路径，与 cwd 无关。
    cwd 边界限制的是「命令默认在哪里落地」，真正的隔离是不授予 `shell` 权限或 P2 的子进程
    宿主。这句如实写在 `paths.py` 里，不假装挡得住。同理**不移植 legacy 的
    `_guard_command` 命令黑名单**：模型能写出的绕过形式无穷（换行、变量展开、base64 管道），
    一张挡不住的黑名单只会让人以为挡住了。
  - **只声明一条 `shell` 权限**：它是五种权限里最强的一个，`fs:read` / `fs:write` / `net`
    在它面前都是子集，再声明一遍只会让「这个插件到底要什么」变模糊。未授予时由 kernel 的
    `ToolExecutor` 在**执行之前**折成 `PERMISSION_DENIED` + `side_effect=NONE`，工具自己
    不抄一遍这个判定（有一条走真实 `ToolExecutor` 的用例）。
  - **`critical=False`**，单工具禁用直接复用 `D20` 的 `keep` 那条路（`enabled_tool_names`
    + `runtime/wiring.py`），没有发明第二套机制。**未新增 `ErrorCode`**（`TIMEOUT_TOOL_CANCEL`
    / `TIMEOUT_TOOL_CALL` / `CANCELLED_BY_USER` / `PERMISSION_PATH_OUTSIDE_WORKSPACE` 够用），
    **未碰 `kernel/`**，`tools_shell` 按 `D18` 定的规矩**不进**
    `test_builtin_no_privilege.py::_READ_ONLY_BUILTIN_PACKAGES`。
  - **`process._release()` 显式关传输**：被强杀后我们 `cancel()` 掉 waiter 与两个抽干任务，
    传输对象会活到下一次 GC，届时事件循环多半已关，`__del__` 里那句 `call_soon` 抛
    `Event loop is closed`——表现是一串挂在**无辜用例**上的 `ResourceWarning`（本轮就是这么
    发现的），而在一个跑几个月的实例里那是真实的 fd 泄漏。`_transport` 是私有属性，用
    `getattr` 取：CPython 换内部名字时应当安静地少做一件清理，而不是让每次调用都炸。
  - 验收：`tests/builtins`(416) 全绿；新层八个测试目录共 **1767 个用例全绿**（`D20` 收口时
    1693）。`builtins/tools_shell/` 语句覆盖率 **96%**（未覆盖的全是 POSIX 分支与防御性
    路径：`default_shell` 的 POSIX 探测、`_spawn` 的 exec 分支、`BaseException` 兜底、
    `relative()` 的不变量违规、两个 property）。`ruff check`（src + plugins + tests）、
    `basedpyright`（新层 0 报错，legacy 仍是既有 4 个）、`legacy_debt --check` 未变、
    `check_startup_cost --check` OK（`import nucleamind` 仍 0.71 ms、只拉入 1 个模块）；
    新层 `Any` 数仍为 0。**技术方案 §8.2 的冻结清单六件套至此交齐。**

- **`D22` 内建命令：`commands_core`**（`builtins/commands_core/` 五个模块约 560 行 +
  `builtins/registry.py` 的第六条 manifest + `runtime/introspection.py` +
  `contracts/protocols.py` 与 `sdk/api.py` 各扩一处 + `tests/builtins/test_commands_core.py`
  49 个用例）：
  - **本轮唯一需要拍板的事是 `D21` 留下的那条：六个命令有五个够不到自己需要的数据**
    （`/help` 要 registry、`/capabilities` 与 `/plugins` 要诊断、`/config` 要完整配置、
    `/cancel` 要 orchestrator），而 `R4` 挡着 `builtins → kernel`，`CommandInvocation` 与
    `PluginContext` 两条路都够不到。四条出路里**取的是「扩 `PluginContext`」**：
    `/plugins`、`/capabilities` 这类命令**本来就该是第三方插件能写的东西**，而其余三条
    （由 `runtime/` 特权注册 / 快照塞进 `ctx.config` / 改注册载荷形状）都在给「内建是特殊的」
    找借口——`BAS-005` 会在这一项上破例，`/help` 还列不出自己。
  - **新增两个 support Protocol 而不是一个七成员门面**（`contracts/protocols.py`）：
    `InstanceView`（`commands` / `capabilities` / `plugins` / `config_document` /
    `session_snapshot`）与 `TurnControl`（`live_turns` / `cancel_turn`）。分开是因为一个是
    只读可观测性、一个是**控制动作**——`D26` 落地权限模型后，「能看」与「能取消别人的 turn」
    应当可以分别授予，合并就没有这条分界线了。它们落在 `contracts/` 而不是 `sdk/`：
    kernel 侧的实现要结构化满足它们，而 `R2` 禁止 `kernel/` import `sdk/`（与 `D05` 下沉
    `CliEntry`、`D11` 下沉 `SecretStr` 同一条理由）。
  - **`CAPABILITY_PROTOCOLS` 仍是 9**：新增的两个进 `SUPPORT_PROTOCOLS`（与 `CancelSignal`
    同一档），它们不是可注册能力，`CapabilityKind` 一个取值都没多。**`sdk.__all__` 一个字
    都没改**——契约类型不从 `sdk` 转发（`R4`：插件直接 import `contracts`），因此这次动
    冻结表面的代价被压到两处快照：`test_protocols.py::SUPPORT_PROTOCOLS`（1 → 3）与
    `test_public_surface.py::API_PROTOCOLS[PluginContext]`（10 → 12）。
  - **`capabilities()` / `plugins()` 返回 JSON 而不是 kernel 类型**：`ResolutionReport` 与
    `PluginStatus` 都在 `kernel/` 里、契约层够不着，而这两样**本来就以 JSON 为发布形态**
    （`NFR-502` 要求报告可序列化，两者各有 `to_json()`）。在契约层复刻一遍它们的字段只会
    多出一份必然漂移的定义。其余三个成员用的 `CommandSpec` / `SessionKey` /
    `SessionSnapshot` 全在 `contracts/` 里，因此**是强类型的**。
  - **生产实现在 `runtime/introspection.py`**（`R5` 的落点，与 `wiring.py` 同一条理由：
    只有 `runtime/` 同时看得见 kernel 与 sdk）。一致性同样**靠类型标注静态证明**——
    `build_instance_view()` / `build_turn_control()` 的返回类型就写成 `InstanceView` /
    `TurnControl`，basedpyright 严格模式下不成立即报错；测试验不了（`**/tests` 被排除在
    类型检查外），`isinstance` 也验不了（`runtime_checkable` 只查属性存在性）。
  - **命令索引是惰性取的**（`commands_source` 是 callable），与
    `Diagnostics.capabilities_source` 同一条理由：索引要等全部插件注册完才建得出来，而
    `PluginContext` 必须在 `setup()` **之前**就交给插件。**这条是测试先发现的**——
    第一版 `FakeInstanceView` 在构造时收命令清单，`/help` 于是永远是空的；`set_commands()`
    是那个时序的最小形态。
  - **`/config` 的脱敏是结构性成立的**：`D11` 定死配置树自始至终持有 `${VAR}` 字面量、
    明文只在 `SecretMap` 里，因此那份文档「没有别的东西可泄漏」。仍然过一道 `redact()` +
    `scrub()` 作纵深防御，并有一条把明文**硬塞进**文档的哨兵用例。它是
    **`operator_only=True`** 的：配置不含明文凭据，但仍然是「实例怎么装的」。
  - **`/cancel` 取消不了自己所在的 turn**：这条命令正持有 session 槽位在跑，
    `live_turns()` 里当然有它；取消自己既没有意义，也会让这条命令的输出发不出去，因此
    **显式拒绝**而不是让用户困惑地看着自己的命令消失。**不带参数时只列出而不是取消全部**
    ——一次误敲把所有并发 turn 全掐掉不可撤销，而列出来再敲一次只多一次往返。
  - **`handle()` 的「约定不抛」只实现一次**（`_Handler.handle` 的统一出口，与 `D20` 的
    `base.FsTool` 同一种做法）。`NucleaError` 原样带出（实现方给的诊断比 Kernel 能编的更准），
    其余异常折成 `KERNEL_INVARIANT_VIOLATED` 且**只放类型名不放异常消息**——第三方命令的
    异常文本可能带着凭据（`D13` 的先例，有哨兵用例）。捕 `Exception` 不捕 `BaseException`。
  - **`critical=False`、一条权限也不声明**（数据全部来自 `ctx.instance` / `ctx.turns`，
    那两个不是资源访问器，与 `ctx.events` 同一档）。**单命令禁用直接复用 `D20` 的 `keep`
    那条路**（`enabled_command_names` + `wire_capabilities`），没有发明第二套机制；有一条
    「忘了传 `keep` 就被 `PLUGIN_LOAD_FAILED` 挡下」的用例。**未新增 `ErrorCode`**，
    **未碰 `kernel/`**。
  - **`/help` 的前缀用默认值渲染**：前缀是 `kernel/config` 的 `routing.command_prefix`，
    而内建够不着它、装配根也没有交下来的通道（`ctx.config` 只给自己那一块）。改过前缀的
    用户会在 `/help` 里看到默认前缀——**这是已知的小偏差**，不值得为它扩配置块，`D23`
    接线时可以顺手把它经配置块交下来。
  - 验收：`tests/builtins`(465) 全绿，`builtins/commands_core/` 语句覆盖率 **99%**
    （未覆盖的 1 行是 `_rows` 的防御性非序列化分支）；新层八个测试目录共 **1822 个用例
    全绿**（`D21` 收口时 1767）。`ruff check`（src + plugins + tests）、`basedpyright`
    （新层 0 报错，legacy 仍是既有 4 个）、`legacy_debt --check` 未变、
    `check_startup_cost --check` OK（`import nucleamind` 仍 0.68 ms、只拉入 1 个模块）；
    新层 `Any` 数仍为 0。完整 `tests/legacy` 14 failed / 4808 passed / 30 skipped，
    与 `D21` 完全一致，失败全部落在既有那批网络、子进程时序与 oauth-cli-kit 家族。

- **`D23` 内建 CLI 能力、装配根与 `nm` 入口**（`builtins/cli_entry/` 四个模块约 480 行 +
  `runtime/{bootstrap,instance,plugin_context}.py` 与 `runtime/cli/` 共约 1250 行 +
  `embed/__init__.py` + `kernel/config/plugin_blocks.py` +
  `tests/{runtime,embed,builtins,kernel}/` 共 137 个新用例）：
  - **本轮拍板的四件事**，逐条记在下面。
  - **① 插件配置块落成 `plugins.<plugin_id>.{config,secrets}`**（新模块
    `kernel/config/plugin_blocks.py`）。此前 `SECTION_SPECS` 是一张扁平字段表，**没有任何
    地方放插件配置**，而六个内建全都要读 `ctx.config`。形状照技术方案 §6.7 的字面表述落地；
    `disable` / `search_paths` 是保留键，不能当插件 id（叫这两个名字的插件被显式拒绝而不是
    静默当成保留键）。`plugins` 小节因此是**唯一**对未知键让路的小节——那些键是插件 id，
    别处一个字都没松。逐字段校验留给 `D25` 阶段 A 的 `config_schema`，本轮只保证形状。
  - **② 凭据是 `config` 的兄弟键 `secrets`，不在 `config` 里面**。`D19` 已定死凭据不进
    插件配置块（`model-openai` 的 `config_schema` 里根本没有 `api_key`），而 §6.7 又要求
    secret 只以 `${VAR}` 引用形式出现——两条合起来的唯一落点就是同级的 `secrets`。
    `ctx.secret(name)` = 取 `plugins.<id>.secrets.<name>` 的字面量 → `resolve_text()`。
    **`CFG-003` 因此仍是结构性成立的**：配置树自始至终只有引用，`/config` 与
    `nm config show` 没有别的东西可泄漏。未授权 → `PERMISSION_DENIED`，授权了但没配或变量
    没导出 → `CONFIG_SECRET_MISSING`（`D19` 依赖这个区分把「改权限」和「补配置」分开）。
  - **③ `builtins/cli_entry/` 一份 manifest 声明两条能力**：`CLI_ENTRY:stdio` 与
    `CHANNEL:cli`。`CliEntry.run()` 只拿得到 `ctx`，而 `PluginContext` 没有「提交一条消息」
    的成员——**不再为此扩一次 `PluginContext`**（`D22` 刚扩过）。把 CLI 的输入做成 Channel
    之后，装配根的 Channel 泵天然把它接上了，`MSG-007`「不得有绕过 `InboundMessage` 的
    专用路径」与开发方案那条「用 `ChannelContract` 验证」的验收同时成立（`CliChannel` 直接
    继承那个契约基类）。入口与 Channel 共用一个 `CliConsole`，那是它们唯一的耦合点：
    入口拥有进程（决定退出码），Channel 拥有消息路径。
  - **④ 生产级 `PluginContext` 落在 `runtime/plugin_context.py`**（`R5`，与 `wiring.py` /
    `introspection.py` 同一条理由）。`D26` 才做权限模型，因此这里**如实**写着：`granted`
    等于 manifest 声明的集合；未声明的访问器抛 `PERMISSION_DENIED`（那条语义是真的），
    已声明的 `fs`/`net`/`shell` 抛 `CAPABILITY_MISSING` 并指向 `D26`——六个内建一个都不用
    它们。给它们一个能跑但没有守卫的实现才是真的危险。`instance` / `turns` 经一个可变
    持有者 `PluginRuntime` 交下来：它们要等 registry 冻结与 orchestrator 装好才存在，而
    ctx 必须在 `setup()` **之前**就交给插件。
  - **`wire_capabilities(context_for=...)` 改成按 manifest 索引**（原来是按 `ProviderId`）。
    这是本轮改到 `D16` 表面的唯一一处，理由是硬的：**全部内建共用一个 `Builtin()`**，
    按提供方索引会让七份内建拿到同一个配置块与同一个状态目录——`session-jsonl` 会读到
    `model-openai` 的配置。有一条 `test_each_manifest_gets_its_own_context` 钉住它。
  - **内建的配置块由装配根合成**：派生默认值（`session-jsonl` 的 `dir`、`tools_fs` /
    `tools_shell` 的 `workspace`、`commands-core` 的 `prefix`、`cli-entry` 的 `instance_id`）
    **加上**用户写的那份，用户显式写过的键压过派生值。`D17`–`D22` 逐个点名的那几个坑
    （会话写进插件私有目录、文件工具在没人预期的目录里读写、`/help` 印出错的前缀）在这里
    一次性兑现，各有一条用例。
  - **`commands-core` 的 `prefix` 顺手补上了**（`D22` 记的那条已知偏差）：命令体的签名
    多一个 `settings` 参数，`/help` 因此印出**生效的** `routing.command_prefix`。
    `DEFAULT_PREFIX` 仍与 `dispatcher.DEFAULT_COMMAND_PREFIX` 各写一份。
  - **`EDG-108` 在装配根落地两次**：`plugins.disable` 含 CLI 提供方时**拒绝启动**并说明
    原因；覆盖 CLI 的提供方没交出实现时，用同一批 manifest **再装一次**、但只让内建提供
    CLI 入口（半装好的 registry 已经冻结，打补丁比重来更容易出错）。后者有一条真的注入
    「声明了 CLI 却一项都不注册」的插件的用例。
  - **被拒的 turn 也要有回音**：去重命中或队列拒绝时 `TurnReceipt.admitted=False`，
    orchestrator 不发终态出站消息（那条 turn 从未开始），Channel 泵因此**自己合成**一条
    `stream_state=FAILED` 的 `OutboundMessage`——否则 CLI 会永远等一个不会到来的终态。
    合成的仍是 `OutboundMessage`，不是绕过契约的旁路。
  - **两次 `Ctrl-C` 的实际语义**（§10.3）：第一次在有 turn 在跑时取消那些 turn、会话继续；
    没有 turn 在跑时它就是「退出」。退出路径先跑 `stop()` 释放实例锁再 `os._exit`——读
    stdin 的工作线程阻塞在 `readline()` 上，没有可移植的唤醒方式，假装能唤醒它只会让退出
    路径多一个不成立的假设。信号处理用 `signal.signal` 而不是 `loop.add_signal_handler`
    （后者 Windows 上没有实现，两个平台各写一条会让「按下去之后发生什么」有两套答案）。
  - **`EDG-501` 的后半句至此有了唯一的调用点**：配置解析失败时
    `write_config_error(layout.config_error_log_path(today), error)`，原文件一个字节不改，
    两条各有一个用例。**JSONL sink 只能在配置加载之后接上**（它的开关在配置里），在此
    之前的事件只进内存环——这是配置与日志开关之间不可消除的先后关系。
  - **`nm` 有了三个真子命令**：`run`（装配 + 交互/单次执行）、`config show [--origins]
    [--json]`、`session list|show`。后两个**不取实例锁**（看一眼配置不该与正在跑的实例
    互斥），`nm session` 只装 `SESSION_STORE` 那一条能力——一条只读诊断不该因为模型凭据
    没导出而失败，但它仍走同一条注册路径，插件覆盖了会话存储时它看到的就是插件那一份。
  - **`embed/` 是真薄门面**：`open_instance()` / `run()` / `EmbeddedAgent`，一行 turn 逻辑
    都没有。`submit()` 走的是 `orchestrator.handle()`，与 CLI 完全同一个入口；嵌入式有
    自己的 `channel_id`（脚本里的问答不和终端里的搅进同一段历史）。`R5` 只允许 `embed/`
    import `contracts/` 与 `runtime/`，因此 `TurnReceipt` 与 `PluginManifest` 由
    `runtime/{instance,bootstrap}.py` 各转发一次——比让门面收 `object` 诚实。
  - **踩到并修掉的两个真问题**：① `CliConsole` 的输入队列原本有界（`maxsize=1`），
    `close()` 在「还有一条没被消费」时抛 `QueueFull`——那是关闭路径上最不需要的一种失败
    （测试先发现）；② Windows 中文控制台是 GBK，默认提示符 `»` 与模型输出里的 emoji 会让
    `sys.stdout.write` 抛 `UnicodeEncodeError`，把一次正常回答变成 traceback。提示符改成
    ASCII，写出口加一层降级（转义而不是失败），各有一条用例。
  - 验收：新层九个测试目录共 **1924 个用例全绿**（`D22` 收口时 1822）；`D23` 新增模块语句
    覆盖率 **91%**（`runtime/wiring.py` 100%、`plugin_context.py` 96%、`bootstrap.py` 96%、
    `cli_entry/` 90–100%、`embed/` 100%；缺口集中在 `nm run` 的信号与硬退出路径——那条路
    会 `os._exit`，在测试进程里跑到那一步会把 pytest 打死，`_Interrupts` 因此单独测）。
    `ruff check`（src + plugins + tests）、`basedpyright`（新层 0 报错，legacy 仍是既有 4 个）、
    `legacy_debt --check` 未变、`check_startup_cost --check` OK（`import nucleamind` 仍
    0.65 ms、只拉入 1 个模块——子命令一律延迟导入）；新层 `Any` 数仍为 0。
    真实 `nm --version` / `nm config show` / `nm session list` 在开发机上跑通。

- **`D24` 首次运行体验与开箱可用验收 ★**（`kernel/config/{scaffold,json_schema}.py` 约 250 行
  + `runtime/first_run.py` 约 200 行 + `runtime/cli/commands/init.py` +
  `scripts/check_startup_cost.py` 扩一项 + `tests/e2e/` 与
  `tests/{kernel,runtime}/` 共 50 个新用例）：
  - **本轮拍板的三件事**，逐条记在下面。
  - **① `$schema` 落成一份由 `SECTION_SPECS` 派生的真 JSON Schema**。开发方案写的是
    「生成含 `$schema` 与占位字段的最小配置」，但 `schema.py` 是 `extra="forbid"`——顶层多
    一个 `$schema` 会让**刚生成的文件在下一次启动时以 `CONFIG_UNKNOWN_FIELD` 失败**，
    那是最糟的首次体验；而项目里又没有任何 JSON Schema 文档可指向，写一个指向 docs 的 URL
    只是形式主义。于是 `nm init` 同时写 `config.json` 与实例目录下的 `config.schema.json`
    （由 `SECTION_SPECS` + `FieldKind` 派生，**字段的唯一真相来源不变**），`config.json` 用
    相对路径引用它；`schema.py` 增加一条**具名**例外 `IGNORED_TOP_LEVEL_KEYS`。
    它是全项目第二处对未知键让路的地方（第一处是 `plugins` 小节的插件 id），因此刻意不写成
    「以 `$` 开头就放行」——后者会让拼错成 `$turn` 的小节静默消失，有一条反向用例钉住。
  - **② 首次运行「生成 + 指引 + 退出」**（照技术方案 §10.1 步骤 2 的字面表述）。
    「凭据已就绪就直接进会话」看起来更顺手，却让同一条命令有两种结局——取决于用户有没有
    提前 export 那个变量，而首次运行恰恰是最需要确定性的时刻。里程碑 1 仍然成立，
    只是分两次调用。
  - **③ 交付 `nm init`**（`kernel/config/sources.py` 的 docstring 早就写着它）。它与
    `nm run` 的首次运行分支走**同一个** `ensure_initial_config()`，不是第二条生成路径。
    **没有 `--force`**：`EDG-501` 要的是「不得静默回退后覆盖原文件」，一个能覆盖用户配置的
    开关是这条需求的反面；已存在时以退出码 3 退让并印出路径。
  - **`kernel/config/` 仍然一个字节都不写**。`scaffold.py` / `json_schema.py` 只**渲染**，
    落盘在 `runtime/first_run.py`——那是全项目 `config.json` 唯一的写入点，用
    `O_CREAT|O_EXCL` 而不是「先判断存不存在再写」：后者在两个 `nm init` 同时跑时会互相覆盖，
    而 `O_EXCL` 让「没有就建、有就退让」是一次原子操作。派生的 `config.schema.json` 反过来
    **会**被刷新（内容不同时），它是我们生成的产物而不是用户的资产；内容相同则一个字节都不写。
  - **`scaffold.py` 不认识任何具体内建**。模板需要「默认模型叫什么、凭据叫什么、从哪个环境
    变量取」，而 `R2` 禁止 `kernel/` 够到 `builtins/`——那四个事实由 `runtime/first_run.py`
    **各写一份**并由 `test_defaults_match_the_builtin_model_provider` 对照（与
    `estimate_tokens` / `DEFAULT_GRACE_MS` 同一种做法）。理由不只是分层：`nm init` 不该为了
    读四个字符串把 httpx 拉进进程。
  - **模板只放用户真的要改的键**（`$schema` / `model` / `plugins.model-openai.secrets`）。
    把 `defaults()` 整份倒进去看起来更完整，实际是把四十多个字段变成不敢动的噪声，
    而且每一个都会被 `nm config show --origins` 记成「来自 config.json」——「我改过什么」
    这个问题从此答不上来。
  - **缺凭据的错误现在带 `file`**（`BAS-006` 的另一半）。`resolve_text()` / `resolve_secrets()`
    多一个可选的 `source=`，装配根经 `build_plugin_context(config_path=...)` 交下来。
    这条只能由调用方传：`kernel/config/` 的解析路径接的是一棵已经在内存里的树，
    它并不知道那棵树是从哪个文件读来的。指针给的是字段名，`file` 给的是位置，两半齐了才叫
    「可操作」。**值一如既往地不出现**（`EDG-502`）。
  - **`ToolExecutor.orphans` 接上了**（`D14` 留的那条）：`AgentInstance.stop()` 在
    `instance.stopping` 之后报告一次，**没有孤儿时不发事件**——一条恒定出现的 `0` 只会让真正
    有孤儿的那次淹在噪声里。它靠 `isinstance(ToolExecutor)` 窄化：孤儿表不在 `ToolInvoker`
    协议里，给协议加一个成员会逼每个第三方实现编一张空表出来。
  - **`schema.py` 又超了 500 行，于是六个 `*_at()` 收窄器搬进 `fields.py`**。分界线仍是
    那一条：它们一个字段名都不认识，只回答「把一个已校验的 `JsonValue` 收窄成 `int` /
    `str` / `bool` / `tuple[str, ...]`」。这是继 `fields.py`（`D13`）、`plugin_blocks.py`
    （`D23`）之后同一条规则的第三次应用。
  - **`NFR-405` 的 300 ms 没达到，如实记录**：`check_startup_cost.py` 新增的 `startup_ms`
    在开发机上约 **480 ms**（import 约 340 ms + bootstrap 约 147 ms），**大头是
    `import httpx` 单独一项约 280 ms**，由 `model-openai` 在 `setup()` 时构造 provider 连带
    拉进来。按 `NFR-405` 的原文这一项**只告警不失败**（贴着线的门禁会天天误报，而误报的
    门禁最后一定会被关掉），并把两段拆开报出来让「该优化哪一段」查得到。真要压下去，方向是
    让 provider 的 httpx 延迟到第一次请求——那要动 `except httpx.HTTPError` 这类语句，
    不是顺手能做的事，因此没有在本轮做。
  - **`tests/e2e/` 里唯一的替身是传输层**：`httpx.AsyncClient` 被换成挂着 `MockTransport` 的
    子类，模型供应商、会话存储、上下文组装、文件工具、命令、CLI 入口与装配根**全是生产
    实现**。这条分界线与 `tests/integration/`（Fake 在能力边界）互补——把某个内建换成 Fake，
    这套用例就退化成那边的重复。录制脚本**超出即失败**而不是回一个默认响应：多出来的那次
    请求正是最值得看见的东西。9 个用例 0.76 s。
  - **写这批用例时踩到并修掉的两个真问题**：① `config_json_schema()` 里 `STR_LIST` 的默认值
    是元组，`jsonschema` 不认（JSON 没有元组）——这份文档同时是**被直接传给
    `validate()` 的那个对象**，不只是被序列化，因此在生成时就转成列表；② 中断用例第一版用
    一条「永不结束」的 SSE 制造等待点，取消之后那个响应挂着不收尾，**下一个 turn 卡满 60 s
    的流空闲看门狗**才失败。改成「取消登记之后放行下一片」既让取消赢得确定，又让那条流正常
    收尾。
  - 验收：新层十个测试目录共 **1974 个用例全绿**（`D23` 收口时 1924）。`ruff check`
    （src + tests + scripts）、`basedpyright`（新层 0 报错，legacy 仍是既有 4 个）、
    `legacy_debt --check` 未变、`check_startup_cost --check` 通过（`startup_ms` 告警如上）。
    真实 `nm init`（0）/ 重复 `nm init`（3）在开发机上跑通。
    **需求 §16.1 的五条至此逐条有对应用例，这是对外可宣称「可用」的第一个节点。**

- **`D25` Manifest 与插件发现**（`kernel/plugins/discovery.py` 约 300 行 +
  `runtime/inventory.py` 约 270 行 + `kernel/config/` 两处小改 + `runtime/bootstrap.py` 接线
  + `tests/{kernel/test_discovery,runtime/test_inventory}.py` 与 `test_bootstrap.py` 共
  43 个新用例）：
  - **本轮拍板的三件事**，逐条记在下面。
  - **① 不交付开发方案点名的 `kernel/plugins/manifest.py`**。manifest 的类型与校验自
    `D05` 起就在 `sdk/manifest.py`，而 `R2` 禁止 `kernel/` import `sdk/`——在 kernel 侧
    再写一份就是**第二套 manifest 校验**，那正是 `D06` 定下要避免的事。改成 `D16` 的
    做法：机制（entry point 枚举、路径扫描、取回**原始**数据）在
    `kernel/plugins/discovery.py`，翻译与判定（`parse_manifest` → id/平台/`sdk_range`）在
    `runtime/inventory.py`（`R5` 的落点，与 `wiring.py` / `introspection.py` 同一条理由）。
    已回写技术方案 §7.1。
  - **② 「未启用即不导入」靠「候选 id 先于 manifest 可知」成立**，不是靠纪律。三条来源的
    候选 id 分别是 entry point 的 **name**、目录名与 `.py` 文件名，都不需要读、更不需要
    导入 manifest，因此启用判定发生在 `read_candidate()` **之前**。代价是 entry point 的
    name 必须等于 manifest 里的 `id`，对不上即失败——静默以 manifest 为准会让
    `plugins.enabled` 指不到任何东西，而用户看到的现象是「我明明启用了它」。
    可观察的后果：未启用候选的 `version` 是**空串**，那不是漏填而是这条设计的证据。
  - **③ 配置新增 `plugins.enabled`，键名沿用已发布的 `search_paths`**（技术方案原文写的是
    `plugins.paths`，`D23` 已经发过 `search_paths`，不改名）。`enabled` 决定「这个候选要不要
    进加载阶段」，既有的 `disable` 仍是**按提供方禁用**（对内建同样有效），两张表都写了时
    **`disable` 胜出**。`RESERVED_PLUGIN_KEYS` 因此是三个。
  - **`enabled` 不是一个没人读的键**（`plugin_blocks.py` 立过这条规矩）：本轮把清单接到
    `Diagnostics.plugins_source` 上（README 点名的那条），`/plugins` 与 `D29` 的
    `nm plugins` 从此列得出候选、跳过原因与失败。**只发现、不加载**——`setup` 指向一个
    根本不存在的模块时实例照样起来，两阶段加载是 `D27`。
  - **`PluginStatus` 补了一个 `reason` 字段**。`DISABLED` 至少有三个来源（没列进 `enabled` /
    列进了 `disable` / 平台不匹配），而 `PluginState` 刻意不为它们各加一个取值（`D12` 定死
    「不发明第二套生命周期 taxonomy」），差别因此落在这一行自由文本上。已校验但尚未加载
    仍是 `DISCOVERED`——`LOADED` 要等 `D27` 真的跑过 `setup`。
  - **不扫描 `InstanceLayout.plugins_dir`**：那是插件的**状态**目录（`D17` 起就在用），
    同时当成代码来源会让一个只写了状态的子目录看起来像一个装错了的插件。搜索路径只有
    `plugins.search_paths` 一条来源，相对路径按**实例目录**解析（用户写 `"./my-plugins"`
    时「相对谁」的唯一合理答案是那份配置所在的目录，不是 `nm` 的 cwd）。
  - **不兼容与不匹配是两回事**：`sdk_range` 对不上是**失败**（`PLUGIN_SDK_INCOMPATIBLE`，
    不带病加载，`SDK-005`）；平台不匹配只是**跳过**（用户什么都不用改，换个平台就生效）。
    跨来源重复 id 时**各方都不生效**并记一条 `PLUGIN_REGISTRATION_CONFLICT`，与
    `kernel/registry` 的冲突语义一致；搜索路径不存在是**失败而不是静默跳过**——那是用户
    显式写下的一条配置，静默忽略会让「我的插件怎么没被发现」查不出原因。
  - **单文件插件用 `spec_from_file_location` 加载，不改 `sys.path`、不登记
    `sys.modules`**：搜索路径是用户随手指的目录，把它塞进导入路径会让那里的任何 `.py`
    都能被后续 `import` 命中。导入期异常折成 `PLUGIN_LOAD_FAILED` 且**只放类型名不放
    异常消息**（`D13` 的先例，有哨兵用例）。
  - **两条自证用例**：「发现阶段不导入任何东西」旁边有一条「真的去读时那份模块**必须**
    被执行」——否则前一条断言在任何实现下都会通过。20 个未启用 entry point 的用例断言
    0 次导入 + 一个很松的墙钟上界（`NFR-401`）。
  - **未新增 `ErrorCode`**（`PLUGIN_SDK_INCOMPATIBLE` / `PLUGIN_MANIFEST_UNSUPPORTED` /
    `PLUGIN_LOAD_FAILED` / `PLUGIN_REGISTRATION_CONFLICT` / `CONFIG_INVALID` 够用），
    **未新增 `EventName`**（发现发 `plugin.discovered`、失败发 `plugin.failed`，载荷第一个键
    与内建那次发布同名）。
  - 验收：新层十个测试目录共 **2017 个用例全绿**（`D24` 收口时 1974）。`ruff check`
    （src + tests）、`basedpyright`（新层 0 报错，legacy 仍是既有 4 个）、
    `legacy_debt --check` 未变、`check_startup_cost --check` 通过——`bootstrap+start`
    在 D25 前后都是 185–196 ms，发现阶段没有可测量的开销（`startup_ms` 的告警仍是
    `D24` 记的那条 `import httpx`）。新层 `Any` 数仍为 0。语句覆盖率
    `runtime/inventory.py` **100%**、`kernel/plugins/discovery.py` **96%**
    （未覆盖的 5 行全是防御性分支：`iterdir` 的 `OSError`、`spec_from_file_location`
    交回 `None`、`match` 的兜底）。完整 `tests/legacy`
    16 failed / 4806 passed / 30 skipped，失败全部落在既有那批网络（`test_web_fetch_security`）
    与 oauth-cli-kit 家族，落在文档记的 14–18 区间内。

- **`D26` 权限门面与生产级 `PluginContext`**（`kernel/plugins/{permissions,permission_codec}.py`
  约 590 行 + `runtime/access/` 四个模块约 700 行 + `runtime/cli/commands/permissions.py` +
  `contracts/{errors,events}.py` 各扩两条 + `runtime/{plugin_context,bootstrap}.py` 接线 +
  `docs/permissions.md` + `tests/{kernel/test_permissions,runtime/test_access,
  runtime/test_permission_wiring}.py` 与 CLI 用例共 100 个新用例）：
  - **本轮拍板的三件事**，逐条记在下面。
  - **① 批准模型定为 TOFU + 扩权需显式**。`D23` 起 `grants` 一直等于 manifest 声明本身，
    而技术方案 §7.5 只说「配置授权」、没说授权从哪来。取的路是：**第一次见到一个提供方时
    按声明整份授予并记进 `permissions.json`**（`source="first_use"`），**此后声明集合扩大
    时新增项默认拒绝**（记 `pending`，要 `nm permissions grant` 或改文件才生效），撤销
    同样是显式操作（`revoked` 压过声明）。理由是内建与插件必须走同一条判定（`BAS-005`）：
    「配置白名单为准」会逼 `nm init` 要么列举六份内建的全部权限（违背 `D24`「模板只放
    用户真的要改的键」）、要么给内建开一条默认全授的特权路径；「启动时交互式提示」则要为
    `embed/`、CI、`tests/e2e/` 与将来的 Channel-only 部署再定义一套非交互回退，等于同时
    维护两套语义。**局限如实写在模块 docstring 与 `docs/permissions.md` 里**：首次授予不是
    用户点头，它让**扩权**可见、不让**初装**可见；要更严就把 `first_use_policy` 设成
    `PENDING`（那条路真的可用，有用例）。
  - **② 三个资源门面落在 `runtime/access/` 而不是开发方案点名的 `kernel/plugins/`**：
    `HttpResponse` / `ShellResult` 在 `sdk/api.py`，而 `R2` 禁止 `kernel/` import `sdk/`。
    下沉到 `contracts/` 是另一条路（`CliEntry`、`SecretStr` 的先例），但那两次是因为
    **kernel 要调用**那些类型，这里 kernel 一次也不碰它们——为一个只有 `runtime/` 用得到的
    返回值去动已冻结的契约表面不划算。代价是 workspace 双重校验成为**第三份实现**
    （`runtime/access/paths.py`，前两份是 `tools_fs.WorkspaceGuard` 与 `tools_shell.CwdGuard`），
    由 `test_path_guard_matches_the_fs_workspace_guard` 逐条对照钉住。
  - **③ 新增一个 `EventName` `capability.permission_granted`**（技术方案 §7.5 点名，
    `NFR-301`）。授予 / 待批准 / 撤销**共用它**，靠载荷的 `decision` 区分——一次授权状态
    变化不值得发明三个事件名。`EventName` 的字面量快照因此从 31 条变 **32 条**。
    **事件只在账本真的变了时发**（与 `D24` 的「没有孤儿时不发事件」同一条判据）：一条每次
    启动都出现的「已授予」只会让真正的扩权淹在噪声里；`pending` / `revoked` 例外，
    它们是当前生效的拒绝，每次启动都值得说一遍。
  - **账本按 plugin id 索引而不是 `ProviderId`**：全部内建共用一个 `Builtin()`，按提供方
    索引会让六份内建的权限并成一条——`D23` 在配置块上踩过同一个坑。
  - **「首见」看的是有没有被 `decide()` 见过，而不是有没有记录**（这条是测试先发现的）：
    用户可以**预先**批准一个还没装上的插件的权限，那些记录的 `source` 是 `user`。把它们
    算成「见过」会让插件第一次真的加载时，除预批的那条外全部落进 `pending`——用户做了一个
    更宽松的动作，却得到一个更严的结果。
  - **`ctx.fs` 的读写分别判定**（`NFR-302`）：`fs:read` 与 `fs:write` 各自收窄 `target`，
    「可以读整个 workspace、只能写 `cache/`」因此表达得出来；访问器本身只要求两者之一
    ——只声明了写的插件同样该拿得到门面。**认不出的 `target` 收窄成「什么都不许」而不是
    「整个根」**：一条写错的配置应当让插件读不到东西，而不是悄悄拿到全部访问权。
  - **`ctx.net` 的 SSRF 守卫判的是「解析之后」的地址**（`EDG-406`）：先 `getaddrinfo()`
    再对**每一个**返回地址判定，只要有一个落在回环/私有/链路本地网段就整体拒绝，
    因此 `http://127.0.0.1.nip.io/` 这类域名伪装同样挡得住；重定向**手动跟随**
    （`follow_redirects=False` + 自己循环），交给 httpx 跟随等于让第 2 跳绕过守卫。
    **挡不住 DNS 重绑定，如实写在 docstring 里**，与 `paths.py` 的 TOCTOU 那段同一种诚实。
    httpx **惰性 import**（`NFR-405`：单独一项约 280 ms，没人用 `ctx.net` 时一分钱不付）。
  - **`ctx.shell` 走 `exec` 而不是 shell**：契约收的是 argv 列表，「不存在 shell 注入面」
    是原文；`tools_shell` 那条 Windows `list2cmdline()` 的坑在这里根本不存在。超时**不抛**
    （契约原文），返回 `timed_out=True` 且带上超时前已产生的输出；起不来折成 `exit_code=-1`
    （不在 0–255 内，与「程序真的返回 1」分得开）。取消仍是「终止信号 → 宽限期 → 强杀」
    三步。环境是白名单，基线名单与 `tools_shell/environ.py` 各写一份、有对照测试；
    **`ctx.shell` 刻意不提供 `pass_env`**——那个开关的读者是运维，而这里的调用方是插件代码。
  - **补了两个 `ErrorCode`**：`EXTERNAL_HTTP_REQUEST` 与 `TIMEOUT_HTTP_REQUEST`（都给
    `ctx.net`）。复用 `EXTERNAL_MODEL_PROVIDER` 会把一次 webhook 故障记到模型供应商头上，
    复用 `TIMEOUT_TOOL_CALL` 会让诊断指向一个根本没被调用的工具。
  - **`nm permissions list|grant|revoke|forget` 是「用户显式操作」本身**（`NFR-307`）。
    与 `nm config show` 一样**不取实例锁**，代价是改动要等实例下次启动才生效——那句话直接
    印在 `grant` / `revoke` 的输出里。只读路径（`nm session` 的 `open_session_store`）
    照常判定但**从头到尾没人调 `save()`**：让一条不取锁的命令改写 `permissions.json` 会与
    正在跑的实例抢同一个文件。
  - **读不懂账本是启动失败**（`CONFIG_INVALID`，10 条坏文件用例）：静默当成空账本等于
    一次静默的**全部重新授予**，那正是这份文件要防的事。
  - **`permissions.py` 超了 `kernel/` 的 500 行上限，于是把文件形态拆到
    `permission_codec.py`**。分界线是「认不认识判定」：codec 知道文件长什么样、认得权限名
    的写法，但一条记录该是 `granted` 还是 `pending` 它一个字都不管——与 `fields.py` /
    `schema.py` 那条分界线同一种（`D10`/`D12`/`D16`/`D24` 之后同一条规则的第五次应用）。
  - 验收：新层十个测试目录共 **2117 个用例全绿**（`D25` 收口时 2017）。`ruff check`
    （src + plugins + tests + scripts）、`basedpyright`（新层 0 报错，legacy 仍是既有 4 个）、
    `legacy_debt --check` 未变、`check_startup_cost --check` 通过。语句覆盖率
    `kernel/plugins/permissions.py` **99%**、`permission_codec.py` **96%**、
    `runtime/access/` **87–100%**（合计 95%，未覆盖的是防御性 IO 分支与平台分支）。
    **账本的启动开销可以忽略**：稳态 `load + 6 次 decide + save` 约 **0.25 ms**；
    首次启动多一次 `permissions.json` 落盘（`fsync`，冷路径上几十 ms 量级，一次性）。
    真实 `nm permissions list/grant/revoke` 在开发机上跑通。

- **`D29` `nm plugins` 命令与诊断输出**（`runtime/{config_edit,inspect}.py` +
  `runtime/cli/commands/{plugins,capabilities}.py` 约 700 行 + `runtime/wiring.py` 与
  `bootstrap.py` 各一处 + `tests/runtime/{test_config_edit,test_inspect}.py` 与
  `tests/runtime/cli/test_plugins_cli.py` 共 43 个新用例）：
  - **本轮拍板的四件事**，逐条记在下面。
  - **① `config.json` 有了第二个写入点**（`runtime/config_edit.py`）。`D24` 立的规矩是
    「`first_run.py` 是唯一写入点，`O_CREAT|O_EXCL`、没有 `--force`」，而
    `nm plugins enable` 按定义就是改用户的配置，它不可能走 `O_EXCL`。分工因此定成硬的：
    **`first_run.py` 负责「没有就建」，`config_edit.py` 负责「已经有了，改其中一个列表」**。
    三条约束让它不违背 `EDG-501` 与 `CFG-003`：**只读写 `config.json` 那一层**（写回合并树
    会把四十多个默认值、env 与 `--set` 一并物化，`nm config show --origins` 从此答不出
    「我改过什么」）；**从不解析 secret**，因此写回时没有别的东西可写，`${VAR}` 字面量
    原样留着（`D11` 的 `prepare_for_write()` 是给「解析过又要落盘」准备的闸门，这条路上
    解析从未发生）；**原子替换**（临时文件 → `fsync` → `os.replace`）。
    `config.json` 不存在时**不生成**而是让用户先 `nm init`（退出码 3）——写一份只有
    `plugins.enabled` 的配置会绕过首次运行的模板与 `config.schema.json`。
  - **② 只读诊断不走 `bootstrap()`**（`runtime/inspect.py`）。直接调它有三个不能接受的
    副作用：取实例锁（看一眼装了什么不该与正在跑的实例互斥）、写 `permissions.json`
    （`D26` 定死只读路径判定照做但没人 `save()`）、跑步骤 8 的必需能力校验（一个还没配
    模型的实例会让 `nm capabilities` 以「没有指定要用哪个模型」失败，而那恰恰是最需要看
    能力表的时刻）。于是 `inspect_plugins()` / `inspect_capabilities()` 复用 `bootstrap`
    的 `select_manifests` / `plan_external` / `wire_all`（本轮从下划线名提升为公开名），
    **不重写装配逻辑**；`D23` 的 `open_session_store()` 也一并搬进来——它本来就是同一类
    「只读的部分装配」。`plan_external` 多一个 `strict=False`：关键插件在阶段 A 失败时
    只记不抛，因为 `nm plugins list` 的全部意义就是把那条失败印出来。
  - **③ `wire_capabilities(halt_on_critical=False)`**：`model-openai` 是 `critical=True`
    且它的 `setup()` 会取密钥，凭据没导出时照常抛出会让 `nm capabilities` 直接死掉。
    这是「失败的后果由装配根决定」（`PLG-004`）的一次应用，**manifest 里的 `critical`
    一个字都没动**，只是这一次调用不据它中止；失败落进 `Wiring.outcomes`，由命令印成
    「加载失败的提供方」一节——那些提供方的能力**从来没进过** registry，与「冲突」
    （进了又被判出局）是两件事，因此分两段印。
  - **④ `/plugins` 的状态接上了生命周期**（`bootstrap._plugin_statuses`）。`D28` 的
    `PluginLifecycle` 一直挂在 `AgentInstance` 上，而 `Diagnostics.plugins_source` 仍是
    `inventory.statuses`——于是一个跑完 `setup()` 的插件在 `/plugins` 里仍显示
    `discovered`。现在按 id 用 `lifecycle.state`（`PHASE_STATES` 那张唯一的投影表）覆盖，
    **不另造一份映射**；已记下的失败不被「后来它又被加载了」盖掉，内建不进这张表。
  - **`enable` 会顺手把 id 从 `disable` 里摘掉**：`disable` 压过 `enabled`（`D25`），
    不摘就等于让一条明确的「启用」静默失效。摘掉了什么印在输出里——这条命令不做用户看不见
    的改动。反过来 `disable` **不动 `enabled`**，这样 `enable` 才是它的逆操作。
  - **`uninstall` 不碰已安装的发行包**（那是 pip 的事），只移除配置里的引用并**保留**
    `<instance>/plugins/<id>/`（`EDG-505`），顺带印出「要一并删除就跑 purge」。
    `purge` 在 `--confirm` **之前**就打印路径与体积——一句「确定吗」不足以让用户知道自己
    将要失去什么，而这是这套命令唯一不可撤销的动作。没有 `--confirm` 时一个字节都不删
    （退出码 3）。
  - **跳过原因的文案只有一份**：CLI 直接印 `PluginStatus.reason`（来自
    `inventory._SKIP_REASONS`），没有在渲染侧再写一遍（`D25` 点名的那条）。
  - **交付清单的两处偏差**：① 开发方案写的测试落点是 `tests/plugins/test_cli_plugins.py`，
    本仓库的 CLI 用例在 `tests/runtime/cli/`，按仓库惯例落在那里；② 开发方案的交付里有
    「`builtins/commands_core/` 扩展」，但 `/plugins` 与 `/capabilities` 在 `D22` 就已交付
    且渲染齐全，本轮**没动它**——要动的是它的数据源（见 ④）。
  - **`bootstrap.py` 撞上 800 行上限**（非 `kernel/` 的阈值），因此把 `open_session_store`
    搬进 `inspect.py`：它与那两个新查询是同一类东西（不取锁、不 `save()` 账本、
    不装 orchestrator），这不是为了腾行数而随手挪的。
  - 验收：新层十个测试目录共 **2238 个用例全绿**（`D26` 收口时 2117）。`ruff check`
    （src + plugins + tests）、`basedpyright`（新层 0 报错，legacy 仍是既有 4 个）、
    `legacy_debt --check` 未变、`check_startup_cost --check` 通过（`startup_ms` 仍是
    `D24` 记的那条 `import httpx` 告警）。语句覆盖率 `runtime/inspect.py` **100%**、
    `config_edit.py` **99%**、`cli/commands/plugins.py` **99%**、`capabilities.py` **93%**
    （未覆盖的是渲染的防御性分支与 `rmtree` 的 `OSError`；`disabled` 段在当前装配路径上
    恒为空——被禁用的提供方在 `select_manifests` 就被摘掉了，根本到不了解析器）。
    真实 `nm plugins list/enable/disable/uninstall/purge` 与 `nm capabilities`
    在开发机上跑通。
- **`D30` 示例插件与 Plugin Runtime 验收 ★**（`examples/plugins/` 两个独立发行包约
  400 行 + `tests/e2e/{test_plugin_runtime,test_plugin_docs}.py` 30 个用例 +
  `docs/plugin-development.md` + `runtime/plugin_disable.py`）：
  - **本轮唯一需要拍板的事是 `on_disable`**，它在此之前一直写着「留给 `D25`/`D27`」而
    两轮都没做。现象是：`plugins.disable` 掉一个覆盖了内建会话存储的插件之后，内建会
    **自动**复活——因为被禁用的插件根本不读 manifest、不注册，覆盖关系于是不存在。
    那正是 `BAS-004` 禁止的「隐式恢复」，而且它不是无害的：用户可能正是因为不想让对话
    落盘才装的那个插件。三种落法里选了**最严的一种**：只有当被禁用的插件**声明过
    `overrides`** 时才要求表态，没写即 `CONFIG_INVALID` 并指向 `/plugins/<id>/on_disable`。
    没有默认值是刻意的——两个方向都会替用户做一个关于他数据的决定。
  - **`leave_missing` 走 registry 的按能力抑制**（`resolve(suppressed=...)`），而不是
    `D20` 那条 `keep` 声明过滤。分界线是「作用在解析还是注册上」：被抑制的能力照常注册、
    照常出现在 `ResolutionReport.disabled` 段里，只是不生效——`nm capabilities` 因此答得出
    「它为什么不在」。走 `keep` 则那项能力从报告里彻底消失，用户无从判断是没装还是被关了；
    而且内建的 `setup()` 仍会注册它，`CapabilityHost.finish()` 会以「未声明的注册」拒绝。
  - **被 `disable` 关掉的插件现在会读一次 manifest**（`inventory._disabled`），前提是它
    也在 `plugins.enabled` 里。读它只为知道它覆盖过什么。§7.1 的「未启用即零导入开销」
    没有松动：`enabled` 仍是「会不会被读」的唯一闸门，`disable` 只决定「读了之后跑不跑」。
    读不出来时记进 `failures` 并按禁用处理——不为一个已经被关掉的插件让实例起不来。
  - **示例插件必须真的装进环境**才会被发现（entry point 没有第二条路）。代价是
    `tests/runtime/` 那一层的用例开始看见它们：三个文件的 5 条用例一直依赖着「开发环境
    里没装任何插件」这个它们没有声明的前提。修法是 `tests/runtime/conftest.py` 加一条
    autouse 夹具把 entry point 清空（patch `importlib.metadata.entry_points`，因为
    `build_inventory` 的形参默认值在定义时就绑好了）。这不是回归，是一个隐含前提被显式化。
  - **文档防漂移是执行而不是比对**：`tests/e2e/test_plugin_docs.py` 把
    `docs/plugin-development.md` 里每个 Python 块 `exec` 一遍、每个 JSON/TOML 块解析一遍，
    外加「文档列出的 9 个注册方法 == `NucleaAPI` 上真有的那 9 个」。比对片段挡不住这类
    漂移——复制粘贴来的文档在实现改名之后仍然长得一模一样。
  - 验收：需求 §16.2 的八条逐条一个分节，全部通过（30 个用例）；两个示例插件各自的
    `tests/` 继承 `sdk.testing` 的契约测试基类（`ToolContract` / `SessionStoreContract`），
    其中 `SessionStoreContract` 与内建 `session_jsonl` 用的是**同一个基类**。

- **`D31` 遗留 Agent 路径切换与删除 ★**（删 `legacy/` 约 55600 行 + 新增
  `plugins/nucleamind-plugin-openai-api/` 约 850 行 + `runtime/cli/commands/serve.py` +
  `tests/e2e/test_openai_api.py` 与 `tests/runtime/cli/test_serve_cli.py` 共 38 个新用例）：
  - **本轮拍板的三件事**，逐条记在下面。
  - **① 开发方案 §12 的一处假设与代码不符，据实修正。** 方案写的是「`legacy/api/server.py`
    与 WebUI gateway 改为调用新 Kernel」。`api/server.py` 确实只有三个鸭子类型调用点
    （`process_direct` 的两种签名 + 私有 `_last_usage`），但 **WebUI 不是**：`legacy/webui/`
    的 32 个模块要的是 agent 的 `ToolRegistry`、`SkillsLoader`、MCP 生命周期与 token-usage
    Hook，新 Kernel 一样都没有——那是 `D32+` 的工作量而不是 200 行改造。因此
    **WebUI 与 gateway 一并删除**（`D32+` 以插件形态重来），只有 OpenAI 兼容接口在新层
    重写。删掉 `legacy/cli/` 之后 gateway / webui / api 本来也失去了唯一的启动入口。
  - **② 删除范围定在「Agent 路径及其依赖方」，不是整个 `legacy/`。** 保留
    `providers/`（14103 行）、`channels/`（47807 行，去掉 websocket）、`session/`、`cron/`、
    `command/`、`config/`、`utils/`、`bus/`、`security/` 等**不依赖 agent 的库代码**，
    作为 `D32+`（Model / Channel / Cron 插件化）的**在树迁移源**——它们已经改过名、有通过的
    测试，比 `references/nanobot` 的上游副本好用。它们此后**不可达**（没有任何入口能启动
    它们），这是刻意的：债务棘轮继续压着，每迁完一个模块就删掉对应目录。
  - **③ OpenAI 兼容接口做成 `plugins/` 的官方插件 + 一条 `CHANNEL` 能力，而不是
    `builtins/` 或 `runtime/` 里的一个 HTTP 服务。** 三条理由：**流式只有 Channel 拿得到**
    （出站增量经 `OrchestratorDeps.deliver` 按 `channel_id` 路由回注册过的 Channel，而
    `instance.submit()` 要等整条 turn 跑完才返回，做不出 SSE）；`plugins.enabled` 天然就是
    「默认不开监听端口」的闸门，落 `builtins/` 反而要给 `CHANNEL` 再加一层 `keep` 过滤；
    开发方案原文就写着它在 `D32+` 迁为插件——直接落到终局形态，不做一次中间态。
    `nm serve` 相应是**通用无头模式**（bootstrap → `start()` → 等信号 → `stop()`），
    `D32+` 的 Telegram / Discord 插件用的是同一条命令。
  - **`kernel/turn/orchestrator.py` 的唯一发布点补了两个键**（`input_tokens` /
    `output_tokens`）。这是本轮唯一一处改 kernel：token 用量在进程外此前**完全不可观测**
    （`TurnOutcome` 与 `TurnReceipt` 都不带它），而旧实现读的是 `AgentLoop._last_usage`
    这个私有属性。键名用复数形式，`D02` 的整词脱敏规则因此原样放行。顺带 JSONL 事件日志
    也有了用量记录。报出来的是**整条 turn 之和**（含工具往返），与 OpenAI 的单次调用语义
    不同，拿不到时**省略 `usage` 字段而不是报零**。
  - **保留集的修补原则是「删掉引用与它服务的那段代码」，不留空壳**：`command/` 删掉 dream
    家族 / `/goal` / `/trigger` 七个处理器（它们服务的子系统已不存在），`build_help_text()`
    与其余命令保留——`channels/{discord,telegram}` 的 `/help` 靠它；`config/schema.py` 的
    `tools` 小节六个按工具切分的子配置随 `agent/tools/` 一并删除，前向引用的
    `model_rebuild` 机制整套移除；`utils/restart.py` 把一个 webui 常量内联。
    **保留集的 167 个模块逐个 `import` 验证通过**，无悬挂引用。
  - **踩到并修掉的两个真问题**：① `ctx.turns` 在 `setup()` 期间**不可用**（orchestrator
    那时还没装好，`runtime/plugin_context.py` 会抛 `KERNEL_INVARIANT_VIOLATED`），因此
    取消门面只能惰性取——这条是测试先发现的；② manifest 的 `config_schema` 里 `port` 的
    `minimum` 写成 1 会让 `port: 0`（内核分配空闲端口）在阶段 A 就被拒，而那正是测试与
    「随便给我一个空闲端口」的部署要用的值。
  - **两条如实记着的边界**（写进插件 docstring、README 与本文档，不留给用户发现）：
    ① **同一 Channel 的 turn 是串行的**——装配根的泵要等上一条跑完才取下一条，因此并发
    客户端会排队，这是相对 `legacy/api/server.py` 的**能力回退**，修它要动
    `runtime/instance.py` 并重新回答 `EDG-202` 的严格 FIFO 断言；② 五种权限里**没有
    「监听端口」**这一种（`net` 判的是出站），因此这个插件声明不出与它实际行为对应的权限
    ——默认只绑回环，绑非回环地址时没配 `api_key` 直接以 `CONFIG_INVALID` 拒绝启动。
    **①  已由 `D33` 消除**（泵按 conversation 扇出），②  仍然成立。
  - 验收：**完整套件 4900 passed / 18 skipped / 0 failed**（`D30` 收口时新层 2238，
    另有 14–18 个既有失败落在网络、子进程时序与 oauth-cli-kit 家族——**那批用例全部位于被
    删除的目录里，因此这一轮真的是零失败**）。`ruff check`（src + tests + plugins +
    examples + scripts）、`basedpyright`（新层 0 报错，legacy 仍是既有 4 个，全在
    `skills/skill-creator/scripts/`）、`legacy_debt --check` 通过（基线已下调）、
    `check_startup_cost --check` 通过（`startup_ms` 约 500 ms，仍是 `D24` 记的那条
    `import httpx` 告警）。**legacy 债务 352 文件 / 133317 行 → 225 文件 / 77040 行**
    （降 42%）。真实 `nm --help`（无 legacy 子命令）/ `nm serve --bogus`（退出码 2）
    在开发机上跑通。


- **`D32` 官方插件：Anthropic 原生 Model Provider ★**（`plugins/nucleamind-plugin-anthropic/`
  六个模块约 1690 行 + 四个测试文件 124 个用例 + 删除 `legacy/providers/anthropic_provider.py`
  与 9 个 legacy 测试文件）：
  - **技术方案 §13 M5 五步法的第一次完整应用**：a 步的行为基线用的是 `tests/legacy/providers/`
    里既有的 12 个 Anthropic 相关文件（`D07` 的 `tests/baseline/` 已随 `D31` 删除，
    不为一个要删掉的实现再写一遍基线）；b/c 步是本插件；d/e 步同 PR 删除。
  - **本轮拍板的四件事**，逐条记在下面。
  - **① 落 `plugins/` 而不是 `builtins/`，用 raw httpx 而不是 `anthropic` SDK。** 前者：
    §7.3 的内建默认能力集不该因为多一个供应商而变长，而 `plugins.enabled` 天然就是闸门
    （与 `D31` 的 openai-api 同一条理由）。后者有三个后果都指向同一边：`transport=` 可注入
    让 `ModelProviderContract` 走 `httpx.MockTransport`、零真实网络（124 个用例一个 socket
    都不开）；宿主发行版因此把 `anthropic>=0.100.0` 从根 `pyproject.toml` 摘掉了；
    以及线格式的每一条规则都能在纯函数上逐字节钉住。
  - **② 一张按模型名版本号 gating 的表都不移植。** legacy 有四张
    （`_ADAPTIVE_ONLY_MIN_VERSIONS` / `_THINKING_DISABLE_MIN_VERSIONS` /
    `_SAMPLING_DEPRECATED_MODELS` + 解析版本号的正则），`D19` 拒过同类的 `max_tokens_field`
    slug 表，理由一个字没变：表只会越滚越大，而用户换一个新模型要等我们发版。改成
    `thinking.mode`（四取值一一对应线格式的四种形状）/ `supports_temperature` / `effort`
    三个配置项。**legacy 那两处「替用户改主意」的行为也一并拒掉**：thinking 开启时强制
    `temperature=1.0` 不做（答案是 `supports_temperature: false`）、`budget_tokens` 超了就把
    `max_tokens` 抬到 `budget+4096` 不做（直接 `CONFIG_INVALID`——抬完之后生效的上限就不是
    用户配的那个）。
  - **③ 能力声明与开关同源，两个方向都判死。** `describe()` 交出「配置基线 ∪ thinking 开着
    时的 `reasoning` ∪ 缓存开着时的 `prompt_caching`」；反过来**声明了 `reasoning` 却没开
    thinking 是 `CONFIG_INVALID`**。只做前一半的话，一份声明得漂亮的配置会让组装器以为
    拿得到一份它拿不到的东西，`MOD-005` 的「缺席即报缺失、绝不静默降级」只在一个方向上成立。
    做法与 `D20` 的 `enabled_tool_names(config)` 同源。
  - **④ `critical=False`。** 第二个 Model Provider 起不来不该让实例整个起不来——内建
    `openai` 仍在，装配根步骤 8 的必需能力判定照样通过。代价是配置错误只表现为
    `nm plugins` 里的一行 `PLUGIN_LOAD_FAILED`，因此配置校验仍在 `setup()` 里一次做完、
    不拖到第一次 turn（`D18` 的先例），是「响」而不是静默。
  - **工具名必须编码，这是与内建 `model_openai` 最大的一处线格式差异**（也是写之前没想到
    的一条）：`contracts/tool.py` 的工具名式样是点分命名空间（`fs.read`），而 Anthropic 的
    `tools[].name` 只收 `^[a-zA-Z0-9_-]{1,64}$`——`.` 直接 400。契约名恒不含 `-`，因此
    `.` ↔ `-` 是**无碰撞双射**，有一条「全部合法契约名往返恒等」的用例钉住。内建那句
    「`parameters` 已是 JSON Schema，原样透传」对参数成立、对名字不成立。
  - **`StopReason.STOP_SEQUENCE` 在全项目第一次可达**：`model_openai/wire.py` 的注释写着
    OpenAI 对「自然结束」与「撞上 stop 序列」都回 `"stop"`、线格式里没有第三种取值；
    Anthropic 明确分得开。`refusal` 同理走 `CONTENT_FILTER`，且它是 **HTTP 200 上的正常
    响应而不是异常**（`is_complete_answer` 因此为假）。
  - **usage 的输入侧必须三项相加**（`input_tokens + cache_creation + cache_read`）：线格式里
    的 `input_tokens` 只是**未命中缓存的余量**，不加会让报出去的输入量凭空少一大截（开了
    prompt caching 之后差得尤其远）。`reasoning_tokens` **恒为 0 且不估算**——Anthropic 不
    单独报它（含在 `output_tokens` 里），一个猜出来的数字会被当成实测值写进事件日志；
    `cache_creation_input_tokens` 进 `provider_metadata`，那是「缓存到底写进去没有」的唯一
    观测信号。
  - **交付六个模块而不是四个**（比内建 `model_openai` 多一个）：分界线仍是「碰不碰 IO」，
    但 Anthropic 的翻译量大得多——请求侧多了 system 提升、`tool_result` 折叠进前一条 user 轮、
    首尾 assistant 规整、工具名编码、`cache_control` 布点、thinking 四形态；响应侧多了 6 种
    SSE 事件 × 4 种 delta。合成一个 `wire.py` 约 800 行、正好顶在 `test_file_size.py` 的阈值
    上，因此按**方向**切成 `wire.py`（请求）与 `decode.py`（响应），共享的只有工具名 codec。
  - **SSE 只解析 `data:` 行、按载荷自带的 `type` 分派**，`event:` 行忽略：认两个真相来源会在
    中转改写 `event:` 时静默分叉。Anthropic 也没有 `[DONE]` 哨兵，迭代结束即流结束。
    `tool_use` 增量的身份键是 `index`（`id`/`name` 只在 `content_block_start` 出现一次），
    好消息是首帧就给全，因此内建那套「补一个 `call_auto_N` 并记进 metadata」的补救在这里
    根本不存在。
  - **测试文件被架构守卫逼着拆开**：一份 1209 行的用例文件撞上 `tests/architecture/
    test_file_size.py` 的 800 行上限（那条守卫对 `plugins/` 全目录生效，含测试）。拆成
    `test_wire.py` / `test_decode.py` / `test_anthropic_plugin.py` + 一个 `_support.py`。
    另一条被守卫挡下的是 `R4`：插件测试**也**不许 import `kernel/`，因此哨兵用例里那句
    `prepare_payload` 换成了对 `NucleaError` 各渲染面的直接断言（脱敏在构造时完成，
    结论不变）。零网络闸门是本项目第三份同判据实现，刻意不共享。
  - **删除清单**：`legacy/providers/anthropic_provider.py`（860 行）、`factory.py` 的
    `backend == "anthropic"` 整支与那条 `in {...}` 判断、`__init__.py` 的三处懒加载登记、
    `registry.py` 三条 `backend="anthropic"` 的 `ProviderSpec`（`anthropic` / `kimi_coding` /
    `minimax_anthropic`——留着会落进 factory 的 `else` 被 `OpenAICompatProvider` 静默错服，
    而这三家的能力已由插件的 `base_url` + `auth` + `beta_headers` 覆盖）、
    `config/schema.py` 随之失效的三个 `ProviderConfig` 字段；`tests/legacy/providers/` 整删
    9 个文件、部分删 6 个文件里的 Anthropic 用例（其余为 openai_compat / azure / bedrock
    提供覆盖，保留）。**根 `pyproject.toml` 摘掉 `anthropic>=0.100.0`**，全仓库
    `import anthropic` 零命中。
  - **未新增 `ErrorCode`**（`CONFIG_SECRET_MISSING` / `PERMISSION_DENIED` /
    `INPUT_TOO_LARGE` / `EXTERNAL_MODEL_PROVIDER` / `TIMEOUT_MODEL_REQUEST` /
    `CAPABILITY_MISSING` / `CONFIG_INVALID` / `CONFIG_UNKNOWN_FIELD` 够用），
    **未新增 `EventName`**，**未碰 `kernel/` 与 `contracts/`**。
  - **本轮不做与理由**：重试引擎与 fallback（编排层策略，两处都做会叠成放大器）、
    图像/文档输入（`ModelMessage.content` 是纯 `str`，契约层没有多模态位置）、
    server tools（会绕过 `ToolExecutor`，等于给模型开一条不受 `TurnLimits` 与权限约束的
    副作用通道）、结构化输出与 `tool_choice` 控制（契约里没有对应槽）、
    Bedrock / Vertex / Foundry（三套认证机制，不是一个 `base_url`）。
  - **一条如实记着的能力回退**：**thinking 块无法多轮回放**。Anthropic 要求续写时把
    `thinking` 块（含 `signature`）原样回传，而 `ModelMessage` 只有
    `role`/`content`/`tool_calls`/`tool_call_id`，**没有放 provider 私有块的槽位**，
    `signature_delta` 因此被吞掉。写进插件 docstring 与 README，不当成没发生；要修得先给
    `contracts/model.py` 加一个 opaque 块槽位——那是要走评审的冻结表面变更（`NFR-104`），
    列为下一轮的契约变更候选。
  - 验收：**完整套件 4938 passed / 18 skipped / 0 failed**（`D31` 收口时 4900 / 18 / 0）；
    插件自测 124 个用例 0.8 s。`ruff check`（src + plugins + examples + tests + scripts）、
    `basedpyright`（新层 0 报错，legacy 仍是既有 4 个）、`legacy_debt --check` 通过
    （基线已下调）、`check_startup_cost --check` 通过（`startup_ms` 仍是 `D24` 记的那条
    `import httpx` 告警）。**legacy 债务 225 文件 / 77040 行 → 224 文件 / 76136 行**，
    其中 `providers/` 从 14103 降到 13202。真实 `nm plugins list` / `nm capabilities` 在
    开发机上跑通：插件被发现、被加载，`model:anthropic → plugin:anthropic` 出现在生效集合里。
    **已知偏差**：插件目录不在 `basedpyright` 的 `include` 范围内（CI 只查 `src/nucleamind`），
    单独对它跑严格检查会在那份嵌套 JSON Schema 字面量上报一条 `reportArgumentType`——
    与官方插件 `openai-api` 同一类情况（它单独跑有 22 条）。本轮没有改 `include` 范围。


- **`D33` Channel 泵扇出 + 官方 Discord 插件 ★**（两个可分别回退的 commit：
  `kernel/routing/fanout.py` + `runtime/instance.py` 接线 ≈ 300 行 / 20 个新用例；
  `plugins/nucleamind-plugin-discord/` 八个模块约 1600 行 / 106 个用例 +
  删除 `legacy/channels/discord/` 2363 行）：
  - **Half A 修掉了 `D31` 明确推迟、四处文档如实记着的那条能力回退**：泵的 `await` 原来
    在 `async for` 里面，一条 Channel 同时只跑一条 turn、跨会话也串行。对 HTTP 接口它是
    排队，对聊天 Channel 它是「一个用户的慢 turn 卡住同一个 bot 上所有人」。
  - **① 按 conversation 扇出，不是每条消息 `create_task`。** 后者在 CPython 上其实也能
    保住 FIFO（ready 队列是 FIFO，且 `submit()` 在第一个 `await` 之前就同步入队），
    但那正是 `session_lock.py` 的 docstring 明文拒绝依赖的那类实现细节——项目已经为
    「不依赖 `Lock` 的唤醒顺序」付过一次钱，在泵这一层反过来依赖它就是把刚拆掉的东西
    装回去。**有界队列 + 一个 worker** 是同一份设计的延伸。
  - **② `EDG-202` 逐字成立而不是「大概成立」**：`InboundMessage.session_key(scope)` 的
    `scope` 是实例级常量、一条 Channel 上 `channel_id` 也是常量，因此
    `conversation_id ↔ SessionKey` 是**双射**，「每 conversation 一个 worker」与
    「每 session 一个 worker」是同一句话。已有的单写者不变量用例一个字未改地继续通过。
  - **③ `openai-api` 插件代码零改动**：`SessionHub` 的「同一 conversation 最老等待者」
    关联依赖同 conversation 内串行，而扇出保住了它（`_waiting` 是按 conversation 索引的
    deque，两条并发 turn 永远不碰同一个）。**但那五处「能力回退」的文档全部变成了假话，
    同 commit 改掉**，并在 `hub.py` 补了一段「为什么这条关联在新并发模型下仍成立」的
    书面证明——下一个人不必重新推一遍。
  - **④ 两个上界不与 scheduler 的 `queue_max_size` 串联**：lane 串行意味着同 session 在
    scheduler 里至多一个来自泵的等待者，因此 lane 队列是 Channel 流量**唯一生效**的界，
    没有 `D28` 那个「等了多久取决于两个数的最小值」的陷阱。`channel_queue_max_size` 取
    与 `queue_max_size` 相同的 32，让用户可见的积压容量一个字没变。
  - **⑤ lane 队列空即退出，没有 idle TTL**（`SessionScheduler._discard_if_idle` 的同一条
    判据）：`lanes()` 恒等于此刻有活儿的 conversation 数，没有后台计时器也没有泄漏。
    再发明一个「空闲 N 秒回收」就是第二套机制加第二个要调的数。
  - **⑥ 新增 `instance.input_dropped` 而不是复用 `turn.rejected`**：被扇出拒掉的消息
    **从未进过 orchestrator**，而 turn 事件只有那一个发布点，给它发一条会在事件流里凭空
    造一条 orchestrator 没见过的 turn（`OBS-002` 的按序重放随之作废）。背压是实例级现象，
    落 INSTANCE 族。`EventName` 快照 32 → 33 条。**`Channel.deliver` 因此可能被并发调用**
    （同 conversation 内仍不会），已写进契约 docstring。
  - **Half B 的 Discord 插件是第一个 Channel 插件，后续十几个照它写。**
    切分的支点是 `gateway.py`——**唯一** import `discord` 的模块，其余全是纯函数或对
    `Platform` / `Reactions` 两个 Protocol 编程，因此 106 个用例里只有一条需要碰 SDK
    （而且是验「没装它时说什么」）。legacy 的测试第 11 行是 `pytest.importorskip`，
    CI 没装依赖时 52 个用例静默全跳。
  - **不移植的四样，各有理由**：配对码流程（它服务的审批界面 `D31` 已随 WebUI 后端删除，
    新层的等价物是 `allow_from` + TOFU；**代价如实写进 README**：陌生人 DM 从「收到配对码」
    变成「被静默忽略」）、Discord 原生 slash command（命令只有 `routing/dispatcher` 一个
    来源，再注册一套会让「命令有几个来源」变成两个答案）、`ChannelSetupSpec` 与 WebUI 向导、
    发送重试（legacy 也没有，不发明一套）。
  - **新增 `operators` 配置键**：legacy 没有这个概念（它的 `allow_from` 就是全部权限），
    而契约要求 `Sender.is_operator` 由 Channel 在边界决定。默认空 = 无人是 operator，
    `/config` 这类命令因此默认不可用——那是安全的一侧。
  - **时长配置统一 `*_ms`**：legacy 的 `working_emoji_delay: 2.0` 与
    `_STREAM_EDIT_INTERVAL = 0.8` 数值一字不改，只换单位与命名。留一个秒制字段会让它
    成为新层配置里唯一的例外。
  - **thread 天然是独立会话**：`conversation_id` 取频道 id，而 thread 有自己的 id，因此
    `SessionKey` 已经表达完了，不需要 legacy 那个自造的 session key。
    **入站附件不下载**（契约只存引用，CDN 给直链），本插件因此一条 `fs:*` 权限都不需要。
  - **写这批用例时踩到并修掉的三个真问题**：① 契约在构造时就拒绝空正文的 `FINAL`
    （只有 `CANCELLED`/`FAILED` 允许空），因此「终态回退到累积文本」那条路只有中断/失败
    才走得到——而那恰好是最需要它的时候；② 注入的 `sleep` 替身**必须真的让出事件循环**，
    否则 `_type_loop` 的 `while True` 会饿死事件循环（整套用例挂住了一次）；
    ③ 开发环境里 `discord.py` 是装着的（legacy channel 的依赖），验「没装」要用
    `monkeypatch.setitem(sys.modules, "discord", None)`。
  - **两条如实记着的边界**：① **五种权限里没有「连接一个聊天平台」这一种**——`net` 判的是
    经 `ctx.net` 门面的出站请求，而 `discord.py` 自己开连接，因此本插件除两条 `secret` 外
    声明不出任何权限而它确实会连出去（与 `openai-api` 那条「没有『监听端口』」并列）；
    ② **出站 workspace 附件传不出去**（当时 `FileAccess` 没有 `read_bytes`；`D42` 补了它，
    但**这条边界没有因此消失**——新层至今没有任何地方产出带附件的出站消息，缺的是出站侧
    的附件通路）。发一条文本标记而不是假装发过。
  - **`kernel/config/schema.py` 又撞上 500 行上限**，把诊断视图 `to_json` 拆到
    `document.py`（`D13` → `fields.py`、`D24` → 六个 `*_at()`、`D28` → `defaults.py` 之后
    同一条规则的第四次应用：先挪走「只是把已有结构换个形状」的派生物，不动字段表）。
  - **`ruff` 的 `per-file-ignores` 补了插件测试树**：`TRY` 等阈值原本只豁免顶层 `tests/`，
    而插件是独立发行包、测试树不在那底下。理由与既有那条完全相同（阈值针对产品代码，
    不针对夹具），`anthropic` 插件只是碰巧没有 `raise` 才没暴露它。
  - 验收：插件自测 106 个用例、`tests/kernel/test_fanout.py` 16 个、
    `tests/runtime/test_instance.py` 新增 4 条（含「两个会话互不阻塞」与 `EDG-202` 的逐字
    断言）。`ruff check`、`basedpyright`（新层 0 报错，legacy 仍是既有 4 个）、
    `legacy_debt --check`（基线已下调）、`check_startup_cost --check` 全通过。
    **legacy 债务 224 文件 / 76136 行 → 218 / 73773**，其中 `channels/` 从 47762 降到 45399。


- **`D36` 官方 web 插件：`web.fetch` 与 `web.search`**（`plugins/nucleamind-plugin-web/`
  五个模块约 1100 行 + 四个测试文件 135 个用例 + `tests/e2e/test_web_tools.py` 7 个）：
  - **本轮拍板的三件事**，逐条记在下面。
  - **① 两个工具走两条不同的出网路径，判据是「谁决定了那个 URL」。** `web.fetch` 的 URL
    **整个来自模型**，因此走 `ctx.net`——`runtime/access/net.py` 的 SSRF 守卫（解析后逐地址
    判定 + 手动跟随重定向）正是为这种输入存在的（`EDG-406`），插件**不写第二份守卫**。
    `web.search` 的端点**来自运维配置**、模型只控制 query，而自托管 SearXNG 常在私有网段
    （`ctx.net` 会按设计拒掉它），因此直接用 httpx 并如实声明 `net`——与内建 `model_openai`
    要连本地 vLLM / Ollama 是同一条先例。**后果如实写在 README 里**：`web.search` 的请求
    不过守卫，那条 `base_url` 本身就是一个信任边界。
  - **② 13 个写死的搜索后端收窄成 4 个 + 一个可配置的 `custom` 通用 JSON 后端**
    （url + headers + 点分结果路径 + `{api_key}` 占位符）。理由与 `D19` 拒掉
    `max_tokens_field` slug 表、`D32` 拒掉四张版本 gating 表一字不差：**表只会越滚越大，
    而用户接一个新后端要等我们发版**。
  - **③ 默认后端必须不要凭据。** 外部插件用不上 `runtime/bootstrap.py` 的 `keep` 声明
    过滤（那张 `_ENABLED_NAMES` 按**内建 id** 索引），因此 manifest 声明的两条能力**恒被
    注册**；默认后端要凭据的话就成了 `D20` 明确拒过的「声明了却不可用」。于是默认是
    `duckduckgo`，自己解析它的 HTML 返回（旧实现依赖第三方包 `ddgs`）。代价：站点改版即
    失效，但失效的形态必须是「没有结果」而不是一次异常，有用例钉着。
  - **凭据刻意不在 `setup()` 里取。** `PLUGIN_LOAD_FAILED` 是**提供方级**的，在 `setup()`
    里因为缺一个搜索凭据而抛错会把 `web.fetch` 一起带走。因此凭据在第一次调用
    `web.search` 时才解析，缺失折成那一次调用的 `CONFIG_SECRET_MISSING`。代价如实记着：
    配置里少一个 `api_key` 不会在启动时报出来。有一条 e2e 用例断言这两件事同时成立。
  - **凭据缺失不静默回退到 DuckDuckGo**（旧实现会）。配了 tavily 却没给 key，得到的是一条
    指名道姓的错误，而不是一份来自另一个后端、看起来一切正常的结果（原则 7）。
  - ~~**抓回来的正文前那行横幅是提醒不是隔离。**~~ **`D42` 已解决**：`ToolResult.trust`
    落地，`fold_tool_result` 把它包成带来源标注的数据块，那行横幅（`UNTRUSTED_BANNER`）
    已删。当时的记述是：「`ToolResult` 没有 trust 字段，
    `contracts/context.py::as_model_text` 的包裹只作用于 `ContextFragment`，一段写着
    「忽略以上指令」的网页仍然会原样进模型」——这条**列为契约变更候选之后真的被做了**。
  - ~~**`ctx.net` 不能流式**~~ **`D42` 已把上界挪到读取上**（`request(max_bytes=…)`）。
    当时的记述是：`fetch.max_bytes` 作用在解码之前但那些字节已经进过内存，无法按字节提前
    中断。**完整的流式接口仍然没做**（没有消费者），因此这条只解决了一半。
  - **正文抽取用标准库 `html.parser`，不是浏览器**：JS 渲染的内容、表格的视觉布局、CSS
    隐藏的节点都拿不到或分不清，如实写在 docstring 与 README 里。踩到并修掉的两个真问题：
    ① 未知 charset 退回 UTF-8 时**先严格试一次**，否则一份完好的正文会带上「可能有乱码」
    的假警报；② `</li><li>` 连着产出两个换行会让每两条列表项之间空一行——`_break()` 因此
    先丢掉标签之间的缩进空白再判重。
  - 验收：新层 135 + 7 个用例；`ruff check`、`basedpyright`（新层 0 报错）、
    `tests/architecture` 56 个全绿。一个 socket 都不开。

- **`D37` 官方 image 插件：`image.generate`**（`plugins/nucleamind-plugin-image/`
  五个模块约 950 行 + 三个测试文件 87 个用例 + `tests/e2e/test_image_tool.py` 4 个）：
  - **按模型名分支的表一张都没搬**（旧实现的 `_aihubmix_size`、`_ollama_dimensions`、
    `_round_to_multiple`）。对应物是 `size` / `response_format` / `extra_body` 三个显式
    配置项，**留空即不发这个字段**。实践上：`gpt-image-1` 恒回 base64 且会**拒绝**
    `response_format`，`dall-e-3` 要写 `b64_json` 否则回一个有期限的 URL（插件会去取，
    多一次往返，两条路都有用例）。
  - **三个后端类收窄成两个形状差异大的**：`openai` 的专用图像端点与 `openrouter` 的
    chat-with-image；第三家用 `provider="openai"` + `base_url` 接上（aihubmix 与多数网关
    本来就是 OpenAI 兼容的）。
  - **产物落盘 + `ArtifactRef` 引用，文件名内容寻址**（`image-<sha256 前 16 位>.<ext>`）：
    同样的字节永远落在同一个文件上（重跑不堆图），而文件名里**不含 prompt**——prompt 可能
    很长、可能带路径分隔符，也可能包含用户不想留在文件系统上的内容。写走「同目录临时文件
    → `fsync` → `os.replace`」。
  - **`side_effect` 只有两档**：落盘**之前**失败一律 `NONE`，写成功 `OCCURRED`。
    **本工具从不产出 `UNKNOWN`**——`os.replace` 成功之后没有可失败的步骤，替换之前一个
    字节都没到目标路径上。**取消不删已落盘的图**：取消不是回滚，而那些字节是用户已经
    付过钱的。
  - **三条如实记着的边界**：① **`ToolResult.artifacts` 今天在全项目零消费者，本插件是它的
    第一个生产者**——`OutboundMessage` 的附件路径没有生产者，因此没有任何 Channel 能把这些
    字节发出去（当时也记了「`FileAccess` 没有 `read_bytes`」，`D42` 补了它而**这条边界没变**
    ——缺的是出站侧的附件通路）；
    ② **不用 `ctx.fs`**：当时记的原因是它只有文本面，**那只对了一半**；真正的原因是
    `ctx.fs` 的根是 workspace 而图落在插件自己的 state_dir，两个目录树。因此即使 `D42`
    补了 `write_bytes`，这里仍然如实声明 `fs:write` 并直接用 `pathlib`（`session_jsonl` 先例）；
    ③ **不用 `ctx.net`**，图像端点由运维配置（要能连本地 ollama），而**模型在这里决定不了
    任何地址**——这与 `web.fetch` 恰好相反。
  - **`setup()` 不创建目录**：为一个可能永远不被调用的工具建目录，是在没人要求的时候动
    用户的磁盘。有一条用例钉着。
  - **语音转写（旧实现的 `providers/transcription.py`）不做**：它是另一类能力（音频输入），
    而契约层今天没有多模态输入位置。参考图 / 图生图同理（`D42` 之后 `FileAccess.read_bytes`
    已经有了，但缺的是**多模态输入位置**，不是读字节的方法）。
  - 验收：新层 87 + 4 个用例；e2e 那条走**真实装配根**，断言图落在
    `<instance>/plugins/image/images/` 里——落点由装配根分配，插件自己只知道 `ctx.state_dir`。

- **`D38-A` 命名空间声明机制 ★**（`sdk/manifest.py` + `kernel/plugins/{declarations,host}.py`
  + `runtime/wiring.py` 各一处 + `docs/plugin-development.md` §7.5 + 四个测试文件 20 个新用例）：
  - **它解决的问题是硬的**：`CapabilityHost.finish()` 要求 manifest 声明的 `(kind, name)`
    与实际注册的**逐条相等**（`D16` 的不变量），而桥接类插件（MCP、远端工具网关）的能力名
    要连上外部服务、`list_tools()` 之后才可知，manifest 又是静态的。
  - **取的是「扩机制」而不是「退化成单条 `mcp.call` 代理工具」**：后者会让模型拿不到每个
    远端工具的 JSON Schema，参数校验从 kernel 的 `ToolInvoker._compile()` 退到运行期，
    工具选择质量也随之下降。
  - **形状先例就在 `host.py::on()`**：Hook 早就是「一条声明、N 次注册」（`<hook>.2` / `.3`
    派生名按基名回查声明）。命名空间是同一形状的推广。**做成显式布尔而不是
    `name="mcp.*"` 通配串**：后者会让「名字」这个字段有两种含义，而 `CapabilityRef` 的
    形状校验对通配串又不成立（原则 7）。
  - **五条判死的规则**：① 只放行 `<前缀>.<后缀>`——前缀本身与 `mcpx.read` 都不在内
    （比较落在分隔符边界上，`WorkspaceGuard` 的路径前缀同一条道理）；② **精确声明优先**，
    两条命名空间同时匹配是 `PLUGIN_LOAD_FAILED`（静默择一等于让加载顺序说了算，
    `EDG-102` 在这一层的对应物）；③ **命名空间豁免 `finish()` 的兑现检查**，且这条豁免是
    **结构性的**——`_declared` 里根本没有命名空间声明（分成两张表就是为了让规则只有一条）；
    ④ 不得与 `overrides` 并存（一条声明能注册出任意多个名字，哪一个是覆盖者无从判定）；
    ⑤ 只允许 arity 为 `MULTI_UNIQUE` 的 kind，**判据取自 `CAPABILITY_ARITY` 而不是手写
    名单**——那张表已经是全部冲突语义的唯一来源，另写一份必然分叉。
  - **registry 的冲突语义与权限模型一个字未改**：仍按精确 `(kind, name)` 判，
    `nm capabilities` 印的是**实际注册的**名字；`namespace` 不放宽任何权限。
  - **翻译只在 `runtime/wiring.py` 一处**（`R2` 决定的），漏掉那个字段的后果是插件在
    `setup()` 里注册第一条工具时就被判成「未声明」，有一条用例钉着。
  - `docs/plugin-development.md` 的 §7.5 由 `tests/e2e/test_plugin_docs.py` **直接执行**。

- **`D38-B` 官方 mcp 插件**（`plugins/nucleamind-plugin-mcp/` 七个模块约 1200 行 +
  两个测试文件 99 个用例 + `tests/e2e/test_mcp_namespace.py` 7 个）：
  - **它是 `D38-A` 的第一个使用者**：manifest 只声明
    `CapabilityDecl(kind=TOOL, name="mcp", namespace=True)`，两条远端工具名一个字都没写。
  - **连接必须由一条后台任务拥有，这是本插件最要紧的一个设计决定**（`supervisor.py`）。
    `mcp` 的三种传输都建在 anyio 的任务组上，而**任务组必须在进入它的那个任务里退出**——
    在 `setup()` 里 `enter_async_context`、再由停止路径 `aclose()`，会炸出
    `Attempted to exit cancel scope in a different task`（参考实现为此写了
    `_OwnedMCPConnection`）。而本插件**没有第二条清理通道**：manifest 没有 teardown 字段，
    `EDG-105` 的痕迹清理只作用在 `ctx.spawn_task()` 派生的任务上。形状因此定成：
    `setup()` 派生任务 → 等它把工具表准备好 → 注册 → 返回；停止时取消它，`finally` 在
    **同一个任务**里关掉 `AsyncExitStack`。**`setup()` 因此是 `async` 的**
    （`builtin_loader.py` 早就写着同步异步都接受）。
  - **工具名归一化会丢信息，因此必须处理撞车**（`get-file` 与 `get_file` 撞成同一个名字）。
    **撞车的各方都不生效**并写日志，与 registry 对同名冲突的判定一致；旧实现靠 `hashlib`
    生成后缀。**这与 `D32` anthropic 那条「`.` ↔ `-` 编码」结论相反**——那是无碰撞双射。
  - **只桥接 tools，不桥接 resources / prompts**（旧实现三样都做）：新层没有对应的能力
    种类，把它们伪装成工具会让模型拿到一堆语义不明的调用（原则 3）。**热重载也不做**
    （旧实现的 `RUNTIME_CONTROL_MCP_RELOAD`）：registry 解析后只读且首版不热更新，
    只在自己那一层成立的「重载」会让 `nm capabilities` 印的东西与实际生效的不一致。
  - **新增 `ErrorCode.EXTERNAL_TOOL_SERVER`**（→ `EXTERNAL_SERVICE`）。它既不是 HTTP
    专属（stdio 一个字节的 HTTP 都没有），也不该混进 `EXTERNAL_CHANNEL`——后者说的是
    「消息发不出去」，这里说的是「一次工具调用没能给出结论」。
  - **四条如实记着的边界**：① **`side_effect` 恒为 `UNKNOWN`、`read_only` 恒为 `False`**
    ——MCP 协议不报告副作用，远端的 `annotations.readOnlyHint` 是**它自己说的**，而它正是
    那个不可信的一方；失败分两档（发起**之前** `NONE`、发起之后 `UNKNOWN`），谎报 `NONE`
    会让编排层以为可以安全重试一次可能已经生效的写操作；② **权限模型对它基本失效**——
    声明了 `shell` 与 `net` 但那两条挡不住任何东西（stdio 要长驻子进程与管道而 `ctx.shell`
    是一次性 exec、HTTP 由 SDK 自己开连接），**真正的边界是「你配了哪些 server」**；
    ③ 连接在启动路径上，每台 server 都加上它自己的连接时间（`connect_timeout_ms` 是上界，
    超时即跳过，且**不取消那条任务**——取消会把已经连上的一起关掉）；④ 停止预算是每插件
    5000 ms，赖着不退的 stdio server 会让 `StopOutcome.timed_out` 为真。
  - **只有 `client.py` import `mcp`**，其余全部对 `session.py` 的两个 Protocol 编程，
    因此 99 个用例在**没装 `mcp` 的环境里全绿**（CI 用 `--no-deps` 装插件）。有一条 **AST**
    守卫扫 import 语句（不是文本包含——docstring 里提到 `mcp` 是正常的），外加一条自证用例。
  - 验收：新层十个测试目录共 **3116 passed / 10 skipped / 0 failed**；`ruff check`
    （src + plugins + examples + tests + scripts）、`basedpyright` **0 errors**、
    `tests/architecture` 56 个、`check_startup_cost --check` 全通过。
    **`startup_ms` 读数约 800–870 ms**（`D31` 时约 500 ms）：`startup_import_ms` 约 480–530、
    `bootstrap+start` 约 320–340。**大头仍是 `D24` 记的那条 `import httpx`**；
    另一项可测量的是 entry point 枚举约 **50 ms/次**，它扫的是**整个 site-packages** 而不是
    我们的插件数（本轮多装 3 个插件的增量可以忽略）。这一项按 `NFR-405` 原文只告警不失败。

- **`D39` 官方插件 `memory`：跨 Session 的长期记忆 ★**（`plugins/nucleamind-plugin-memory/`
  八个模块约 1500 行 + `sdk/testing/contracts.py` 的第 6 个契约基类 +
  `tests/sdk/` 两处快照与一个反向样例 + 插件自己 230 个用例）：
  - **本轮拍板的五件事**，逐条记在下面；`kernel/` 与 `runtime/` **一行未改**。
  - **① 形状定为「插件自洽」，因为探查发现 `CapabilityKind.MEMORY` 至今没有 kernel
    消费者**：`memory_providers_from()` 除测试外没有调用方、`runtime/bootstrap.py` 从不取它、
    `kernel/turn/context_builder.py` 只认 `ContextProvider`——**只注册一条 `MEMORY` 能力，
    记忆永远进不了模型**。于是一份 manifest 声明四类能力，四者共用同一个 `MemoryStore`：
    `MEMORY:jsonl`（契约形状，给第三方换后端一个可对照、可被新契约基类驱动的目标）、
    `CONTEXT:memory`（记忆真正进上下文的**唯一**路径）、三条 `TOOL:memory.*`、
    `COMMAND:memory`。另一条路是给装配根加「选哪一个 MemoryProvider」的配置与 `MEM-003`
    的降级策略——那是核心扩张，本轮刻意没做，**这一点写在 README 与 docstring 里，
    不假装它已经接上了**。
  - **② 分区只用召回路径真的拿得到的身份**（`partition.py` 是唯一映射点）：
    `session` → `SessionKey.storage_id()`（复用已发布的编码契约）、`workspace` →
    `SessionKey.scope`、`agent` → 一份。**`FragmentScope.USER` 拒绝写入并说明原因**：
    `SessionSnapshot` 里一个 sender 字段都没有，折成「按 conversation 存」会让群聊里 A 的
    用户记忆被召回给 B——那是真实的隐私泄漏，静默降级比报错危险得多。
    记录标识是 `<scope>-<token>#<seq>`，`#` 不在 `storage_id()` 的安全字符集里，
    因此切分不可能切错位置（与 `storage_id()` 用 `~` 是同一条推理）。
  - **③ 存储照搬 `builtins/session_jsonl` 的 `committed_bytes` 提交水位**，检索是自写打分
    （`scoring.py`，TF-IDF 式 + `sqrt` 长度归一；英文按词切、**CJK 按字符二元组**切——
    无词典的折中，会有「模式深色」部分命中「深色模式」这类误召回，如实写在 README 里）。
    记忆是 10²–10³ 条量级，全量扫描是毫秒级，为它上索引或引入向量后端都是过早抽象
    （后者还需要一次 embedding 调用，而**插件今天发不起模型请求**）。**`forget()` 真的删**：
    重写整个分区文件，不留墓碑——`MEM-005` 要的是删除，而墓碑不是删除。
  - **④ 一切写入统一 `trust=UNTRUSTED` 并忽略调用方声明的 trust**
    （`record.from_fragment()`，本插件唯一一处刻意不采纳调用方声明的地方）：
    `/memory add` 敲进来的内容与模型写的一样不可信，群聊里任何人都能敲那条命令。
    召回内容因此恒被 `as_model_text()` 包成 `<untrusted-data>` 数据块（`EDG-306`）。
    **`sensitivity=SECRET` 直接拒绝写入**——组装器本来就不会把它送进模型，存进去只是一条
    永远召不回来、却躺在明文文件里的记录。
  - **⑤ 召回片段的 `priority` 必须 > 0，且一条记录一个片段**：`HISTORY_TRIM_PRIORITY` 是 0
    而组装器按 priority **逆序**丢弃，记忆排在历史之前被丢是刻意的（记忆下一轮还能重新
    召回，历史丢了就是丢了）；拼成一大块就只能整块留或整块丢，`dropped` 的记账也失去精度。
  - **一处冻结表面变更**：`sdk/testing` 新增 **`MemoryProviderContract`**（第 6 个契约基类）。
    `MEM-001`「Kernel 只依赖接口、不假设后端」的全部意义就是后端可替换，而在此之前
    **唯独 `MemoryProvider` 没有可执行的契约基类**，那句话只是文档。按 `D30` 立的规矩同时
    加了一个反向样例（`_RecallsInInsertionOrder`：按插入顺序返回——契约写死「顺序即相关性」，
    而按插入顺序返回是最省事、也最难被发现的一种违约）。代价是 `sdk.testing.__all__` 的两处
    字面量快照；**`sdk.__all__` 一个字未动，`CapabilityKind` 一个取值未加**。
  - **本轮抓到的一个真 bug，它值得单独记**：`CommandHandler.handle` 收
    `(invocation, cancel)` 两个参数，而第一版只写了一个。**49 个命令用例全绿**——它们直接用
    一个实参调 `handle()`，测的是「我自己写的那个签名」而不是「kernel 会怎么调」；
    真实表现是 `nm run` 下一条 `kernel.unexpected` + `TypeError`，**只有跑真实 CLI 才暴露**。
    `isinstance` 对 `runtime_checkable` Protocol 只查属性存在性，而 basedpyright 的
    `include = ["src/nucleamind"]` **把全部插件排除在类型检查之外**。补的守卫是
    `test_memory_plugin.py` 里一条 `inspect.signature` 逐个比对注册实现与契约 Protocol 的
    用例，**下一个插件照抄它**；命令用例也全部改成 kernel 的调用形状。
  - **零新依赖、零权限扩张**：只声明 `fs:read` / `fs:write`（`FileAccess` 没有追加、
    `fsync` 与原子替换，与 `session_jsonl` 逐字同一条先例）。不出网，因此**没有**那份零网络
    autouse 夹具。`critical=False`——没有长期记忆的 Agent 仍然能对话，那正是 `MEM-003` 的
    降级形态。
  - **参考实现里刻意没搬的三样**（`references/nanobot/nanobot/agent/memory.py` 1221 行）：
    **Dream**（定时让 LLM 读历史、增量改写长期记忆）——它要「插件能发起模型调用」，
    而 `PluginContext` 没有这条通道，定时触发又是 `D40`；**GitStore**（记忆变更的版本历史）
    ——它要求把记忆存成 Git 仓库里的文本文件，那会把存储形态钉死成一种后端；
    **`SOUL.md` / `USER.md` / `MEMORY.md` 三份固定文件**——那是 Agent 人格与用户画像，
    属于 `builtins/context_basic` 的运维指令那一档，不是长期记忆机制。
  - 验收：新层十个测试目录 + 八个插件共 **3351 passed / 10 skipped / 0 failed**
    （`D38` 收口时 3116）；`ruff check`（src + plugins + examples + tests + scripts）、
    `basedpyright` **0 errors**、`tests/architecture` 56 个、`check_startup_cost --check`
    全通过（`startup_ms` 读数约 470 ms，本机比 `D38` 记的 800–870 低，告警仍是那条
    `import httpx`；**未启用的插件零导入开销**这条没松动）。
    **端到端在开发机上真的跑过**：`nm plugins list` 发现 → `nm plugins enable memory` →
    `nm capabilities` 六条全在 → 一次真实 turn 里模型调 `memory.remember` 写盘 →
    **换一个进程**再问，那条记忆以 `<untrusted-data source="plugin:memory">` 出现在请求里 →
    `/memory list|search|show|forget` 与别名 `/mem` 逐条验过。
- **`D40` 官方插件 `cron`：定时任务 / Automation ★**（`plugins/nucleamind-plugin-cron/`
  九个模块约 1600 行 + 插件自己 230 个用例）：**M5 的最后一项，`kernel/`、`runtime/`
  与 `sdk/` 一行未改，一个新依赖都没引入。**
  - **它解决的是一个此前根本不存在的能力**：在此之前**所有** turn 都由外部输入触发
    （人敲字、平台来消息、HTTP 请求进来），没有任何机制能让实例在没人说话的时候自己开一条
    turn。提醒、每日汇总、CI 跟进因此做不出来。
  - **① 调度器就是一条 `CHANNEL`，`receive()` 本身是调度循环。** Channel 的入站是**拉模型**
    （契约原文），因此 `receive()` 可以直接是「睡到下一个到期时刻 → yield 一条
    `InboundMessage`」的异步生成器：`AgentInstance.start()` 已经会 `channel.start()` 并为它
    派生泵，而泵把消息投进 lane 之后**立即回来接着拉**（`_fanout_for`），一条跑十分钟的 turn
    不会堵住调度。于是本插件**既不需要 `ctx.spawn_task` 也不需要 Hook**——本文档原先那条
    「依赖后台任务与 Hook」的备注写在 `D33` 的 Channel 泵扇出落地之前，现在有更短的路。
  - **② 任务绑定创建时的会话，结果由原 Channel 投递回去。** `Origin` 取自
    `ToolInvocation.correlation.session_key` / `CommandInvocation.correlation`，只存
    `channel_id + conversation_id`（`scope` 是实例级常量 `deps.scope`，存下来只会与配置
    分叉）。到期时构造一条**寻址到原会话**的 `InboundMessage`：turn 因此跑在原会话里、
    历史连续，出站按 `message.channel_id` 路由回那条 Channel 是 Kernel 既有行为。
    「每天 9 点在这个群里提醒我」因此不需要任何新机制。
  - **③ cron 表达式自己解析**（`expr.py`，标准 5 字段，`* , - */n` 与三字母星期/月份名，
    日与星期都被限定时取 POSIX 的**并集**）。不引入 `croniter`：CI 用 `--no-deps` 装插件，
    依赖它会让所有涉及表达式的用例在 CI 里跑不起来；`L`/`W`/`#`/`@别名`/秒字段**报错而不是
    静默当字面量吞掉**。**时区名解析只在 `settings.py` 一处且可注入**，`expr.py` 与
    `schedule.py` 只接受已解析的 `tzinfo`——因此**整棵测试树不依赖 tzdata**，DST 用例用手写的
    `tzinfo` 子类驱动，验的是真的跳表行为（不存在的墙钟跳过、重复的只取 `fold=0`）。
  - **④ 错过的运行默认跳过，一个旋钮表达两种行为。** `catch_up_window_ms` 默认 0（不补，
    按 now 重排）；> 0 时错过的到期时刻落在窗口内则**补跑一次而不是逐次补齐**。一次性任务
    过期标 `MISSED` 并停用，**不静默消失**。
  - **⑤ 运行历史记的是「派发」不是「turn 的成败」。** 泵吞掉 `TurnReceipt`，而按
    `session_key` 关联 turn 事件分不清同会话的并发 turn。README 与 `/cron show` 的输出里
    都这么写着，**不假装看得到结局**。
  - **⑥ 任务表损坏时进降级态而不是抛异常。** `AgentInstance.start()` 里的
    `await channel.start()` 没有 try/except，在那里抛会连 CLI 一起带走，而 `BAS-009` 要求
    任何配置下都有本地交互入口。因此：零任务、不调度、任何改动都以
    `PERSISTENCE_READ_FAILED` 拒绝并指向那份 `.corrupt-<时间戳>` 备份，**不用空表覆盖**。
  - **本轮踩到的三个真问题**（都由用例逼出来）：**(a)** 工具原先自己调 `datetime.now()`，
    于是注入的时钟只管调度循环，「排一条一分钟后的任务」跑去和真实墙钟比——收口成
    `CronScheduler.now()` 这**一个**时钟出口；**(b)** `datetime.astimezone(tz)` 在
    `tz is self.tzinfo` 时直接返回自身（CPython 短路），因此「这个墙钟时刻存在吗」的往返
    判据**必须绕一次 UTC**，否则恒真、春季跳表那天会排出一个不存在的时刻；
    **(c)** 全文扫 `L`/`W` 会把 `jul` 与 `wed` 一并拒掉，判定必须落在取值粒度上。
    另外 `due_decision` 需要一条与补跑窗口**分开**的「醒晚了」容差
    （`DUE_TOLERANCE_MS`，5s）——没有它，默认配置会把每一次正常触发都判成过期。
  - **参考实现里刻意没搬的三样**（`references/nanobot/nanobot/cron/` 830 行 service +
    294 行 tool）：**heartbeat**（`HEARTBEAT.md`，用一条普通任务加一句「没有要紧的就回一个
    字」即可表达）、**local trigger**（`nanobot trigger <id>`，它要进程外入队通道与至少一次
    投递语义，是另一件事）、**`CronPayload` 那六个投递字段与整套 legacy 兼容分支**
    （出站按 `channel_id` 路由是 Kernel 既有行为，插件不需要自己认路）。
  - 验收：新层十个测试目录 + 九个插件共 **3583 passed / 10 skipped / 0 failed**
    （`D39` 收口时 3351）；`ruff check`（src + plugins + examples）、`tests/architecture`
    56 个、`check_startup_cost --check` 全通过。
    **端到端在开发机上真的跑过**（替身 SSE 模型端点 + 临时实例）：
    `nm plugins enable cron` → `nm capabilities` 五条全在 → 一次真实 turn 里模型调
    `cron.schedule` 排下一条 15 秒任务（origin = `cli/local`）→ `nm serve` 常驻 45 秒，
    **三次到期各注入一条 turn，答复回到 CLI 会话**、`history` 三条 `dispatched` →
    `/cron list|show|pause|resume|run|rm` 与 `list all` 逐条验过（`show` 里能看到一条
    进程停机期间产生的 `skipped`，那正是默认不补跑**被看见**的样子）→
    `catch_up_window_ms=600000` 后重启，错过的运行**只补跑一次** →
    把 `jobs.json` 写坏：实例照常启动、`/cron list` 明说损坏并点名备份、
    `jobs.json.corrupt-<时间戳>` 留在原处。

- **`D41` 守卫 CI 清单与类型检查范围，并把插件纳入 basedpyright**（无新模块，两条守卫 +
  一处真实缺陷）
  - **先修了一个 CI 一直红的真问题。** `pytest` 的 `testpaths` 收集整个 `plugins/`，
    而每棵插件测试树第一行就 `import nucleamind_plugin_<id>`；`web` / `image` / `mcp` /
    `memory` / `cron` 五个插件从没进过 `ci.yml` 的安装清单，所以那约 1100 个用例在 CI 里
    **不是「少跑几个」，是收集期 `ModuleNotFoundError` 直接中断整个作业**。卸载 `cron`
    复现验证过（`Interrupted: 7 errors during collection`）。本地装了插件所以没人看见。
    `a7bda23` 补齐清单，`D41` 加守卫堵复发。
  - **两条守卫**（`tests/architecture/`）：`test_ci_plugin_list.py` 断言 CI 的安装清单 ==
    `plugins/` ∪ `examples/plugins/` 下有 `pyproject.toml` 的目录集合（不解析 YAML——
    架构守卫刻意不装可选依赖，正则扫原文即可，读的就是人会去改的那几行）；
    `test_type_check_scope.py` 断言 basedpyright 的 `include` 覆盖两棵插件树、`exclude`
    **恰好等于** import 了 CI 缺席 SDK（`discord` / `lark_oapi` / `mcp`）的模块集合。
    两条各带一个**自证用例**：找不到任何插件 / 任何 SDK 边界模块时失败——一条恒真的断言
    在报表里也是绿的。后者顺带钉住了 `D33` 定下的「每个插件只有一两个模块碰 SDK」。
  - **纳入范围当场抓到一个真缺陷**：`sdk.EventHandler` 声明
    `Callable[[RuntimeEvent], Awaitable[None]]`，而 `EventBus` 的订阅面本来就是同步的，
    官方插件 `feishu`（工具提示）与 `openai-api`（用量统计）注册的都是同步 handler。
    `PluginEventBridge` 无条件把返回值喂给 `create_task`，于是同步 handler 先被正常调用、
    再在一条无人认领的 Task 里 `await None` 抛 `TypeError`，只留下一句
    "Task exception was never retrieved"。**这与 `D39` 漏掉 `handle(invocation, cancel)`
    是同一类：测试全绿而实际会炸。** 修法是放宽返回类型为 `Awaitable[None] | None`，
    桥接层按**返回值**分派（不是 `iscoroutinefunction`——它认不出 `partial`、`__call__`
    是 async 的对象、返回协程的普通函数）；同步 handler 就地跑完、不派生 Task、
    无 loop 时也照跑（`dropped` 只记协程那一半）。
  - **`sdk.ManifestJsonSchema`**（进 `sdk.__all__`）：八个官方插件的 `config_schema` 在
    严格模式下全部报 `reportArgumentType`。四个候选逐个试过并记在
    `sdk/manifest.py` 里：`contracts.JsonValue` 进不了 pydantic 模型
    （`typing._eval_type` 在生成 core schema **之前**就 `RecursionError`）、pydantic 自带的
    `JsonValue` 用**不变的 `list`**（`sorted(...)` 赋不进去，双向推断够不着函数调用的返回
    值）、`TypeAliasType` 的具名递归 basedpyright 1.39 不认、只放宽一层会让深度 1 与深度 2
    的坏值报出两套说法（pydantic 的 union 校验在字段校验器**之前**跑）。结论：类型只说
    「是个 JSON 对象」，递归判定归 `PluginManifest._check_config_schema`（报 JSON Pointer、
    带深度上界——自引用文档在类型上完全合法），对外的收窄出口只有
    `PluginManifest.json_schema` 一处。
  - 其余 45 条是 `Unknown` 泄漏，按既有的 cast-after-isinstance 形状收在边界上，
    外加 13 处「声明 `Mapping` 而工厂是裸 `dict`」的 `default_factory` 参数化。
  - 验收：`basedpyright` **0 error（215 个文件，含两棵插件树）**、`ruff` 全绿、
    **3606 passed / 10 skipped**；`tests/architecture` 65 个。

- **`D42` 三条冻结表面变更 + 发布 SDK 1.0.0**（三条都被两个以上官方插件真实撞过，
  合成一次 `NFR-104` 评审）
  - **A. `ToolResult.trust`**（`contracts/tool.py`）。在此之前工具结果一律以裸文本进
    tool 消息，于是 `web.fetch` 抓回的网页与 `memory.recall` 召回的记录只能靠工具自己加
    一行**提醒性**横幅——那挡不住「忽略以上指令」，两个插件的 README 里都如实写着
    「是提醒不是隔离」。现在隔离由契约层完成：默认 `UNTRUSTED`（安全的那一个），
    只接受 `SYSTEM` / `UNTRUSTED` 两档（`OPERATOR` / `USER` 在工具结果上没有意义）；
    `ToolResult.as_model_text(source=…)` 与 `ContextFragment` 共用
    `contracts.context.wrap_untrusted`（**从后者提出，全项目唯一实现**）；
    `fold_tool_result` **在截断之后**包裹（先包再截会把闭合标记截掉），`source` 取
    `call.name` 而不是工具自报的字段。声明 `SYSTEM` 的都是「正文是自己的话」：Kernel 四条
    合成结果、`fs` 的写回执与失败、`shell` 起不来、`image`、`mcp` 的本地失败、`memory` 的
    写回执、`cron` 的 schedule/cancel；**`cron.list` 反过来声明 `UNTRUSTED`**——它原样印
    任务正文，那是创建者写的。`web` 的 `UNTRUSTED_BANNER` 与 `memory` 召回时自加的提醒
    一并删除。
  - **B. `FileAccess.read_bytes` / `write_bytes`**（`sdk/api.py` + `runtime/access/files.py`）。
    `read_text` 用 `errors="replace"`，因此它对一个 PNG 也「成功」，只是内容变了。
    **顺带纠正了 `image` 一条误导性注释**：它用不上这两个方法，真正的原因是落点在
    state_dir 而 `ctx.fs` 的根是 workspace——两个目录树，不是缺个方法。原来的注释把原因
    记成「没有 `write_bytes`」，只对了一半；补完方法之后重新看一遍才分清。
  - **C. `HttpAccess.request(max_bytes=…)` + `HttpResponse.truncated`**。`web.fetch` 的
    `max_bytes` 原来只在整份响应体进过内存**之后**才切一刀，对着一个几百 MB 的 URL 等于
    没有上界。现在上界落在**读取**上（有上界时走 `client.stream()`，到量即 `break`），
    「正好等于上界且流已尽」不算截断。**完整流式刻意没做**：今天没有消费者——两个 provider
    消费 SSE 走 raw httpx，`openai-api` 产出 SSE 用 aiohttp——而守卫的重定向重校验正发生在
    响应头与响应体之间，为一个没有消费者的用例设计要长期兼容的接口只能设计错。
  - **SDK 1.0.0**。0.x 的条件写的是「`D30` 插件里程碑达成后」；`D30` 之后又过了十一个官方
    插件，`D41` 把它们全部纳入类型检查、`D42` 补齐了它们撞出来的四个缺口。
    `tests/sdk/test_version.py` 那条「发 1.0 时本用例会失败——那是刻意的提醒」**真的失败过
    一次**，顺着它确认承诺可兑现，然后换成 `major == 1`（`major == 2` 时同样会失败）。
    十一个 manifest 的 `sdk_range` 一并改为 `>=1.0.0,<2.0.0`。**如实记着**：那四个缺口是
    `D41`/`D42` 才发现的，说明此前「表面已稳定」判断过一次早——1.0 承诺的是**从现在**起
    不再破坏性变更，不是追认此前每一版都对。
  - **本轮改动的爆炸半径只有 6 条用例**（`trust` 默认 `UNTRUSTED` 之后）：一条字段可追溯性
    快照、两条用**消息**长度验截断的 engine 用例（改成验 `result.content`——预算作用在结果
    正文上，包装那几行是常数开销）、两条 folding 用例、一条 e2e。都不是意外，都是断言口径
    需要跟着改。
  - 验收：`basedpyright` 0 error、`ruff` 全绿、**3628 passed / 10 skipped**。

- **`D43` `channel.delivery_failed`：消解 `Channel.deliver` 与 `EDG-204` 的矛盾**
  - **要解决的问题是一条真实存在的契约矛盾**，不是一次功能新增：`Channel.deliver` 的
    docstring 写「投递失败抛 `EXTERNAL_CHANNEL`」，而 `EDG-204` 要求投递失败时 turn 仍走到
    终态并完整持久化。抛出去会把一次**成功**的 turn 变成失败，于是四个现存实现
    （`cli_entry` / `openai-api` / `discord` / `feishu`）**全都选了不抛**。一条写在契约上却
    没人遵守的约定，比没有约定更坏。
  - **新事件族 `EventFamily.CHANNEL` + `channel.delivery_failed`**。刻意**不是**
    `turn.failed`：投递是 turn 的最后一步，模型输出与会话历史都已经正确产生了，记成 turn
    失败会让「答案没算出来」与「答案没送出去」不可区分，而这两件事的处置完全不同
    （重跑 vs 重发）。也**不是** `plugin.failed`——内建 CLI 的投递失败与插件无关，
    而它此前正是被折进那条事件里的。
  - **捕获点只有一处**：`runtime/instance.py::outbound_router`（`OrchestratorDeps.deliver`
    的唯一构造者）。它从 `bootstrap.py` **搬了出来**：那个文件贴着 800 行上限，而「出站
    怎么走」本来就是 `instance.py` 职责的第二条。事件带着完整的 `Correlation`（出站消息自带
    `session_key + turn_id`），`OBS-002` 的按序重放不需要猜。合成回音（`[未受理：…]`）走
    `AgentInstance._echo`，发同一个事件、载荷加 `synthetic: True`——回音发不出去意味着用户
    连「被拒了」都不知道，那是最需要被看见的一种失败。
  - **`delivery_error()` 是折叠的唯一实现**：照约定抛的 `NucleaError` 原样带出
    （`retryable` 是实现方的判断，不替它覆写）；其余折成 `EXTERNAL_CHANNEL` 而不是
    `KERNEL_UNEXPECTED`（原因在外部平台那一侧，记成内核异常会把排查方向指错），
    且**只放异常类型名不放消息**（平台 SDK 的异常文本可能带 webhook URL 或令牌）。
  - **兑现它，这才是本轮真正的收益**：discord 与 feishu 此前用 `_quietly` 把投递故障整个
    吞掉，于是「答案发不出去」在事件流里一个字都没有——用户看到 bot 不说话，而日志一片
    正常。两者改为照约定抛，**只有正文会抛、指示器仍静默**（一个没清掉的「正在输入」是外观
    问题，一条没发出去的答案不是）。**飞书的失败信号是 `None` 返回值而不是异常**
    （`client.py` 四个方法都是），因此判定落在 `stream._send_plain` 的返回值上，
    且**部分成功不算失败**。两条原本钉住旧行为的用例随之反转。
  - 验收：`ruff` 全绿、`basedpyright` 0 error、**3632 passed / 10 skipped**。

- **`D44` `CapabilityKind.MEMORY` 通电：M5 唯一一件「交了但没通电」的补上了**
  - **`D39` 交了 `MEMORY` 能力与一个实现它的插件，但 kernel 里没有消费者**：
    `memory_providers_from()` 除测试外没有调用方、`context_builder` 只认
    `ContextProvider`。因此**只注册一条 `MEMORY` 能力，记忆永远进不了模型**——那条能力当时
    只是「契约形状」。本轮之后第三方可以只写一条 `MEMORY` 能力、不必自带 Context Provider。
  - **形状先定死**：`MemoryProvider` 的三个方法**一个 `SessionKey` 都不带**，因此经它只能
    表达实例级（`FragmentScope.AGENT`）记忆。这条从「目前这么理解」升成契约上的**决定**
    （`contracts/protocols.py`）：会话级与工作区级归 `ContextProvider`（它的 `provide()`
    拿得到 `SessionSnapshot.session_key`）。**不加 `scope_key` 参数**——SDK 已发 1.0，
    那是 §7.6 意义上的破坏性变更；也**不许**用「约定在 `query` 里编码会话 id」绕过它
    （两个后端会对同一个字符串有两种理解）。
  - **`kernel/turn/memory.py`（新）**：`MemoryRecall` + `select_memory`。四条判定——
    只用 `AGENT` 范围召回；**priority 有下界，且那是本模块唯一会改写的字段**
    （`HISTORY_TRIM_PRIORITY` 是 0，priority 0 的记忆与会话历史在裁剪序里不可区分，
    而记忆下一轮还能重新召回、历史丢了就是丢了——这是 kernel 自己的裁剪不变量，
    不是对 Provider 语义的覆写；**`trust` 因此不改**）；失败按 `MEM-003` 分叉
    （默认 `degrade`，**但错误一定经 `on_failure` 报出去**，降级不等于静默）而
    **取消不走降级**（判据是 `ErrorCategory` 而不是逐个列举错误码）；空查询不打扰后端。
  - **召回落在 `context_builder.assemble(memory=…)` 而不是 orchestrator**：召回就是上下文
    组装的 a 步，放在外面会让「片段从哪来」有两个答案。召回片段与 Provider 片段、命令片段
    **完全同等**——同批拦截、同批放置、同批裁剪，没有旁路（一条 `sensitivity=SECRET` 的
    记忆照样进不了请求且记进 `dropped`，有用例钉着）。
  - **新 `memory` 配置小节五个字段。`provider = None` 是默认，含义是「不启用」而不是
    「自动挑一个」**——自动挑会让「装上一个记忆插件」悄悄改变每一轮请求的内容。
    配了却不存在是 `CAPABILITY_MISSING` 并指向 `/memory/provider`，不是静默不启用。
  - **两个文件撞上行数上限，各拆一次**：`kernel/config/sections.py`（九个小节 dataclass，
    理由同 `D28` 的 `defaults.py`）与 `runtime/selection.py`（`select_model` /
    `select_recall` / `require_sessions` 三项「配置指名一个、registry 里找它」）。
    **两个拆分都原样再导出，既有 import 一个都没变。** `orchestrator.py` 加一个
    `memory=deps.memory,` 就到了 501 行，为此压缩了 `_emit` 的签名。
  - **如实记着的代价**：`memory` 插件的 `enabled_scopes` 默认已含 `agent`，两边同时开会让
    同一条记忆在一轮里出现两次。**两条路径都是对的，只是不该同时开**——处置写进插件
    README、`__init__.py`、`store.py` 与 `MemorySection` 的 docstring，不留给用户发现。
  - 验收：`ruff` 全绿、`basedpyright` 0 error、**3658 passed / 10 skipped**、
    `tests/architecture` 65 个、启动成本 501 ms（仍是告警不是失败）。

- **`D45` `ModelMessage` 的 opaque 块槽位 + SDK 1.1.0**
  - **`D32` 起记着的一处真实能力回退**：Anthropic 要求续写时把 `thinking` 块（含
    `signature`）原样回传，而 `ModelMessage` 没有放 provider 私有块的槽位，
    `signature_delta` 在流式解码里被直接吞掉——因此 `anthropic` 插件的 thinking 与工具调用
    **不能同时用**。`D42` 判断它「不是同一量级」是对的：真正要决定的不是加不加字段，
    而是所有权、上界与生命周期。
  - **`contracts.OpaqueBlock(provider, kind, payload)`** 是 `EDG-305` 的**受控**例外。
    受控的三处：`payload` 走 `normalize_metadata()`（SDK 对象连塞进来的机会都没有）；
    `provider` 是所有权标记且消费方**必须**按 `owned_by()` 过滤（两家供应商的 `thinking`
    块不是同一种东西）；它**不进 `SessionMessage`**，因此活不过本轮 turn。
  - 另外三项：`ModelResponse/ModelMessage.provider_blocks`（只有 assistant 能带、
    上界 `MAX_OPAQUE_BLOCKS = 64` 防随消息累积、**不算正文**——一条只有 thinking 块的消息
    对模型不构成发言）、`ChunkKind.OPAQUE` + `ModelChunk.block`（流式下 opaque 块必须与
    文本、工具调用走同一条通路，否则 `StreamFolder` 收不到它）、`StreamFolder` 按到达顺序
    累积 + `folding.assistant_message()` 原样搬到下一轮。**Kernel 从不读它们的内容。**
  - **anthropic 插件**：`decode.py` 把两种思考块解成 `OpaqueBlock`（流式下
    `content_block_start` / `thinking_delta` / `signature_delta` **三处到达**，按 `index`
    拼装；opaque 分片排在 `finish()` 最前面，因为 Anthropic 要求 thinking 块排在同一条
    assistant 轮的开头且保持原序——**序摆在解码侧，编码侧因此不需要再排一次**）；
    `wire.thinking_blocks()` 编回线格式并跳过三种情况：别家产出的、缺 `signature` 的
    （Anthropic 直接拒绝，留一半比不留更糟）、不认识的 kind。
    `PROVIDER_NAME` / `THINKING_KINDS` 移到 `wire.py`——`settings` 已经 import 它，
    反向会成环。`provider_metadata` 里的 `dropped_thinking_blocks` 改成 `thinking_blocks`：
    现在没有东西被丢掉了，留着那个名字会说反话。
  - **`SDK 1.1.0`**：五项全是新增，声明 `">=1.0"` 的插件一个字都不用改。想用 `OpaqueBlock`
    的插件把 `sdk_range` 写成 `">=1.1,<2.0"`。
  - **仍然没解决的一条，如实记着**：`ModelMessage.content` 仍是纯 `str`，因此**多模态输入
    还是没有落点**。`OpaqueBlock` 是 provider **私有**块的槽位（内容对 Kernel 无意义），
    而多模态内容恰恰是 Kernel 要参与裁剪与预算的东西——那要让 `content` 变成块序列，
    是一次 major 级变更。
  - 验收：`ruff` 全绿、`basedpyright` 0 error、**3680 passed / 10 skipped**。


## 正在进行
- `D00`、`D01` 已完成，阶段 0 工程基座收口；`D02`–`D06` 已完成，契约层三层（基础 /
  领域与执行 / 能力）、SDK 表面与 Capability Registry 全部落地，**阶段 1 已收口**；
  `D07` 已完成，旧实现行为基线就位；`D08` 已完成，取消与预算就位；`D09` 已完成，
  Turn Engine（纯循环 ≤400 行）就位，`D09` 的两个前置依赖（`D06` + `D08`）已兑现，
  阶段 2 的 engine 一层完成；`D10` 已完成，实例布局、分层配置与实例锁就位，
  `D06`/`D08` 欠给配置层的两件事（`resolve(disabled=...)` 的输入、`TurnLimits` 的配置
  来源）已兑现，阶段 3 开始；`D11` 已完成，`${VAR}` 凭据引用、`SecretStr` 与写回保护
  就位（`SecretStr` 下沉到 `contracts/errors.py`，`sdk` 表面相应调整）；
  `D12` 已完成，事件总线、脱敏与序列化、内建两个 sink 与诊断查询就位，
  `D09` 欠的 `EventName` 缺口与 `D10` 欠的 `EDG-501` 后半句一并兑现，**阶段 3 收口**；
  `D13` 已完成，输入分流、Session 并发三策略与去重就位，阶段 4 开工；
  `D14` 已完成，Turn Orchestrator（≤500 行）、Hook 调度、Context 组装与工具执行器就位，
  `D07` 基线里 `test_loop_behavior.py` 的编排决定项、`D08` 欠的 `tool.cancel_timeout` 码、
  `D09` 欠的检查点 1/4 与总超时看门狗一并兑现，**turn 事件从此有了唯一发布点**；
  `D15` 已完成，`tests/integration/` 用 Fake 能力把整条装配链跑通（28 个用例、0.67 s），
  **阶段 4 收口**；`D16` 已完成，唯一的 Host `NucleaAPI` 实现、九个 kind 的注册载荷与取回
  函数、静态清单 bootstrap 与组装根就位，`D15` 暴露的五个 kind 缺口一并补齐，
  **阶段 5 开工**；`D17` 已完成，第一个内建能力 `builtins/session_jsonl/` 落地
  （JSONL + `meta.json`、`committed_bytes` 提交水位、发布格式文档），
  `BUILTIN_MANIFESTS` 从此不再是空元组；`D18` 已完成，内建 Context Provider
  `builtins/context_basic/` 落地（基线系统指令 + 运行时事实 + 运维指令三类片段、
  零权限零 IO），`CTX-006`/`EDG-307` 的「无 Memory 也有可用上下文」由此成立；
  `D19` 已完成，内建 Model Provider `builtins/model_openai/` 落地（OpenAI 兼容 Chat
  Completions、流式 tool_call 增量拼装、凭据走 `ctx.secret`、httpx + 声明 `net` 权限），
  实例从此有了真模型、`BAS-001`「配置一份凭据就能用」对最多用户成立；
  `D20` 已完成，内建文件工具 `builtins/tools_fs/` 落地（`fs.read`/`write`/`edit`/`list`/`grep`
  五件套、双重路径校验、单工具禁用经 `wiring` 的声明过滤钩子）；
  `D21` 已完成，内建 shell 工具 `builtins/tools_shell/` 落地（`shell.exec`、
  「终止信号 → 宽限期 → 强杀」三步取消、宽限期用尽标 `SideEffect.UNKNOWN`、
  子进程环境白名单），**§8.2 冻结清单六件套至此交齐**。
  `D22` 已完成，内建命令集 `builtins/commands_core/` 落地（`/help` `/config` `/session`
  `/plugins` `/capabilities` `/cancel`），`D21` 留下的「五个命令够不到自己的数据」由
  **扩 `PluginContext`**（新增 `ctx.instance` / `ctx.turns`，类型是 `contracts` 的
  `InstanceView` / `TurnControl`）解决，第三方插件从此也能写 `/status` 这类命令。
  `D23` 已完成，内建 CLI 能力 `builtins/cli_entry/`（`CLI_ENTRY:stdio` + `CHANNEL:cli`
  两条能力）、装配根 `runtime/{bootstrap,instance,plugin_context}.py`、`nm` 的三个真子命令
  与嵌入式门面 `embed/` 一并落地，`plugins.<id>.{config,secrets}` 补上了配置层最后一个
  缺口，**阶段 5 收口**。
  `D24` 已完成，首次运行体验落地（`kernel/config/{scaffold,json_schema}.py` 纯渲染、
  `runtime/first_run.py` 唯一写入点、`nm init`），缺凭据的错误补上了「哪个文件」这一半，
  `ToolExecutor.orphans` 接上报告，`check_startup_cost.py` 增加冷启动到可接受输入指标，
  `tests/e2e/` 逐条对应需求 §16.1 的五个里程碑，**阶段 6 收口、开箱可用达成**。
  `D25` 已完成，插件发现落地（`kernel/plugins/discovery.py` 的两条显式来源 +
  `runtime/inventory.py` 的 manifest 翻译与判定 + `plugins.enabled`），
  `Diagnostics.plugins_source` 从此有了真实现，**阶段 7 开工**；开发方案点名的
  `kernel/plugins/manifest.py` 不交付（`R2` 禁止 kernel 认识 manifest，理由见上）。
  `D26` 已完成，权限账本（`kernel/plugins/{permissions,permission_codec}.py`，TOFU +
  扩权需显式）与三个受守卫的资源门面（`runtime/access/`：workspace 双重校验、读写分离的
  文件门面、SSRF 守卫、受限子进程）落地，`ctx.fs` / `ctx.net` / `ctx.shell` 从「抛
  `CAPABILITY_MISSING` 指向 D26」变成真身，`nm permissions` 成为「用户显式扩权」的落点。
  `D27` 已完成，两阶段加载落地（`kernel/plugins/loader.py` 的依赖拓扑 / `config_schema`
  校验 / `state_version`，`runtime/plugin_plan.py` 的 manifest 判定与加载计划，装配根把
  内建与外部插件合并进**同一次** `wire_capabilities()`），外部插件从此真的跑得起来，
  阶段 A 的七步至此交齐。
  `D28` 已完成，插件生命周期落地（`kernel/plugins/lifecycle.py`：六阶段状态机与唯一一张
  转换表、`stop_order()` 取 `LoadPlan.order` 的逆序、每插件独立停止预算），
  `AgentInstance.stop()` 从「取消一堆任务」变成「逐个提供方走完状态机并各发一条事件」，
  `RuntimePluginContext.shutdown()` 成为退订与取消任务的唯一落点；顺带把
  `kernel/config/schema.py` 里那批镜像常量拆到 `kernel/config/defaults.py`（它撞上了
  `kernel/` 的 500 行上限）。
  `D29` 已完成，`nm plugins list|enable|disable|uninstall|purge` 与 `nm capabilities`
  落地（`runtime/config_edit.py` 是 `config.json` 唯一的**修改**点，
  `runtime/inspect.py` 是不取锁、不写账本的只读诊断路径），`/plugins` 的状态从此叠上
  `D28` 的生命周期投影。
  `D30` 已完成，`examples/plugins/` 的两个示例插件（`echo-tool` 新增一项工具、
  `session-memory` 覆盖内建会话存储）经 entry point 真的被发现、被加载、参与真实 turn，
  `on_disable` 从「留给以后」变成真的判定（`runtime/plugin_disable.py` +
  registry 的按能力抑制），插件开发入门文档就位且其代码块由测试直接执行，
  **阶段 7 收口、需求 §16.2 达成**。
  `D31` 已完成，遗留 Agent 路径删除：`legacy/{agent,cli,webui,gateway,api,sdk,triggers}` 与
  `nanobot.py`、`__main__.py`、`channels/websocket/` 全部删除，`nm legacy`、
  `runtime/legacy_entry.py` 与 `R6` 的唯一白名单例外一并删除（`R6` 自此无例外），
  `tests/baseline/` 随 `legacy/agent/` 一并删除；被删掉的 OpenAI 兼容接口由新层的官方插件
  `plugins/nucleamind-plugin-openai-api/` 与通用无头命令 `nm serve` 取代，
  **阶段 8 收口**。
  `D32` 已完成，能力插件化的第一项落地：官方插件 `plugins/nucleamind-plugin-anthropic/`
  （Anthropic 原生 Messages API 的一条 `MODEL` 能力，raw httpx + 可注入 transport，
  与内建 `model-openai` 并存），同 PR 删掉 `legacy/providers/anthropic_provider.py`、
  三条 `backend="anthropic"` 的 `ProviderSpec` 与 9 个 legacy 测试文件，
  并把 `anthropic` 从根 `pyproject.toml` 的依赖里摘掉，**技术方案 §13 M5 的五步法
  第一次完整走通、阶段三 P1 开工**。
  `D33` 已完成，Channel 泵的按 conversation 扇出（`kernel/routing/fanout.py`）与第一个
  Channel 插件 `plugins/nucleamind-plugin-discord/` 一并落地，同 PR 删掉
  `legacy/channels/discord/`；`D31` 推迟的「Channel 泵的并发」至此兑现。
  `D34` 已完成，官方 Feishu Channel 插件 `plugins/nucleamind-plugin-feishu/` 落地
  （WS 长连接 + CardKit 流式卡片 + 工具进度提示），并补齐了 legacy 唯一未被文档化的
  功能丢失——工具提示改由订阅 `tool.call_started` 事件实现，因为出站消息不带工具信息。
  **`D35` 已完成，`legacy/`（218 文件 / 73773 行）、`tests/legacy/`（97 文件）与
  `webui/` 全部删除**，`R6` 守卫、`scripts/legacy_debt.py` 与债务棘轮一并退休，
  宿主第三方依赖从 36 个降到 4 个，`docs/` 里 21 篇描述被继承实现的文档删除。
  **项目范围本轮收窄**：Model Provider 止步、Channel 只做 feishu、WebUI 不做，
  剩下三项（Memory / 扩展 Tool / Cron）的迁移参考退回 `references/nanobot/`。
  `D36`–`D38` 已完成，**M5 的「扩展 Tool」一项交齐**：官方插件 `web`（两条工具，
  按「谁决定 URL」分走 `ctx.net` 与 raw httpx 两条出网路径）、`image`（产物落盘 +
  `ArtifactRef`，全项目 `artifacts` 的第一个生产者）、`mcp`（把 MCP server 的工具桥接进来）；
  为最后一个先做了一次机制扩展 **`D38-A` `CapabilityDecl.namespace`**——manifest 从此可以
  声明一个**前缀**，放行「能力名要连上外部服务才知道」的插件在 `setup()` 里注册任意多条
  派生名。同 PR 新增 `ErrorCode.EXTERNAL_TOOL_SERVER`。
  `kernel/` 目前有 `registry/`、`turn/`、`config/`、`observability/`、`routing/` 与
  `plugins/`；`builtins/` 有 `registry.py` 与七个内建子包（`session_jsonl/`、
  `context_basic/`、`model_openai/`、`tools_fs/`、`tools_shell/`、`commands_core/`、
  `cli_entry/`）；`runtime/` 有 `wiring.py`、`introspection.py`、`plugin_context.py`、
  `bootstrap.py`、`first_run.py`、`inventory.py`、`plugin_plan.py`、`instance.py`、
  `inspect.py`、`config_edit.py`、`access/` 与 `cli/`；`embed/` 已落地薄门面。
  `D39` 已完成，**M5 的「Memory」一项交齐**：官方插件 `memory`
  （`plugins/nucleamind-plugin-memory/`，一份 manifest 声明四类能力——`MEMORY:jsonl` 存储
  本体、`CONTEXT:memory` 每轮自动召回、三条 `TOOL:memory.*`、`COMMAND:memory`，
  JSONL + 提交水位 + 自写关键词打分，**零新依赖**），外加一次冻结表面变更
  **`sdk.testing.MemoryProviderContract`**（第 6 个契约基类 + 一个反向样例）。
  探查中发现的决定性事实：**当时 `CapabilityKind.MEMORY` 没有 kernel 消费者**，
  因此本插件自产自销、`kernel/` 一行未改（详见下方「`D39` 留下的事实」）。
  **`D44` 已经通电**（`memory.provider` 显式开启，默认关；两边同时开会重复召回）。
  **`plugins/` 目前有九个官方插件**：`openai-api`、`anthropic`、`discord`、`feishu`、
  `web`、`image`、`mcp`、`memory`、`cron`。
  `D40` 已完成，**M5 的最后一项「Cron / Automation」交齐**（`cron` 插件，Kernel 一行未改）。
  `D41` 已完成，插件纳入 basedpyright + 两条清单守卫；`D42` 已完成，三条冻结表面变更 +
  SDK 1.0.0。
  `D43` 已完成，`channel.delivery_failed`（新事件族 `CHANNEL`，捕获点只有
  `runtime/instance.py::outbound_router` 一处；discord / feishu 从吞掉投递故障改成照约定抛）。
  `D44` 已完成，`CapabilityKind.MEMORY` 通电（`kernel/turn/memory.py` + `memory` 配置小节 +
  `context_builder.assemble(memory=…)`；`MemoryProvider` 只服务实例级记忆从「默认这么理解」
  升成契约上的决定），同 PR 拆出 `kernel/config/sections.py` 与 `runtime/selection.py`。
  `D45` 已完成，`contracts.OpaqueBlock` + `ChunkKind.OPAQUE` + 两个 `provider_blocks` 字段
  （`anthropic` 的 thinking 块可以多轮回放，**SDK 1.1.0**）。
  `D46` 已完成，用户文档四篇 + `tests/e2e/test_user_docs.py`（配置字段表 == `SECTION_SPECS`、
  CLI 子命令 == `main.py` 的派发分支、插件安装清单 == 磁盘上的发行包，每条都带自证用例），
  `docs/README.md` 里那句「新层的用户文档尚未写」至此作废；同 PR 修掉 `deploy/` 的三处
  陈旧项（compose 的构建参数名写成 `NANOBOT_CHANNELS` 而 Dockerfile 要 `NUCLEAMIND_PLUGINS`、
  默认值 `whatsapp` 这个插件不存在、`EXPOSE 18790` 而默认端口是 8760）。
  `D47` 已完成，出站附件通路（`ToolResult.attachments` + `TurnState.collect_attachments` +
  终帧投递 + 两个消费方 + `image` 落点迁到 workspace，**SDK 1.2.0**）。
  `runtime/` 至此有 `wiring.py`、`introspection.py`、`plugin_context.py`、`bootstrap.py`、
  `first_run.py`、`inventory.py`、`plugin_plan.py`、`plugin_disable.py`、`instance.py`、
  `inspect.py`、`config_edit.py`、`selection.py`、`access/` 与 `cli/`。
- [`开发方案`](./development-plan.md) 已完成评审修订。把 P0 改造范围拆成 32 个可独立
  验收的模块（`D00`–`D31`），分 9 个阶段推进：
  - 阶段 0 先做 `D00` 仓库重构（受限的结构与命名迁移，遗留配置、环境变量和状态目录
    保持不变，验收标准是除明列命名变化外现有行为逐项一致），
    再做 `D01` 架构守卫与 CI 门禁——守卫写在最终路径上，只写一次。
  - 阶段 4（`D15`）在写任何真实能力前，用 Fake 能力打通端到端 turn，提前暴露集成风险。
  - 阶段 6（`D24`）达成需求 §16.1 开箱可用里程碑；阶段 7（`D30`）达成 §16.2 插件里程碑。
  - `D00` 之后 `legacy/` 业务代码在阶段 1–7 期间完全不动，新 Kernel 以独立入口 `nm`
    在同一仓库内并行生长；`D31` 直接删除 `legacy/agent/` 与 `legacy/cli/`，
    不搭桥、不设双路径开关，回退用 git。任何阶段中止都不影响现有可用功能。
  - `runtime/legacy_entry.py` 是 `R6` 唯一、限期存在的过渡例外，只为 `nm legacy`
    转发遗留 CLI；D31 连同架构测试白名单一起删除。
  - 高风险模块 4 个：`D09` Turn Engine、`D14` Orchestrator、`D21` tools_shell、
    `D27` 两阶段加载，建议单独评审实现方案后再动手。
- [`技术方案`](./technical-design.md) 已完成评审修订。要点：
  - **NucleaMind 是改造，不是 nanobot 的兼容发行版**：新层的命名、目录、配置格式、
    环境变量与 CLI 冲突时一律以新架构为准，不留别名、不双读、不写长期迁移垫片；
    `legacy/` 在迁移期继续使用旧运行契约。
  - 目标目录结构：`src/` 布局 + 五层分层（contracts / kernel / sdk / builtins /
    runtime）+ 顶层 `plugins/` 独立发行包 + `legacy/` 隔离区，依赖规则 `R1`–`R6`
    由 `tests/architecture/` 的 AST 断言强制，而非仅文档约定。
  - `legacy/` 是「只出不进」的隔离区：新代码禁止 import 它，债务指标接入 CI 只降不升，
    每迁完一个模块同 PR 删除对应目录，最终清空并删除该目录与 `R6` 守卫。
    迁移期它通过 `nm legacy` 单个子命令可运行，`D31` 一并删除。
  - 借鉴 Pi 的两层循环把 nanobot `agent/loop.py` + `runner.py`（约 3900 行）拆为
    `kernel/turn/engine.py`（纯循环，≤400 行）与 `orchestrator.py`（有状态编排）。
  - `NucleaAPI` 冻结 9 个注册方法（包含 `register_cli_entry`），Hook 冻结 10 个，
    内建工具冻结 6 个；
    `sdk.__all__` 做快照测试，表面变化必须走评审。
  - `D16` 先建立唯一 Host `NucleaAPI` 与事务性注册通道，内建 bootstrap 和后续外部
    插件 loader 共用；两者只在发现、依赖校验和生命周期上不同。
  - 覆盖内建能力必须在 manifest 显式声明，禁止由加载顺序决定；解析结果产出
    `ResolutionReport`（active / shadowed / disabled / failures）。
  - 需求 §17.2 的 12 项设计决策已在技术方案 §15 逐项给出结论、依据和验证方式。
- [`需求分析`](./requirements-analysis.md) 已完成第一轮评审修订，主要变更：
  - 明确“最小核心”指能力范围最小，不指开箱不可用；新增开箱可用目标与 §7.3 内建默认
    能力集（CLI、最小 Model Provider、Session、Context、基础工具集、最小命令集、配置）。
  - 确认 Session、Context、基础工具、最小 Model Provider、CLI 为 Kernel 内建默认实现，
    插件负责覆盖和扩展；Memory 仍为可选插件。
  - CLI 入口不可禁用（`BAS-009`、`BAS-010`、`EDG-108`）：不装任何 Channel 插件也必须能用，
    插件可覆盖 CLI 实现但失败时回落到内建实现，保证任何配置下都存在本地交互入口。
  - 补齐命令分流、turn 中断、Session 并发默认策略、声明式扩展、安装发行与多实例需求。
  - §11 边界条件与 §12 非功能需求全部编号（`EDG-*`、`NFR-*`），支持需求追溯。
  - §17 拆分为产品结论与设计阶段决策项；后者已由技术方案 §15 全部闭环。

## 下一步工作

**M5 已全部交齐**（`D36`–`D38` 扩展 Tool、`D39` Memory、`D40` Cron），项目范围本轮收窄
（见文首）：Model Provider 止步于内建 `model-openai` + `anthropic`，Channel 只做 `feishu`，
WebUI 不做。**没有待迁移的模块了**，`references/nanobot/` 从此只是历史对照。

`D41`–`D47` 已经把当时清单上那几件**动作明确**的做完了：

- **`D41`**：插件进 basedpyright（`include` 加两条 glob，`exclude` 恰好四个碰 CI 缺席 SDK
  的模块），并给两张手工维护的清单各加一条守卫（`tests/architecture/test_ci_plugin_list.py`
  与 `test_type_check_scope.py`）。它当场抓到 `sdk.EventHandler` 声明 `Awaitable[None]`
  而两个官方插件注册的是同步 handler，每来一个事件多产一条 `TypeError` 任务。
  顺带发现 `D36`–`D40` 连着五轮漏改 CI 安装清单，约 1100 个用例在 CI 里从未跑过
  （`a7bda23` 先修症状，守卫堵复发）。
- **`D42`**：三条冻结表面变更 + SDK 1.0.0。`ToolResult.trust`（默认 `UNTRUSTED`，包裹与
  `ContextFragment` 共用 `wrap_untrusted`）、`FileAccess` 的二进制读写、
  `HttpAccess.request(max_bytes=…)`。**完整流式刻意没做**（没有消费者）；
  **`ModelMessage` 的 opaque 块槽位这一轮没动**（`D45` 补上了）。
- **`D43`**：`channel.delivery_failed`。消解 `Channel.deliver` 的 docstring 与 `EDG-204`
  那条**真实存在**的矛盾——契约要求投递失败抛，而抛出去会把一次成功的 turn 变成失败，
  于是四个实现全都选了不抛。新事件族 `CHANNEL`，捕获点只有
  `runtime/instance.py::outbound_router` 一处。**兑现它**：discord 与 feishu 从「用
  `_quietly` 把投递故障整个吞掉」改成照约定抛，「答案发不出去」从此在事件流里看得见。
- **`D44`**：`CapabilityKind.MEMORY` 通电。`kernel/turn/memory.py`（`MemoryRecall` +
  `select_memory`）+ `memory` 配置小节 + `context_builder.assemble(memory=…)`。
  **M5 唯一一件「交了但没通电」的至此通电**；`MemoryProvider` 只服务实例级（`AGENT`）
  记忆这一点从「默认这么理解」升成契约上的**决定**。同 PR 拆出
  `kernel/config/sections.py` 与 `runtime/selection.py`（两个文件都撞上了行数上限）。
- **`D45`**：`contracts.OpaqueBlock` + `ChunkKind.OPAQUE` + 两个 `provider_blocks` 字段 +
  `ModelChunk.block`，**全部只增不改 → SDK 1.1.0**。`anthropic` 的 thinking 块因此可以
  多轮回放，`D32` 起记着的那处真实能力回退消除。**它只活到本轮 turn 结束**（opaque 块不进
  `SessionMessage`），如实写在契约 docstring 里。

- **`D46`**：新层的用户文档四篇（`getting-started` / `configuration` / `cli` / `deployment`），
  外加 `tests/e2e/test_user_docs.py` 的三条防漂移守卫。**写文档顺带发现 `deploy/` 三处
  陈旧项**：compose 的构建参数名与 Dockerfile 对不上、默认值指向一个不存在的插件、
  `EXPOSE` 的端口与实际默认端口差了一位数——照着自己的文档走一遍才会发现这些。
- **`D47`**：出站附件通路。`ToolResult.attachments`（**SDK `1.2.0`**）→
  `TurnState.collect_attachments`（按 `(source, locator)` 去重、封顶 `MAX_ATTACHMENTS`、
  超出的经终帧 metadata 说出来）→ 终帧 `OutboundMessage.attachments` → 两个消费方
  （内建 CLI 印路径、`discord` 经 `ctx.fs.read_bytes()` 真上传）。`image` 的落点从
  `<state_dir>/images` 换到 `<workspace>/artifacts/images`——**那是它能被当成附件发出去的
  前提**，不是顺手整理目录。`orchestrator.py` 只加了一行（它当时 497/500）。

因此下一轮的候选是下面清单里**剩下的那几件**，加上两条刻意推迟的机制（插件热更新、
`state_version` 迁移）。**M6「生态兼容」（OpenClaw）没有立项**，它计划落在独立包
`nucleamind-compat-openclaw` 里、不进本仓库，因此不阻塞任何一条。

**「扩展 Tool」里刻意没做的两样**：参考实现的 `agent/tools/search.py` 是**文件搜索**，
已被内建 `tools_fs` 的 `fs.grep` / `fs.list` 覆盖；`providers/transcription.py`
（语音转写）是另一类能力（音频输入），而契约层今天**仍然**没有多模态输入位置——
`D45` 的 `OpaqueBlock` 是 provider **私有**块的槽位，不是多模态内容的槽位。
**「Cron」里刻意没做的两样**：heartbeat 与 local trigger（理由见 `D40` 条目）。

**五步法在本仓库已经跑通九遍**（`D32` anthropic、`D33` discord、`D34` feishu、`D35` 收尾、
`D36` web、`D37` image、`D38` mcp、`D39` memory、`D40` cron），下次做别的模块时照它们的
形状写：

- a 步**不新写基线**——`references/nanobot/` 里的实现与它自己的测试就是行为说明书。
- b 步在 `plugins/` 里**新写**而不是搬运（`AGENTS.md` 原则 5）。那份副本被 Git 忽略、
  不在包里、也 import 不到，因此「搬」在物理上就不成立。
- c/d/e 步：`legacy/` 已经没有对应目录可删，因此这三步退化成「切换调用方 + 更新文档」。

写新插件时**从第一天就按守卫的形状切**（`D32`–`D42` 逐条踩出来的）：

- 单文件 ≤800 行、`Any` 须带 `# boundary:`、测试树也不许 import `kernel/`——
  `tests/architecture/` 的三条守卫对 `plugins/` **全目录**生效，包括测试。
- **加插件要同时改 `.github/workflows/ci.yml` 的安装清单**（`D41` 起有守卫盯着，
  漏了直接红）。理由：`testpaths` 收集整个 `plugins/`，插件没 editable 装进环境就是
  **收集期 `ModuleNotFoundError`**，不是「少跑几个用例」。
- **测试模块名要带插件前缀**（`test_feishu_stream.py` / `_mcp_fakes.py` / `_cron_fakes.py`）。
  `testpaths` 一次收集整个 `plugins/`，而 pytest 按模块名去重：两个插件各有一个
  `test_stream.py` 时，先导入的会顶掉后一个，另一棵测试树整体 `ImportError`。
  **单独跑各自的目录看不出来，跑全量才炸**（`D34` 就是这么发现的）。
- 平台 SDK 只准一两个模块碰，其余对自定义 Protocol 编程；CI 用 `--no-deps` 装插件，
  因此**测试树在没有平台 SDK 的环境里必须全绿**。`D38-B` 把这条守成了一条 **AST 断言**
  （扫 import 语句而不是文本包含，另配一条自证用例），下一个插件照抄它。
  `D40` 把它扩成「整棵源码树只 import 标准库 + `nucleamind`」的一条断言。
  **`D41` 又给它加了一层**：碰那三个 CI 缺席 SDK 的模块必须恰好等于 basedpyright 的
  `exclude` 清单，在第二个模块里 import 平台 SDK 会让守卫失败。
- 会发 HTTP 的插件照抄零网络闸门那条 autouse 夹具（现在有八份，判据逐条相同、
  刻意不共享——`R4` 够不着彼此）。
- **照抄 `inspect.signature` 那条守卫**（`D39` 起，`D40` 扩到了 `Channel` 的四个方法）。
  `D41` 之后插件**已经在** basedpyright 范围内，但这条守卫仍然要写：类型检查看不到
  `register_*` 那一刻传进去的是哪个对象，两者盖住的不是同一片地方。
- **`CONFIG_SCHEMA` 标注成 `sdk.ManifestJsonSchema`**（`D42` 起）。不要标
  `contracts.JsonSchema`——那个类型进不了 pydantic 模型，理由与另外三个被否掉的候选
  逐条记在 `sdk/manifest.py::ManifestJsonSchema` 的注释里。
- **工具结果要表态 `trust`**（`D42` 起）。默认是 `UNTRUSTED`（安全的那一个），
  正文确实是工具自己的话时才写 `SYSTEM`——回执、错误文案属于后者，文件内容、命令输出、
  网页、远端响应属于前者。
- **有注入时钟的插件不该再有第二处 `datetime.now()`**（`D40` 踩到）：两个时钟会让用例只
  覆盖其中一个，而另一个跑去和真实墙钟比。
- **错误消息定义成模块级 `Final` 常量**，动态部分一律进 `detail`：`ruff` 的 `TRY003` 会拦
  写在 `raise` 处的多词消息（`builtins/model_openai/settings.py::_BASE_URL_SCHEME` 的先例）。

### 挂着的独立事项（`D47` 之后剩三件，全部需要先做一个决定）

`D42` 之后清单上的**前五条已经交掉**，逐条留下判据：

- **`ModelMessage` 的 provider-opaque 块槽位** ✅ `D45`。`OpaqueBlock(provider, kind,
  payload)` + `ChunkKind.OPAQUE` + `ModelResponse/ModelMessage.provider_blocks` +
  `ModelChunk.block`。它是 `EDG-305` 的**受控**例外：受控的部分是「仍然只能是归一化 JSON、
  仍然带所有权标记（消费方必须按 `owned_by()` 过滤）、仍然不进 `SessionMessage`」。
  **`D42` 当时判断它「不是同一量级」是对的**——真正要决定的不是加不加字段，而是所有权、
  上界（`MAX_OPAQUE_BLOCKS = 64`，防的是随 assistant 消息累积）与生命周期（本轮内）。
- **`Channel.deliver` 与 `EDG-204` 的矛盾** ✅ `D43`。消解它的是新事件而不是改约定——
  「投递失败了」必须有人说出来，而能说的只有实现方自己。
- **三条冻结表面缺口** ✅ `D42`（两条半：`ToolResult.trust` 完整，`FileAccess` 的二进制面
  补齐但 `image` 那一半是「两个目录树」而不是缺方法，`HttpAccess` 的字节上界补齐而完整
  流式刻意没做——没有消费者）。**`image` 那半条在 `D47` 补上了**：不是给门面加方法，
  而是把落点从 state_dir 挪进 workspace——真正的问题从来不是「缺个方法」，
  而是「生成的图属于谁的目录树」。
- **出站附件通路没有生产者** ✅ `D47`。**决定是路径引用而不是字节**——`AttachmentRef` 的
  docstring 早就答过（「契约层只存引用不存字节」），而当时顾虑的「Channel 会拿到一个
  workspace 之外的绝对路径」由契约自己挡掉（附件禁止绝对路径），代价是**产出物必须落进
  workspace 才发得出去**，`image` 因此换了落点。
- **`MemoryProvider` 的形状 + `MEMORY` 没有 kernel 消费者** ✅ `D44`。**决定是「后者」**：
  `MemoryProvider` 就是实例级（`AGENT`）长期记忆的接口，会话级与工作区级归
  `ContextProvider`。不加 `scope_key`——SDK 已发 1.0，那是 §7.6 意义上的破坏性变更。
  通电靠 `memory.provider` 显式开启（**默认关**，自动挑会让「装上一个记忆插件」悄悄改变
  每一轮请求的内容）。**如实记着的代价**：memory 插件的 `enabled_scopes` 默认已含 `agent`，
  两边同时开会重复召回。

剩下的三件，**每一件都是先要一个决定而不是先要工时**：

1. **多模态输入没有落点。** `ModelMessage.content` 是纯 `str`，因此图像输入、语音转写
   （M5 里刻意没做的 `providers/transcription.py`）与图生图都卡在同一处。**`D45` 的
   `OpaqueBlock` 不是这个槽位**——它是 provider 私有块的槽位，内容对 Kernel 无意义；
   多模态内容恰恰是 Kernel 要参与裁剪与预算的东西。要做得让 `content` 从 `str` 变成块序列,
   那是 **major 级**的破坏性变更（§7.6），牵动 `SessionMessage` / `ContextFragment` /
   两个 provider 的 wire 编码。

2. **权限模型没有「监听端口」这一种**（`net` 判的是出站）。`openai-api` / `discord` /
   `feishu` / `cron` 都声明不出与自己实际行为对应的权限。**这是个定位问题**：当权限模型是
   「给用户看的知情声明」就必须补，当它只是运行期闸门就可以不补。先定位再动手。

3. **两条刻意推迟、有记录的机制**（不是遗漏）：
   - **插件热更新**（技术方案 §10.4 写着「首版不做」）。它要求 registry 可变，而
     「解析后只读」（`NFR-403`）是一大批现有不变量的地基——真要做是一个独立里程碑。
   - **`state_version` 迁移机制**（P0 没有，版本不符即拒绝加载，升与降都拒）。
     在第一个插件真的要升 `state_version` 之前，写一套迁移框架就是在猜。

一条相关但更小的：**opaque 块跨 turn 拿不回来**（`D45` 如实记着）。它不进
`SessionMessage`，因此 `anthropic` 的 thinking 回放只在同一条 turn 的工具循环内成立。
要跨 turn 得先决定「一份加密的思考签名该不该成为用户资产」——`SES-006` 一旦发布就是契约。

### `D46`/`D47` 留下的、后续必须用到的事实

1. **文档也能有守卫，而且值得有。** `tests/e2e/test_user_docs.py` 的三条判据分别读
   `SECTION_SPECS`、`main.py` 的 AST、磁盘上的发行包——**不比对片段**（复制粘贴来的文档
   在实现改名之后仍然长得一模一样，这是 `test_plugin_docs.py` 早就立下的先例）。
   **加一个配置字段现在要改六处**（那五处 + `docs/configuration.md`）。
   **说明文字刻意不钉**：钉住它会让每次改文案都失败一次，而漂了也不会误导人；
   钉的是名字与默认值，那两样漂了文档就是在骗人。

2. **CLI 子命令要用 AST 扫而不是文本包含。** `_USAGE` 里也有那些名字，文本扫描会把
   「说明里提过」当成「真的分派了」——那正好放过「文档与 `--help` 都写了、实现漏了」
   这一种。守卫因此扫 `app()` 里的 `command == "<字面量>"`，另有一条断言钉住
   「`_USAGE` 提到每一条被分派的子命令」。

3. **`ToolResult.artifacts` 与 `attachments` 是两个消费者。** 分工写在 `ArtifactRef` 的
   docstring 里（产物面向 Workspace 与后续工具，附件面向 Channel 投递），因此
   **Kernel 不做两者之间的翻译**——那需要 Kernel 认识 workspace 根并做路径相对化，
   而 `ArtifactRef.locator` 允许是宿主机绝对路径。**由生产者表态**，判据是
   `AttachmentRef.__post_init__`（拒绝绝对路径与上跳段）。

4. **产出物落在哪，决定了它能不能被发出去。** 这是 `D47` 最容易被下一个人忽略的一条：
   `image` 换落点不是「顺手整理一下目录」，而是**出站的前提**。下一个会产出文件的工具
   插件默认落点也该在 workspace 里；确实要落在别处时，如实写明「那些文件发不出去」。

5. **`orchestrator.py` 只剩不到三行余量。** `D44` 加一行到 501、`D47` 又加一行到 498——
   两次都是「往编排里塞逻辑」的诱惑，两次的正确动作都是问「这段逻辑该在哪」：
   收集归 `TurnState`、投递归 `emit_outbound`、召回归 `context_builder`。

6. **`emit_outbound` 没有加形参。** 它已经收 `state`，加参数会让唯一的调用方
   （`orchestrator._emit`）跟着长——而那个文件正贴着上限。**「需要更多输入」不总是
   「加一个参数」**，有时是「那个输入本来就该在已有的载体上」。

7. **`R4` 又逼出一处双写**：`attachments_dropped` 的键名在 `kernel/turn/orchestration.py`
   与 `builtins/cli_entry/console.py` 各一份，由对照测试钉住。这是
   `estimate_tokens` / `DEFAULT_GRACE_MS` 之后的第三处，做法完全相同。

8. **`deploy/` 的陈旧项是「没人跑过」的直接证据**：compose 的构建参数名与 Dockerfile
   对不上、默认值指向一个不存在的插件、`EXPOSE` 的端口与实际默认端口差了一位数。
   **写文档是发现它们的方式**——照着文档走一遍才会发现文档写不出来。

### `D43`–`D45` 留下的、后续必须用到的事实

1. **投递失败与 turn 失败是两件事，事件名必须分得开。** 「答案没算出来」重跑，
   「答案没送出去」重发。`D43` 之前它被折进 `plugin.failed`——内建 CLI 的投递失败与插件
   无关，那条记法从一开始就是错的。**新增事件族要同时改两处快照**：
   `contracts/events.py::EventFamily` 与 `tests/contracts/test_events.py` 的
   `EVENT_NAME_SNAPSHOT`（字面量，那是刻意的评审闸门）。

2. **飞书的失败信号是 `None` 返回值而不是异常**（`client.py` 四个方法都是这样）。
   因此「让 feishu 报出投递失败」不是加一个 `except`，而是**看返回值**——`D43` 的判定落在
   `stream._send_plain` 上，且**部分成功不算失败**（长正文拆成多条，前两条到了就不是
   「一个字都没送到」）。下一个碰它的人先读这条。

3. **`kernel/` 的 500 行上限会在加依赖时先撞上你。** `D44` 给 `orchestrator.py` 加一个
   `memory=deps.memory,` 就到了 501 行。**不要为此把逻辑塞进别处**：正确的动作是问「这段
   逻辑该在哪」——召回是上下文组装的 a 步，因此它落在 `context_builder.assemble()` 而不是
   orchestrator。同一轮还拆出了 `kernel/config/sections.py`（九个小节 dataclass，
   理由同 `D28` 的 `defaults.py`）与 `runtime/selection.py`（三项「配置指名一个、registry
   里找它」）。**两个拆分都原样再导出，既有 import 一个都没变。**

4. **加一个配置小节要改五处**：`schema.SECTION_SPECS`（唯一依据）、`sections.py` 的
   dataclass、`validate_config()` 的构造、`defaults.py` 的常量（如果镜像自 `kernel.turn`
   就必须加一条逐项对照测试）、`document.py` 的渲染。**漏掉最后一处的后果是
   `nm config show` 里没有它**，而那不会让任何测试失败——`D44` 是靠通读 `document.py` 发现的。

5. **`priority_floor` 是 kernel 唯一会改写 Provider 交出来的片段的地方**（`D44`）。
   判据是「这条改写是 kernel 自己的裁剪不变量，还是对 Provider 语义的覆写」：
   `HISTORY_TRIM_PRIORITY = 0` 是 kernel 常量，priority 0 的记忆与历史在裁剪序里不可区分，
   而历史丢了就是丢了——这是前者。**`trust` 是后者，因此不改**：声明 `SYSTEM` 的记忆进系统
   指令位置，与一个 Context Provider 声明 `SYSTEM` 是同一件事、同一份 manifest 担保。

6. **降级必须报出去，取消不走降级**（`D44`，`MEM-003`）。前者：一个被吞掉的后端故障会让
   「记忆一直召不回来」查不出原因。后者：取消不是后端故障而是这条 turn 该停了，折成
   「这轮没有记忆」会让一条已被取消的 turn 带着半份上下文继续跑。**判据是
   `ErrorCategory` 而不是逐个列举错误码**——`CODE_CATEGORIES` 已经是那份归类的唯一来源。

7. **加一个 `ChunkKind` 取值要看三处消费者**（`D45`）：`StreamFolder.push`（累积）、
   `engine.py`（发 delta 事件）、`sdk/testing/fakes.py`（假 provider 产出什么）。
   `ModelChunk.__post_init__` 的 `expectations` 表是全部载荷约束的唯一来源，
   新 kind 不进那张表就会 `KeyError` 而不是报一句人话。

8. **`PROVIDER_NAME` 从 `settings.py` 移到了 `wire.py`**（`D45`，anthropic）。理由是环：
   `settings` 已经 import `wire`，而 `OpaqueBlock.provider` 的取值属于线格式一侧的身份。
   `settings.py` 原样再导出它。**下一个要在 `wire` 里用 `settings` 常量的人先看这条**——
   那个方向是不通的。

9. **opaque 块的顺序是行为。** Anthropic 要求续写时 thinking 块排在同一条 assistant 轮的
   **最前面且保持原序**。`D45` 把序摆在解码侧（`StreamDecoder.finish()` 先发 opaque 分片、
   按 `index` 升序），因此 `wire.encode_messages` 不需要再排一次。改任一侧要想到另一侧。

10. **SDK minor 只允许新增，而「新增」包括枚举取值。** `D45` 的五项全是新增 → `1.1.0`，
    声明 `">=1.0"` 的插件一个字都不用改。想用 `OpaqueBlock` 的插件把 `sdk_range` 写成
    `">=1.1,<2.0"`——`contracts` 虽然不由 `sdk` 导出（`R4` 让插件直接 import 它），
    `sdk_range` 仍然是「我需要多新的宿主」唯一的声明处。

### `D41`/`D42` 留下的、后续必须用到的事实

- **两张手工维护的清单现在各有一条守卫**：CI 的插件安装清单必须等于磁盘上的发行包集合
  （`test_ci_plugin_list.py`），basedpyright 的 `exclude` 必须恰好等于「import 了 CI 缺席
  SDK」的模块集合（`test_type_check_scope.py`）。两条都带一个**自证用例**——
  找不到任何插件 / 任何 SDK 边界模块时要失败，否则一条恒真的断言在报表里也是绿的。
- **插件不在类型检查范围里，就没有任何自动闸门能发现签名与契约不一致。** `D39` 的
  `handle(invocation, cancel)` 与 `D41` 的 `EventHandler` 都是**测试全绿而实际会炸**：
  契约测试基类只在你自己传的实参下跑，`isinstance` 对 `runtime_checkable` Protocol 又只查
  属性存在性。这是同一个教训的第二次。
- **`contracts.JsonValue` 永远进不了 pydantic 模型。** `typing._eval_type` 在 pydantic
  生成 core schema **之前**就 `RecursionError`（它是带前向引用的匿名递归 Union），因此
  `SkipValidation` / `PlainValidator` / 自定义 `__get_pydantic_core_schema__` 一个都救不
  回来。pydantic 自带的 `JsonValue` 又用**不变的 `list`**，`sorted(...)` 这类非字面量赋不
  进去；`TypeAliasType` 的具名递归 pydantic 认而 basedpyright 1.39 不认。四档都试过，
  结论是 `Mapping[str, object]` + 一个真的走一遍文档的校验器（报 JSON Pointer、带深度上界）。
- **不可信包裹的实现只有一份**（`contracts.context.wrap_untrusted`），`ContextFragment` 与
  `ToolResult` 共用。两处各拼一遍字符串就等于「不可信内容长什么样」有两个定义，
  而模型侧的提示词只认得其中一个。**包裹必须在截断之后**：先包再截会把闭合标记截掉，
  而一个没有闭合的数据块正是它要防的东西。代价是最终消息比 `tool_result_max_bytes` 长出
  包装那几行——那是常数，如实记着。
- **`ctx.fs` 的根是实例的 workspace，不是插件的 state_dir。** 想「用了新的
  `write_bytes` 就能不绕道」的人先读这条：那是两个目录树，`PathGuard` 对越界与绝对路径
  一律拒绝。`session_jsonl` / `image` / `memory` / `cron` 都用 `pathlib` + 如实声明权限。
- **SDK 已发 1.0.0，§7.6 的兼容承诺从此起算。** `tests/sdk/test_version.py` 那条
  「发 1.0 时本用例会失败」的提醒真的失败过一次，现在换成 `major == 1`，`major == 2` 时
  同样会失败。**如实记着**：那四个缺口是 `D41`/`D42` 才发现的，说明此前「表面已稳定」
  判断过一次早。1.0 承诺的是**从现在**起不再破坏性变更，不是追认此前每一版都对。

### `D40` 留下的、后续必须用到的事实

- **「让实例自己开一条 turn」的正规做法是注册一条 `CHANNEL`，`receive()` 就是那个循环。**
  不需要 `ctx.spawn_task`、不需要 Hook、不需要给装配根开投递回调。`D31` 的
  「HTTP 服务是一条 `CHANNEL` 而不是 `submit()` 的包装」与这条是同一句话的两个应用。
  **下一个「定时 / 事件驱动」能力照这条走。**
- **一条 Channel 可以产出寻址到别的 Channel 的入站消息**，出站会按 `message.channel_id`
  路由到那一条。泵不校验「消息的 `channel_id` 是不是产出它的那条 Channel」，
  `deliver` 找不到目标时静默丢弃。这是 cron 能把结果送回原会话的全部机制，
  也是它唯一一处**不可检测的失败**（原 Channel 未加载）。
- **`datetime.astimezone(tz)` 在 `tz is self.tzinfo` 时直接返回自身**（CPython 短路）。
  任何「这个墙钟时刻在这个时区里存在吗」的往返判据都**必须绕一次 UTC**，否则恒真。
- **Windows 没有系统时区数据库**，`ZoneInfo("Asia/Shanghai")` 需要 `tzdata`，而 CI 用
  `--no-deps` 装插件。做法是把名字 → `tzinfo` 的解析收在一处并可注入，其余代码只接受
  已解析的 `tzinfo`——**整棵测试树因此不依赖时区数据库**，DST 行为用手写的 `tzinfo` 子类
  真的测到。**下一个碰时区的能力照这条切。**
- **`nm serve` 下 CLI 仍然是一条已注册的 `CHANNEL`**（`cli_entry` 在 `setup()` 里注册它，
  与跑的是哪条子命令无关），因此寻址到 `cli` 的出站消息在 `nm serve` 里会打到 stdout。
  手验 cron 就是靠这一点看到注入 turn 的答复的。
- **`OutboundMessage` 强制 `channel_id` / `conversation_id` 与 `session_key` 一致**，
  构造替身出站消息时三者要一起改，否则 `KERNEL_INVARIANT_VIOLATED`。
- **`StreamState` 的终态叫 `FINAL` 而不是 `COMPLETED`**（五个取值：`STARTED` / `DELTA` /
  `FINAL` / `CANCELLED` / `FAILED`）。
- **`ToolResult.data` 里的列表在构造时会被规范化成 tuple**，用例断言要按 tuple 写。
- **替身 `sleep` 应当真的挂起**（用一个 `asyncio.Event` 门控），不要立即返回：
  `while True` + `await sleep` 配一个立即返回的替身会变成占满事件循环的忙等，
  而「循环有没有真的停下来等」这件事就断言不了了。`D33` 踩的是反面（替身不让出事件循环），
  两条都要避开。等一条「本该到期」的消息一律经 `asyncio.wait_for` 包一层超时——
  挂住的用例给不出任何信息。
- **手写替身模型端点要按内容分派而不是按第几次请求**：一次探活请求就会把「该调工具那一轮」
  用掉；而且工具结果回来后那条 user 消息**仍在上下文里**，只看 user 文本会让它无限调工具
  直到撞上 `max_iterations`（本轮真的撞了一次，16 条任务）。判据加一条「消息里有没有
  `role == "tool"`」即可。

### `D39` 留下的、后续必须用到的事实

- **`CapabilityKind.MEMORY` 仍然没有 kernel 消费者。** `memory` 插件自产自销：记忆靠它
  自己的 `CONTEXT:memory` 进上下文。要让「换一个 `MEMORY` 实现即刻生效」成立，得给装配根
  加「选哪一个 MemoryProvider」的配置与 `MEM-003` 的降级策略——那是核心扩张，
  `D39` 刻意没做。**在那之前，别以为注册一条 `MEMORY` 能力就够了。**
- **`ContextProvider.provide()` 与 `ToolInvocation` 都拿不到发送者身份**
  （`SessionSnapshot` 里的 `SessionMessage` 一个 sender 字段都没有），因此
  `FragmentScope.USER` 今天落不了地。要支持它得先让身份到得了召回路径，那是一次契约变更。
- **`CommandInvocation` 里能拼出 `SessionKey` 的只有 `correlation`**：
  `InboundMessage` 只有 `channel_id + conversation_id`，缺 `scope`。
- **插件发不起模型调用**：`PluginContext` 没有这条通道。因此任何「让 LLM 自己整理数据」
  的设计（Dream 式记忆整理、自动摘要、语义 embedding）在今天的机制下都做不出来。
  **定时触发这一半已经由 `D40` 兑现**（`cron` 插件到点注入一条 turn，模型因此可以被定时
  唤醒去做事）；缺的是「插件自己在 turn 之外发起一次模型调用」。**`D40` 的形状说明这一半
  也许不必加**：想让 LLM 定期整理记忆，写一条 cron 任务让**模型**去调 `memory.*` 工具，
  比给 `PluginContext` 开一个模型通道更符合「机制优先于功能」。要真的加那条通道，
  先评审一次 `PluginContext` 的表面扩展。
- **basedpyright 的 `include = ["src/nucleamind"]` 把 `plugins/` 全部排除在类型检查之外。**
  加上「`isinstance` 对 `runtime_checkable` Protocol 只查属性存在性」「契约基类只在你自己
  传的实参下跑」，**插件实现与契约 Protocol 的签名不一致没有任何自动闸门**——`D39` 就是这么
  漏掉 `handle(invocation, cancel)` 的第二个参数、直到跑真实 `nm run` 才发现。
  `plugins/nucleamind-plugin-memory/tests/test_memory_plugin.py` 里那条 `inspect.signature`
  守卫是目前唯一的对策，**下一个插件照抄它**。
- **Git Bash 会把 `-p "/memory list"` 里的 `/memory` 转成 `D:/env/Git/memory`**（MSYS 路径
  转换）。验证斜杠命令要带 `MSYS_NO_PATHCONV=1`，否则会看到命令「没有被分流」的假象。
- **`nm run` 的实例目录环境变量是 `NUCLEAMIND_INSTANCE_DIR`**（不是 `NUCLEAMIND_HOME`）。
  写错会静默落到 `~/.nucleamind/default`，而 `nm plugins enable` 会真的改那份配置。
- **CLI 走流式**：手写替身端点必须返回 SSE（`data: {...}` + `data: [DONE]`）。返回一份普通
  JSON 会被折成「没有分片」，推断出 `END_TURN` + 0 个工具调用——看起来像模型没调工具，
  实际是替身写错了（`D39` 在这上面绕了一圈）。

### `D36`–`D38` 留下的、后续必须用到的事实

- **外部插件用不上 `runtime/bootstrap.py` 的 `keep` 声明过滤**（`_ENABLED_NAMES` 按**内建
  id** 索引）。因此一份 manifest 声明了几条能力就必须注册几条——想让某条「默认可用」，
  就得让它在零配置下真的可用（`web` 的默认搜索后端因此必须不要凭据）。要按配置少注册
  一条，唯一的路是 `D38-A` 的命名空间声明。
- **`PLUGIN_LOAD_FAILED` 是提供方级的。** 一份 manifest 里的两条能力共命运：在 `setup()`
  里因为缺一个凭据而抛错会把另一条一起带走。`web` 因此把凭据解析推迟到第一次调用
  （代价：配置里少一个 `api_key` 不会在启动时报出来）。
- **anyio 任务组必须在进入它的那个任务里退出。** 任何用 `AsyncExitStack` 持有
  第三方 async 上下文的插件都要照 `plugins/…-mcp/supervisor.py` 的形状写：
  `ctx.spawn_task()` 派生一条任务拥有整个 stack，`setup()` 等它就绪再注册。
  **manifest 没有 teardown 字段**——那条任务是唯一的清理通道。
- **`setup()` 可以是 `async` 的**（`kernel/plugins/builtin_loader.py:40` 早就写着），
  而外部插件的 `setup()` 跑在 `wire_capabilities` 里，**有运行中的事件循环**，
  因此 `ctx.spawn_task()` 在那里可用。

### `D34`/`D35` 留下的、后续必须用到的事实

- **工具进度提示的唯一数据源是 `tool.call_started` 事件**（`plugins/…-feishu/tool_hints.py`）。
  `OutboundMessage` 只有 `content` 与 `metadata`，不带工具调用信息，因此 Channel 想显示
  「agent 正在读文件」只能订阅事件、按 `correlation.session_key` 路由回 conversation。
  载荷里**没有工具参数**，所以提示只有工具名——要恢复参数级细节就得把文件内容、绝对路径
  与 shell 命令放进一条会被全部订阅者看到、会落进事件日志、还会被发到聊天平台上的载荷里，
  那是一次要单独评审的脱敏决定。
- **事件订阅者签名是同步的 `Callable[[RuntimeEvent], None]` 且连续 5 次抛异常会被自动退订**。
  要异步处理就在回调里 `put_nowait` 进自己的**有界**队列，再由一条后台任务消费
  （`feishu` 的 `_drain_hints`）。
- **`R6` 与债务棘轮都没了**：`scripts/legacy_debt.py`、`legacy_debt_baseline.json`、
  `tests/architecture/test_legacy_debt.py` 与 CI 的那个步骤全部删除。
  `tests/architecture/` 现在守的是 `R1`–`R5`。
- **沙箱下跑 pytest 要加 `--basetemp=.pytest-tmp`**：系统临时目录不可写时 `tmp_path`
  夹具会以 `PermissionError` 报错，而那与被测代码无关。
- **`docs/` 只剩三篇能力文档**（`session-storage` / `permissions` / `plugin-development`）。
  21 篇描述被继承实现的文档随 `D35` 删除。新层的用户文档（安装、配置字段、CLI 参考、
  部署）**由 `D46` 补齐**——`docs/{getting-started,configuration,cli,deployment}.md`。
  **一条能力以插件形态落地时，在同一个 PR 里写它的文档**。
  `D36`–`D38` 的三个插件各自带一份 README（配置表 + 已知边界 + 不做的事），
  `plugins/README.md` 的清单同步更新；`plugin-development.md` 因 `D38-A` 多了 §7.5
  （它的代码块由 `tests/e2e/test_plugin_docs.py` 直接执行）。

## 本目录文档分类

本目录同时存放长期文档和临时开发文档，两者的生命周期不同：

**长期文档**（不随模块完成删除）

- [`开发背景.md`](./开发背景.md)：项目愿景、目标和核心开发原则。
- `README.md`：本交接文档。

**临时开发文档**（模块完成后删除）

开发某个模块前，可以直接在本目录新增临时 Markdown 文档，例如
`plugin-runtime.md` 或 `memory-interface.md`。文档用于记录该次开发的目标、技术方案、
任务拆分、风险和验收方式。

模块开发完成后：

1. 将项目状态、关键结果和后续工作同步到本文档。
2. 将仍然有效的使用方式或架构事实更新到正式代码文档。
3. 删除已经完成使命的临时开发文档，避免旧方案干扰后续开发。
