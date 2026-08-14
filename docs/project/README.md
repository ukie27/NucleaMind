# NucleaMind 项目交接

- 更新时间：2026-08-14
- 当前阶段：阶段 8 旧路径清理 **已收口**（`D00`–`D31` 均已完成；
  下一步 `D32+` 能力插件化，从 Model 与 Channel 开始）

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
  - 验收：**完整套件 4900 passed / 18 skipped / 0 failed**（`D30` 收口时新层 2238，
    另有 14–18 个既有失败落在网络、子进程时序与 oauth-cli-kit 家族——**那批用例全部位于被
    删除的目录里，因此这一轮真的是零失败**）。`ruff check`（src + tests + plugins +
    examples + scripts）、`basedpyright`（新层 0 报错，legacy 仍是既有 4 个，全在
    `skills/skill-creator/scripts/`）、`legacy_debt --check` 通过（基线已下调）、
    `check_startup_cost --check` 通过（`startup_ms` 约 500 ms，仍是 `D24` 记的那条
    `import httpx` 告警）。**legacy 债务 352 文件 / 133317 行 → 225 文件 / 77040 行**
    （降 42%）。真实 `nm --help`（无 legacy 子命令）/ `nm serve --bogus`（退出码 2）
    在开发机上跑通。


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
  `kernel/` 目前有 `registry/`、`turn/`、`config/`、`observability/`、`routing/` 与
  `plugins/`；`builtins/` 有 `registry.py` 与七个内建子包（`session_jsonl/`、
  `context_basic/`、`model_openai/`、`tools_fs/`、`tools_shell/`、`commands_core/`、
  `cli_entry/`）；`runtime/` 有 `wiring.py`、`introspection.py`、`plugin_context.py`、
  `bootstrap.py`、`first_run.py`、`inventory.py`、`plugin_plan.py`、`instance.py`、
  `inspect.py`、`config_edit.py`、`access/` 与 `cli/`；`embed/` 已落地薄门面。
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

1. **`D32+` 能力插件化**（阶段三 P1）：按技术方案 §13 M5 的顺序与五步法逐个立项
   （Model / Memory / Tool / Channel / Cron / WebUI），每个模块独立编号、独立验收。
   建议从 **Model** 与 **Channel** 起步——`legacy/providers/`（14103 行）与
   `legacy/channels/`（47807 行）是 `D31` 刻意留在树里的迁移源。
   每迁完一个模块，同 PR 内删除 `legacy/` 对应目录与其 `tests/legacy/` 用例
   ——`legacy/` 债务指标不下降即视为该模块未完成。`legacy/` 清空后删除该目录、
   `R6` 守卫与 `scripts/legacy_debt.py`。
2. **两件 `D31` 明确推迟的事**，立项时一并考虑：
   - **Channel 泵的并发**：`runtime/instance.py::_pump` 串行处理同一 Channel 的消息，
     因此 `openai-api` 的并发客户端会排队。放开它要重新回答 `EDG-202` 的严格 FIFO 断言，
     不是顺手能做的事。
   - **WebUI**：`D31` 删掉了它的后端（`legacy/webui/` + gateway + websocket 通道），
     前端源码 `webui/` 仍在树里但没有服务端可连。

`D31` 留下的、`D32+` 必须用到的事实：

- **`R6` 自此没有例外**：`runtime/legacy_entry.py` 与那条精确白名单都已删除，
  守卫的断言从「恰好只有一处新层 → legacy 导入」改成「一处也没有」。
  迁移期间**不要**为了图快再开一条例外——`legacy/` 里的代码要用就搬到新家并补测试
  （`AGENTS.md` 原则 5）。
- **`legacy/` 剩下的是不可达的库代码**（225 文件 / 77040 行）：没有任何入口能启动它，
  `nm legacy`、`legacy/__main__.py` 与 gateway 都不在了。它只有一个用途——`D32+` 的
  在树迁移参考。`legacy/__init__.py` 的惰性导出表已缩到三个仍有实现可指的名字。
- **`command/` 被削过**：dream 家族 / `/goal` / `/trigger` 七个处理器随它们服务的子系统
  （agent 的 memory、goal_permission、triggers/）一并删除，`build_help_text()` 与其余命令
  保留——`channels/{discord,telegram}` 的 `/help` 靠它。`config/schema.py` 的 `tools` 小节
  六个按工具切分的子配置也随 `agent/tools/` 一并删除，前向引用的 `model_rebuild` 机制
  整套移除。
- **OpenAI 兼容接口现在是插件**（`plugins/nucleamind-plugin-openai-api/`）：它要 `pip
  install --no-deps -e` 装上才会被 entry point 发现，CI 有独立一步，`pyproject` 的
  `testpaths` 也加了 `plugins`。**它是第一个官方插件，`D32+` 的 Channel 插件照它的形状写。**
- **`nm serve` 是通用的**：任何 `CHANNEL` 能力都能用它跑无头模式，不要为某个插件写第二条
  常驻命令。`--host` / `--port` 是所有网络 Channel 的公分母，翻成
  `plugins.openai-api.config.*` 的覆盖；其余配置走 `--set`。
- **`model.response_received` 的载荷多了 `input_tokens` / `output_tokens`**：这是 token
  用量在进程外的**唯一**公开出口（`TurnOutcome` / `TurnReceipt` 都不带它）。JSONL 事件
  日志因此也有了用量记录。

`D30` 留下的、`D31` 用到的事实：

- **`on_disable` 是 `plugins.<id>` 条目的第三个键**（`config` / `secrets` / `on_disable`，
  `kernel/config/plugin_blocks.py::ENTRY_KEYS`）。`on_override_failure` 仍未落地，仍不放行
  ——放行一个没人读的键等于让它看起来生效了。取值写错时**不回落到任何一个**。
- **判定只在 `runtime/plugin_disable.py::suppressed_capabilities()` 一处**，由
  `bootstrap` 在步骤 3d（发现之后、注册之前）调用，`inspect_capabilities()` 也调同一个
  ——两条路印出来的生效集合必须是同一份。它是 `R5` 的又一个落点（manifest 的 `overrides`
  在 `sdk/`，registry 的抑制表在 `kernel/`）。
- **`resolve()` 现在有两个禁用输入**：`disabled`（按提供方）与 `suppressed`（按能力，
  `(kind, provider, name) -> 原因`），在 `_partition_disabled` 一处合并判定，后果相同——
  既不生效也不参与冲突判定，但都留在报告的 `disabled` 段里。**按能力抑制不是给覆盖开的
  后门**：它只能让一项能力消失，不能让某一方赢。
- **`tests/runtime/conftest.py` 有一条 autouse 夹具把 entry point 清空**。示例插件在开发
  环境里是真的装着的，那一层的用例不该看见它们。要在那一层验真实 entry point 的用例自己
  传 `entry_points=`——夹具挡不住那条显式路径，那正是它可注入的理由。
