# NucleaMind 项目交接

- 更新时间：2026-08-11
- 当前阶段：阶段 3 支撑设施推进中（`D00`–`D11` 均已完成，下一步 `D12`）

本文档用于在新会话或开发者之间交接 NucleaMind 当前状态。完成一个较大的模块、
项目阶段或架构调整后，应同步更新本文档，使下一次开发可以直接从“下一步工作”
开始。

长期愿景和开发原则见 [`开发背景.md`](./开发背景.md)，仓库开发规则见
[`../../AGENTS.md`](../../AGENTS.md)。

## 当前项目状态

- NucleaMind 已与上游 nanobot 的 Git 历史和协作流程分离。
- **`D00` 已落地**：包名 `nucleamind`，发行名 `nucleamind`，CLI 命令只有 `nm`。
  仓库为 `src/` 布局：`src/nucleamind/{contracts,kernel,sdk,builtins,runtime,embed}/`
  为空骨架，遗留实现全部在 `src/nucleamind/legacy/`（352 个 Python 文件 / 133317 行，
  债务基线）；顶层新增 `plugins/`、`examples/plugins/`、`deploy/`，
  原 `tests/` 移到 `tests/legacy/`。
- nanobot 原有的 Agent Runtime、Channels、Tools、Memory、WebUI 等能力仍保留，
  通过 `nm legacy <原参数>` 运行；`legacy/` 内部继续使用 `NANOBOT_*`、`~/.nanobot/`
  和 camelCase 配置（迁移期运行契约，不是兼容承诺）。
- 当前目标是先明确核心边界和扩展机制，再逐步将具体能力迁移为可选插件。
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
    分发、续写 = 共享 ledger 再调 `run_turn`、收尾请求归 D14）。完整 33 行对照表在
    `docs/project/d09-turn-engine.md`（临时文档，收口后删除）。
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

## 正在进行

- `D00`、`D01` 已完成，阶段 0 工程基座收口；`D02`–`D06` 已完成，契约层三层（基础 /
  领域与执行 / 能力）、SDK 表面与 Capability Registry 全部落地，**阶段 1 已收口**；
  `D07` 已完成，旧实现行为基线就位；`D08` 已完成，取消与预算就位；`D09` 已完成，
  Turn Engine（纯循环 ≤400 行）就位，`D09` 的两个前置依赖（`D06` + `D08`）已兑现，
  阶段 2 的 engine 一层完成；`D10` 已完成，实例布局、分层配置与实例锁就位，
  `D06`/`D08` 欠给配置层的两件事（`resolve(disabled=...)` 的输入、`TurnLimits` 的配置
  来源）已兑现，阶段 3 开始；`D11` 已完成，`${VAR}` 凭据引用、`SecretStr` 与写回保护
  就位（`SecretStr` 下沉到 `contracts/errors.py`，`sdk` 表面相应调整）。
  `kernel/` 目前有 `registry/`、`turn/` 与 `config/`；`builtins/`、`runtime/`、`embed/`
  仍是空骨架，尚未开始拆分 `legacy/` 的现有模块。
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

1. 执行 `D12` 可观测性：`kernel/observability/{bus,redaction,diagnostics}.py`。
   `EventBus` 只做扇出；**脱敏在事件构造时完成**（`redaction.py` 复用
   `contracts.errors.redact`，它在 `D11` 之后已经认得 `SecretStr`，不要另写一份）；
   订阅者异常与超时被隔离（`NFR-204`）；内存环有容量上限（`NFR-404`）。
   同时补上 `D10` 欠的 `EDG-501` 后半句（把配置解析错误写到 `logs/`，落点
   `layout.config_error_log_path(day)`）。前置依赖 `D02` 早已就绪。
2. 阶段 2 的编排层 `D14` Orchestrator（≤500 行，`kernel/turn/orchestrator.py`）：
   承接 `test_loop_behavior.py` 的 12 条决定项，消费 `D09` 的事件流
   （`TurnEvent` 封闭联合 + `ToolCallCompleted.message` 直接持久化），实现
   `ToolInvoker` / `HookDispatcher` 的真实版本（宽限期 + 孤儿任务表 `EDG-407`/`EDG-104`）。
   属于 4 个高风险模块之一，建议先单独评审实现方案。前置依赖 `D10` 已就绪。

