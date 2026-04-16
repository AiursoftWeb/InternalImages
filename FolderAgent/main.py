import os
import subprocess
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from loguru import logger

app = FastAPI(title="Folder Agent API")

class AskRequest(BaseModel):
    system_prompt: str
    question: str

def ensure_qwen_config():
    """Ensure qwen configuration exists based on environment variables."""
    qwen_dir = Path.home() / ".qwen"
    qwen_settings = qwen_dir / "settings.json"
    
    # Read configuration from environment variables
    api_key = os.getenv("QWEN_API_KEY") or os.getenv("OLLAMA_GATEWAY_API_KEY")
    base_url = os.getenv("QWEN_BASE_URL", "https://ollama.aiursoft.com/v1")
    model_name = os.getenv("QWEN_MODEL_NAME", "aiursoft-instruct:latest")
    
    if api_key:
        qwen_dir.mkdir(parents=True, exist_ok=True)
        config = {
            "security": {
                "auth": {
                    "selectedType": "openai"
                }
            },
            "model": {
                "name": model_name
            },
            "env": {
                "QWEN_CUSTOM_API_KEY": api_key
            },
            "modelProviders": {
                "openai": [
                    {
                        "id": model_name,
                        "name": "Folder Agent Provider",
                        "envKey": "QWEN_CUSTOM_API_KEY",
                        "baseUrl": base_url
                    }
                ]
            }
        }
        with open(qwen_settings, "w") as f:
            json.dump(config, f, indent=2)
        logger.info(f"Configured Qwen with model: {model_name}, base_url: {base_url}")
    else:
        logger.warning("QWEN_API_KEY not found. Qwen might not work unless ~/.qwen/settings.json is manually provided.")

@app.on_event("startup")
async def startup_event():
    ensure_qwen_config()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/ask")
async def ask(request: AskRequest):
    logger.info(f"Received question: {request.question}")
    
    # Target directory for qwen to run in
    import_dir = "/import"
    if not os.path.exists(import_dir):
        # Fallback to current directory if /import doesn't exist (local dev)
        import_dir = os.getcwd()

    # Build the command
    cmd = [
        "qwen",
        "-y", # YOLO mode
        "--system-prompt", request.system_prompt,
        "-p", request.question
    ]
    
    try:
        # Run qwen and capture output
        process = subprocess.run(
            cmd,
            cwd=import_dir,
            capture_output=True,
            text=True,
            check=True
        )
        return {"answer": process.stdout.strip()}
    except subprocess.CalledProcessError as e:
        logger.error(f"Qwen execution failed: {e.stderr}")
        raise HTTPException(status_code=500, detail=f"Qwen error: {e.stderr}")
    except Exception as e:
        logger.exception("Unexpected error")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