- **`pytest` 的 `testpaths` 多了 `examples/plugins`**，且那两个包必须先
  `pip install --no-deps -e` 装上（CI 有独立一步，`AGENTS.md` 的开发命令里也记了）。
  没装时 `tests/e2e/test_plugin_runtime.py` 的第一条用例会以一句能照做的话失败。
- **`docs/plugin-development.md` 是对外的插件开发入口**，代码块由
  `tests/e2e/test_plugin_docs.py` 直接执行。`D31` 改动 SDK 表面时那套测试会先失败。

`D29` 留下的、`D31` 必须用到的事实：

- **`config.json` 现在有两个写入点，分工是硬的**：`runtime/first_run.py` 只用
  `O_CREAT|O_EXCL` 建**新**文件（既有文件一个字节都不动、没有 `--force`）；
  `runtime/config_edit.py` 只**改**既有文件里的一个字符串列表。要再加一条「改配置」的
  命令就走后者，别在别处第三次拼写「读 → 改 → 写」。它只读写 `config.json` 那一层、
  从不解析 secret、原子替换，三条缺一条 `CFG-003` 或 `CFG-005` 就有一条不再成立。
- **只读诊断走 `runtime/inspect.py`，不走 `bootstrap()`**：`inspect_plugins()`（到阶段 A
  为止）、`inspect_capabilities()`（跑一次注册拿 `ResolutionReport`）与
  `open_session_store()`（`D23` 搬来的）共用同一套承诺——不取实例锁、不 `save()` 权限
  账本、不装 orchestrator、不做步骤 8 的必需能力判定、不 `raise_if_failed()`。
  `nm plugins` / `nm capabilities` / `nm session` 都从这里取数。
- **`plan_external(strict=False)` 与 `wire_capabilities(halt_on_critical=False)` 是诊断
  路径专用的两个旋钮**：前者让关键插件在阶段 A 的失败只记不抛，后者让关键提供方的
  `setup()` 失败只记不抛。**它们都不改 manifest 里的 `critical`**——那是「失败的后果由
  装配根决定」（`PLG-004`）的应用，启动路径的默认值仍是 `True`。
- **`/plugins` 的状态 = 清单 + 生命周期投影**（`bootstrap._plugin_statuses`）：
  `PluginState` 由 `lifecycle.state` 给出（`PHASE_STATES` 是唯一那张表），因此一个跑完
  `setup()` 的插件显示 `loaded`、`start()` 之后显示 `activated`。**已记下的失败不被覆盖**，
  内建不进这张表（它们是 `Builtin()` 提供方而不是插件）。
- **跳过原因的文案只有一份**（`inventory._SKIP_REASONS` → `PluginStatus.reason`）。
  `D30` 写文档时如果要解释「为什么我的插件没被加载」，引用那张表而不是重写一遍。
- **`bootstrap.py` 已经贴着 800 行上限**（本轮 784 行）。再往装配根加东西之前先想清楚
  它属不属于「装配」——只读查询归 `inspect.py`，改配置归 `config_edit.py`。
- **`nm` 现在有七个子命令**：`init` / `run` / `config show` / `session` / `permissions` /
  `plugins` / `capabilities`。全部在 `main.py` 里**延迟导入**（`nm --version` 不该付装配根
  那条 import 链的代价），加子命令时照抄这条。

`D28` 留下的、`D29`–`D31` 必须用到的事实：
`D28` 留下的、`D29`–`D31` 必须用到的事实：

- **停止顺序只有一个来源，且它是加载顺序的逆序**：`stop_order(LoadPlan.order)`。
  装配根交给 `units_for()` 的那张顺序表就是 `contexts` 的顺序（内建在前、外部按拓扑序
  在后），因此「被依赖者后停」与「被依赖者先起」共用同一个序——不要在停止侧再排一次。
- **阶段是判定口径、`PluginState` 是显示口径**：`PluginPhase`（六个阶段 + `FAILED`）与
  `PHASE_TRANSITIONS` 那张唯一的转换表在 `kernel/plugins/lifecycle.py`，投影表
  `PHASE_STATES` 也在那里。`D12` 定的「不发明第二套生命周期 taxonomy」的兑现方式就是
  这个投影，`nm plugins` 渲染时读 `lifecycle.state` 而不是自己判。
- **`FAILED` 不是终态**：`setup()` 中途失败的插件可能已经订阅过事件或派生过任务
  （`setup` 跑在事件循环里），它欠一次清理，因此 `FAILED -> STOPPING` 是合法边。
  唯一的终态是 `STOPPED`。
- **停止超时后是放弃等待而不是等它结束**（`EDG-104`）：那个协程可能仍在跑，
  `StopOutcome.timed_out` 与独立的 `TIMEOUT_PLUGIN_STOP` 错误码如实标着这件事。
  预算是 `plugins.stop_timeout_ms`（默认 5000），**按插件各算一份**。
- **`EDG-105` 的三项在 P0 分别落在两处**：取消订阅与取消任务在
  `RuntimePluginContext.shutdown()`；「注销能力」**不在运行期**——registry 解析后只读
  （`NFR-403`）且首版不热更新（§10.4），被禁用的提供方在下一次启动时连 `setup()` 都不跑。
  想做热更新就要先回答「已经被别人取回的实现体怎么办」（`ToolExecutor` 在装配时就持有
  它们了），那不是加一个 `unregister()` 能解决的。
- **`kernel/config/schema.py` 撞过 500 行上限**：那批「镜像自 `kernel.turn` /
  `kernel.routing` / `kernel.plugins` 的默认值字面量」已经拆到
  `kernel/config/defaults.py`，schema 从那里 import 再原样再导出。加新配置字段时，
  默认值常量写进 `defaults.py`，字段声明仍然只进 `SECTION_SPECS`。
- **`plugins` 小节的保留键现在有四个**（`enabled` / `disable` / `search_paths` /
  `stop_timeout_ms`）。它们与插件 id 共用命名空间但撞不上：插件 id 不允许下划线。
  新增保留键时沿用带下划线的形状，理由写在 `plugin_blocks.RESERVED_PLUGIN_KEYS` 上。

`D27` 留下的、`D28`–`D30` 必须用到的事实：

- **阶段 A 的七步现在分布在三处**，加东西前先认这条分界线：A1/A2/A3 在
  `runtime/inventory.py`（`D25`），A4/A5/A7 的**机制**在 `kernel/plugins/loader.py`、
  **manifest 判定**在 `runtime/plugin_plan.py`（`D27`），A6 在
  `runtime/bootstrap.py::approve()`（`D26`）。加一种排序或校验机制改 kernel 那份，
  加一条 manifest 判定改 runtime 那份——与 `discovery` / `inventory` 完全相同的分界线。