`D11` 留下的、`D19`/`D24`/`D26` 必须用到的事实：

- **`ctx.secret()` 返回的就是 `contracts.SecretStr`**（`D26`），不需要任何跨层转换——
  这正是把它下沉到 `contracts/` 换来的。
- **要落盘一份配置，先过 `prepare_for_write()`**（`D24`）。`kernel/config/` 自身仍然一个
  字节都不写。
- **provider 凭据用 `resolve_text()` 解单个字段**（`D19`）：没有引用时它原样返回 `str`，
  「这个值来自环境变量」这条信息因此保得住；缺失时抛 `CONFIG_SECRET_MISSING`，必须与
  `PERMISSION_DENIED` 可区分（`sdk/api.py::secret` 的 docstring 已写死这条）。

`D10` 留下的、`D11`/`D12`/`D14`/`D23` 必须用到的事实：

- **`EDG-501` 的「把解析错误写到 `<instance_dir>/logs/`」`D10` 没有讨完**，是刻意的：
  文件 sink 是 `D12` 的职责，事件总线此刻还不存在，而一个在自己错误路径上做 IO 的 loader
  是第二个故障面。`layout.config_error_log_path(day)` 已备好落点，`NucleaError.detail`
  本身可 JSON 序列化。**`D12` 落地 sink、`D23` 接线时必须补上这一句**，否则这条需求会
  静默地没人实现。`EDG-501` 的核心（拒绝启动 + 原文件不被改写）在 `D10` 已完整兑现：
  `config.json` 只以 `"rb"` 打开、只在 `sources.read_config_file` 一处，
  `kernel/config/` 全包不出现任何写文件调用。
- **`EDG-108`（配置试图禁用 CLI 入口）超出 `D10` 能力范围**：`resolve(disabled=...)` 是按
  **提供方**索引的，表达不了「禁用某一个能力 kind」。**交给 `D23`/wiring**，在那里
  `BUILTIN_MANIFESTS` 才存在、能知道哪一项是 `CLI_ENTRY`。
- **`D11` 的缝已留好**（`D11` 已按此落地）：loader 把 `${VAR}` 当普通字符串、从不解析；
  `config.json` 缺失不是错误（`file_present` 语义由默认值层承担）；`kernel/config/`
  **从不写文件**，因此 `CFG-003` 的写回天然不会被加载路径破坏。
  `LoadedConfig.merge.origins` 保留了逐指针来源，写回时可据此判断哪些值是用户显式写的。
- **`D24` 的缝已留好**：`schema.SECTION_SPECS` 与 `schema.defaults()` 是**唯一**的字段
  真相来源，`bootstrap.py` 生成最小 `config.json` 时应当从它派生，不要再手写一份模板。
  命名待对齐：技术方案 §4.2 叫 `scaffold.py`，开发方案 `D24` 那行叫 `bootstrap.py`。
- **配置的四层优先级只在 `sources.collect_layers()` 的返回顺序里定义一次**
  （`default < config.json < env < cli`）。新增来源要改那一处，不要在 loader 里另排一遍。
- **环境变量是 `NUCLEAMIND_CFG_<SECTION>__<KEY>`**（双下划线分隔层级，因为字段名本身
  含下划线），与选实例用的 `NUCLEAMIND_INSTANCE_DIR` / `NUCLEAMIND_INSTANCE` 靠前缀区分。
  **实例定位的优先级是「显式目录 > 显式实例名 > 目录环境变量 > 名环境变量 > default」**
  ——命令行参数压过环境变量，与配置四层同序；否则 shell 里导出过的
  `NUCLEAMIND_INSTANCE_DIR` 会静默吃掉 `nm --instance work`。
