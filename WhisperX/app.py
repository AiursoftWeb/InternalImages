import os
import secrets
import shutil
import tempfile
import threading
import time

import whisperx
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, BackgroundTasks
from fastapi.responses import JSONResponse

from models_config import BAKED_MODELS

app = FastAPI()
model_token = os.getenv("ASR_WHISPERX_TOKEN", "").strip()
if not model_token:
    raise RuntimeError("ASR_WHISPERX_TOKEN is required")

MODEL_REGISTRY = {}
MODEL_LOCK = threading.Lock()


def load_model(name: str):
    """Lazily load a whisperx model and cache it. Unknown or unloadable names
    raise so the caller can return a clear error instead of a 500."""
    if name not in BAKED_MODELS:
        raise ValueError("model is not allowed")

    with MODEL_LOCK:
        if name in MODEL_REGISTRY:
            return MODEL_REGISTRY[name]

        # Clear previous models to release VRAM/RAM before loading a new one
        MODEL_REGISTRY.clear()
        import gc
        import torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        try:
            model = whisperx.load_model(
                name,
                os.getenv("WHISPERX_DEVICE", "cuda"),
                compute_type=os.getenv("WHISPERX_COMPUTE_TYPE", "float16"),
            )
        except Exception as exc:
            raise ValueError(f"cannot load model '{name}': {exc}") from exc
        MODEL_REGISTRY[name] = model
        return model


@app.middleware("http")
async def require_model_token(request: Request, call_next):
    if request.url.path == "/health" or request.url.path.startswith("/v1/"):
        expected = f"Bearer {model_token}"
        authorization = request.headers.get("Authorization", "")
        if not secrets.compare_digest(authorization, expected):
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok", "models_loaded": list(MODEL_REGISTRY.keys())}


@app.get("/v1/models")
def list_models():
    loaded = set(MODEL_REGISTRY.keys())
    data = []
    for name in BAKED_MODELS:
        data.append({
            "id": name,
            "object": "model",
            "owned_by": "whisperx",
            "baked": True,
            "loaded": name in loaded,
        })
    for name in loaded:
        if name not in BAKED_MODELS:
            data.append({
                "id": name,
                "object": "model",
                "owned_by": "whisperx",
                "baked": False,
                "loaded": True,
            })
    return {"object": "list", "data": data}


@app.post("/v1/cancel")
def cancel(background_tasks: BackgroundTasks):
    def exit_process():
        print("[WhisperX] Gracefully exiting process in 500ms to free GPU resources...")
        time.sleep(0.5)
        # Force terminate process to release CUDA resources
        os._exit(0)
    
    print("[WhisperX] Received cancellation request. Scheduling exit...")
    background_tasks.add_task(exit_process)
    return {"status": "cancelling"}


@app.post("/v1/audio/transcriptions")
def transcribe(
    file: UploadFile = File(...),
    model: str = Form(default=""),
    language: str = Form(default=""),
    response_format: str = Form(default="json"),
):
    model_name = model or os.getenv("WHISPERX_MODEL", "large-v3")
    print(f"[WhisperX] Received transcription request. Model: {model_name}, File: {file.filename}, Language: {language or 'auto'}")
    start_time = time.time()
    try:
        asr_model = load_model(model_name)
    except ValueError as exc:
        print(f"[WhisperX] Error loading model {model_name}: {exc}")
        raise HTTPException(status_code=400, detail=str(exc))

    with tempfile.NamedTemporaryFile(suffix=os.path.splitext(file.filename or "audio")[1]) as audio_file:
        shutil.copyfileobj(file.file, audio_file)
        audio_file.flush()
        print(f"[WhisperX] Saved temp audio file: {audio_file.name}. Starting transcription...")
        result = asr_model.transcribe(
            whisperx.load_audio(audio_file.name),
            language=language or None,
        )
    
    elapsed = time.time() - start_time
    print(f"[WhisperX] Transcription completed for {file.filename} in {elapsed:.2f} seconds")
    if response_format == "json":
        return {"text": " ".join(segment["text"].strip() for segment in result["segments"])}
    return {
        "text": " ".join(segment["text"].strip() for segment in result["segments"]),
        "language": result.get("language"),
        "segments": result["segments"],
    }
