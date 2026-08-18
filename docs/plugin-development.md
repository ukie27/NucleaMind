# 插件开发入门

本文写给要为 NucleaMind 写插件的人。读完你会知道一个插件由哪几样东西组成、它能做什么、
不能做什么，以及出错时去哪里看。

仓库里有两个可以直接对照的最小示例：

| 示例 | 演示 |
| --- | --- |
| [`examples/plugins/nucleamind-plugin-echo-tool`](../examples/plugins/nucleamind-plugin-echo-tool) | 新增一项能力（工具） |
| [`examples/plugins/nucleamind-plugin-session-memory`](../examples/plugins/nucleamind-plugin-session-memory) | 覆盖一项内建能力（会话存储） |

本文里的代码块由 `tests/e2e/test_plugin_docs.py` 直接执行，因此它们不会与实现脱节。

## 1. 一个插件由四样东西组成

```text
nucleamind-plugin-<id>/
├── pyproject.toml                      # entry point：让宿主发现得到它
├── src/nucleamind_plugin_<id>/
│   └── __init__.py                     # MANIFEST（声明） + setup（注册）
└── tests/                              # 继承 sdk.testing 的契约测试基类
```

插件是**独立发行包**，不放在宿主包里面。这条边界由打包机制强制：包内的「插件」可以随手
import 兄弟模块，依赖规则就成了空话。

## 2. Manifest：声明你要做什么

`MANIFEST` 是一个模块顶层的常量。**导入这个模块必须无副作用且廉价**——宿主在发现阶段只
import 它取这一个对象，此时不该发生任何 IO。

```python
from nucleamind.contracts import CapabilityKind, PermissionKind
from nucleamind.sdk import CapabilityDecl, PermissionDecl, PluginManifest

MANIFEST = PluginManifest(
    # 小写字母、数字与中划线。它同时是包名 nucleamind-plugin-<id> 的后半段、
    # 状态目录名，以及别人覆盖你时写的 "plugin:<id>:<name>"。
    id="my-plugin",
    version="0.1.0",
    # 你支持的 SDK 区间。宿主落在区间外时拒绝加载并报 PLUGIN_SDK_INCOMPATIBLE，
    # 不带病运行。
    sdk_range=">=1.0.0,<2.0.0",
    setup="nucleamind_plugin_my_plugin:setup",
    # 有约束力的全集：setup 里注册的每一项都必须在这里声明，反之亦然。
    capabilities=(CapabilityDecl(kind=CapabilityKind.TOOL, name="my.tool"),),
    # reason 必填——它会展示给批准权限的用户，"因为需要" 在评审阶段就该被打回。
    permissions=(
        PermissionDecl(kind=PermissionKind.NET, reason="调用 example.com 的公开接口。"),
    ),
    # 用户能在 plugins.my-plugin.config 里写什么。宿主在加载前按它校验。
    config_schema={
        "type": "object",
        "properties": {"endpoint": {"type": "string"}},
        "additionalProperties": False,
    },
)
```

几条容易踩的：

- **不要写 `priority`**。它的默认值是 100，而内建的基准是 0；写了就会被原样采纳，
  「内建排在插件前」会静默失效。
- **`capabilities` 是有约束力的**。声明了却没注册、注册了却没声明，都是
  `PLUGIN_LOAD_FAILED`。这不是形式主义——`overrides` 只能从声明来，`nm capabilities`
  与权限校验都建立在「声明即全集」上。
- **`critical=True` 意味着你坏了实例就起不来**。只有「没有它就没有 Agent」的能力才配得上
  它，第三方插件一般不该写。

## 3. setup：注册

```python
from nucleamind.contracts import RiskLevel, ToolSpec
from nucleamind.sdk import NucleaAPI


def setup(api: NucleaAPI) -> None:
    """在同步返回前完成全部注册。"""
    api.register_tool(
        ToolSpec(
            name="my.tool",
            description="模型只能靠这句话决定要不要调用它。",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            read_only=True,
            risk=RiskLevel.SAFE,
        ),
        MyTool(api.ctx.config.get("endpoint")),
    )
```

`NucleaAPI` 恰好有 10 个注册方法，与 10 类能力一一对应：`register_tool` /
`register_command` / `register_context_provider` / `register_model_provider` /
`register_channel` / `register_memory_provider` / `register_session_store` /
`register_context_compactor` / `register_cli_entry` / `on`（Hook）。

`register_context_compactor(name, compactor)` 注册的是持久化上下文压缩策略。安装或注册不会
自动生效，用户还必须在 `context.compactor` 显式选择同名能力。`ContextCompactor.compact()`
只返回摘要正文与 `through` 水位；何时触发、结果校验、Session 写入、重载和故障回退都由
Kernel 负责。

**注册是事务性的**：先进暂存批次，`setup` 正常返回才一次性并入能力表；中途抛异常则整批
丢弃，不会留下半注册状态。因此不要在 `setup` 里派生一个后台任务去「稍后注册」。

