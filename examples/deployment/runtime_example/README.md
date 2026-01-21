# Runtime Example

This example demonstrates how to use the AgentScope Runtime module to deploy a simple chat agent as an HTTP service.

## Project Structure

```
runtime_example/
├── agentapp.yaml    # Runtime configuration file
├── app.py           # Application entry point
└── README.md        # This file
```

## Prerequisites

1. Install AgentScope with runtime dependencies:

```bash
uv pip install -e ".[runtime]"
```

2. Set up your API key:

```bash
export DASHSCOPE_API_KEY="your-api-key-here"
```

## Running the Example

### Method 1: Using the CLI

```bash
# From the project root
agentscope run examples/deployment/runtime_example

# Or from the example directory
cd examples/deployment/runtime_example
agentscope run .
```

### Method 2: With custom port

```bash
agentscope run examples/deployment/runtime_example --port 9000
```

## Testing the Service

Once the server is running, you can test it using curl:

```bash
# Health check
curl http://localhost:8080/health

# Send a message (SSE streaming response)
curl -X POST http://localhost:8080/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-session-001",
    "message": {
      "name": "user",
      "role": "user",
      "content": "Hello! What can you help me with?"
    }
  }'
```

## Configuration

The `agentapp.yaml` file contains the runtime configuration:

- **models**: Define LLM providers and settings
- **session**: Configure session persistence
- **server**: HTTP server settings

### Using Different Model Providers

To use OpenAI instead of DashScope:

```yaml
models:
  main:
    provider: openai
    model: gpt-4
    api_key: ${OPENAI_API_KEY}
    stream: true
```

Remember to update the formatter in `app.py` accordingly:

```python
from agentscope.formatter import OpenAIChatFormatter
# ...
formatter=OpenAIChatFormatter()
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check endpoint |
| `/invoke` | POST | Send a message and receive streaming response (SSE) |

### Request Format for `/invoke`

```json
{
  "session_id": "unique-session-id",
  "message": {
    "name": "user",
    "role": "user",
    "content": "Your message here"
  },
  "metadata": {}
}
```

### Response Format

Responses are streamed using Server-Sent Events (SSE). Each event contains a JSON message:

```json
data: {"name": "Assistant", "role": "assistant", "content": "Response text..."}
```