- **外部插件与内建共用一次 `wire_capabilities()`**（`SDK-007`）：同一个 manifest 序列、
  同一个 `context_for`、同一个 `keep`，唯一的差别是 `provider_for` 交出 `Builtin()` 还是
  `Plugin(<id>)`。内建在前、外部按拓扑序在后，但**顺序不决定覆盖**（`EDG-102`）。
  想给插件加一条「特殊的」注册路径之前，先读 `builtin_loader.py` 的模块 docstring。
- **加载顺序的唯一来源是 `LoadPlan.order`**。`plan_load_order()` 同层按 id 字典序，
  因此同一份配置每次得到同一个顺序；依赖可以指向内建（经 `provided` 交进去）。
- **阶段 A 落榜的三种理由分得开**：依赖缺失（`detail.missing`）、成环
  （`detail.cycle` 是整条环，`PLG-003`）、级联（`detail.blocked_by`）。别把它们并成
  一句「依赖有问题」——三者的补救动作分别是装插件、改 manifest、先修另一个插件。
- **`state_version` 变化即拒绝加载，升与降都是**（`kernel/plugins/loader.py`）：P0 没有
  状态迁移机制，两个方向都是拿用户数据赌一把，而 `EDG-503` 要的是「升级失败保住旧状态」。
  标记文件是 `<instance>/plugins/<id>/.nucleamind-state.json`，**只在状态目录已经存在时**
  才读写——不为一个从未写盘的插件建目录（与 `ctx.state_dir` 的惰性创建同一条约定）。
  `D28` 做迁移函数时，放宽的是这一处判定，不是再加一条并行路径。
- **`jsonschema` 现在有两个接触点**：`kernel/turn/invoker._compile()` 与
  `kernel/plugins/loader._compile()`，**两处都惰性 import**（`NFR-405` 的冷启动预算）。
  加第三处之前先想清楚它会不会落在 `nm config show` 那类只读路径上。
- **`/plugins` 的「已发现」= 真的会被加载的那一批**：阶段 A 落榜的插件由
  `plan_plugins()` 从 `discovered` 移进 `failures`（`PluginState.FAILED`，
  `failed_phase="discovery"`），因此 `D29` 渲染时不需要再区分是哪个阶段落的榜。
- **`nm session` 也会加载外部会话存储插件**了（`open_session_store`）：它仍然只取声明了
  `SESSION_STORE` 的 manifest、仍然不取实例锁、仍然不写 `permissions.json`。
- **冷启动实测已与 `README` 早先记录的 480 ms 不同**（本机 ~900 ms，`import` 约 550 ms）。
  这与 `D27` 无关——在 `D27` 之前的 HEAD 上实测 ~990 ms，同一台机器。`NFR-405` 的这一项
  按原文只告警不失败，真要压下去仍然是「让 `model-openai` 的 httpx 延迟到第一次请求」。

`D26` 留下的、`D27`–`D30` 必须用到的事实：

- **授权判定只有一个调用点**：`runtime/bootstrap.py::approve()`。`D27` 的外部插件加载
  必须走它，不要在 loader 里另判一次——账本的 TOFU 语义（首见即授予、扩权落 `pending`）
  只在那一处成立。manifest → `Grant` 的翻译同样只在 `declared_grants()` 一处（`R2` 禁止
  kernel 认识 `PermissionDecl`）。
- **`PluginGrants` 从 `kernel/plugins/permissions.py` 取**，不再在 `runtime/` 里定义；
  它的形状是 `frozenset[(PermissionKind, target)]`，`allows()` / `allows_secret()` /
  `targets()` 是它的全部查询面。`PluginGrants.of("fs:read", ...)` 是测试与 `embed/` 的
  便利构造。
- **`ctx.fs` / `ctx.shell` 需要 workspace**：`build_plugin_context(workspace=...)` 没传时
  两个门面抛 `CAPABILITY_MISSING`（授权判定在此之前已经过了）。装配根传的是
  `loaded.workspace_root`，与 `tools_fs` 同一个根。
- **`runtime/access/paths.py` 是 workspace 双重校验的第三份实现**，改判定要改三处
  （另两处：`builtins/tools_fs/paths.py`、`builtins/tools_shell/paths.py`），有对照测试。
  `runtime/access/shell.py` 的环境基线名单同理，与 `builtins/tools_shell/environ.py` 对照。
- **`import nucleamind.runtime.access` 不会拉进 httpx**（`net.py` 里是函数内 import）。
  加新调用点前想一下这件事——`NFR-405` 的冷启动预算已经被 `model-openai` 那笔占满了。
- **`EventName` 现在是 32 条**，新增的 `capability.permission_granted` 由授予 / 待批准 /
  撤销共用，靠载荷的 `decision` 区分。加事件名要同时改
  `tests/contracts/test_events.py::EVENT_NAME_SNAPSHOT`。

`D25` 留下的、`D26`–`D29` 必须用到的事实：

- **`plugins.enabled` 是外部插件的总开关**，`plugins.disable` 压过它。前者是 `D25` 新增的
  保留键，后者仍是既有的「按提供方禁用」（对内建同样有效）。`RESERVED_PLUGIN_KEYS`
  现在是三个，改它要同时改 `SECTION_SPECS["plugins"]`。
- **`D27` 的加载计划输入是 `build_inventory().discovered`**，每一项带着候选（来源、位置）
  与已校验的 manifest。**不要在 `D27` 里重新发现一遍**，也不要把发现挪进加载——「未启用
  即零导入开销」是靠「先筛后读」成立的。
- **entry point 的 name 必须等于 manifest 的 id**，这条判定在
  `runtime/inventory.py::_validate`。`D30` 写插件模板与文档时要写明这一条。
- **`PluginStatus.reason` 是自由文本**，取值来自 `inventory._SKIP_REASONS` 那张表。
  `D29` 渲染 `nm plugins` 时直接印它，不要在 CLI 侧再写一份原因文案。
- **`kernel/plugins/discovery.py` 不认识 manifest 类型**（`R2`），它交出的是 `object`。
  要给发现加一种来源，加在那里；要给校验加一条规则，加在 `runtime/inventory.py`。
  分界线与 `builtin_loader` / `wiring` 那次完全相同。
- **`import nucleamind.runtime.inventory` 会拉进 pydantic**（`sdk/manifest.py`）。
  它只在装配根上被 import，`nm config show` 这类路径够不着——加新调用点前想一下这件事。

`D24` 留下的、`D25`–`D29` 必须用到的事实：

- **`kernel/config/` 依然一个字节都不写**。`scaffold.py` / `json_schema.py` 只渲染，
  唯一的写入点是 `runtime/first_run.py`，用 `O_CREAT|O_EXCL`、**没有 `--force`**。
  要再加一份「生成到实例目录里的文件」，落点是那里，不是 `kernel/`。
- **顶层 `$schema` 是 `validate_config()` 唯一放行的非小节键**
  （`schema.IGNORED_TOP_LEVEL_KEYS`，具名一条而不是前缀规则）。往那张表里加第二个键之前
  先想清楚：它会让一个拼错的小节静默消失。
