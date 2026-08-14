# nucleamind-plugin-openai-api

NucleaMind 官方插件：把一个实例接到 **OpenAI 兼容的 HTTP 接口**上。

它取代了 `D31` 删除的 `legacy/api/server.py`，但不是移植——它是一条 `CHANNEL` 能力，
消息走与 CLI 完全相同的契约路径（`MSG-007`），没有任何私有通道。

## 安装

```bash
pip install "nucleamind-plugin-openai-api[server]"   # [server] 带上 aiohttp
```

## 启用

```jsonc
// ~/.nucleamind/<instance>/config.json
{
  "plugins": {
    "enabled": ["openai-api"],
    "openai-api": {
      "config": {
        "host": "127.0.0.1",
        "port": 8760,
        "model": "gpt-4o-mini"        // 只用于 /v1/models 与响应里的 model 字段
      },
      "secrets": {
        "api_key": "${NUCLEAMIND_API_KEY}"   // 可选；绑非回环地址时必填
      }
    }
  }
}
```

```bash
nm serve                       # 用配置里的 host/port
nm serve --port 9000           # 覆盖
```

## 端点

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/v1/chat/completions` | 支持 `stream=true`（SSE） |
| `GET` | `/v1/models` | 只有一个条目：本实例配的那个模型 |
| `GET` | `/health` | 存活探针 |

会话由 `X-NucleaMind-Conversation` 请求头决定，其次是请求体的 `user`，都没有时用
配置里的 `conversation`（默认 `"default"`）。**同一个会话标识 = 同一段历史**。

## 有意不支持

- **只提交最后一条 `user` 消息**。历史归实例的会话存储，不由请求携带。
- **`system` 消息被拒绝（400）**。系统指令归 `plugins.context-basic.config.instructions`，
  静默忽略它会让客户端相信自己设了一个没生效的东西。
- **客户端工具**（`tools` / `functions` / `tool_choice`）被拒绝：工具是实例的。
- **多模态内容部件**被拒绝（`content` 必须是字符串）。
- **采样参数**（`temperature` / `max_tokens` / `top_p` / `seed` …）接受但忽略——
  它们归模型配置与 `TurnLimits`。`n > 1` 被拒绝。
- 无 TLS、无限流、无 CORS：前面放反向代理。

## 已知边界

- **同一 Channel 的 turn 是串行的**：装配根的 Channel 泵要等上一条跑完才取下一条，
  因此两个并发客户端会排队，即使会话不同。这是相对旧实现的一处能力回退，
  修它要动 `runtime/instance.py` 并重新回答 `EDG-202` 的严格 FIFO 断言。
- **`usage` 是整条 turn 之和**（含工具往返），不是最后一次模型调用——与 OpenAI 的
  单次调用语义不同，但那才是用户真正付的数。拿不到用量时**省略该字段**而不是报零。
- **能连上这个端点的调用方能驱动实例的全部工具**，包括 `shell.exec`。默认只绑回环；
  绑非回环地址时没配 `api_key` 会直接以 `CONFIG_INVALID` 拒绝启动。
- 权限模型的五种权限里**没有「监听端口」**这一种（`net` 判的是出站），因此本插件
  除 `secret` 外声明不出与它实际行为对应的权限。这是当前的一个空档，如实记着。
