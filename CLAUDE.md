# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AgentScope is a multi-agent framework for building LLM applications, developed by Alibaba's SysML team. It emphasizes transparency, modularity, and explicit message passing for agent-oriented programming.

**Key characteristics:**
- Python 3.10+ required
- Async-first design (v1.0+)
- Model-agnostic (supports OpenAI, Anthropic, DashScope, Gemini, Ollama)
- Core agent is `ReActAgent` - all other agents should be built as examples first

## Common Commands

```bash
# Install in development mode (recommended: use uv for faster installs)
uv pip install -e ".[dev]"

# Run all tests
pytest tests/

# Run a single test file
pytest tests/memory_test.py

# Run a specific test function
pytest tests/memory_test.py::test_function_name

# Run pre-commit checks (required before submitting)
pre-commit run --all-files

# Install pre-commit hooks
pre-commit install
```

## Architecture Overview

```
src/agentscope/
├── agent/          # AgentBase, ReActAgent (core), UserAgent, A2AAgent
├── model/          # LLM integrations (OpenAI, Anthropic, DashScope, Gemini, Ollama)
├── formatter/      # Convert Msg objects to provider-specific API formats
├── message/        # Message types with content blocks (TextBlock, ToolUseBlock, etc.)
├── memory/         # Working & long-term memory (InMemory, Redis, SQLAlchemy, Mem0, ReMe)
├── tool/           # Toolkit management, execution, built-in tools
├── mcp/            # MCP clients (HTTP, SSE, StdIO) - stateful and stateless modes
├── pipeline/       # Multi-agent coordination (MsgHub, sequential/fanout pipelines)
├── session/        # Session state persistence
├── rag/            # RAG system (readers, vector stores, knowledge bases)
├── tracing/        # OpenTelemetry-based execution tracing
├── token/          # Token counting for various models
├── embedding/      # Text and multimodal embeddings
├── a2a/            # Agent-to-Agent protocol support
├── evaluate/       # Distributed evaluation (Ray-based)
├── tuner/          # Agent tuning (Trinity-RFT integration)
├── tts/            # Text-to-Speech capabilities
└── platform/       # Multi-tenant deployment infrastructure
```

### Key Design Patterns

**Message Flow:** Agents communicate via `Msg` objects containing content blocks. The `formatter` module converts these to provider-specific formats.

**Tool Integration:** Tools are registered in a `Toolkit` and can be sync/async, support streaming, and include user interruption handling.

**MCP Support:** Both stateful (persistent connection) and stateless (per-request) MCP clients are available with fine-grained control.

## Code Standards

### Lazy Imports (REQUIRED)
Third-party libraries must be imported at point of use, not at file top:
```python
def some_function():
    import openai  # Import here, not at file top
    # Use openai library
```

### File Naming
- All Python files under `src/agentscope/` should use `_` prefix (e.g., `_utils.py`)
- Expose public APIs through `__init__.py`
- Internal classes/functions must use `_` prefix

### Docstring Format
```python
def func(a: str, b: int | None = None) -> str:
    """{description}

    Args:
        a (`str`):
            The argument a
        b (`int | None`, optional):
            The argument b

    Returns:
        `str`:
            The return str
    """
```

### Type Hints
- Required for all function signatures
- mypy with `--disallow-untyped-defs` and `--disallow-incomplete-defs` is enforced

### Code Style
- Line length: 79 characters (black formatting)
- All code must pass: black, flake8, pylint, mypy

## Testing

- New features must include unit tests in `tests/`
- Use `pytest-forked` for process isolation
- Mock external services (e.g., use `fakeredis` for Redis tests)
- Test naming convention: `{module_name}_test.py`

## Commit Format

Follow Conventional Commits: `<type>(<scope>): <subject>`

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `ci`, `chore`

Examples:
```
feat(memory): add redis cache support
fix(agent): resolve memory leak in ReActAgent
refactor(formatter): simplify message formatting logic
```

## Adding New Components

**New Chat Models:** Requires implementing `ChatModelBase`, a `FormatterBase` subclass, and optionally a `TokenCounterBase`. Must support tools API, streaming, and non-streaming modes.

**New Agents:** Prototype in `examples/agents/` first. The core `ReActAgent` should remain the primary agent class.

**New Memory Backends:** For relational databases, use SQLAlchemy integration. Only add separate implementations for NoSQL databases not covered by existing abstractions.

**New Examples:** Place in appropriate subdirectory under `examples/` (agents, functionality, workflows, evaluation, tuner).
