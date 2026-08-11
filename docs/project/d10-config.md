# D10 实例布局与配置加载（临时开发文档）

> 收口后删除。长期事实已写入 `README.md` 与 `technical-design.md`。

## 目标

补上 `D06`/`D08` 在 docstring 里欠给配置层的两件事，外加实例目录本身：

- `kernel/registry/resolution.py` 的 `resolve(disabled=...)` 需要一个「按提供方禁用」的输入。
- `kernel/turn/limits.py` 的 `TurnLimits` 六项需要配置来源。
- `D14` orchestrator 需要知道实例目录在哪。

## 交付

`src/nucleamind/kernel/config/` 共 8 个文件（`__init__` + 7 个模块），
`tests/kernel/test_layout.py`（27 例）+ `tests/kernel/test_config.py`（79 例）。

包内依赖是单向的：

```text
layout ─┐
process ─→ lock
merge ──→ schema ──→ sources ──→ loader
```

## 三个关键决定

### 1. schema 手写，不用 pydantic（与技术方案 §6.7 字面表述不同）

§6.7 写的是「内置默认值（代码中的 Pydantic default）」。取其意不取其形：
`extra="forbid"` 与 JSON Pointer 定位两条规范要求照做，实现方式另选。

**先按 pydantic 写了一版，实测后改掉。** 数据：

| | `import kernel.config` 耗时 | 进程内模块数 | pydantic 是否上路径 |
| --- | --- | --- | --- |
| pydantic 版 | 313 ms | 250 | 是 |
| 手写版 | 110 ms | 138 | 否 |

`NFR-405` 给**整个冷启动**的预算是 300 ms，而配置加载在启动第 2 步、永远在必经路径上
（`sdk/manifest.py` 用 pydantic 无妨——它只在真的要发现插件时才付这笔钱）。
另外两条理由与耗时无关：

- `CFG-005` 要求默认值层也带来源，这就要求默认值**物化成一份 dict**（`schema.defaults()`）。
  一旦如此，合并与来源追踪已经全在 `merge.py` 里自己写了，pydantic 只剩校验十几个字段。
- pydantic 的 `ValidationError.loc` 是元组，仍要自己转 RFC 6901；而
  `sdk/manifest.py::_format_location` 产出点分路径且 `R2` 禁止 import。

守卫：`test_loading_config_does_not_import_pydantic`（子进程查 `sys.modules`）。

### 2. 默认值是一层，不是「查不到来源」的兜底

`collect_layers()` 返回**四**层而不是三层：`default < config.json < env < cli`。
只有默认值也是一层，`CFG-005` 的「每个生效值可追溯来源」才对所有字段成立——否则
「这个值取自默认值」和「来源索引漏了这个字段」在数据上不可区分。
`test_every_known_field_has_an_origin` 遍历 `SECTION_SPECS` 断言这件事。

### 3. turn 引擎不得被拖上配置路径

`schema.py` 重写六个默认值字面量，`to_limits()` 用**函数内 import**。原因：
`import kernel.turn.limits` 会执行 `kernel/turn/__init__.py`，把 engine / scheduling /
folding 与 asyncio 一起拉进来，而 `nm config show` 只需要六个整数。

代价是两张默认值表，由 `test_turn_defaults_match_the_limits_module` +
`test_default_limits_round_trip_through_turn_limits` 两条测试钉住。
守卫：`test_loading_config_does_not_import_the_turn_engine`。

> 这条是**测试先发现、再改实现**的：最初 `schema.py` 直接 import 那些常量，
> 守卫测试立刻报 LEAKED。

## 跨平台：`os.kill(pid, 0)` 在 Windows 上会杀进程

CPython 在 Windows 上把非 CTRL 的信号映射到 `TerminateProcess`，所以那个 POSIX 惯用的
「探测」会**杀掉持锁进程**。`process.py` 因此分平台实现：

