# nucleamind-plugin-discord

NucleaMind 官方插件：**Discord Channel**。它把实例接到一个 Discord bot 上——收消息、跑
turn、流式地把回复编辑进同一条消息。

## 安装与启用

```bash
pip install 'nucleamind-plugin-discord[gateway]'   # gateway extra 带上 discord.py
nm plugins enable discord
nm serve
```

装上不等于启用（`plugins.enabled` 是唯一闸门），改完配置要重启实例。
`nm serve` 是通用无头模式，任何 `CHANNEL` 能力都用它。

## 最小配置

```jsonc
{
  "plugins": {
    "enabled": ["discord"],
    "discord": {
      "secrets": { "bot_token": "${DISCORD_BOT_TOKEN}" },
      "config": {
        "allow_from": ["123456789012345678"],
        "operators": ["123456789012345678"]
      }
    }
  }
}
```

凭据只能以 `${VAR}` 引用出现（`CFG-003`：明文不进配置文档）。

## 配置项

全部落在 `plugins.discord.config` 下。

| 键 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `channel_id` | string | `discord` | `SessionKey` 的第一分量与出站路由键。多 bot 部署时改它 |
| `allow_from` | string[] | `[]` | 发送者白名单。**空 = 允许所有**（与旧实现一致） |
| `allow_channels` | string[] | `[]` | 频道白名单，空 = 全部。**thread 命中它的父频道也算** |
| `operators` | string[] | `[]` | 谁是 operator。`/config` 这类 `operator_only` 命令只对名单里的人可用；**默认空 = 无人**，那是安全的一侧 |
| `group_policy` | `mention` \| `open` | `mention` | 群聊门控。`mention` 下四条命中路径：被 @、raw mention、正文里有 `<@id>`、**回复了 bot 自己的消息** |
| `intents` | integer | `37377` | Discord 的 intent 位掩码，原样转发 |
| `streaming` | bool | `true` | 关掉就只在终态发一条完整消息（`MSG-005` 的降级） |
| `stream_edit_interval_ms` | integer ≥100 | `800` | 两次编辑之间的最小间隔（旧实现的 `0.8s`） |
| `read_receipt_emoji` | string | `👀` | 收到消息立刻打的反应 |
| `working_emoji` | string | `🔧` | 延迟之后打的「工作中」反应 |
| `working_emoji_delay_ms` | integer ≥0 | `2000` | 旧实现的 `working_emoji_delay: 2.0` |
| `typing_interval_ms` | integer ≥1000 | `8000` | typing 指示器的续期间隔 |
| `max_attachment_bytes` | integer | `20971520` | 入站附件门限；超限的只留正文标记 |
| `proxy` / `proxy_username` | string | — | HTTP 代理。密码在 `secrets.proxy_password` |

Secret 两条：`bot_token`（必填，缺失即 `CONFIG_INVALID` 并指向那一个键）与
`proxy_password`（可选）。

## 行为

- **thread 是独立会话**：`conversation_id` 取频道 id，而 thread 有自己的 id，因此它天然
  拥有自己的历史。父频道进 `metadata.discord.parent_channel_id`。
- **入站附件不下载**：Discord CDN 的直链直接变成 `AttachmentRef(source=URL)`，因此本插件
  一条 `fs:*` 权限都不需要。超过 `max_attachment_bytes` 的只在正文留一条标记。
- **流式 edit-in-place**：第一片非空文本发一条消息，此后按节流编辑它；超过 2000 字符时
  收束成「编辑首块 + 补发其余」。
- **中断与失败有明确标记**（`EDG-304`）：正文尾部追加 `[已中断：以上是中断前已产生的内容]`
  或 `[本轮失败]`，与终端里看到的**逐字相同**。标记与半截答案在同一条消息里，不另发。
- **只忽略 bot 自己的消息，不忽略其它 bot 的**：多 bot 编排（一个 bot @ 另一个求助）
  因此可用；bot 之间的循环仍被「每个 bot 都忽略自己」挡住。

## 已知边界

- **陌生人的 DM 被静默忽略**，不再像旧实现那样回一个配对码——配对流程依赖的审批界面在
  `D31` 已随 WebUI 后端删除。要让人能用，把他的 id 写进 `allow_from`。
- **没有 Discord 原生 slash command**。命令只有一个来源（`routing.command_prefix`），
  在 Discord 里打 `/help` 就是一条普通消息，由内建 `commands-core` 处理。
- **出站 workspace 附件传不出去**：`FileAccess` 没有 `read_bytes`，本插件发一条
  `[附件：…（本轮无法上传）]` 标记而不是假装发过。今天新层也没有任何地方产出带附件的
  出站消息。
- **五种权限里没有「连接一个聊天平台」这一种**：`net` 判的是经 `ctx.net` 门面的出站请求，
  而 `discord.py` 自己开连接。因此本插件除两条 `secret` 外声明不出任何权限，而它确实会
  连出去。这是权限模型当前的一个空档，与 `openai-api` 那条「没有『监听端口』」并列。
- **应用级权限不是进程隔离**：能在允许的频道里说话的人就能驱动实例上的全部工具，
  包括 `shell.exec`。`allow_from` 与 `allow_channels` 是唯一的闸门。
- **没有发送重试与限流退避**：失败即记日志。旧实现也没有，本轮不发明一套。

## 并发

同一 conversation 的 turn 严格按到达顺序串行（`EDG-202`），**不同 conversation 并发**
（`D33` 的泵扇出）。上界由 `routing.channel_concurrency`（默认 64）与
`routing.channel_queue_max_size`（默认 32）控制，撞上时用户会收到一条明确的忙碌回音。

## 开发

```bash
pip install --no-deps -e plugins/nucleamind-plugin-discord
python -m pytest plugins/nucleamind-plugin-discord -q
```

**绝大多数用例不需要装 `discord.py`**：`gateway.py` 是唯一接触它的模块，其余全是纯函数或
对 `Platform` / `Reactions` 两个 Protocol 编程。`tests/conftest.py` 有一条 autouse 的网络
闸门盯着「一个 socket 都不开」。
