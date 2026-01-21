# Runtime 模块开发概述

本文档面向 AgentScope 框架开发者，说明 Runtime 模块的设计理念和开发规范。

## 模块定位

Runtime 模块是 AgentScope 框架的**平台化运行时支撑**，负责：

1. **资源初始化**：从配置文件初始化模型、MCP 客户端、Toolkit 等
2. **应用托管**：加载和运行用户的 AgentApp
3. **会话管理**：支持多用户会话的状态持久化
4. **平台通信**：心跳上报、配置更新检查
5. **HTTP 服务**：暴露 `/invoke` 和 `/health` API

## 核心设计原则

### 1. 复用现有能力

Runtime 不重复造轮子，复用 AgentScope 已有模块：

| 功能 | 复用模块 | 说明 |
|------|----------|------|
| 模型调用 | `agentscope.model` | ChatModelBase 及其子类 |
| 工具管理 | `agentscope.tool` | Toolkit 类 |
| MCP 客户端 | `agentscope.mcp` | HttpStatefulClient |
| 状态持久化 | `agentscope.session` | JSONSession |
| 消息格式 | `agentscope.message` | Msg 类 |

### 2. 懒加载原则

遵循 AgentScope 代码规范，第三方库在使用时才导入：

```python
# 正确：在函数内导入
def build_app(...):
    from fastapi import FastAPI
    ...

# 错误：在文件顶部导入
import fastapi  # ❌
```

### 3. 异步优先

所有 I/O 操作都是异步的：

```python
async def initialize(self, ...):
    # 异步初始化 MCP 客户端
    await client.connect()
```

### 4. 配置驱动

资源通过 `agentapp.yaml` 声明，Runtime 负责解析和初始化：

```yaml
models:
  main:
    provider: openai
    model: gpt-4
    api_key: ${OPENAI_API_KEY}
```

## 文件命名规范

所有内部文件使用 `_` 前缀：

```
src/agentscope/runtime/
├── __init__.py      # 公开导出
├── _runtime.py      # Runtime 核心类
├── _config.py       # 配置解析
├── _app_base.py     # AgentApp 基类
├── _server.py       # HTTP 服务
├── _platform.py     # 平台通信
├── _session.py      # Session 重导出
└── _cli.py          # CLI 入口
```

## 公开 API

通过 `__init__.py` 导出以下公开 API：

```python
from agentscope.runtime import (
    runtime,         # Runtime 全局单例
    AgentApp,        # 应用基类
    SessionContext,  # 会话上下文
)
```

## 依赖关系

```
_cli.py
    └── _runtime.py (runtime 单例)
    └── _platform.py (PlatformClient)
    └── _server.py (build_app)
            └── _app_base.py (SessionContext)

_runtime.py
    └── _config.py (配置解析)
    └── _app_base.py (AgentApp)
    └── agentscope.model (模型类)
    └── agentscope.tool (Toolkit)
    └── agentscope.mcp (MCP 客户端)
    └── agentscope.session (JSONSession)
```

## 下一步

- [架构详解](06-dev-architecture.md)：各组件的实现细节
- [扩展指南](07-dev-extending.md)：如何扩展 Runtime
- [测试指南](08-dev-testing.md)：测试规范和示例
