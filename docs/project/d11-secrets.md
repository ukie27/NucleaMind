# D11 Secret 与凭据（临时开发文档）

**依赖**：`D10`（`kernel/config/`）。**交付**：`kernel/config/secrets.py`、
`tests/kernel/test_secrets.py`，外加一次跨层调整（`SecretStr` 下沉到 `contracts/`）。

需求出处：技术方案 §6.7、`CFG-003`、`EDG-502`；开发方案 `D11`。

## 1. 目标

- `${VAR}` 引用解析为 `SecretStr`，`__str__` / `__repr__` / 格式化 / 序列化恒为 `***`。
- 配置写回时保留原始 `${VAR}` 字面量，绝不回写明文（`CFG-003`）。
- 缺失变量只报变量名，不报值（`EDG-502`），错误码 `CONFIG_SECRET_MISSING`。

## 2. 两个决策

### 2.1 `SecretStr` 从 `sdk/api.py` 下沉到 `contracts/errors.py`

技术方案 §7.5 把 `SecretStr` 放在 `sdk/api.py`，理由是「它只出现在
`PluginContext.secret()` 的返回位置」。`D11` 让这个前提失效：`${VAR}` 的解析结果在
`kernel/config/` 里产生，而 `R2` 禁止 `kernel/` import `sdk/`。

采用与 `D05` 处理 `CliEntry` 完全相同的解法——**谁都要用的类型下沉到 `contracts/`**。
落点选 `errors.py` 而不是新开模块：掩码常量 `MASK`、`redact()` 与 `SecretStr` 是同一件
事的三个面，`redact()` 现在能直接把 `SecretStr` 认成 `MASK` 并把明文交给 `scrub()`
从自由文本里一并擦掉——分模块就要么成环、要么留一处认不出 `SecretStr` 的脱敏。

连带修改：`sdk/api.py` 改为从 `contracts` 导入，`SecretStr` 移出 `sdk.__all__`
（契约类型不从 `sdk` 转发，插件按 `R4` 直接 import `contracts`），`tests/sdk` 的规范性
快照同步更新。这是本模块唯一一处动已冻结表面的改动，已单独评审。

顺带修掉一个真实泄漏面：原实现是 `@dataclass(frozen=True, slots=True)`，
`dataclasses.asdict()` 会把 `_value` 明文抖出来，任何**包含**它的 dataclass 被
`asdict()` 时同样中招。下沉后改为普通不可变类（`__slots__` + 拒绝 `__setattr__`），
`asdict()` 对它不再递归；并补 `__format__`，让 `f"{secret:>20}"` 也只能得到掩码。

### 2.2 `${VAR}` 的语义：任何位置的引用都算密钥

一种机制一种含义：字符串里**只要出现** `${VAR}`（整串或内嵌 `Bearer ${TOKEN}`），
整个值解析后就是 `SecretStr`。不提供「插值但不是密钥」的第二种语义，也不提供 `${VAR:-默认值}`
这类 shell 风格回退（与 `legacy` 一致：缺变量是硬错误，不是静默降级）。

副作用是 `"https://${HOST}/v1"` 这类值在诊断里也显示为 `***`。可以接受：诊断视图展示的是
**原始字面量** `${HOST}`（见 §3.3），用户看到的仍然是「这里引用了 HOST」这一有用信息。

不支持转义（`$${VAR}`）：半个机制不如没有，需要时另开一次评审。

## 3. 设计

### 3.1 明文不进文档（`CFG-003` 的结构性保证）

`resolve_secrets()` **不返回一份替换过的配置文档**，而是返回一个按 JSON Pointer 索引的
`SecretMap`：

```text
SecretRef(pointer, literal, names)     一处引用：位置 + 原始字面量 + 引用到的变量名
SecretMap.refs      pointer -> SecretRef
SecretMap.values    pointer -> SecretStr（明文只在这里，且只能经 reveal() 取出）
```

配置树本身自始至终持有 `${VAR}` 字面量。因此「写回保留字面量」不是一条要人记得遵守的
流程，而是**没有别的东西可写**——加载路径不产生含明文的文档，也就毁不掉用户的文件。