- **`kernel/config/` 不获取实例锁**：加载配置是纯读操作，必须能在 `nm config show`、
  诊断与测试里安全调用；获取锁会改全局状态且需要配对释放。`InstanceLock` 的生命周期
  归 `runtime/bootstrap.py`（§10.1 步骤 1 在步骤 2 之前）。本包也不注册 `atexit`。
- **实例名的长度上限是 64**（`MAX_INSTANCE_NAME_LENGTH`），远小于 `contracts` 的通用标识
  上限：它会成为一段路径分量，下面还要接 `sessions/<storage_id>.jsonl`，Windows 默认
  MAX_PATH 是 260。想放宽要先想清楚会话写入在运行期失败的场景。

`D09` 留下的、`D10`/`D12`/`D14` 必须用到的事实：

- **engine 只分发 4 个 Hook**（`ENGINE_HOOKS`）：`BEFORE_MODEL_REQUEST`（每轮，次数 ==
  迭代数——`D14` **不得**再分发一次，§10.2 已加脚注）、`AFTER_MODEL_RESPONSE`（观察者，
  `HookOutcome` 没有 `response` 槽，响应改写永远走不通，续写只能多次调 `run_turn`）、
  `BEFORE_TOOL_CALL`、`AFTER_TOOL_CALL`（`REPLACE` 发生在截断之前）。`turn_start` /
  `context_assemble` / `turn_end` 归 orchestrator。
- **`ToolInvoker.invoke` 必须在 `timeout_ms + tool_cancel_grace_ms` 内返回**（docstring
  写死）；宽限期与孤儿任务登记只能在那里做。engine 不加第二层超时。`D14` 验收必须有一条
  「不可取消工具在宽限期后返回 `side_effect=UNKNOWN`」的独立测试。
- **工具失败不升级为 `TurnFailed`**（与开发方案验收表措辞不同的一处，结论在
  `test_engine.py::test_tool_invoke_error_does_not_fail_the_turn` 与 §6.2.1）。
  `fail_on_tool_error` 若需要由编排层多次调用之间检查，engine 不认识它。
- **`TurnStoppedByLimit` 的 `EventName` 缺口未解决**：`EventName` turn 族只有 5 个，
  没有 `turn.stopped_by_limit`。`D12` 按 `NFR-104` 评审新增，或 `D14` 显式论证用
  `turn.completed` 承载。倾向前者（`EDG-304`）。
- **「用完预算后发一次不带 tools 的收尾请求」归 `D14`**（引擎撞上限即停）。
- **参数非法由 `ToolInvoker` 判定**（§10.2 第 10 步 schema 校验划给 invoker）；
  未知工具名仍由 engine 合成错误消息。
- **写内建/插件工具时**：声明 `FS_WRITE` 或 `SHELL` 权限的工具必须显式
  `concurrency=EXCLUSIVE`（默认 `PARALLEL` 与旧行为相反，`scheduling.py` docstring 写死）。

`D08` 留下的、`D09`/`D14` 必须用到的事实：

- **检查点归属已经定死**：`CHECKPOINT_OWNERS` 里 engine 拿 2/3/5/6
  （`BEFORE_MODEL_REQUEST` / `BETWEEN_STREAM_CHUNKS` / `BEFORE_TOOL_CALL` /
  `AFTER_TOOL_RESULT`），orchestrator 拿 1/4。engine 里出现 1 或 4 就是分层错了——
  它不知道 context 从哪来，也不负责写 assistant 消息。一律用 `token.checkpoint(where)`
  而不是 `raise_if_requested()`，前者才带得上「停在哪一步」。
- **engine 主循环的记账骨架**是 `check(pending_tool_calls=…)` -> `begin_iteration()` ->
  模型 -> `record_tool_calls()`。判定必须在**发起前**，`test_limits.py` 里那段最小循环
  就是这个骨架；`D09` 落地后由 `tests/kernel/test_engine.py` 在真引擎上重跑同一条
  「缺省配置下有限步终止」的性质。