## 4. entry point：让宿主发现得到

```toml
[project.entry-points."nucleamind.plugins"]
my-plugin = "nucleamind_plugin_my_plugin:MANIFEST"
```

**name 必须等于 manifest 的 `id`**，对不上即失败。理由是「发现与启用分离」：宿主要在
**读 manifest 之前**就知道候选叫什么，才能把没启用的候选直接筛掉——那是「未启用的插件
不产生任何导入开销」的实现方式，不是一条要人遵守的纪律。

除 entry point 外还有两条来源，都需要用户在 `plugins.search_paths` 里显式指出目录：
目录形态（目录里放 `plugin.toml`）与单文件形态（一个 `.py`，里面有 `MANIFEST`）。
**没有 site-packages 全量扫描，也没有目录自动加载。**

## 5. 安装 ≠ 启用

```bash
pip install nucleamind-plugin-my-plugin      # 装上，不生效
nm plugins enable my-plugin                  # 写进 plugins.enabled
nm run                                       # 下次启动生效（首版不热更新）
```

配置里长这样：

```json
{
  "plugins": {
    "enabled": ["my-plugin"],
    "my-plugin": {
      "config": { "endpoint": "https://example.com" },
      "secrets": { "api_key": "${MY_PLUGIN_TOKEN}" }
    }
  }
}
```

- `config` 原样交给 `ctx.config`。**你只看得见自己那一块**，没有读别人配置的 API。
- `secrets` 的值只能是 `${VAR}` 引用，明文由 `ctx.secret("api_key")` 在调用时从环境变量
  取。配置树里自始至终只有那个字面量，因此 `/config` 的脱敏是结构性成立的。

## 6. 权限：声明式 + 应用级强制

`ctx` 上的四个资源访问器需要 manifest 里声明过、且用户批准过，否则**属性访问**就抛
`PERMISSION_DENIED`——你拿不到一个「看起来能用、调用才失败」的对象。

| 访问器 | 权限 | 说明 |
| --- | --- | --- |
| `ctx.fs` | `fs:read` / `fs:write` | 路径相对授予的根，`realpath` 之后重新校验 |
| `ctx.net` | `net` | 走 SSRF 守卫，私有网段与云元数据地址一律拒绝，手动跟随重定向 |
| `ctx.shell` | `shell` | 参数是列表不是命令行，因此没有注入面；非零退出码不是异常 |
| `ctx.secret(name)` | `secret:<name>` | `secret` 必须带 target——不带等于申请全部凭据 |

`ctx.events`（事件订阅）、`ctx.instance`（只读诊断视图）与 `ctx.turns`（取消在跑的 turn）
**不需要权限声明**：只读可观测性不是资源访问。

批准模型是 TOFU + 扩权需显式：首次见到时按声明整份授予并记进 `permissions.json`；此后
声明**扩大**时，新增的那几项默认落 `pending`（即拒绝），要用户显式批准。

> **应用级权限不是进程隔离。** 同进程的 Python 插件可以绕过全部门面直接 `import os`。
> 这些门面的价值是让越界意图**可审计**、在评审与测试中可见，真正的隔离要等子进程插件宿主。
> 这句话写在 `sdk/api.py` 与 `docs/permissions.md` 里，是一条必须保留的诚实声明。

## 7. 覆盖一项已有能力

想替换内建实现（或另一个插件的实现）时，在声明里写 `overrides`：

```python
from nucleamind.contracts import CapabilityKind
from nucleamind.sdk import CapabilityDecl

DECL = CapabilityDecl(
    kind=CapabilityKind.SESSION_STORE,
    name="memory",
    # 覆盖内建写 "builtin:<name>"，覆盖插件写 "plugin:<id>:<name>"。
    # 串里不带 kind——kind 取自声明覆盖的这一方。
    overrides="builtin:jsonl",
)
```

三条规矩：

1. **覆盖永不由加载顺序决定**。没声明 `overrides` 而撞了名字，是
   `PLUGIN_REGISTRATION_CONFLICT`，且**冲突各方都不生效**——选任何一边都是替用户做决定。
2. **覆盖不静默**。`nm capabilities` 的「被覆盖」段会印出被顶掉的那一项与顶掉它的那一项，
   两边都带提供方标识。
3. **覆盖目标不存在不会降级成新增注册**，而是 `CAPABILITY_OVERRIDE_TARGET_MISSING`。

### 被禁用之后：`on_disable`

覆盖了别人的插件被写进 `plugins.disable` 时，用户**必须**说清被顶掉的那一项怎么办：

```json
{
  "plugins": {
    "disable": ["my-plugin"],
    "my-plugin": { "on_disable": "restore_builtin" }
  }
}
```

