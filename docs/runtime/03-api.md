# Runtime 模块设计 - API 和接口

## AgentApp 基类

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator
from agentscope.message import Msg

class SessionContext:
    """会话上下文"""

    def __init__(
        self,
        session_id: str,
        metadata: dict | None = None,
    ):
        self.session_id = session_id
        self.metadata = metadata or {}


class AgentApp(ABC):
    """用户 App 的基类"""

    @abstractmethod
    async def __call__(
        self,
        msg: Msg,
        ctx: SessionContext,
    ) -> AsyncIterator[Msg]:
        """处理用户输入，流式返回结果

        Args:
            msg: 用户输入消息
            ctx: 会话上下文（包含 session_id 和 metadata）

        Yields:
            Msg: 响应消息（流式输出）
        """
        pass

    async def on_startup(self) -> None:
        """App 启动时的钩子，可选实现

        用于初始化 App 级别的资源，如预加载模型、建立连接等。
        此时 runtime 已完成初始化，可以访问 runtime.models 等资源。
        """
        pass

    async def on_shutdown(self) -> None:
        """App 关闭时的钩子，可选实现

        用于清理 App 级别的资源。
        """
        pass
```

## Runtime 单例

```python
class ModelRegistry:
    """模型注册表，支持属性访问"""

    def __getattr__(self, name: str) -> ChatModelBase:
        """通过属性访问模型: runtime.models.main"""

    def __getitem__(self, name: str) -> ChatModelBase:
        """通过索引访问模型: runtime.models["main"]"""

    def keys(self) -> list[str]:
        """返回所有模型名称"""


class Runtime:
    """全局运行时单例"""

    models: ModelRegistry          # 模型注册表
    tools: Toolkit                 # 工具集（合并所有 MCP Server）
    session: SessionBase           # 会话管理器

    async def initialize(self, config_path: str = "agentapp.yaml") -> None:
        """从配置文件初始化所有资源

        初始化顺序：
        1. 解析配置文件
        2. 初始化 Tracing（如果配置）
        3. 初始化模型
        4. 初始化 MCP 客户端和 Toolkit
        5. 初始化 Session
        6. 加载用户 App
        7. 调用 App.on_startup()
        """

    async def shutdown(self) -> None:
        """关闭所有资源

        关闭顺序：
        1. 调用 App.on_shutdown()
        2. 关闭 MCP 客户端连接
        3. 清理其他资源
        """


# 全局单例
runtime = Runtime()
```

## HTTP API

### POST /invoke

处理用户请求，流式返回响应。

**请求格式：**

```json
{
    "session_id": "user_123_conv_456",
    "message": {
        "name": "user",
        "content": "Hello, how are you?",
        "role": "user"
    },
    "metadata": {
        "user_id": "user_123",
        "tenant_id": "tenant_abc"
    }
}
```

**响应格式（SSE）：**

```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive

data: {"name":"assistant","content":"Hello","role":"assistant","metadata":{"chunk":true}}

data: {"name":"assistant","content":"! I'm doing well.","role":"assistant","metadata":{"chunk":true}}

data: {"name":"assistant","content":"","role":"assistant","metadata":{"done":true}}
```

**错误响应：**

```json
{
    "error": {
        "code": "INVALID_REQUEST",
        "message": "session_id is required"
    }
}
```

### GET /health

健康检查端点。

**响应：**

```json
{
    "status": "healthy",
    "instance_id": "instance_xxx",
    "uptime": 3600
}
```

## 平台通信 API

### 心跳上报

Runtime 定期向平台上报状态：

```
POST {platform.endpoint}/instances/{instance_id}/heartbeat

{
    "status": "running",
    "timestamp": "2024-01-15T10:30:00Z",
    "metrics": {
        "active_sessions": 5,
        "total_requests": 1000,
        "memory_usage_mb": 512
    }
}
```

### 配置更新检查

Runtime 定期检查配置是否有更新：

```
GET {platform.endpoint}/instances/{instance_id}/config

Response:
{
    "updated": true,
    "action": "restart"    # restart | reload | none
}
```

如果 `action` 为 `restart`，Runtime 应自行重启以加载新配置。

## CLI 命令

```bash
# 启动服务
agentscope run [project_path] [options]

# 参数说明
project_path          Project 目录路径（默认当前目录）

# 选项
--port PORT           HTTP 服务端口（默认 8080，或读取配置）
--config FILE         配置文件路径（默认 agentapp.yaml）
--no-platform         禁用平台通信（本地开发模式）
--log-level LEVEL     日志级别（debug | info | warning | error）

# 示例
agentscope run .
agentscope run ./my_project --port 9000
agentscope run . --no-platform --log-level debug
```