### 3.2 写回仍有一道闸

结构性保证挡不住「有人 `reveal()` 之后把明文塞回文档再写盘」。`prepare_for_write()`
是写盘前的最后一道闸：遍历待写文档，把 `SecretStr` 与**等于已知明文**的裸字符串换回原始
`${VAR}` 字面量；换不回去（没有对应引用）时抛错而不是写明文。`D24` 生成 `config.json`
必须过这道闸。

`kernel/config/` 依旧**一个字节都不写**（`EDG-501`）：`prepare_for_write()` 是纯函数，
返回可写文档，真正的写盘在 `D24`。

### 3.3 诊断视图不需要新函数

原始文档本身就是安全视图（值是 `${VAR}` 字面量）。`nm config show` 直接打印它即可，
不必再造一个 masked 视图——多一个视图就多一条要被哨兵测试覆盖的输出路径。

### 3.4 缺失变量

一次报全部缺失（与 `validate_config()` 的「一次报全」同构），`detail` 里只有变量名、
JSON Pointer 与缺失原因（`unset` / `empty`），**没有任何值**。定义为空字符串按缺失处理：
`OPENAI_API_KEY=` 几乎总是配错，静默接受一个空密钥只会把错误推到第一次模型调用。

### 3.5 不接进 `load_config()`

`SECTION_SPECS` 目前没有任何 secret 字段（provider 凭据按 §6.7 不进配置文件），而
`SecretStr` 不是 `JsonValue`，塞进合并后的文档会让 `validate_config()` 无从校验。
`D11` 只给机制，接线在 `D19`（provider 凭据）与 `D26`（`ctx.secret()`）。

## 4. 验收（实测）

- **哨兵测试覆盖全部输出路径**：`str` / `repr` / f-string / `%` 格式化 / `format()` /
  `json.dumps`（抛 `TypeError` 而不是写出明文）/ `logging` / `dataclasses.asdict` /
  `NucleaError` 的 `user_message` 与 `detail` / `SecretMap` 自身的 `repr`。
- **写回往返**：读取 → 改别的字段 → `prepare_for_write()` → `${VAR}` 字面量原样保留。
- **缺失变量**：消息与 `detail` 含变量名，不含任何值；多处缺失一次报全。
- JSON Pointer 转义（`~` / `/`）与列表下标位置正确。

实测：`tests/kernel/test_secrets.py` 42 个用例 + `tests/contracts/test_errors.py` 新增
4 个；`tests/architecture + contracts + sdk + kernel + baseline` 共 990 passed；
完整套件 14 failed / 5798 passed / 30 skipped（失败全在 `legacy/` 的既有那批）；
`ruff check`、`basedpyright`（新层 0 报错）、`legacy_debt --check`、
`check_startup_cost --check` 均通过；`secrets.py` 语句覆盖率 100%。

两处实现期才发现的问题，已修并各有回归测试：

- 原 `SecretStr`（dataclass）被 `dataclasses.asdict()` 递归时会抖出明文；改成普通不可变
  类后 `asdict()` 对它不透明。副作用是 `copy.deepcopy` 会撞上 `__setattr__`，补
  `__deepcopy__` 返回自身（不可变对象复制即自身）。
- 按明文反查换回字面量必须有长度阈值（复用 `MIN_SCRUB_LENGTH`），否则一个 4 字符的密钥
  会让用户配置里任何等于它的普通值（`"1234"`）被悄悄改写成 `${VAR}`。按**位置**恢复
  不受此限。

## 5. 交棒

- `D19`：provider 凭据用 `resolve_value()` 解一个字段，缺失时 `CONFIG_SECRET_MISSING`
  要能和 `PERMISSION_DENIED` 区分（`sdk/api.py::secret` 的 docstring 已经写死这条）。
- `D24`：生成 `config.json` 前必须过 `prepare_for_write()`。
- `D26`：`ctx.secret(name)` 返回的就是 `contracts.SecretStr`，不再需要跨层转换。