- **越界不等于失败**：`LimitBreach.terminal_status` 为 `None` 的三项（单工具超时、
  结果截断、上下文超限）turn 继续；`turn_timeout_ms` 的终态是 `CANCELLED` 而不是
  `STOPPED_BY_LIMIT`。不要在 engine 里另写一份 kind→终态的判断，查 `LIMIT_OUTCOMES`。
- **旧实现的 `_MAX_LENGTH_RECOVERIES = 3` / `_MAX_EMPTY_RETRIES = 2` 没有进
  `TurnLimits`**：六项是技术方案 §6.4 冻结的表格，这两个是「模型返回异常时重试几次」
  的编排策略（`EDG-303`），归 `D14`。engine 不该认识它们。工具超长结果落盘同理。
- **取消宽限期在 `cancel.py`**（`DEFAULT_TOOL_CANCEL_GRACE_MS = 2000`），不在 `TurnLimits`
  里。`EDG-407` 的等待与孤儿任务登记由 `D09` 的工具调用路径实现，用
  `asyncio.wait_for(task, grace)` 或 `token.wait()` 赛跑；超时后写
  `ToolResult(ok=False, side_effect=UNKNOWN)`，届时需要在 `contracts/errors.py` 补
  `tool.cancel_timeout` 码（`D08` 未预先登记未被使用的码）。

`D07` 留下的、`D09`/`D14` 必须用到的事实：

- **`tests/baseline/` 是一次性设施**：只锁 `legacy/agent/{loop,runner}.py` 的五类行为，
  `D31` 删 `legacy/agent/` 的同一个 PR 内一并删除（`tests/baseline/README.md` 写死了这条）。
  不要往里加与那五类无关的测试——越像通用套件越删不动。
- **`D09` 的用法是「换构造、不换断言」**：把 `AgentRunner` 与 `AgentRunSpec` 的构造换成新
  engine，断言尽量原样重跑。改不动的断言就是新旧语义差异，要在 `D09` 的文档里给结论，
  **不要靠放宽断言让它通过**。`test_loop_behavior.py` 的决定项由 `D14` 的 orchestrator 承接。
- 旧实现的两条边界值得在新引擎里重新论证而不是照抄：`_MAX_LENGTH_RECOVERIES = 3`、
  `_MAX_EMPTY_RETRIES = 2` 与「工具超长结果落盘到 workspace」都属于 `D08` `TurnLimits`
  六项预算或 `D14` 的编排范畴，engine 本身不该再认识它们。
- 基线里出现的 `.nanobot/tool-results/`、`NANOBOT_LLM_TIMEOUT_S` 是**迁移期运行契约**，
  新层不保留（技术方案 §4.5），它们出现在断言里只是因为被测的是旧实现。

`D07` 之前就已成立、继续有效的事实：

- **`kernel/` 读 manifest 的分层张力，`D06` 已给出结论：不读。** `Registration` 只带
  `overrides` 的**原始串**，由契约层的 `parse_capability_target()` 解码——manifest 的
  `overrides` 字段（`sdk`）与覆盖解析（`kernel`）复用同一份实现，两边都不认识对方的类型。
  因此 `D05` 记下的三条出路选的是**第三条的最小形态**：需要跨层传递的形状已经在
  `contracts/capability.py` 里（`CapabilityRef` / `parse_capability_target`），
  `PluginManifest` 整体**不必**下沉。`D25` 的 `kernel/plugins/` 沿用同一约定：
  由 `runtime/`（唯一组装根）把 manifest 翻译成 `RegistrationBatch.add()` 的参数，
  kernel 侧不出现第二套 manifest 校验。
- **注册分派只有一套。** `builtins/registry.py` 只提供 `BUILTIN_MANIFESTS`，内建 bootstrap
  与外部插件 loader 都走同一个 Host `NucleaAPI` 实现和 `RegistrationBatch`（技术方案 §6.1
  末段）。`D16` 建立 Host 分派并接收注入的 Context，`D26` 补齐生产级权限实现——
  **禁止为外部插件复制第二套注册分派**。