- **`config.schema.json` 是 `SECTION_SPECS` 的派生物**，`nm init` 每次都会把过期的那份刷新
  （内容相同则不写）。加配置字段不需要动它，但**加一种 `FieldKind` 必须在
  `json_schema._KIND_SCHEMAS` 里补一条**——缺项是 KeyError 而不是静默退化成「任意值」，
  有测试盯着这条。
- **首次运行只生成、不进会话**（§10.1 步骤 2）。要改成「凭据就绪就直接跑」之前先读
  `runtime/cli/commands/run.py` 的模块 docstring：那会让同一条命令有两种结局。
- **缺凭据的错误现在带 `file`**（`config.json` 的绝对路径），由装配根经
  `build_plugin_context(config_path=...)` 交下来，`resolve_text(source=...)` 放进 `detail`。
  `kernel/config/` 自己不知道那棵配置树是从哪个文件读来的，因此这条只能由调用方传。
- **`NFR-405` 的 300 ms 目前没达到**：`scripts/check_startup_cost.py` 的 `startup_ms` 在
  开发机上约 480 ms，其中 import 约 340 ms。**大头是 `import httpx`**（单独一项约 280 ms），
  它由 `model-openai` 在 `setup()` 时构造 provider 连带拉进来。按 `NFR-405` 的原文这一项
  **只告警不失败**；真要压下去，方向是让 `builtins/model_openai/provider.py` 的 httpx 延迟到
  第一次请求——那会动 `D19` 的 `except httpx.HTTPError` 这类语句，不是顺手能做的事。
- **`tests/e2e/` 里唯一的替身是传输层**（`conftest.recorder` 换掉 `httpx.AsyncClient`）。
  往里加用例时守住这条：把某个内建换成 Fake，它就退化成 `tests/integration/` 的重复。
- **`ToolExecutor.orphans` 已经接上了**（`AgentInstance.stop()` 里的 `_report_orphans`，
  `D14` 留的那条）。它靠 `isinstance(ToolExecutor)` 窄化——`ToolInvoker` 协议里没有孤儿表，
  第三方执行器可以完全没有这个概念，给协议加成员会逼每个实现编一张空表。

`D23` 留下的、`D25`–`D27` 必须用到的事实：

- **`plugins.<id>` 是插件配置的落点**，值形如 `{"config": {...}, "secrets": {...}}`。
  `disable` / `search_paths` 是保留键。**`plugins` 小节是全项目唯一对未知键让路的小节**
  （那些键是插件 id），校验在 `kernel/config/plugin_blocks.py`，别在 `schema.py` 里另开
  一张表。逐字段校验（manifest 的 `config_schema`）是 `D25` 阶段 A 的活，现在还没人做。
- **`ctx.secret()` 已经接到 `resolve_text()` 上**（`runtime/plugin_context.py`）。`D26`
  要做的是在 `grants_of(manifest)` 之前再叠一层**用户批准**（`permissions.json`）——形状
  不必改，只是构造 `PluginGrants` 的人多问一句。`fs` / `net` / `shell` 三个访问器目前抛
  `CAPABILITY_MISSING` 并指向 `D26`，那不是遗漏，是「没有守卫就不给门面」。
- **`wire_capabilities(context_for=...)` 按 manifest 索引**，不是按 `ProviderId`。`D27` 加
  外部插件时照抄这条：内建全是 `Builtin()`，按提供方索引会让配置块串到一起。
- **`AgentInstance.stop()` 会取消 ctx 派生的任务与事件桥任务**（`EDG-104`/`EDG-105` 的
  当前形态）。`D27` 落地插件生命周期时，`plugin_stop_timeout_ms` 的等待要加在这里，
  而不是另起一套任务表。
- **`ToolExecutor.orphans` 仍然没有调用方**（`D14` 留的那条）：实例停止时应当报告它。
  `AgentInstance.stop()` 是它唯一合理的落点，`D24` 或 `D26` 顺手接上即可。
- ~~**`Diagnostics.plugins_source` 仍是默认的空元组**~~ **`D25` 已接上**：数据源是
  `runtime/inventory.py::PluginInventory.statuses`，在 `runtime/bootstrap.py` 里传入。
  `D27` 加载完插件后应当**更新**那一份状态，而不是再写第二套查询。
- **`nm plugins` / `nm capabilities` 还没有**（`D29`）。`runtime/cli/commands/` 里加一个
  模块即可，数据源是 `AgentInstance.diagnostics`，与会话内的 `/plugins` 共用。
- **Windows 上有两条已知的平台差异**：控制台编码不是 UTF-8（输出遇到编不出来的字符会
  降级成转义，提示符因此只用 ASCII）；`tools_shell` 的 `shell` 配置项不生效（`D21`）。
  两条都如实写在各自的 docstring 里。

`D22` 留下的、`D23`/`D26` 必须用到的事实：

- **`D23` 必须给 `commands_core` 装上 `ctx.instance` 与 `ctx.turns` 的生产实现**，
  两个 builder 都在 `runtime/introspection.py`：
  `build_instance_view(commands_source=…, diagnostics=…, config_source=…, sessions=…)` 与
  `build_turn_control(orchestrator)`。**`commands_source` 与 `config_source` 必须是
  callable 而不是快照**——命令索引要等全部插件注册完才建得出来，而 `PluginContext` 必须在
  `setup()` **之前**就交给插件，传一份当时还不存在的索引是不可能的。漏传的后果是 `/help`
  永远显示「当前没有可用的命令」而**不报任何错**（`FakeInstanceView` 上已经踩过一次，
  `set_commands()` 就是那个时序的最小形态）。
- **`/help` 里的命令前缀目前是硬编码的默认 `/`**（`commands_core/commands.py::DEFAULT_PREFIX`，
  与 `kernel/routing/dispatcher.py::DEFAULT_COMMAND_PREFIX` 各写一份）。改过
  `routing.command_prefix` 的用户会在 `/help` 里看到错的前缀。`D23` 接线时可以把它经
  `commands-core` 的配置块交下来——那是这条偏差的正确落点，**不要让内建去读 routing 小节**
  （`ctx.config` 按 `CFG-002` 只给自己那一块）。
- **`InstanceView.config_document()` 是全项目唯一越过 `CFG-002` 的地方**。`D23` 传给它的
  应当是 `LoadedConfig.to_json()` 那棵**持有 `${VAR}` 字面量**的树，不要传解析过 secret 的
  版本——`/config` 的脱敏是靠这条结构性保证成立的，`redact()` + `scrub()` 只是纵深防御。
- **`ctx.instance` / `ctx.turns` 不需要权限声明**，与 `ctx.events` 同一档（只读可观测性不是
  资源访问）。`D26` 落地权限模型时若要给它们加门，`TurnControl` 是该先加的那个——取消别人的
  turn 是控制动作，这正是它与 `InstanceView` 分成两个 Protocol 而不是一个七成员门面的理由。
