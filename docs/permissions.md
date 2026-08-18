# 插件权限

> 本文描述新 Kernel（`nm`）的权限模型，以及 `D52` 确定的开放式插件信任模型。

## 信任模型

**安装并启用一个插件，等同于信任它在 NucleaMind 进程中执行 Python 代码。** 插件可以
直接使用 `os`、`socket`、`httpx`、`subprocess`，不要求所有资源访问都经过 `ctx.fs` /
`ctx.net` / `ctx.shell`。这是开放式、可 DIY 的插件模型，不是一个待补齐的沙箱。

因此，manifest 的权限声明是插件作者提交的**能力意图**，不是 Kernel 观测到的完整行为清单。
`permissions.json` 与资源门面的目标是：

- 让插件主动声明常见资源需求，用户在安装和升级时可审计；
- 让声明变化可追踪，尤其是升级后的新增权限；
- 对自愿使用 `ctx.fs` / `ctx.net` / `ctx.shell` / `ctx.secret` 的插件提供应用级误用防护。

**应用级权限不是进程隔离，也不防御恶意插件。** 需要更严格控制时，应使用独立插件宿主、
容器、独立操作系统用户、网络命名空间或其他部署隔离；这些可以由安全插件或外部运行方案
提供，不进入极简 Kernel 的必备职责。

各个守卫还各自有说明不了的边界，都写在实现的 docstring 里：

- `ctx.fs` 的路径校验与随后的 `open()` 之间有 TOCTOU 窗口；
- `ctx.net` 挡不住 DNS 重绑定（校验时解析到的地址与真正连接时的可能不同）；
- `ctx.shell` 守住的是 cwd，不是命令能碰到的文件——`cat /etc/shadow` 用绝对路径。

## 五种权限

| 权限 | `target` 的含义 | 门面 |
| --- | --- | --- |
| `fs:read` | workspace 内的相对路径前缀，省略即整个 workspace | `ctx.fs.read_text` / `list_dir` |
| `fs:write` | 同上（与读**独立**收窄） | `ctx.fs.write_text` |
| `net` | 允许连的主机名，省略即「任意公网地址」 | `ctx.net.request` |
| `shell` | 暂未使用 | `ctx.shell.run` |
| `secret:<名字>` | 凭据名，**必填** | `ctx.secret("<名字>")` |

权限种类中刻意**没有** `listen` / `net.listen`。监听端口、连接聊天平台、直接启动子进程等
行为都可能绕过门面，继续扩枚举也无法把同进程 Python 的全部行为变成可强制的权限清单。
监听型插件是否运行，由 `plugins.enabled`、`plugins.disable` 与该插件自己的配置决定。

manifest 里这样声明（`reason` 必填，用户批准时读的就是这句）：

```python
PluginManifest(
    id="notes",
    permissions=(
        PermissionDecl(kind=PermissionKind.FS_READ, target="notes", reason="读取用户的笔记"),
        PermissionDecl(kind=PermissionKind.SECRET, target="api_key", reason="调用整理服务"),
    ),
    ...,
)
```

**声明是上限**：账本里批准过、manifest 没声明的权限不生效。

## 批准模型：首次记录 + 扩权需显式

1. **第一次见到一个插件**时，它声明的权限被整份授予，并记进
   `<实例目录>/permissions.json`（`source: "first_use"`）。开箱可用因此不受影响。
2. **此后声明集合变大**（插件升级、换了实现、内建新增一条权限），新增项默认**拒绝**
   并记为 `pending`；已有项继续生效。
3. **撤销**是显式操作，记为 `revoked`：此后即使 manifest 仍然声明也不授予。

第 1 条不是「用户点了头」，它是一条被记录下来的默认值——它让**扩权**可见，不让**初装**
可见。内建与外部插件走同一条判定，没有内建专用的特权路径。

## 命令

```bash
nm permissions list                     # 列出全部记录
nm permissions list --json              # 同上，JSON
nm permissions grant  notes shell 跑构建 # 批准一项（第三个参数起是理由，可省）
nm permissions revoke notes shell       # 撤销一项
nm permissions forget notes             # 删掉一个插件的全部记录，下次启动重新走首次授予
```

改动在**实例下次启动时**生效——账本在启动期读一次。

## 文件格式

`<实例目录>/permissions.json`：

```json
{
  "version": 1,
  "providers": {
    "notes": {
      "grants": [
        {
          "permission": "fs:read:notes",
          "decision": "granted",
          "reason": "读取用户的笔记",
          "decided_at": "2026-08-13T12:00:00+00:00",
          "source": "first_use"
        }
      ]
    }
  }
}
```

- `decision`：`granted` / `pending` / `revoked`。`pending` 是一个**已经生效的拒绝**，
  与「用户明确说不」（`revoked`）分开，因为两者的下一步动作不同。
- `source`：`first_use`（首次授予）/ `declared`（声明扩大后自动记的待批准）/
  `user`（`nm permissions` 或手工编辑）。
- 手写这份文件是支持的：`reason` 与 `decided_at` 可以省略，下次启动会从 manifest 补上
  `reason`，但**决定本身不动**。
- **读不懂就启动失败**（`CONFIG_INVALID`），不会静默当成空账本——那等于一次静默的全部
  重新授予。

**这里面没有凭据。** 记的是引用的名字（`secret:api_key`），凭据的值只以 `${VAR}` 形式
出现在 `config.json` 里，明文只在进程内经 `SecretStr` 传递。

## 被拒绝时会看到什么

未授予的资源访问器在**属性访问**时就抛 `PERMISSION_DENIED`，插件拿不到一个「看起来能用、
调用才失败」的对象：

```text
nm: 插件未被授予该权限。
  permission: shell
  plugin: notes
  suggestion: manifest 里声明它，并用 `nm permissions grant notes <权限>` 批准。
```

`ctx.secret()` 区分两种失败：未授权是 `PERMISSION_DENIED`（去改权限），
授权了但配置里没有该引用、或环境变量没导出是 `CONFIG_SECRET_MISSING`（去补配置）。