- **`ResolutionReport` 是 `nm capabilities`（`D29`）与诊断接口的数据源**，四段
  （`active` / `shadowed` / `disabled` / `failures`）已可序列化。`disabled` 由调用方传入的
  「按提供方禁用」集合填充，`D10` 的配置层负责构造它。当前语义：**覆盖一个被禁用的目标
  等同于目标不存在**（报 `override_target_missing`，不回退成新增注册）。若 `D10` 要放宽，
  应在那里显式论证，不要在解析器里留隐式回退。
- **priority 基准值由 `base_priority_for()` 决定**（内建 0 / 插件 100），`D16` 的内建
  bootstrap **不要**自己传 priority，`D18` 的 `context_basic` 与 `D14` 的裁剪逻辑都依赖
  这个基准：§10.2 「其余按 priority 逆序丢弃」意味着内建上下文最后被裁。
- `on_override_failure`（`fail_start` / `use_builtin`，`CLI_ENTRY` 强制后者）**尚未实现**：
  它描述的是「覆盖插件加载失败」时的行为，属于 `D27` 的加载流程，不在 registry 里。

`D06` 之前就已成立、继续有效的事实：

- `sdk.__all__` 与 `sdk.testing.__all__` 是**规范性清单**，有字面量快照测试
  （`tests/sdk/test_public_surface.py`）。增删导出必须改快照，这就是评审闸门（`NFR-103`）。
- `NucleaAPI` 的 9 个注册方法与 `CapabilityKind` 的 9 个取值一一对应，对照表以字面量写死在
  测试里。新增一类能力 = 同时改 `CapabilityKind`、`CAPABILITY_ARITY`、`NucleaAPI`、
  对应 Protocol 与三处快照，没有捷径。
- 契约类型**不从 `sdk` 转发**：插件按 `R4` 直接 `from nucleamind.contracts import ...`。
  有一条测试盯着这件事，不要「顺手加个再导出」。
- manifest 的所有校验失败都是 `NucleaError(PLUGIN_MANIFEST_UNSUPPORTED)` 且带字段路径；
  外部数据只走 `sdk.parse_manifest(data, origin=...)`，不要直接 `PluginManifest(**data)`。
- `sdk/manifest.py` **导入即不得有副作用**，有子进程 audit hook 测试盯着（写文件/网络/
  牵连 `kernel`、`legacy`、`builtins` 都会失败）。往里加 import 前先想清楚。
- 写内建能力或插件时，先继承 `sdk.testing` 的 5 个契约测试基类再写自己的用例；
  基类里「后续应补齐」的清单就是各模块要补的验收项。

`D02` 起就已经成立、继续有效的事实：

- 新层每个模块的首个 docstring 必须含「职责：」「不负责：」两行，
  否则 `tests/architecture/test_module_docstrings.py` 会失败。
- 新层不得出现无 `# boundary:` 说明的 `Any`，不得 import `legacy/`。
  契约层用 `JsonValue` 代替 `Any`，目前新层的 `Any` 数为 0，保持这个数字。
- 错误码只能加在 `contracts/errors.py` 的 `ErrorCode` 并同步登记 `CODE_CATEGORIES`，
  其他模块出现错误码字面量视为违规；`NucleaError` 的 `category` 不接受调用方传入。
- `SessionKey.storage_id()` 的编码**已发布，不可更改**：改动会让历史会话目录失联。
  新增分量同理需要评审——分量数变化会让 `from_storage_id()` 的三段假设失效。
- 标识字段一律用 `contracts.ids.validate_identifier()`，不要在各模块重写非空/长度/
  控制字符三件套。
- `metadata` 与任何「来自外部的 JSON 映射」一律过 `contracts.metadata.normalize_metadata()`：
  它同时完成上限校验、深拷贝与冻结。不要自己 `dict(...)` 了事——快照语义（调用方事后
  改自己那份 dict 不影响已构造对象）依赖它。
- 需要脱敏时复用 `contracts.errors.redact` / `scrub`，不要另写一套；
  新增敏感键名要同时补「必须保留」的反向用例，防止把用量统计一并打掉。