- **`SUPPORT_PROTOCOLS` 现在是 3 条**（`tests/contracts/test_protocols.py`），
  `CAPABILITY_PROTOCOLS` 仍恒为 9——新增的两个不是可注册能力。往 `PluginContext` 加成员要
  同时改 `test_public_surface.py::API_PROTOCOLS` 与那里的只读属性豁免名单，两处都是
  `NFR-103` 的评审闸门。

`D21` 留下的、`D22`/`D23`/`D26` 必须用到的事实：

- **`D23` 必须给 `tools_shell` 传两样东西**，与 `tools_fs` 完全同构：① 配置块里的
  `workspace` 键（没配就退回插件私有状态目录 `<instance>/plugins/tools-shell/`，命令会在
  一个没人预期的目录里执行）；② `wire_capabilities()` 的 `keep` 参数
  （`lambda manifest, decl: decl.name in enabled_tool_names(config_of(manifest))`）。
  不传 `keep` 且用户禁用了 `shell.exec` 时，`tools-shell` 会以 `PLUGIN_LOAD_FAILED` 加载
  失败——那是 `CapabilityHost.finish()` 在如实报告「声明与注册对不上」。`critical=False`，
  因此失败只记进 `Wiring.outcomes`，实例仍会起来但没有 shell 工具。
- **`SideEffect.UNKNOWN` 现在有了唯一的产出点**：`tools_shell` 的取消宽限期用尽
  （`executor._fold` 的第三档）。`D22` 之后如果还有别的工具要产出 `UNKNOWN`，判据是同一条
  ——「失败发生在副作用可能已经发生**之后**，且无法确认做完没有」。`tools_fs` 一次都不产出，
  别把两者的规矩搞混。
- **`shell` 权限未授予时，工具仍然会被注册**，只是每次调用被 kernel 的 `ToolExecutor` 折成
  `PERMISSION_DENIED` + `side_effect=NONE`。开发方案 `D21` 那句「未授予 shell 权限时工具
  不注册」在当前架构下**没有落地点**：`granted` 是 `ToolExecutor` 的实例级参数（`D14`），
  而注册发生在装配期、那时还没有权限集合。**要真正做到「不注册」得等 `D26`**——届时可以在
  `wire_capabilities` 的 `keep` 里再加一条「manifest 声明的权限 ⊆ 实例已授予的权限」，
  机制已经在那里了。当前行为由 `TestPermissionGate` 如实钉住，不是遗漏而是已知边界。
- **cwd 守卫有第二份实现**（`builtins/tools_shell/paths.py::CwdGuard`），与
  `tools_fs.WorkspaceGuard` 由 `test_cwd_guard_matches_the_fs_workspace_guard` 五条对照钉住。
  改任何一边的判定都要同时改另一边并更新那条测试——这是刻意的重复（两个独立提供方，
  见该模块 docstring），不是待清理的债务。
- **Windows 上 `shell` 配置项不生效**，命令恒由 `%ComSpec%`（`cmd.exe`）执行。改这件事之前
  先读 `command.py` 的模块 docstring：那不是偷懒，是 `list2cmdline()` 与 `cmd /c` 的原始
  命令行语义不兼容。`D23` 写文档时要如实说明这条平台差异。
- **`DEFAULT_GRACE_MS` 与 `kernel/turn/cancel.py::DEFAULT_TOOL_CANCEL_GRACE_MS` 各写一份**
  （`R4` 逼的，与 `estimate_tokens` 同一种做法），由一条对照测试钉住。要把宽限期做成配置项
  之前先想清楚：它在 kernel 那侧是取消参数而不是六项预算之一（`D14` 的结论）。

`D20` 留下的、`D21`/`D23` 必须用到的事实：

- **`D23` 必须给 `tools_fs` 传两样东西，缺一样都会安静地跑偏**：① 配置块里的
  `workspace` 键（没配就退回插件私有状态目录 `<instance>/plugins/tools-fs/`，文件工具会
  在一个没人预期的地方读写，与 `D17` 的 `dir` 是同一个坑）；② `wire_capabilities()` 的
  `keep` 参数（`lambda manifest, decl: decl.name in enabled_tool_names(config_of(manifest))`）。
  **不传 `keep` 时，只要用户在配置里禁用了任何一个工具，`tools-fs` 就会以
  `PLUGIN_LOAD_FAILED` 加载失败**——那是 `CapabilityHost.finish()` 在如实报告「声明与注册
  对不上」，有一条用例专门钉住它。`critical=False`，因此失败只记进 `Wiring.outcomes`，
  实例仍会起来但没有文件工具。
- **`D21` 的 `tools_shell` 直接复用 `keep` 这条路**：单工具禁用不需要再发明第二套机制，
  `shell.exec` 只有一个名字，但形态完全一致。同时注意 `tools_shell` **不进**
  `test_builtin_no_privilege.py::_READ_ONLY_BUILTIN_PACKAGES`——它如实声明 `shell` 权限，
  与 `tools_fs` 声明 `fs:read`/`fs:write` 同理。
- **`SideEffect.UNKNOWN` 在 `D21` 才第一次真的出现**。`tools_fs` 的失败全部发生在落盘之前
  （临时文件 + `os.replace`），因此它一次 `UNKNOWN` 都不产出；`shell.exec` 的取消宽限期用尽
  是那个取值的正主（`EDG-407`），别照抄 `base.FsTool` 里「折出来的失败一律 `NONE`」那一句。
- **路径守卫可以直接复用**：`shell.exec` 的 cwd 要限定在 workspace，`tools_fs.WorkspaceGuard`
  就是那道门。但它在 `builtins/tools_fs/` 里，而 `builtins/` 之间互相 import 是否可接受要先
  确认（`R4` 只管 `builtins → kernel`）；不确定就照 §4「优先重复而非过早抽象」各写一份，
  两份由一条对照测试钉住——与 `estimate_tokens` 在 `context_basic` 与 `context_builder` 里
  各写一份是同一种做法。

`D19` 留下的、`D23`/`D26` 必须用到的事实：

- **`ctx.secret("api_key")` 必须真的能取到值，`model_openai` 才起得来**。`D19` 只能对着
  `FakePluginContext` 测（生产级 `PluginContext` 是 `D26`）。`D23`/`D26` 落地时，
  `ctx.secret()` 的实现要接到 `kernel/config/secrets.py::resolve_text` 上——那是 `D11` 那条
  「provider 凭据用 `resolve_text()`」笔记的正确落点：由 ctx 那侧调，而不是让 `builtins/`
  直接调（`R4` 拦得住）。`CONFIG_SECRET_MISSING`（授权了但环境变量没导出）与
  `PERMISSION_DENIED`（没授权）必须可区分，`model_openai` 依赖这个区分把「去补配置」和
  「去改权限」两种补救分开。
- **`OpenAIModelProvider` 有一个 `aclose()`，`ModelProvider` 协议里没有它**。httpx 连接池
  要在实例停止时释放，`D23` 装配时应当在关停路径上调它一次（多次调用安全）。协议不加生命
  周期钩子是刻意的——不是每个 Provider 都有连接池。
