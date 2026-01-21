# Runtime 架构详解

本文档详细说明 Runtime 模块各组件的实现细节。

## 1. Runtime 核心类 (`_runtime.py`)

### 1.1 ModelRegistry

模型注册表，支持属性和索引两种访问方式：

```python
class ModelRegistry:
    def __getattr__(self, name: str) -> ChatModelBase:
        """属性访问: runtime.models.main"""

    def __getitem__(self, name: str) -> ChatModelBase:
        """索引访问: runtime.models['main']"""

    def keys(self) -> list[str]:
        """返回所有模型槽位名"""

    def __contains__(self, name: str) -> bool:
        """检查槽位是否存在"""
```

**关键实现**：
- 使用 `_models: dict[str, ChatModelBase]` 存储
- `__getattr__` 需过滤私有属性（`_` 开头）

### 1.2 Runtime 单例

```python
class Runtime:
    models: ModelRegistry
    tools: Toolkit
    session: SessionBase

    async def initialize(self, config_path, project_path):
        """初始化顺序：
        1. 加载配置
        2. 创建模型实例
        3. 连接 MCP 客户端，注册到 Toolkit
        4. 初始化 Session
        5. 加载用户 App
        6. 调用 App.on_startup()
        """

    async def shutdown(self):
        """关闭顺序：
        1. 调用 App.on_shutdown()
        2. 关闭 MCP 客户端（LIFO 顺序）
        3. 重置状态
        """
```

### 1.3 模型创建 (`_create_model`)

根据 provider 创建对应的模型实例：

```python
provider_map = {
    "openai": OpenAIChatModel,
    "anthropic": AnthropicChatModel,
    "dashscope": DashScopeChatModel,
    "gemini": GeminiChatModel,
    "ollama": OllamaChatModel,
}
```

**注意事项**：
- `base_url` 参数名因 provider 而异
- OpenAI: `client_kwargs.base_url`
- Ollama: `host`

## 2. 配置解析 (`_config.py`)

### 2.1 配置数据类

```python
@dataclass
class ModelConfig:
    provider: Literal["openai", "anthropic", ...]
    model: str
    api_key: str | None = None
    base_url: str | None = None
    stream: bool = True
    generate_kwargs: dict = field(default_factory=dict)
    client_kwargs: dict = field(default_factory=dict)

@dataclass
class MCPServerConfig:
    url: str
    transport: Literal["sse", "streamable_http"]
    headers: dict = field(default_factory=dict)
    timeout: float = 30.0
    sse_read_timeout: float = 300.0
```

### 2.2 环境变量展开

`_expand_env_vars` 递归处理 `${VAR}` 语法：

```python
def _expand_env_vars(value: Any) -> Any:
    if isinstance(value, str):
        # 匹配 ${VAR} 并替换
        pattern = re.compile(r"\$\{([^}]+)\}")
        ...
    elif isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value
```

**重要**：未设置的环境变量会抛出 `ValueError`。

## 3. AgentApp 基类 (`_app_base.py`)

### 3.1 SessionContext

```python
class SessionContext:
    session_id: str
    metadata: dict[str, Any]  # 平台传递的额外信息
```

### 3.2 AgentApp 抽象类

```python
class AgentApp(ABC):
    @abstractmethod
    async def __call__(
        self,
        msg: Msg,
        ctx: SessionContext,
    ) -> AsyncIterator[Msg]:
        """处理请求，流式返回响应"""
        yield  # 占位，满足类型检查

    async def on_startup(self) -> None:
        """可选：App 启动钩子"""

    async def on_shutdown(self) -> None:
        """可选：App 关闭钩子"""
```

## 4. HTTP 服务 (`_server.py`)

### 4.1 FastAPI 应用构建

```python
def build_app(runtime, platform_client=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        # 启动：启动平台心跳
        if platform_client and platform_client.enabled:
            await platform_client.start()
        yield
        # 关闭：停止心跳，关闭 runtime
        ...
```

### 4.2 /invoke 端点

SSE 流式响应：

```python
@app.post("/invoke")
async def invoke(request: Request):
    async def event_iter():
        async for msg in runtime.app(msg, ctx):
            line = json.dumps(msg.to_dict())
            yield f"data: {line}\n\n".encode()
        # 结束信号
        yield 'data: {"metadata":{"done":true}}\n\n'.encode()

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
    )
```

## 5. 平台通信 (`_platform.py`)

### 5.1 心跳机制

```python
class PlatformClient:
    async def _heartbeat_loop(self):
        while True:
            await self._send_heartbeat()
            action = await self._check_config_update()
            if action == "restart":
                sys.exit(0)  # 触发容器重启
            await asyncio.sleep(self.config.heartbeat_interval)
```

### 5.2 指标收集

```python
def _get_metrics(self) -> dict:
    return {
        "active_sessions": len(self._active_sessions),
        "total_requests": self._request_count,
        "memory_usage_mb": ...,
    }
```

## 6. CLI 入口 (`_cli.py`)

```bash
agentscope run [project_path] [options]

# 选项
--port PORT           HTTP 端口（默认 8080）
--config FILE         配置文件（默认 agentapp.yaml）
--no-platform         禁用平台通信
--log-level LEVEL     日志级别
```

**执行流程**：
1. 解析参数
2. `runtime.initialize()`
3. 创建 `PlatformClient`（如启用）
4. `build_app()` 构建 FastAPI
5. `uvicorn.Server(config).serve()`
