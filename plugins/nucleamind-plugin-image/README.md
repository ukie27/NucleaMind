# nucleamind-plugin-image

NucleaMind 官方插件：一条 **`image.generate`** 工具能力——按文字描述生成图像并保存到本地。

```bash
pip install -e plugins/nucleamind-plugin-image
nm plugins enable image
```

## 配置

```jsonc
{
  "plugins": {
    "enabled": ["image"],
    "image": {
      "config": {
        "provider": "openai",
        "model": "gpt-image-1",
        "size": "1024x1024",
        "max_count": 4
      },
      "secrets": { "api_key": "${OPENAI_API_KEY}" }
    }
  }
}
```

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `provider` | `openai` | `openai`（`/v1/images/generations`）或 `openrouter`（chat 里回图） |
| `base_url` | 后端官方地址 | 自建网关、代理或本地 ollama |
| `model` | `gpt-image-1` | |
| `size` | 空 | **留空即不发这个字段** |
| `response_format` | 空 | `b64_json` / `url`。留空即不发 |
| `max_count` | `4` | 单次调用的张数上限 |
| `dir` | `<state_dir>/images` | 相对路径按插件状态目录解析 |
| `extra_body` | `{}` | 透传给后端的额外字段（标量或数组） |

**没有按模型名分支的表。** 参考实现按模型 slug 换算尺寸、按模型名判断支不支持
`response_format`；这里的对应物是 `size` / `response_format` / `extra_body` 三个显式配置项，
留空即不发。理由与项目此前拒掉 `max_tokens_field` slug 表（`D19`）、四张版本 gating 表
（`D32`）完全相同：**表只会越滚越大，而用户换一个新模型要等我们发版**。

实践上：`gpt-image-1` 恒回 base64 且会**拒绝** `response_format`，所以留空；
`dall-e-3` 要写 `"response_format": "b64_json"`，否则回一个有期限的 URL（插件会去取，
多一次往返）。

## 产物

文件名是**内容寻址**的：`image-<sha256 前 16 位>.<ext>`。同样的字节永远落在同一个文件上，
而文件名里不含 prompt——prompt 可能很长、可能带路径分隔符，也可能包含用户不想留在文件系统
上的内容。写走「同目录临时文件 → `fsync` → `os.replace`」。

工具返回值里既有给模型看的路径列表，也有 `ToolResult.artifacts` 的 `ArtifactRef`。

## 三条如实记着的边界

### 1. `artifacts` 今天没有消费者，图发不到聊天平台

本插件是全项目 `ToolResult.artifacts` 的**第一个生产者**。生成的图只能由用户到目录里去看：

- `OutboundMessage` 的附件路径今天没有任何生产者；
- `sdk.api.FileAccess` 没有 `read_bytes`，Channel 插件读不到这些字节
  （`D33` 已把 `read_bytes` 记为契约变更候选）。

### 2. 不用 `ctx.fs`，如实声明 `fs:write`

`FileAccess` 只有 `read_text` / `write_text` / `list_dir`，表达不了二进制写入。
与 `builtins/session_jsonl/` 同一条先例：门面能力不足时，**诚实声明比绕道更符合
「应用级权限的价值是让越界意图可审计」**。

### 3. 不用 `ctx.net`，如实声明 `net`

图像端点由**运维配置**（要能指到本地 ollama 与自建网关），而 `ctx.net` 的 SSRF 守卫按设计
拒绝私有地址与回环。**模型在这里决定不了任何地址**，它只给 prompt——这与同批交付的
`web.fetch` 恰好相反，那一条抓的是模型给的 URL，因此必须走守卫。

## 副作用语义

三档判定只在 `tool.py::execute` 一处（`builtins/tools_shell/executor.py::_fold` 的同一条判据）：

| 情况 | `side_effect` |
| --- | --- |
| 参数非法 / 凭据缺失 / 请求失败 / 响应读不懂 | `NONE`（一个字节都没落盘） |
| 至少写成功一张 | `OCCURRED` |

**本工具不产出 `UNKNOWN`**：`os.replace` 成功之后没有可失败的步骤，替换之前一个字节都没到
目标路径上。取消同理——**已经落盘的图不会被删掉**，取消不是回滚，而那些字节是用户已经付过
钱的。

## 不做的事

- **语音转写**（参考实现的 `providers/transcription.py`）：那是另一类能力（音频输入），
  而契约层今天没有多模态输入位置。
- **参考图 / 图生图**：`ToolSpec.parameters` 收得下一个路径列表，但读那些文件需要
  `FileAccess.read_bytes`，同上。

## 测试

```bash
python -m pytest plugins/nucleamind-plugin-image -q
```

一个 socket 都不开：全部用例走 `httpx.MockTransport`，`tests/conftest.py` 的 autouse
夹具是那句话的可执行断言。
