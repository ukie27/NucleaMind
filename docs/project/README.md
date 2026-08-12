# NucleaMind 项目交接

- 更新时间：2026-08-12
- 当前阶段：阶段 5 内建能力**进行中**（`D00`–`D17` 均已完成，下一步 `D18`–`D22`）

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
  `BUILTIN_MANIFESTS` 从此不再是空元组。
  `kernel/` 目前有 `registry/`、`turn/`、`config/`、`observability/`、`routing/` 与
  `plugins/`；`builtins/` 有 `registry.py` 与 `session_jsonl/`（`D18`–`D22`
  逐个追加其余六项），`runtime/` 有 `wiring.py`；`embed/` 仍是空骨架。
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

1. 继续阶段 5 的其余内建能力：`D18` context_basic、`D19` model_openai、`D20` tools_fs、
   `D21` tools_shell、`D22` commands_core。它们之间无相互依赖，可并行开发。
   **每个内建能力的落地形态已经定死**：写一份 `PluginManifest` 追加进
   `builtins/registry.py::BUILTIN_MANIFESTS`，再写一个 `setup(api)` 用 `api.register_*`
   注册——没有别的路，`tests/architecture/test_builtin_no_privilege.py` 会当场拦下任何
   自建注册通道。先继承 `sdk.testing` 的对应契约基类再写自己的用例。
   `D17` 的 `builtins/session_jsonl/` 是这个形态的第一个样例，照着它写即可。
2. `D23` 装配根接线时把 `runtime/wiring.py` 扩成完整 bootstrap（§10.1 的 10 步）。

`D17` 留下的、`D18`–`D23` 必须用到的事实：

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

`D16` 留下的、`D18`–`D23` 必须用到的事实：

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
  分批注册，`D18`–`D22` 写 manifest 时要意识到这一点。
- **`priority` 在 manifest 里别写**，除非真的要偏离基准值。写了就会被原样采纳（哪怕写的
  正好是默认值 100），而内建的基准是 0——`D18` 的 `context_basic` 尤其要注意，§10.2 的
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

`D11` 留下的、`D19`/`D24`/`D26` 必须用到的事实：

- **`ctx.secret()` 返回的就是 `contracts.SecretStr`**（`D26`），不需要任何跨层转换——
  这正是把它下沉到 `contracts/` 换来的。
- **要落盘一份配置，先过 `prepare_for_write()`**（`D24`）。`kernel/config/` 自身仍然一个
  字节都不写。
- **provider 凭据用 `resolve_text()` 解单个字段**（`D19`）：没有引用时它原样返回 `str`，
  「这个值来自环境变量」这条信息因此保得住；缺失时抛 `CONFIG_SECRET_MISSING`，必须与
  `PERMISSION_DENIED` 可区分（`sdk/api.py::secret` 的 docstring 已写死这条）。

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
D10 ✅  D11 ✅  D12 ✅  D13 ✅  D14 ✅  D15 ✅  D16 ✅  D17 ✅   D18– ⬜（尚未开始）

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
