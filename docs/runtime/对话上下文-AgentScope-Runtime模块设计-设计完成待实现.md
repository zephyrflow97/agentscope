# 对话上下文 - AgentScope Runtime 模块设计

> 生成时间：2026-01-19T16:27:46Z
> 状态：设计完成，待实现

---

## 📋 问题背景

### 项目信息
- **项目名称**：AgentScope
- **项目路径**：`/Users/suifeng/Project/agentscope`
- **项目描述**：阿里巴巴 SysML 团队开发的多 Agent 框架，用于构建 LLM 应用
- **当前分支**：`feat/runtime`

### 当前状态
用户希望设计一个 **Agent 管理平台**，专门用于管理使用 AgentScope 框架开发的 Agent 应用。需要在 AgentScope 框架中新增一个 **Runtime 模块**，作为平台化部署的运行时支撑。

### 涉及组件
- `src/agentscope/model/` - 模型抽象层
- `src/agentscope/mcp/` - MCP 客户端
- `src/agentscope/tool/` - Toolkit 工具管理
- `src/agentscope/session/` - 状态持久化
- `src/agentscope/tracing/` - OpenTelemetry 追踪
- `src/agentscope/message/` - Msg 消息对象

---

## 🎯 实现目标

### 主要目标
设计并实现 AgentScope Runtime 模块，支持：
1. 从配置文件初始化模型、工具等资源
2. 作为 Agent 应用的统一入口
3. 支持多用户会话管理
4. 与平台通信（心跳、状态上报）
5. 本地开发和平台部署使用同一套配置

### 核心概念
- **Project**：用户开发的 Agent 应用单元（代码 + 配置）
- **Instance**：Project 的运行实例，运行在独立容器中
- **Runtime**：全局单例，管理 Instance 的所有资源
- **AgentApp**：用户实现的应用入口类

### 具体要求
1. Project 结构：`agentapp.yaml` + `app.py` + `requirements.txt`
2. 入口约定：`app.py` 中的 `App` 类
3. 资源注入：全局单例 `runtime.models.xxx` / `runtime.tools`
4. 配置格式：YAML，支持 `${ENV_VAR}` 环境变量
5. AgentApp 接口：`async def __call__(msg, ctx) -> AsyncIterator[Msg]`

---

## 🔧 技术约束

### 必须遵守的原则
1. **复用现有能力**：复用 AgentScope 的 Session、Tracing、Toolkit 等模块
2. **懒加载**：第三方库在使用时才导入（AgentScope 代码规范）
3. **异步优先**：所有 I/O 操作都是异步的
4. **本地可运行**：同一份配置本地和平台都能运行

### 技术限制
- MCP Server 只支持 URL 方式（sse / streamable_http）
- 槽位类型暂时只支持 Model 和 Tool
- Session 存储先用本地 JSON 文件，后续可扩展
- 热更新配置通过重启实现

### 关键设计决策

| 决策项 | 选择 | 原因 |
|--------|------|------|
| 资源注入方式 | 全局单例 | 代码最简洁，用户随时随地都能获取资源 |
| AgentApp 发现 | 约定文件名 `app.py:App` | 零配置，最简单 |
| session_id 传递 | 显式参数 | 更清晰，易于测试 |
| 平台通信方式 | HTTP 轮询 | 实现简单 |
| 用户请求入口 | 平台统一网关转发 | 统一管理 |

---

## ✅ 当前方案

### 模块结构
```
src/agentscope/runtime/
├── __init__.py          # 导出 runtime, AgentApp, SessionContext
├── _runtime.py          # Runtime 核心类
├── _config.py           # 配置解析
├── _app_base.py         # AgentApp 基类
├── _server.py           # HTTP 服务
├── _platform.py         # 平台通信
├── _session.py          # Session 管理
└── _cli.py              # CLI 入口
```

### 核心接口

**AgentApp 基类：**
```python
class AgentApp(ABC):
    @abstractmethod
    async def __call__(
        self,
        msg: Msg,
        ctx: SessionContext,
    ) -> AsyncIterator[Msg]:
        pass

    async def on_startup(self) -> None:
        pass

    async def on_shutdown(self) -> None:
        pass
```