- **`auth="none"` 时 `model_openai` 不碰 `ctx.secret()`**。本地 vLLM / Ollama / LM Studio
  没有密钥，`D23` 给本地端点装配时**不要**为它授予 `secret:api_key`，否则一个必然缺失的
  凭据会让实例起不来。授不授 `secret` 权限要跟着 `auth` 走。
- **`model_openai` 声明了 `net` 权限并直接用 httpx**，`ctx.net` 的 SSRF 守卫对它不生效。
  `D26` 落地权限模型后，`net` 权限对内建的意义仍只是「可审计」而非进程隔离——这是
  `sdk/api.py` 写死的应用级权限语义，不是 `model_openai` 的特例。

`D18` 留下的、`D20`–`D23` 必须用到的事实：

- **`context_basic` 不产出 `trust=SYSTEM` 的运维内容**。用户在配置里写的自定义指令是
  `TrustLevel.OPERATOR`，落在历史之后的一条 user 消息里而不是 system 消息里（`CMD-005`）。
  `D23` 装配后如果有人反馈「我的系统提示词没生效」，答案是这条而不是 bug。要改这个语义，
  改的是契约层对 OPERATOR 的定义，不是内建实现。
- **只读内建有一张显式清单**：`tests/architecture/test_builtin_no_privilege.py::
  _READ_ONLY_BUILTIN_PACKAGES`。往里加一个包，就等于承诺它连 `os` / `pathlib` / 裸 `open`
  都不出现、manifest 里一条权限都不声明。`D20`/`D21` 的 `tools_fs` / `tools_shell` **不进**
  这张表——它们如实声明权限，走 `session_jsonl` 那条路。
- **token 估算公式现在有两份**（`builtins/context_basic/instructions.py` 与
  `kernel/turn/context_builder.py`，都是 `ceil(len/3)`）。任何要自报 `estimated_tokens` 的
  新 Provider 都得用同一把尺，改比值要同时改两处并更新对照测试。
- **`D14` 定的「同优先级先丢片段再丢历史」现在有了真实样例**：运维指令片段与历史同为
  `priority=0`，预算收紧时先丢片段。`D19` 接上真模型后，`resolve_context_max_tokens` 会从
  模型窗口推导预算，这条裁剪顺序才第一次真正生效。

`D17` 留下的、`D19`–`D23` 必须用到的事实：

- **内建能力拿不到实例布局**（`R4` 禁止 import `kernel/`），要写盘就只能让装配根把路径
  经 `ctx.config` 交下来。`session_jsonl` 用的键是 `dir`，没配时退回 `ctx.state_dir`。
  **`D23` 必须在装配时把 `layout.sessions_dir` 填进 `session-jsonl` 的配置块**，否则会话
  会写到 `<instance_dir>/plugins/session-jsonl/` 而不是 `sessions/`——两处都能跑，
  只有 `nm session` 找不到文件。`D20` 的 `tools_fs`（workspace 根）会遇到同一件事。
- **文件名在 `layout.session_paths()` 与 `session_jsonl` 里各写了一份**，由
  `tests/builtins/test_session_jsonl.py::test_filenames_match_the_instance_layout` 对照。
  改后缀要同时改两处。
- **`docs/session-storage.md` 是发布出去的格式契约**（`SES-006`），文档里的示例被测试直接
  解析。改 `codec.py` 的字段就得改文档，反之亦然——这是刻意的双向闸门。
- **`tests/` 现在是一个包**（新增了 `tests/__init__.py`）。没有它 `tests/builtins/` 会与标准库
  的 `builtins` 撞名、整个目录收集失败。新增测试目录时不需要再操心这件事。
- **`SESSION_SCHEMA_VERSION` 现在从 `nucleamind.contracts` 直接可导**（`D17` 补的转发）。

`D16` 留下的、`D19`–`D23` 必须用到的事实：

- **注册载荷形状现在九个 kind 全齐了**。`D14` 的四个（`RegisteredTool` / `RegisteredHook` /
  `RegisteredContextProvider` / `RegisteredCommand`）加 `D16` 的五个（`RegisteredModelProvider`
  / `RegisteredSessionStore` / `RegisteredChannel` / `RegisteredMemoryProvider` /
  `RegisteredCliEntry`，都在 `kernel/plugins/capabilities.py`）。取回函数同理九个，
  取回后的实现体在 `binding.value` 上。
  **内建能力自己不构造这些形状**——Host 会按 `register_*` 的参数替你构造。
- **`session_store_from()` 与 `cli_entry_from()` 返回 `| None`**。`D23` 必须在装配根上把
  「MODEL / SESSION_STORE / CLI_ENTRY 各须有一个生效实现」变成明确的启动错误
  （§10.1 步骤 8），并实现 `EDG-108` 的「覆盖失败时 CLI 强制回落内建」——kernel 层不做这个
  判定，它只如实回答有没有。（`D17` 之后 SESSION_STORE 已经有了。）
- **`critical` 是提供方级的，不是每项能力各有一个**。同一份 manifest 里的全部能力共享一个
  `critical`；需要不同关键性就得是两个插件。`tests/integration/_support.py` 因此按 `critical`
  分批注册，`D19`–`D22` 写 manifest 时要意识到这一点。
- **`priority` 在 manifest 里别写**，除非真的要偏离基准值。写了就会被原样采纳（哪怕写的
  正好是默认值 100），而内建的基准是 0——`D18` 的 `context_basic` 已经按这条落地，§10.2 的
  「其余按 priority 逆序丢弃」依赖内建排在最前。
  `tests/runtime/test_wiring.py::test_every_builtin_manifest_leaves_priority_unset` 是这条的棘轮。
- **`wire_capabilities(context_for=...)` 没有默认值**，因为 `D16` 还没有生产级
  `PluginContext`（那是 `D26`）。`D23` 之前一律传 `FakePluginContext`；`D26` 落地后在
  `host.py` 之外补 `PluginContext` 的实现，**不得重写注册分派**。
- ~~**`BUILTIN_MANIFESTS` 现在是空元组**~~ **`D17` 起不再为空**，第一条是 `SESSION_JSONL`。
  想验「零内建可装配」要显式传 `manifests=()`，不能指望默认值。
- **五个契约基类各有一个反向样例盯着**（`tests/sdk/test_contract_reverse_samples.py`）。
  往基类里加用例时，要同时想清楚「什么样的实现会被这条拦下」——加不出反向样例的用例，
  多半是在描述某个具体实现的行为而不是契约。

`D15` 留下的、`D16` 已兑现的事实：

- ~~**五个 kind 还没有取回函数与注册载荷形状**~~ **`D16` 已补齐**，见上。
- ~~**`sdk.testing` 目前没有 Fake 工具 / Fake Channel / Fake Context Provider**~~
  **`D16` 已补**（另加 `FakeMemoryProvider` / `FakeCliEntry` / `FakePluginContext`），
  `sdk.testing.__all__` 快照相应更新。
