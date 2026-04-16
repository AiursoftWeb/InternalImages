# Folder Agent

Folder Agent is a containerized REST API wrapper for the [Qwen Code CLI](https://github.com/QwenLM/qwen-code). It allows you to query a knowledge base (like a directory of Markdown files) via a simple HTTP POST request.

## Features

- **Agentic RAG**: Uses Qwen Code's built-in reasoning to search and read your files.
- **REST API**: Simple FastAPI backend to integrate with your existing systems.
- **YOLO Mode**: Runs without user intervention, perfect for automated backends.
- **Dynamic Configuration**: Automatically configures Qwen based on environment variables.

## How to Run

### Build the Image

```bash
docker build -t folder-agent .
```

### Run the Container

You need to mount your knowledge base (e.g., your blog's Markdown folder) to `/import` and provide your API Key and endpoint.

```bash
docker run -d \
  -p 8000:8000 \
  -v /path/to/your/markdowns:/import \
  -e QWEN_API_KEY=your_api_key_here \
  -e QWEN_BASE_URL=https://ollama.aiursoft.com/v1 \
  -e QWEN_MODEL_NAME=aiursoft-instruct:latest \
  --name folder-agent \
  folder-agent
```

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `QWEN_API_KEY` | Your AI provider API Key. | (Required) |
| `QWEN_BASE_URL` | The base URL of the OpenAI-compatible API. | `https://ollama.aiursoft.com/v1` |
| `QWEN_MODEL_NAME` | The name of the model to use. | `aiursoft-instruct:latest` |
| `OLLAMA_GATEWAY_API_KEY` | Legacy alias for `QWEN_API_KEY`. | - |

## API Usage

### Health Check

`GET /health`

### Ask a Question

`POST /ask`

**Payload:**

```json
{
  "system_prompt": "You are a helpful assistant. Use the files in the current directory to answer the question.",
  "question": "What is the main topic of my recent blog posts?"
}
```

**Response:**

```json
{
  "answer": "Based on the files in the directory, your recent blog posts focus on..."
}
```

## Integration Example (Python)

```python
import requests

response = requests.post(
    "http://localhost:8000/ask",
    json={
        "system_prompt": "You are Anduin's Cyber-Twin.",
        "question": "What do you think about AI agents?"
    }
)

print(response.json()["answer"])
```
