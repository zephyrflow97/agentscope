# Runtime 扩展指南

本文档说明如何扩展 Runtime 模块的功能。

## 1. 添加新的模型 Provider

### 1.1 修改 `_config.py`

在 `ModelConfig.provider` 类型中添加新的 provider：

```python
@dataclass
class ModelConfig:
    provider: Literal[
        "openai",
        "anthropic",
        "dashscope",
        "gemini",
        "ollama",
        "your_provider",  # 新增
    ]
```

### 1.2 修改 `_runtime.py`

在 `_create_model` 函数中添加映射：

```python
def _create_model(name: str, config: ModelConfig) -> ChatModelBase:
    from ..model import (
        ...,
        YourProviderChatModel,  # 新增导入
    )

    provider_map = {
        ...,
        "your_provider": YourProviderChatModel,
    }

    # 处理 base_url 等特殊参数
    if config.base_url is not None:
        if config.provider == "your_provider":
            kwargs["endpoint"] = config.base_url  # 根据实际参数名调整
```

### 1.3 前置条件

确保在 `agentscope.model` 中已实现对应的 `ChatModelBase` 子类。参考 [CONTRIBUTING.md](../../CONTRIBUTING.md) 的模型贡献指南。

## 2. 添加新的 Session 后端

### 2.1 修改 `_config.py`

```python
@dataclass
class SessionConfig:
    backend: Literal["json", "redis", "your_backend"] = "json"
    save_dir: str = "./sessions"
    # 新增后端特有配置
    redis_url: str | None = None
```

### 2.2 修改 `_runtime.py`

在 `initialize` 方法中添加分支：

```python
async def initialize(self, ...):
    # 4. Initialize Session
    if self._config.session.backend == "json":
        from ..session import JSONSession
        self.session = JSONSession(
            save_dir=self._config.session.save_dir,
        )
    elif self._config.session.backend == "redis":
        from ..session import RedisSession
        self.session = RedisSession(
            url=self._config.session.redis_url,
        )
    # 新增后端
    elif self._config.session.backend == "your_backend":
        from ..session import YourSession
        self.session = YourSession(...)
```

## 3. 添加新的 MCP Transport

### 3.1 修改 `_config.py`

```python
@dataclass
class MCPServerConfig:
    transport: Literal["sse", "streamable_http", "stdio"]  # 新增 stdio
    # stdio 特有配置
    command: str | None = None
    args: list[str] = field(default_factory=list)
```

### 3.2 修改 `_runtime.py`

修改 `_create_mcp_client` 函数：

```python
async def _create_mcp_client(
    name: str,
    config: MCPServerConfig,
) -> StatefulClientBase:
    if config.transport in ("sse", "streamable_http"):
        from ..mcp import HttpStatefulClient
        client = HttpStatefulClient(...)
    elif config.transport == "stdio":
        from ..mcp import StdioStatefulClient
        client = StdioStatefulClient(
            name=name,
            command=config.command,
            args=config.args,
        )

    await client.connect()
    return client
```

## 4. 添加新的 HTTP 端点

在 `_server.py` 的 `build_app` 函数中添加：

```python
def build_app(runtime, platform_client=None):
    from fastapi import FastAPI

    app = FastAPI(lifespan=lifespan)

    # 现有端点
    @app.get("/health")
    async def health(): ...

    @app.post("/invoke")
    async def invoke(request): ...

    # 新增端点
    @app.get("/metrics")
    async def metrics():
        """返回详细指标"""
        return JSONResponse({
            "models": runtime.models.keys(),
            "tools": runtime.tools.get_tool_names(),
            ...
        })

    return app
```

## 5. 添加新的 CLI 子命令

在 `_cli.py` 中添加：

```python
def _parse_args(argv=None):
    parser = argparse.ArgumentParser(...)
    subparsers = parser.add_subparsers(dest="command")

    # 现有 run 命令
    run_p = subparsers.add_parser("run", ...)

    # 新增 validate 命令
    validate_p = subparsers.add_parser(
        "validate",
        help="Validate project configuration",
    )
    validate_p.add_argument(
        "project_path",
        nargs="?",
        default=".",
    )

    return parser.parse_args(argv)


async def _run_async(args):
    if args.command == "run":
        ...
    elif args.command == "validate":
        await _validate_project(args.project_path)


async def _validate_project(project_path: str):
    """验证项目配置"""
    from ._config import load_config
    config = load_config(os.path.join(project_path, "agentapp.yaml"))
    logger.info("Configuration valid: %d models, %d MCP servers",
                len(config.models), len(config.mcp_servers))
```

## 6. 扩展配置格式

### 6.1 添加新的顶级配置段

```python
# _config.py
@dataclass
class NewFeatureConfig:
    enabled: bool = False
    option_a: str = "default"

@dataclass
class RuntimeConfig:
    models: dict[str, ModelConfig]
    mcp_servers: dict[str, MCPServerConfig]
    session: SessionConfig
    platform: PlatformConfig
    tracing: TracingConfig
    server: ServerConfig
    new_feature: NewFeatureConfig = field(default_factory=NewFeatureConfig)  # 新增


def load_config(config_path: str) -> RuntimeConfig:
    ...
    # 解析新配置段
    new_feature_raw = raw_config.get("new_feature", {})
    new_feature = NewFeatureConfig(
        enabled=new_feature_raw.get("enabled", False),
        option_a=new_feature_raw.get("option_a", "default"),
    )

    return RuntimeConfig(
        ...,
        new_feature=new_feature,
    )
```

## 7. 注意事项

### 7.1 保持向后兼容

- 新配置字段应有默认值
- 新功能应可选启用
- 不要修改现有 API 签名

### 7.2 遵循代码规范

- 懒加载第三方库
- 使用 `_` 前缀命名内部模块
- 编写完整的类型注解
- 添加对应的单元测试

### 7.3 文档更新

扩展后需更新：
- `02-config.md` - 配置格式说明
- `03-api.md` - API 接口说明
- `04-guide.md` - 使用示例
