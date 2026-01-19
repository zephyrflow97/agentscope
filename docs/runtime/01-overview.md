# Runtime 模块设计 - 概述

## 背景

AgentScope Runtime 是一个用于管理和运行 AgentScope Agent 应用的运行时模块。它支持：

- 从配置文件初始化模型、工具等资源
- 作为 Agent 应用的统一入口
- 支持多用户会话管理
- 与平台通信（心跳、状态上报）
- 集成 Tracing 和 Session 持久化

## 核心概念

### Project

用户使用 AgentScope 开发的应用单元，包含：

```
my_project/
├── agentapp.yaml     # 配置文件（槽位声明 + 资源配置）
├── app.py            # 入口文件，包含 App 类
├── requirements.txt  # Python 依赖
└── ...               # 其他业务代码
```

### Instance

Project 的运行实例。一个 Project 可以部署多个 Instance，每个 Instance：

- 运行在独立容器中
- 有独立的配置（模型、工具等）
- 支持多个用户会话
- 与其他 Instance 完全隔离

### Runtime

全局单例，管理 Instance 的所有资源：

- `runtime.models` - 模型注册表
- `runtime.tools` - 工具集（Toolkit）
- `runtime.session` - 会话管理器

### AgentApp

用户实现的应用入口类，必须：

- 定义在 `app.py` 文件中
- 类名为 `App`
- 继承 `AgentApp` 基类
- 实现 `__call__` 方法

## 模块结构

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

## 设计原则

1. **配置驱动**：通过 `agentapp.yaml` 声明资源，Runtime 负责初始化
2. **全局单例**：资源通过 `runtime` 单例访问，简化用户代码
3. **显式会话**：`session_id` 显式传递，便于理解和测试
4. **本地可运行**：同一份配置本地和平台都能运行
5. **复用现有能力**：复用 AgentScope 的 Session、Tracing 等模块
