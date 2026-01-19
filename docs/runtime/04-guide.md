# Runtime 模块设计 - 开发指南

## 快速开始

### 1. 创建 Project 结构

```bash
mkdir my_agent_app
cd my_agent_app
```

创建以下文件：

```
my_agent_app/
├── agentapp.yaml
├── app.py
└── requirements.txt
```

### 2. 编写配置文件

```yaml
# agentapp.yaml
models:
  main:
    provider: openai
    base_url: https://api.openai.com/v1
    model: gpt-4
    api_key: ${OPENAI_API_KEY}
```

### 3. 实现 App 类

```python
# app.py
from agentscope.runtime import runtime, AgentApp, SessionContext
from agentscope.message import Msg
from typing import AsyncIterator


class App(AgentApp):
    async def __call__(
        self,
        msg: Msg,
        ctx: SessionContext,
    ) -> AsyncIterator[Msg]:
        model = runtime.models.main
        async for chunk in model.stream([msg]):
            yield Msg(
                name="assistant",
                content=chunk.text,
                role="assistant",
            )
```

### 4. 本地运行

```bash
export OPENAI_API_KEY="your-api-key"
agentscope run .
```

## 完整示例

### 带工具的 ReActAgent

```yaml
# agentapp.yaml
models:
  main:
    provider: openai
    base_url: https://api.openai.com/v1
    model: gpt-4
    api_key: ${OPENAI_API_KEY}

mcp_servers:
  search:
    url: https://mcp.example.com/search/sse
    transport: sse
```

```python
# app.py
from agentscope.runtime import runtime, AgentApp, SessionContext
from agentscope.message import Msg
from agentscope.agent import ReActAgent
from agentscope.memory import InMemoryMemory
from typing import AsyncIterator


class App(AgentApp):
    def __init__(self):
        self._agents: dict[str, ReActAgent] = {}

    def _get_agent(self, session_id: str) -> ReActAgent:
        """获取或创建 session 对应的 Agent"""
        if session_id not in self._agents:
            self._agents[session_id] = ReActAgent(
                name="Assistant",
                sys_prompt="You are a helpful assistant with search capability.",
                model=runtime.models.main,
                toolkit=runtime.tools,
                memory=InMemoryMemory(),
            )
        return self._agents[session_id]

    async def __call__(
        self,
        msg: Msg,
        ctx: SessionContext,
    ) -> AsyncIterator[Msg]:
        agent = self._get_agent(ctx.session_id)

        # 加载历史状态
        await runtime.session.load_session_state(
            ctx.session_id,
            memory=agent.memory,
        )

        # 处理请求
        async for chunk in agent.stream(msg):
            yield chunk

        # 保存状态
        await runtime.session.save_session_state(
            ctx.session_id,
            memory=agent.memory,
        )
```

### 多 Agent 协作

```python
# app.py
from agentscope.runtime import runtime, AgentApp, SessionContext
from agentscope.message import Msg
from agentscope.agent import ReActAgent
from typing import AsyncIterator


class App(AgentApp):
    async def on_startup(self) -> None:
        """初始化多个 Agent"""
        self.planner = ReActAgent(
            name="Planner",
            sys_prompt="You are a planning agent.",
            model=runtime.models.main,
        )
        self.executor = ReActAgent(
            name="Executor",
            sys_prompt="You are an execution agent.",
            model=runtime.models.assistant,
            toolkit=runtime.tools,
        )

    async def __call__(
        self,
        msg: Msg,
        ctx: SessionContext,
    ) -> AsyncIterator[Msg]:
        # 1. Planner 制定计划
        plan = await self.planner(msg)
        yield Msg(
            name="system",
            content=f"Plan: {plan.get_text_content()}",
            role="assistant",
        )

        # 2. Executor 执行计划
        async for chunk in self.executor.stream(plan):
            yield chunk
```

## Session 管理

### 自动状态持久化

```python
class App(AgentApp):
    async def __call__(self, msg: Msg, ctx: SessionContext) -> AsyncIterator[Msg]:
        # 加载状态
        await runtime.session.load_session_state(
            ctx.session_id,
            memory=self.agent.memory,
            toolkit=self.agent.toolkit,
        )

        # 处理...
        async for chunk in self.agent.stream(msg):
            yield chunk

        # 保存状态
        await runtime.session.save_session_state(
            ctx.session_id,
            memory=self.agent.memory,
            toolkit=self.agent.toolkit,
        )
```

### 手动管理 Session

如果需要更细粒度的控制：

```python
class App(AgentApp):
    async def __call__(self, msg: Msg, ctx: SessionContext) -> AsyncIterator[Msg]:
        # 检查是否是新会话
        state = await runtime.session.load_session_state(
            ctx.session_id,
            allow_not_exist=True,
        )

        if state is None:
            # 新会话，初始化
            self.init_new_session(ctx.session_id)

        # 处理...
```

## 错误处理

```python
class App(AgentApp):
    async def __call__(self, msg: Msg, ctx: SessionContext) -> AsyncIterator[Msg]:
        try:
            async for chunk in self.agent.stream(msg):
                yield chunk
        except Exception as e:
            # 返回错误消息
            yield Msg(
                name="system",
                content=f"Error: {str(e)}",
                role="assistant",
                metadata={"error": True},
            )
```

## 生命周期钩子

```python
class App(AgentApp):
    async def on_startup(self) -> None:
        """App 启动时调用

        适合做：
        - 预热模型
        - 建立数据库连接
        - 加载静态资源
        """
        # 预热模型
        await runtime.models.main([
            Msg(name="system", content="warmup", role="system")
        ])

    async def on_shutdown(self) -> None:
        """App 关闭时调用

        适合做：
        - 关闭连接
        - 保存状态
        - 清理资源
        """
        pass
```

## 访问 Metadata

平台可以通过 metadata 传递额外信息：

```python
class App(AgentApp):
    async def __call__(self, msg: Msg, ctx: SessionContext) -> AsyncIterator[Msg]:
        # 获取用户信息
        user_id = ctx.metadata.get("user_id")
        tenant_id = ctx.metadata.get("tenant_id")

        # 根据租户定制行为
        if tenant_id == "enterprise":
            # 企业版逻辑
            pass
```

## 本地调试

```bash
# 启用详细日志
agentscope run . --log-level debug --no-platform

# 使用不同端口
agentscope run . --port 9000

# 测试请求
curl -X POST http://localhost:8080/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test_session",
    "message": {
      "name": "user",
      "content": "Hello",
      "role": "user"
    }
  }'
```