- ~~**`tests/integration/_support.py::wire()` 应当改用真 Host**~~ **`D16` 已改**，
  并因此发现了 `critical` 的层级差异（见上）。
- **`tests/integration/` 的 Fake 边界不要往里挪**：Fake 只在能力边界上，能力之间一律生产
  实现。往里挪一层，这套测试就退化成 `tests/kernel/` 的重复。
- **一次 turn 的事件名序列与 Hook 触发顺序都以字面量钉在
  `tests/integration/test_skeleton_turn.py` 里**。改动编排顺序会让它们失败——那是刻意的
  评审闸门，不要通过放宽断言绕过。（`D16` 改接真 Host 之后它们仍一字未改地通过。）


`D14` 留下的、`D15`/`D16`/`D22`/`D23` 必须用到的事实：

- **注册载荷的形状已定死三个**，`D16` 的 Host 分派必须按这个形状注册，
  各自的 `*_from(registry)` 会当场核对：
  `turn.RegisteredHook(hook, handler, critical)`、
  `turn.RegisteredContextProvider(provider, critical)`、
  `turn.RegisteredTool(spec, handler)`，外加 `D13` 已定的
  `routing.RegisteredCommand(spec, handler)`。**`critical` 由注册方从 manifest 带进来**
  ——`kernel/` 不认识 manifest，而 `CTX-005`/`PLG-004` 的分叉必须在 kernel 里判。
- **`D23` 装配 `OrchestratorDeps` 的清单**（`kernel/turn/orchestration.py` 是唯一真相）：
  必填 `instance_id` / `bus` / `sessions` / `model` / `tools` / `hooks` / `dispatcher` /
  `scheduler` / `dedup` / `limits` / `model_id`；其余有默认值。三个超时从新的配置小节来：
  `HookRouter(bindings, observer_timeout_ms=cfg.hooks.observer_timeout_ms,
  interceptor_timeout_ms=cfg.hooks.interceptor_timeout_ms, on_failure=…)` 与
  `context_provider_timeout_ms=cfg.context.provider_timeout_ms`。
  `scheduler` 的类型参数必须是 `SessionScheduler[TurnReceipt]`。
- **`ToolExecutor` 的 `granted` 是实例级授权**，默认全授予。`D26` 落地权限模型后要把它换成
  真实集合——`prepare()` 取的是 `spec.permissions & granted`，缺权限在 `invoke()` 里折成
  `PERMISSION_DENIED` 结果（`side_effect=NONE`，工具还没被碰过）。
- **`ToolExecutor.orphans` 是 `EDG-104` 的落点**：实例停止时应当报告它（还有
  `orphans_dropped`——「表里没有」与「被挤掉了」是两个结论）。目前没有调用方。
- **`deliver` 回调是 Channel 的接线口**：`OrchestratorDeps.deliver` 缺省为 `None`（只攒不
  发，测试与嵌入式用），`D23` 应当传一个按 `OutboundMessage.channel_id` 路由到对应
  `Channel.deliver()` 的函数。
- **`TurnOrchestrator.cancel(turn_id, reason)` 是 §10.3 的唯一入口**，`live_turns` 列出在跑
  的 turn。`D23` 的 Ctrl-C 处理与 `D22` 的 `/cancel` 命令都走它，不要另建一张令牌表。
- **`EventTap` 不要拆掉**：它是「engine 不发 `RuntimeEvent`」这条边界的兑现方式。想让
  engine 直接拿一个 bus，就等于给 `EngineDeps` 开第五个槽。

`D13` 留下的、`D22`/`D23` 必须用到的事实：

- ~~**turn 事件由 `D14` 独家发布**~~ **`D14` 已落地**：`orchestrator.py` 是唯一发布点，
  命令类 turn 同样有 `turn.started` 与终态事件（`KER-010`）。
- **准入顺序是 去重 → 并发 → 分流**，不能换。`DedupCache.remember()` 返回 `DedupHit`
  就直接跳过执行并引用上一次的 `turn_id`（`EDG-201`），**不要**让它先进队列。
- **`SessionScheduler.submit(key, message, run)` 的 `run` 拿到的是一批消息**
  （`QUEUE`/`REJECT` 恒为一条，`MERGE` 可能多条）。编排层的签名要按元组写，
  换并发策略时才不需要改 orchestrator。会话历史的写入必须发生在 `run` 内部——
  那是「持锁的单一写者」唯一成立的地方。
- **`D22` 的每个内建命令注册的载荷必须是 `routing.RegisteredCommand(spec, handler)`**，
  `build_command_index()` 会当场核对形状。权限（`operator_only`）与参数个数由 dispatcher
  统一前置校验，命令自己不要再抄一遍。**带自由文本的命令要声明一个 `repeated=True` 的尾
  参**，否则 dispatcher 会按「参数过多」拒掉（`D14` 写测试时踩到的）。
- **`D23` 装配时按配置构造三件套**：`Dispatcher(index, prefix=cfg.routing.command_prefix)`、
  `SessionScheduler(policy=ConcurrencyPolicy(cfg.routing.session_concurrency),
  queue_max_size=cfg.routing.queue_max_size)`、
  `DedupCache(capacity=…, ttl_ms=…)`。`build_command_index()` 要在启动期调用一次并让它的
  异常直接冒泡——那正是 `CMD-002` 的「启动期报错」。

`D12` 留下的、`D14`/`D23`/`D29` 必须用到的事实：

- **`EventBus.publish()` 是同步的，不要 `await` 它**，也不要在订阅者里做慢活。
  订阅者签名是 `Callable[[RuntimeEvent], None]`；要异步处理就在回调里塞进自己的有界队列。
  连续 5 次失败或超过 50 ms 的投递会让订阅者被**自动退订**，查 `bus.health()`。
- **发事件只走 `bus.publish(name, correlation=…, payload=…, error=…)`**，不要自己构造
  `RuntimeEvent`：序号由 bus 分配，绕过它就会出现两个真相来源，`OBS-002` 的重放随之失效。
  载荷不必自己脱敏——`prepare_payload()` 在构造前已经做完（`OBS-003`）。
- **`D23` 必须接三根线**：`JsonlFileSink(layout.events_log_path)` 与 `MemoryRingSink()`
  各 `bus.subscribe()` 一次；配置解析失败的 `except` 里调
  `write_config_error(layout.config_error_log_path(today), error)`（`EDG-501` 后半句，
  这是它唯一的落地点，漏了就没人实现）。实例停止时记得 `JsonlFileSink.close()`。
- **`D14` 把 `D09` 的 9 个引擎事件翻译成 `EventName`**：`TurnStoppedByLimit` →
  `turn.stopped_by_limit`（`D12` 新增的那个）。engine 自己不发布任何 `RuntimeEvent`，
  它只产出封闭联合的引擎事件——那条边界不要在 `D14` 里模糊掉。