**Runtime 单例：**
```python
class Runtime:
    models: ModelRegistry      # runtime.models.main
    tools: Toolkit             # runtime.tools
    session: SessionBase       # runtime.session

    async def initialize(self, config_path: str = "agentapp.yaml"):
        pass

    async def shutdown(self):
        pass
```

### 配置文件格式
```yaml
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

session:
  backend: json
  save_dir: ./sessions

platform:
  endpoint: https://platform.example.com/api
  instance_id: ${INSTANCE_ID}
  heartbeat_interval: 30

server:
  port: 8080
```

### HTTP API
- `POST /invoke` - 处理用户请求（SSE 流式响应）
- `GET /health` - 健康检查

### CLI 命令
```bash
agentscope run [project_path] [--port 8080] [--config agentapp.yaml] [--no-platform]
```

---

## 📝 关键代码变更

### 已创建的文件
| 文件 | 描述 |
|------|------|
| `docs/runtime/01-overview.md` | 概述：背景、核心概念、模块结构 |
| `docs/runtime/02-config.md` | 配置：agentapp.yaml 完整格式 |
| `docs/runtime/03-api.md` | API：接口定义、HTTP API、CLI |
| `docs/runtime/04-guide.md` | 指南：快速开始、示例代码 |

### 待创建的文件
```
src/agentscope/runtime/
├── __init__.py
├── _runtime.py
├── _config.py
├── _app_base.py
├── _server.py
├── _platform.py
├── _session.py
└── _cli.py
```

---

## 🎯 当前进度

### ✅ 已完成
- [x] 需求对齐和设计讨论
- [x] Runtime 模块架构设计
- [x] agentapp.yaml 配置格式设计
- [x] AgentApp 接口设计
- [x] Session 管理机制设计
- [x] HTTP API 设计
- [x] 设计文档编写和保存

### 🔄 进行中
- [ ] 无

### ⏳ 待处理
- [ ] 实现 Runtime 核心类
- [ ] 实现配置解析
- [ ] 实现 AgentApp 基类
- [ ] 实现 HTTP 服务
- [ ] 实现平台通信
- [ ] 实现 CLI 入口
- [ ] 编写单元测试
- [ ] 集成测试

---

## 💡 使用方法

### 用户开发流程
1. 创建 Project 目录结构
2. 编写 `agentapp.yaml` 配置
3. 实现 `app.py` 中的 `App` 类
4. 本地运行：`agentscope run .`
5. 打包上传到平台

### 示例代码
```python
# app.py
from agentscope.runtime import runtime, AgentApp, SessionContext
from agentscope.message import Msg
from typing import AsyncIterator

class App(AgentApp):
    async def __call__(self, msg: Msg, ctx: SessionContext) -> AsyncIterator[Msg]:
        model = runtime.models.main
        async for chunk in model.stream([msg]):
            yield Msg(name="assistant", content=chunk.text, role="assistant")
```

---

## 🐛 已知问题和待解决

1. **ModelRegistry 类型提示**：需要通过 `.pyi` 存根文件让 IDE 知道有哪些模型
2. **MCP 客户端生命周期**：SSE 客户端需要在启动时 connect，关闭时 close
3. **Session 并发**：多个请求同时操作同一 session 时的并发控制

---

## 🚀 下一步计划

1. **实现核心模块**：按照设计文档实现 Runtime 模块代码
2. **编写测试**：单元测试 + 集成测试
3. **示例项目**：创建一个完整的示例 Project
4. **文档完善**：补充 API 文档和使用说明

---

## 📝 备注

### 设计讨论要点回顾
1. **资源注入方式**：讨论了全局单例、构造函数注入、装饰器三种方式，最终选择全局单例
2. **AgentApp 发现**：讨论了约定文件名、配置声明、装饰器扫描三种方式，最终选择约定文件名
3. **Session 管理**：确认每个 Instance 支持多用户会话，session_id 由平台网关传递

### 参考资料
- AgentScope 现有模块：model、mcp、tool、session、tracing
- 设计文档：`docs/runtime/01-overview.md` ~ `04-guide.md`

### 相关命令
```bash
# 查看设计文档
ls docs/runtime/

# 运行测试
pytest tests/

# 预提交检查
pre-commit run --all-files
```