- 新增契约类型或字段时，必须同步 `tests/contracts/test_field_traceability.py` 的
  `TRACEABILITY` 表，否则该测试会失败——这是 `D03` 为「字段遗漏到阶段 5 才暴露」
  设的对冲，不要通过放宽断言来绕过。
- `contracts` 内部的模块依赖方向是
  `errors ← ids ← metadata ← {message, session, context, tool} ← {model, command}
  ← capability ← protocols`，
  子模块只在 `TYPE_CHECKING` 下反向从包根导入 `JsonValue`，运行时不成环。
- 冲突语义只查 `contracts/capability.py::CAPABILITY_ARITY`，Hook 语义只查 `HOOK_KINDS`；
  两张表都有以字面量写死的对照测试，改表必须同时改测试——这是「文档漂移」的挡板，
  不要通过把测试改成从实现反推来绕过。
- 覆盖目标串（`"builtin:fs.read"` / `"plugin:<id>:<name>"`）只用
  `CapabilityRef.target` 与 `parse_capability_target()` 编解码，不要在 manifest 校验或
  registry 里另写正则。
- `protocols.py` 的 9 个 Protocol（`D05` 补入 `CliEntry`）是长期兼容承诺的起点：新增/删除方法必须同步
  `tests/contracts/test_protocols.py` 的快照表，且新方法的 docstring 必须含
  「**异常约定**」与「**取消语义**」两段，否则测试失败（`NFR-104`）。
- 能力实现方只拿到只读的 `CancelSignal`；`request()` / `child()` 属于 `D08` 的
  `kernel/turn/cancel.py::CancelToken`，不要把它加进 `contracts`。
- `legacy/` 债务基线：352 个 Python 文件 / 133317 行
  （`scripts/legacy_debt_baseline.json`，只允许用 `--lower-baseline` 下调）。
- `runtime/legacy_entry.py` 是 `R6` 的唯一例外，白名单精确到这一个文件路径。
- 本机跑测试时系统临时目录可能因沙箱权限不可写，`pytest` 需显式指定 basetemp。
  **basetemp 必须落在仓库之外且父目录须已存在**（例如先建好 `D:/nm_pytest_tmp/`，
  再传 `--basetemp=D:/nm_pytest_tmp/run1`）：放在仓库内会让 `GitStore` 的嵌套仓库保护
  生效，凭空多出约 45 个 git 相关假失败；父目录不存在则 `tmp_path` 夹具直接报
  `FileNotFoundError`，架构守卫的反向用例会全部 error。
- 完整套件在本机的既有失败为 14–18 个，全部在 `legacy/`，与 `D00`–`D05` 无关：
  `test_exec_platform.py` 的 Windows PowerShell UTF-8 用例、
  `test_exec_session_tools.py` 的子进程时序用例、`test_web_fetch_security.py`、
  `test_mcp_probe.py`、`test_mcp_tool.py`、oauth-cli-kit 相关用例，
  以及 `channels/websocket` 的 `test_wrong_path_404`。数量在区间内浮动是因为其中几个
  依赖网络与子进程时序；基线里记录的是这些用例的真实结果，不是「全绿」假设。
  `D06` 完成时的实测为 14 failed / 6785 passed / 35 skipped
  （`D05` 时 14 failed / 6729 passed，`D04` 时 17 failed / 6603 passed，
  `D03` 时 14 failed / 6480 passed，`D02` 时 15 failed / 6295 passed）。失败数在区间内下降是因为网络与子进程时序用例
  这一轮碰巧通过，不是修好了——它们仍是同一批家族。
- `basedpyright` 在 `legacy/skills/skill-creator/scripts/` 上有 4 个既有报错
  （`D00` 之前就存在），不是新层引入的。

当前进度：D00 ✅  D01 ✅  D02 ✅  D03 ✅  D04 ✅  D05 ✅  D06 ✅  D07 ✅  D08 ✅  D09 ✅
D10 ✅  D11 ✅   D12– ⬜（尚未开始）

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