- **`D29` 的 `nm capabilities` / `nm plugins` 与会话内 `/plugins` 共用
  `Diagnostics`**，不各写一套查询；`D25`–`D27` 落地后只需给 `plugins_source` 传一个真
  实现，`PluginStatus` / `PluginState` 已经备好。`PluginState` 的取值必须继续对得上
  `EventName` 的 plugin 族，有测试盯着。
- **`EventName` 现在有字面量快照**（`tests/contracts/test_events.py::EVENT_NAME_SNAPSHOT`）。
  新增事件名要同时改那张表，那就是 `NFR-104` 的评审闸门。

`D11` 留下的、`D24`/`D26` 必须用到的事实：

- **`ctx.secret()` 返回的就是 `contracts.SecretStr`**（`D26`），不需要任何跨层转换——
  这正是把它下沉到 `contracts/` 换来的。
- **要落盘一份配置，先过 `prepare_for_write()`**（`D24`）。`kernel/config/` 自身仍然一个
  字节都不写。
- ~~**provider 凭据用 `resolve_text()` 解单个字段**（`D19`）~~ **`D19` 改走 `ctx.secret()`**：
  `resolve_text()` 在 `kernel/config/secrets.py`，`R4` 禁止 `builtins/` import `kernel/`，
  这条笔记按字面已不可执行。`model_openai` 声明 `secret:api_key` 并调 `ctx.secret("api_key")`
  拿 `SecretStr`，`CONFIG_SECRET_MISSING` 与 `PERMISSION_DENIED` 的区分由 ctx 那侧兑现
  （`FakePluginContext` 已有此行为基准）。`resolve_text()` 仍在，接线在 `D23`/`D26`——
  把 `ctx.secret()` 的实现接到它上面，而不是让 `builtins/` 直接调它。

`D10` 留下的、`D11`/`D12`/`D14`/`D23` 必须用到的事实：

- ~~**`EDG-501` 的「把解析错误写到 `<instance_dir>/logs/`」`D10` 没有讨完**~~
  **`D12` 已落地** `write_config_error()`，落点 `layout.config_error_log_path(day)`；
  **`D23` 接线时必须调用它一次**，否则这条需求仍然没人实现。`EDG-501` 的核心
  （拒绝启动 + 原文件不被改写）在 `D10` 已完整兑现：`config.json` 只以 `"rb"` 打开、
  只在 `sources.read_config_file` 一处，`kernel/config/` 全包不出现任何写文件调用。
- **`EDG-108`（配置试图禁用 CLI 入口）超出 `D10` 能力范围**：`resolve(disabled=...)` 是按
  **提供方**索引的，表达不了「禁用某一个能力 kind」。**交给 `D23`/wiring**，在那里
  `BUILTIN_MANIFESTS` 才存在、能知道哪一项是 `CLI_ENTRY`。
- **`D11` 的缝已留好**（`D11` 已按此落地）：loader 把 `${VAR}` 当普通字符串、从不解析；
  `config.json` 缺失不是错误（`file_present` 语义由默认值层承担）；`kernel/config/`
  **从不写文件**，因此 `CFG-003` 的写回天然不会被加载路径破坏。
  `LoadedConfig.merge.origins` 保留了逐指针来源，写回时可据此判断哪些值是用户显式写的。
- ~~**`D24` 的缝已留好**~~ **`D24` 已用上它**：`schema.SECTION_SPECS` 与 `schema.defaults()`
  是**唯一**的字段真相来源，`json_schema.py` 从它派生编辑器用的 schema，`scaffold.py` 只放
  「用户必须动的那几个键」。命名按技术方案 §4.2 定为 `scaffold.py`（开发方案那行写的
  `bootstrap.py` 已作废——`runtime/bootstrap.py` 是 `D23` 的装配根，两者不是一回事）。
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
- ~~**`TurnStoppedByLimit` 的 `EventName` 缺口未解决**~~ **`D12` 已按 `NFR-104` 新增
  `turn.stopped_by_limit`**，并给 `EventName` 补了字面量快照。`D14` 直接用它，不要拿
  `turn.completed` 承载。
- ~~**「用完预算后发一次不带 tools 的收尾请求」归 `D14`**~~ **`D14` 已落地**
  （`orchestrator._wrap_up`）；长度截断续写与空回复重试仍未实现，见技术方案 §6.2.2。
- ~~**参数非法由 `ToolInvoker` 判定**~~ **`D14` 已落地**（`invoker.py` 用 `jsonschema`，
  顺序固定为 schema → 权限 → 执行）；未知工具名仍由 engine 合成错误消息。
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
  **`D14` 也没有实现它们**（技术方案 §6.2.2 已记为待办）：做法已经明确——用同一个
  `ledger` 再调一次 `run_turn`——但它需要真实 Provider 的 `stop_reason=LENGTH` 才有意义，
  留到 `D19` 之后再论证次数。
- ~~**取消宽限期……届时需要在 `contracts/errors.py` 补 `tool.cancel_timeout` 码**~~
  **`D14` 已落地**：码是 `ErrorCode.TIMEOUT_TOOL_CANCEL`，宽限期赛跑与孤儿任务表在
  `kernel/turn/invoker.py`（不 `task.cancel()`——`CancelledError` 会让工具没机会
  「保存已做的事再退出」，那正是 `CancelToken` 存在的理由）。

`D07` 留下的、`D09`/`D14` 必须用到的事实：

- **`tests/baseline/` 是一次性设施**：只锁 `legacy/agent/{loop,runner}.py` 的五类行为，
  `D31` 删 `legacy/agent/` 的同一个 PR 内一并删除（`tests/baseline/README.md` 写死了这条）。
  不要往里加与那五类无关的测试——越像通用套件越删不动。
- **`D09` 的用法是「换构造、不换断言」**：把 `AgentRunner` 与 `AgentRunSpec` 的构造换成新
  engine，断言尽量原样重跑。改不动的断言就是新旧语义差异，要在 `D09` 的文档里给结论，
  **不要靠放宽断言让它通过**。`test_loop_behavior.py` 的决定项已由 `D14` 的 orchestrator
  承接：预算耗尽推流（收尾请求）、工具失败不终止本轮、二次截断、孤儿 tool 丢弃、空
  assistant 不入历史各有对应用例；两条不再成立的是 `fail_on_tool_error`（engine 不认识
  这个开关）与 tool 结果的重放（新层保真存储但重放时跳过，见技术方案 §6.2.2）。
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
D10 ✅  D11 ✅  D12 ✅  D13 ✅  D14 ✅  D15 ✅  D16 ✅  D17 ✅  D18 ✅  D19 ✅  D20 ✅  D21 ✅
D22 ✅  D23 ✅  D24 ✅  D25 ✅  D26 ✅  D27 ✅  D28 ✅  D29 ✅  D30 ✅  D31 ✅
D32+ ⬜（能力插件化，尚未立项）

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