- Windows：`OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetExitCodeProcess`，
  `ctypes.WinDLL(..., use_last_error=True)`，**显式声明 `argtypes`/`restype`**
  （不声明会让 HANDLE 在 Win64 上被截成 32 位 → 句柄泄漏 + 对垃圾值 `CloseHandle`）。
- POSIX：`os.kill(pid, 0)`，`EPERM` 视为存活。
- `pid <= 0` 在任何 syscall **之前**拒绝：`os.kill(0, 0)` 打的是整个进程组。

`Liveness` 是**三态**（ALIVE / DEAD / UNKNOWN）。`UNKNOWN` 绝不授权回收锁——
塌成 bool 就是替调用方在「永久砖掉实例」和「两个进程同时写同一份会话」之间选一个。

回归测试：`test_probing_a_live_process_does_not_kill_it`（起子进程、探测、断言仍在跑）、
`test_non_positive_pids_never_reach_a_syscall`（monkeypatch `os.kill` 成记录器）。

## 锁的占用者分类表（`lock.py`）

| 占用者状态 | 结论 |
| --- | --- |
| 不可解析 / 无 pid / pid ≤ 0 | 陈旧，回收，`reason="unreadable"` |
| hostname 与本机不同 | 占用中（绝不探测另一台机器上的 PID） |
| pid == 本进程 | 占用中，用独立消息（这是重复获取的 bug，藏起来更糟） |
| 探测 = DEAD | 陈旧，回收，`reason="dead_pid"` |
| 探测 = ALIVE 且实测启动时间晚于锁的 `created_at` | 陈旧，回收，`reason="pid_reused"` |
| 探测 = ALIVE，时间取不到或一致 | 占用中 |
| 探测 = UNKNOWN | 占用中 |

把**不可解析**当陈旧是刻意的：它给不出 PID 也给不出恢复路径，一次「create 与 write
之间崩溃」就会永久砖掉实例；窗口只有微秒（create 后立即 fsync），且回收会被记录。

fd 保持打开到 `release()`：Windows 的 `_SH_DENYNO` 共享读写但**不共享删除**，
因此别的进程算错陈旧性也删不掉活锁，只会拿到 `PermissionError`——`_reclaim` 把它降级成
「持有者存活 → 拒绝」。同时第二个进程仍能**读**锁文件，`EDG-507` 才报得出 PID。

## 未讨完 / 交棒

- **`EDG-501` 的「把解析错误写到 `<instance_dir>/logs/`」不在 `D10`**：文件 sink 是 `D12` 的，
  事件总线还不存在，而一个在自己错误路径上做 IO 的 loader 是第二个故障面。
  `layout.config_error_log_path(day)` 已备好落点，`NucleaError.detail` 本身可 JSON 序列化。
  **交给 `D12` + `D23`。**
- **`EDG-108`（配置试图禁用 CLI 入口）超出 `D10` 能力范围**：提供方级禁用无法定位到单个
  能力 kind。**交给 `D23`/wiring。**
- `${VAR}` → `SecretStr` 是 `D11`；首次运行生成最小配置是 `D24`。loader 把 `${VAR}` 当普通
  字符串、`config.json` 缺失不算错误、且**从不写文件**，两者的缝都留好了。

## 验收实测

- `tests/architecture + contracts + sdk + kernel + baseline`：**928 passed**
  （`D09` 收口时 822，本次 +106）。
- `ruff check src/ tests/`：通过。
- `basedpyright`：新层 0 报错，legacy 仍是既有 4 个。
- `scripts/legacy_debt.py --check`：未变（352 文件 / 133317 行）。
- `scripts/check_startup_cost.py --check`：OK。
- `kernel/config/` 语句覆盖率 **88%**。未达 `registry/`、`turn/` 的 100%，缺口全部是
  平台分支与防御性 IO 异常路径：`process.py` 的 POSIX 分支在 Windows 上不可能执行
  （反之亦然，需要两条 CI 腿才能合并覆盖），以及 `lock.py` 里 `os.close` / `unlink`
  的 `except OSError` 兜底。**这是如实记录，不是「约等于 100%」。**
