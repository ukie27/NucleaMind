# NucleaMind 项目交接

- 更新时间：2026-08-10
- 当前阶段：阶段 1 契约与注册表（`D00`–`D02` 均已完成，下一步 `D03`）

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

## 正在进行

- `D00`、`D01` 已完成，阶段 0 工程基座收口；`D02` 已完成，契约基础层落地。
  `kernel/`–`embed/` 各层仍是空骨架，尚未开始拆分 `legacy/` 的现有模块。
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

1. 执行 `D03` 契约·领域与执行层：`contracts/{message,session,context,tool,model}.py`。
   全部 frozen dataclass，字段按需求 §10.2–§10.6 逐条落地并在测试或 docstring 中追溯；
   `ToolResult.side_effect` 必填不给默认值，`ContextFragment.trust` 四级齐全。
   `metadata` 用 `Mapping[str, JsonValue]`（已在 `contracts/__init__.py` 定义）并加大小上限。
2. 按 `D04`–`D06` 落地契约能力层、`sdk/` 骨架与 Capability Registry
   （此阶段不改动 `legacy/` 业务代码）。

`D03` 起需要注意的既有事实：

- 新层每个模块的首个 docstring 必须含「职责：」「不负责：」两行，
  否则 `tests/architecture/test_module_docstrings.py` 会失败。
- 新层不得出现无 `# boundary:` 说明的 `Any`，不得 import `legacy/`。
  契约层用 `JsonValue` 代替 `Any`，目前新层的 `Any` 数为 0，保持这个数字。
- 错误码只能加在 `contracts/errors.py` 的 `ErrorCode` 并同步登记 `CODE_CATEGORIES`，
  其他模块出现错误码字面量视为违规；`NucleaError` 的 `category` 不接受调用方传入。
- `SessionKey.storage_id()` 的编码**已发布，不可更改**：改动会让历史会话目录失联。
  新增分量同理需要评审——分量数变化会让 `from_storage_id()` 的三段假设失效。
- 需要脱敏时复用 `contracts.errors.redact` / `scrub`，不要另写一套；
  新增敏感键名要同时补「必须保留」的反向用例，防止把用量统计一并打掉。
- `legacy/` 债务基线：352 个 Python 文件 / 133317 行
  （`scripts/legacy_debt_baseline.json`，只允许用 `--lower-baseline` 下调）。
- `runtime/legacy_entry.py` 是 `R6` 的唯一例外，白名单精确到这一个文件路径。
- 本机跑测试时系统临时目录可能因沙箱权限不可写，`pytest` 需显式指定 basetemp。
  **basetemp 必须落在仓库之外且父目录须已存在**（例如先建好 `D:/nm_pytest_tmp/`，
  再传 `--basetemp=D:/nm_pytest_tmp/run1`）：放在仓库内会让 `GitStore` 的嵌套仓库保护
  生效，凭空多出约 45 个 git 相关假失败；父目录不存在则 `tmp_path` 夹具直接报
  `FileNotFoundError`，架构守卫的反向用例会全部 error。
- 完整套件在本机的既有失败为 15–18 个，全部在 `legacy/`，与 `D00`–`D02` 无关：
  `test_exec_platform.py` 的 Windows PowerShell UTF-8 用例、
  `test_exec_session_tools.py` 的子进程时序用例、`test_web_fetch_security.py`、
  `test_mcp_probe.py`、`test_mcp_tool.py`、oauth-cli-kit 相关用例，
  以及 `channels/websocket` 的 `test_wrong_path_404`。数量在区间内浮动是因为其中几个
  依赖网络与子进程时序；基线里记录的是这些用例的真实结果，不是「全绿」假设。
  `D02` 完成时的实测为 15 failed / 6295 passed / 35 skipped。
- `basedpyright` 在 `legacy/skills/skill-creator/scripts/` 上有 4 个既有报错
  （`D00` 之前就存在），不是新层引入的。

当前进度：D00 ✅  D01 ✅  D02 ✅  D03– ⬜（尚未开始）

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