| 取值 | 结果 |
| --- | --- |
| `restore_builtin` | 被顶掉的实现重新生效 |
| `leave_missing` | 那项能力保持缺失；是必需能力时实例以 `CAPABILITY_MISSING` 拒绝启动 |
| 不写 | 配置错误，指向 `/plugins/<id>/on_disable` |

不写就报错看起来严格，但它兑现的是「内建默认能力被禁用或覆盖后，Kernel 不得隐式恢复」。
用户可能正是因为不想要那份内建实现才装的你的插件。

## 7.5 能力名要连上外部服务才知道：命名空间声明

manifest 是**静态**的，而 `CapabilityHost.finish()` 要求声明的 `(kind, name)` 与实际注册的
**逐条相等**。桥接类插件（MCP、远端工具网关）撞得上这条：远端工具名要连上 server、
`list_tools` 之后才可知。

对这种情况声明一个**命名空间**：

```python
from nucleamind.contracts import CapabilityKind
from nucleamind.sdk import CapabilityDecl

DECL = CapabilityDecl(
    kind=CapabilityKind.TOOL,
    # `namespace=True` 时 name 是**前缀**：本条声明放行注册任意多条 `mcp.<后缀>`。
    name="mcp",
    namespace=True,
)
```

`setup(api)` 里就可以注册任意多条 `mcp.` 开头的工具，名字不必事先写进 manifest。
**`setup` 可以是 `async` 的**，因此「连上去、拿到工具表、逐条注册」全在它里面完成——
registry 在解析之后只读，没有第二个注册时机。

五条规矩：

1. **只放行 `<前缀>.<后缀>`**。前缀本身（`mcp`）不在内，`mcpx.read` 也不在内——
   前缀比较落在分隔符边界上。要注册前缀本身就再写一条普通声明。
2. **精确声明优先**。同时匹配时用精确的那条；两条命名空间同时匹配则是
   `PLUGIN_LOAD_FAILED`——静默挑一个等于让加载顺序说了算。
3. **零注册是合法的**。远端服务连不上时你注册零条工具，那是如实反映外部状态，
   不算「声明了却没注册」。
4. **不能与 `overrides` 并存**。一条声明能注册出任意多个名字，哪一个是覆盖者无从判定。
5. **只有可并存且按名字唯一的能力**（`tool` / `command` / `model` / `channel` / `memory`）
   能声明命名空间。SINGLETON 的槽位只有一个，给它开前缀等于让「唯一」失去判定对象。

冲突语义一个字没变：registry 仍按精确 `(kind, name)` 判，`nm capabilities` 印的是**实际
注册的**名字。权限也一样——命名空间不放宽任何权限，manifest 的 `permissions` 照常是全集。

## 8. 测试：继承契约测试基类

`nucleamind.sdk.testing` 发布了 7 个契约测试基类与一批 Fake。内建实现与你的插件**继承
同一个基类**——这就是「可替换」的可执行形态。

```python
from nucleamind.contracts import SessionStore
from nucleamind.sdk.testing import InMemorySessionStore, SessionStoreContract


class TestMyStore(SessionStoreContract):
    def make_store(self) -> SessionStore:
        return InMemorySessionStore()
```

基类是 `ModelProviderContract` / `SessionStoreContract` / `ToolContract` /
`ContextProviderContract` / `ContextCompactorContract` / `MemoryProviderContract` /
`ChannelContract`。它们**不 import pytest**，所以你用什么 runner 都行；子类名必须以
`Test` 开头，否则 pytest 不收集。

## 9. 出错时看哪里

| 现象 | 命令 | 说明 |
| --- | --- | --- |
| 插件没被加载 | `nm plugins list` | 列出候选、跳过原因与两个阶段的失败 |
| 不知道谁提供了某项能力 | `nm capabilities` | 生效 / 被覆盖 / 已禁用 / 冲突四段，各带提供方 |
| 权限被拒 | `nm permissions` | 已授予、待批准与已撤销的记录 |

三类失败有各自稳定的错误码，别混着读：

| 错误码 | 含义 | 去改哪里 |
| --- | --- | --- |
| `CONFIG_INVALID` | 用户写的配置不符合你的 `config_schema` | `config.json` |
| `PLUGIN_SDK_INCOMPATIBLE` | 你声明的 `sdk_range` 与宿主不兼容 | 插件的 manifest |
| `PLUGIN_LOAD_FAILED` | `setup` 导不进 / 跑出异常 / 声明与注册对不上 | 插件的实现 |

## 10. 依赖规则

插件**只能** import `nucleamind.contracts` 与 `nucleamind.sdk`。够到 `nucleamind.kernel.*`
的插件在本仓库会被架构守卫拦下；在你自己的仓库里没人拦，但那些是私有模块，不承诺任何
兼容性，随时会变。

契约类型直接从 `nucleamind.contracts` 导入，不从 `nucleamind.sdk` 转发——`SecretStr`、
`SessionKey`、`ToolSpec` 这些都在前者。
