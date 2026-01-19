# Runtime 模块设计 - 配置文件格式

## agentapp.yaml 完整格式

```yaml
# =============================================================================
# 模型配置
# =============================================================================
models:
  # 槽位名称，代码中通过 runtime.models.main 访问
  main:
    provider: openai                    # openai | anthropic | dashscope | gemini | ollama
    base_url: https://api.openai.com/v1 # API 端点
    model: gpt-4                        # 模型名称
    api_key: ${OPENAI_API_KEY}          # API 密钥，支持环境变量
    stream: true                        # 是否流式输出（默认 true）
    # 可选：生成参数
    generate_kwargs:
      temperature: 0.7
      max_tokens: 4096

  assistant:
    provider: anthropic
    base_url: https://api.anthropic.com
    model: claude-sonnet-4-20250514
    api_key: ${ANTHROPIC_API_KEY}

# =============================================================================
# MCP Server 配置
# =============================================================================
mcp_servers:
  # server 名称
  search:
    url: https://mcp.example.com/search/sse   # MCP Server URL
    transport: sse                             # sse | streamable_http
    # 可选：请求头
    headers:
      Authorization: Bearer ${MCP_TOKEN}

  database:
    url: https://mcp.example.com/db/mcp
    transport: streamable_http
    timeout: 60                                # 可选：超时时间（秒）

# =============================================================================
# Session 配置
# =============================================================================
session:
  backend: json                # 存储后端：json（本地文件）
  save_dir: ./sessions         # 本地存储目录

# =============================================================================
# 平台配置（本地开发时可不填）
# =============================================================================
platform:
  endpoint: https://platform.example.com/api  # 平台 API 端点
  instance_id: ${INSTANCE_ID}                 # 实例 ID
  heartbeat_interval: 30                      # 心跳间隔（秒）

# =============================================================================
# Tracing 配置（可选）
# =============================================================================
tracing:
  endpoint: http://localhost:4318/v1/traces   # OpenTelemetry 端点

# =============================================================================
# 服务配置
# =============================================================================
server:
  port: 8080                   # HTTP 服务端口
```

## 环境变量支持

配置文件中支持 `${VAR_NAME}` 语法引用环境变量：

```yaml
models:
  main:
    api_key: ${OPENAI_API_KEY}      # 从环境变量读取
    base_url: ${OPENAI_BASE_URL}    # 可选，有默认值时可不设置
```

解析规则：
- `${VAR}` - 必须存在，否则启动失败
- 不支持默认值语法（如 `${VAR:-default}`），保持简单

## 模型 Provider 配置说明

### OpenAI / Azure OpenAI

```yaml
models:
  gpt4:
    provider: openai
    base_url: https://api.openai.com/v1
    model: gpt-4
    api_key: ${OPENAI_API_KEY}
    # Azure 需要额外配置
    # client_kwargs:
    #   api_version: "2024-02-15-preview"
```

### Anthropic

```yaml
models:
  claude:
    provider: anthropic
    base_url: https://api.anthropic.com
    model: claude-sonnet-4-20250514
    api_key: ${ANTHROPIC_API_KEY}
```

### DashScope (阿里云)

```yaml
models:
  qwen:
    provider: dashscope
    model: qwen-max
    api_key: ${DASHSCOPE_API_KEY}
```

### Gemini

```yaml
models:
  gemini:
    provider: gemini
    model: gemini-pro
    api_key: ${GOOGLE_API_KEY}
```

### Ollama (本地)

```yaml
models:
  local:
    provider: ollama
    base_url: http://localhost:11434
    model: llama2
```

## MCP Transport 说明

### SSE (Server-Sent Events)

适用于需要保持长连接的场景：

```yaml
mcp_servers:
  realtime:
    url: https://mcp.example.com/sse
    transport: sse
    sse_read_timeout: 300    # SSE 读取超时（秒）
```

### Streamable HTTP

适用于无状态请求场景：

```yaml
mcp_servers:
  stateless:
    url: https://mcp.example.com/mcp
    transport: streamable_http
    timeout: 30
```

## 最小配置示例

本地开发最小配置：

```yaml
models:
  main:
    provider: openai
    base_url: https://api.openai.com/v1
    model: gpt-4
    api_key: ${OPENAI_API_KEY}
```

只需要一个模型即可启动，其他配置都有默认值。
