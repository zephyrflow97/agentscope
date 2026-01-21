# Runtime 测试指南

本文档说明 Runtime 模块的测试规范和示例。

## 测试文件结构

```
tests/
└── runtime_test.py    # Runtime 模块单元测试
```

## 测试类组织

按功能模块划分测试类：

| 测试类 | 测试目标 |
|--------|----------|
| `TestExpandEnvVars` | 环境变量展开 |
| `TestLoadConfig` | 配置文件加载 |
| `TestDataclasses` | 配置数据类默认值 |
| `TestSessionContext` | 会话上下文 |
| `TestModelRegistry` | 模型注册表 |
| `TestRuntime` | Runtime 同步方法 |
| `TestRuntimeAsync` | Runtime 异步方法 |
| `TestCliArgumentParsing` | CLI 参数解析 |

## 测试示例

### 1. 配置解析测试

```python
class TestLoadConfig(TestCase):
    def test_load_config_with_env_vars(self) -> None:
        """测试环境变量展开"""
        os.environ["TEST_API_KEY"] = "secret_api_key"
        yaml_content = """
models:
  main:
    provider: openai
    model: gpt-4
    api_key: ${TEST_API_KEY}
"""
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yaml",
            delete=False,
        ) as f:
            f.write(yaml_content)
            f.flush()
            config = load_config(f.name)
        os.unlink(f.name)
        del os.environ["TEST_API_KEY"]

        self.assertEqual(
            config.models["main"].api_key,
            "secret_api_key",
        )
```

**要点**：
- 使用 `tempfile` 创建临时配置文件
- 测试后清理环境变量和临时文件
- 验证环境变量被正确替换

### 2. ModelRegistry 测试

```python
class TestModelRegistry(TestCase):
    def test_register_and_retrieve_by_attr(self) -> None:
        """测试属性访问"""
        registry = ModelRegistry()
        mock_model = MagicMock()
        registry._register("main", mock_model)
        self.assertEqual(registry.main, mock_model)

    def test_attribute_error_for_missing_model(self) -> None:
        """测试缺失模型抛出 AttributeError"""
        registry = ModelRegistry()
        with self.assertRaises(AttributeError) as ctx:
            _ = registry.nonexistent
        self.assertIn("nonexistent", str(ctx.exception))
```

**要点**：
- 使用 `MagicMock` 模拟模型对象
- 测试正常访问和异常情况
- 验证错误消息包含有用信息

### 3. 异步测试

```python
from unittest.async_case import IsolatedAsyncioTestCase

class TestRuntimeAsync(IsolatedAsyncioTestCase):
    async def test_runtime_double_init_raises(self) -> None:
        """测试重复初始化抛出异常"""
        rt = Runtime()
        rt._initialized = True  # 模拟已初始化
        with self.assertRaises(RuntimeError) as ctx:
            await rt.initialize()
        self.assertIn("already initialized", str(ctx.exception))

    async def test_runtime_shutdown_when_not_initialized(self) -> None:
        """测试未初始化时关闭是安全的"""
        rt = Runtime()
        await rt.shutdown()  # 不应抛出异常
```

**要点**：
- 使用 `IsolatedAsyncioTestCase` 进行异步测试
- 每个测试创建新的 Runtime 实例，避免状态污染

### 4. CLI 参数测试

```python
class TestCliArgumentParsing(TestCase):
    def test_parse_run_with_all_options(self) -> None:
        """测试所有选项"""
        args = _parse_args([
            "run", "./project",
            "--port", "9000",
            "--config", "custom.yaml",
            "--no-platform",
            "--log-level", "debug",
        ])
        self.assertEqual(args.command, "run")
        self.assertEqual(args.project_path, "./project")
        self.assertEqual(args.port, 9000)
        self.assertEqual(args.config, "custom.yaml")
        self.assertTrue(args.no_platform)
        self.assertEqual(args.log_level, "debug")
```

## 测试规范

### 命名规范

```python
def test_<功能>_<场景>(self) -> None:
    """<简要描述>"""
```

示例：
- `test_expand_string_env_var` - 测试字符串环境变量展开
- `test_load_config_missing_file` - 测试加载不存在的配置文件
- `test_attribute_error_for_missing_model` - 测试访问不存在的模型

### Mock 使用

```python
from unittest.mock import MagicMock, AsyncMock, patch

# Mock 同步对象
mock_model = MagicMock()
mock_model.some_method.return_value = "result"

# Mock 异步方法
mock_client = MagicMock()
mock_client.connect = AsyncMock()

# Patch 模块
with patch("agentscope.runtime._runtime._create_model") as mock_create:
    mock_create.return_value = MagicMock()
    ...
```

### 临时文件处理

```python
import tempfile
import os

def test_with_temp_file(self) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        delete=False,
    ) as f:
        f.write("content")
        f.flush()
        # 使用 f.name
    os.unlink(f.name)  # 清理
```

## 运行测试

```bash
# 运行所有 Runtime 测试
pytest tests/runtime_test.py -v

# 运行特定测试类
pytest tests/runtime_test.py::TestModelRegistry -v

# 运行特定测试方法
pytest tests/runtime_test.py::TestModelRegistry::test_keys_method -v

# 显示覆盖率
pytest tests/runtime_test.py --cov=src/agentscope/runtime --cov-report=term-missing
```

## 集成测试

完整的端到端测试需要：

1. 创建临时项目目录
2. 写入 `agentapp.yaml` 和 `app.py`
3. 调用 `runtime.initialize()`
4. 模拟请求并验证响应
5. 调用 `runtime.shutdown()`
6. 清理临时目录

```python
class TestRuntimeIntegration(IsolatedAsyncioTestCase):
    async def test_full_lifecycle(self) -> None:
        """测试完整生命周期"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. 创建配置文件
            config_path = os.path.join(tmpdir, "agentapp.yaml")
            with open(config_path, "w") as f:
                f.write("models: {}\nmcp_servers: {}")

            # 2. 创建 App 文件
            app_path = os.path.join(tmpdir, "app.py")
            with open(app_path, "w") as f:
                f.write(MINIMAL_APP_CODE)

            # 3. 初始化并测试
            rt = Runtime()
            await rt.initialize(
                config_path="agentapp.yaml",
                project_path=tmpdir,
            )
            self.assertTrue(rt.is_initialized)

            # 4. 关闭
            await rt.shutdown()
            self.assertFalse(rt.is_initialized)
```

## 测试覆盖目标

- 配置解析：100%
- ModelRegistry：100%
- Runtime 核心方法：90%+
- CLI 参数解析：100%
- HTTP Server：80%+（需要 httpx 测试客户端）
- Platform Client：70%+（需要 mock HTTP 请求）
