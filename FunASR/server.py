"""
FunASR OpenAI-Compatible API Server

Drop-in replacement for OpenAI's /v1/audio/transcriptions endpoint.
Works with any agent framework that supports OpenAI audio API.

Usage:
    python server.py --model sensevoice --device cuda --port 8000

Then use with any OpenAI-compatible client:
    curl http://localhost:8000/v1/audio/transcriptions \
      -F file=@audio.wav -F model=sensevoice
"""

import atexit
import argparse
import multiprocessing
import queue
import secrets
import shutil
import tempfile
import time
import os
import re
import logging
import threading
from typing import Optional

import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="FunASR OpenAI-Compatible API", version="1.0.0")

model_token = os.getenv("ASR_FUNASR_TOKEN", "").strip()
if not model_token:
    raise RuntimeError("ASR_FUNASR_TOKEN is required")


@app.middleware("http")
async def require_model_token(request: Request, call_next):
    if request.url.path == "/health" or request.url.path.startswith("/v1/"):
        expected = f"Bearer {model_token}"
        authorization = request.headers.get("Authorization", "")
        if not secrets.compare_digest(authorization, expected):
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)

MODEL_REGISTRY = {}
DEVICE = "cpu"

MODEL_CONFIGS = {
    "sensevoice": {
        "model": "iic/SenseVoiceSmall",
        "vad_model": "fsmn-vad",
        "vad_kwargs": {"max_single_segment_time": 30000},
    },
    "paraformer": {
        "model": "paraformer-zh",
        "vad_model": "fsmn-vad",
        "punc_model": "ct-punc",
    },
    "paraformer-en": {
        "model": "paraformer-en",
        "vad_model": "fsmn-vad",
    },
    "fun-asr-nano": {
        "model": "FunAudioLLM/Fun-ASR-Nano-2512",
        "hub": "hf",
        "trust_remote_code": True,
        "vad_model": "fsmn-vad",
        "vad_kwargs": {"max_single_segment_time": 30000},
    },
}


class TranscriptionCancelled(Exception):
    pass


def load_model(model_name: str):
    """Load a model and store in registry."""
    if model_name in MODEL_REGISTRY:
        return MODEL_REGISTRY[model_name]

    if model_name not in MODEL_CONFIGS:
        available = list(MODEL_CONFIGS.keys())
        raise ValueError(f"Unknown model '{model_name}'. Available: {available}")

    # Clear previous models to release VRAM/RAM before loading a new one
    MODEL_REGISTRY.clear()
    import gc
    import torch
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    from funasr import AutoModel

    cfg = MODEL_CONFIGS[model_name].copy()
    cfg["device"] = DEVICE
    cfg["disable_update"] = True

    logger.info(f"Loading model '{model_name}' on {DEVICE}...")
    t0 = time.time()
    model = AutoModel(**cfg)
    elapsed = time.time() - t0
    logger.info(f"Model '{model_name}' loaded in {elapsed:.1f}s")

    MODEL_REGISTRY[model_name] = model
    return model


def inference_worker(command_queue, result_queue, device):
    global DEVICE
    DEVICE = device
    while True:
        command = command_queue.get()
        if command is None:
            return

        task_id = command["task_id"]
        try:
            model = load_model(command["model"])
            result_queue.put({
                "task_id": task_id,
                "status": "model_loaded",
                "model": command["model"],
            })
            if command["action"] == "preload":
                result_queue.put({
                    "task_id": task_id,
                    "status": "completed",
                    "model": command["model"],
                    "payload": {},
                })
                continue

            generate_kwargs = {"input": command["audio_path"], "batch_size": 1}
            if command["language"]:
                generate_kwargs["language"] = command["language"]

            started_at = time.time()
            result = model.generate(**generate_kwargs)
            elapsed = time.time() - started_at
            text = clean_text(result[0]["text"])
            payload = {"text": text}
            if command["response_format"] == "verbose_json":
                segments = []
                for segment in result[0].get("sentence_info", []):
                    segments.append({
                        "start": segment.get("start", 0) / 1000.0,
                        "end": segment.get("end", 0) / 1000.0,
                        "text": clean_text(segment.get("text", "")),
                        "speaker": segment.get("spk"),
                    })
                payload.update({
                    "segments": segments,
                    "language": command["language"] or "auto",
                    "duration": round(elapsed, 3),
                    "model": command["model"],
                })
            result_queue.put({
                "task_id": task_id,
                "status": "completed",
                "model": command["model"],
                "payload": payload,
            })
        except ValueError as exc:
            result_queue.put({
                "task_id": task_id,
                "status": "invalid_model",
                "error": str(exc),
            })
        except Exception as exc:
            result_queue.put({
                "task_id": task_id,
                "status": "failed",
                "error": str(exc),
            })


class InferenceProcess:
    def __init__(self, device):
        self.context = multiprocessing.get_context("spawn")
        self.device = device
        self.state_lock = threading.Lock()
        self.run_lock = threading.Lock()
        self.process = None
        self.command_queue = None
        self.result_queue = None
        self.generation = 0
        self.active_task_id = None
        self.loaded_model = None

    def configure(self, device):
        with self.state_lock:
            if self.process is not None:
                raise RuntimeError("cannot configure a running inference process")
            self.device = device

    def transcribe(self, audio_path, model, language, response_format):
        with self.run_lock:
            task_id, generation, command_queue, result_queue = self._prepare_task()
            command_queue.put({
                "action": "transcribe",
                "task_id": task_id,
                "audio_path": audio_path,
                "model": model,
                "language": language,
                "response_format": response_format,
            })
            try:
                return self._wait_for_result(task_id, generation, result_queue)
            finally:
                with self.state_lock:
                    if self.generation == generation and self.active_task_id == task_id:
                        self.active_task_id = None

    def preload(self, model):
        with self.run_lock:
            task_id, generation, command_queue, result_queue = self._prepare_task()
            command_queue.put({
                "action": "preload",
                "task_id": task_id,
                "model": model,
            })
            try:
                self._wait_for_result(task_id, generation, result_queue)
            finally:
                with self.state_lock:
                    if self.generation == generation and self.active_task_id == task_id:
                        self.active_task_id = None

    def cancel(self):
        with self.state_lock:
            if self.active_task_id is None or self.process is None:
                return False
            process = self.process
            self.process = None
            self.command_queue = None
            self.result_queue = None
            self.active_task_id = None
            self.loaded_model = None
            self.generation += 1
            self._terminate_process(process)
            return True

    def stop(self):
        with self.state_lock:
            process = self.process
            self.process = None
            self.command_queue = None
            self.result_queue = None
            self.active_task_id = None
            self.loaded_model = None
            self.generation += 1
            if process is not None:
                self._terminate_process(process)

    def loaded_models(self):
        with self.state_lock:
            if self.process is None or not self.process.is_alive() or self.loaded_model is None:
                return []
            return [self.loaded_model]

    def _prepare_task(self):
        with self.state_lock:
            if self.process is None or not self.process.is_alive():
                self._start_process()
            task_id = secrets.token_hex(16)
            self.active_task_id = task_id
            return task_id, self.generation, self.command_queue, self.result_queue

    def _start_process(self):
        self.command_queue = self.context.Queue()
        self.result_queue = self.context.Queue()
        self.process = self.context.Process(
            target=inference_worker,
            args=(self.command_queue, self.result_queue, self.device),
            daemon=True,
        )
        self.process.start()
        self.generation += 1
        self.loaded_model = None

    def _wait_for_result(self, task_id, generation, result_queue):
        while True:
            try:
                result = result_queue.get(timeout=0.2)
            except queue.Empty:
                with self.state_lock:
                    if self.generation != generation:
                        raise TranscriptionCancelled("transcription was cancelled")
                    if self.process is None or not self.process.is_alive():
                        raise RuntimeError("inference process exited unexpectedly")
                continue

            if result["task_id"] != task_id:
                continue
            if result["status"] == "model_loaded":
                with self.state_lock:
                    if self.generation != generation:
                        raise TranscriptionCancelled("transcription was cancelled")
                    self.loaded_model = result["model"]
                continue
            if result["status"] == "invalid_model":
                raise ValueError(result["error"])
            if result["status"] == "failed":
                raise RuntimeError(result["error"])
            with self.state_lock:
                if self.generation != generation:
                    raise TranscriptionCancelled("transcription was cancelled")
                self.loaded_model = result["model"]
            return result["payload"]

    @staticmethod
    def _terminate_process(process):
        if not process.is_alive():
            process.join()
            return
        process.terminate()
        process.join(timeout=10)
        if process.is_alive():
            process.kill()
            process.join()


inference_process = InferenceProcess(os.getenv("FUNASR_DEVICE", "cuda"))
atexit.register(inference_process.stop)


def clean_text(text: str) -> str:
    """Remove SenseVoice special tags from output."""
    return re.sub(r'<\|[^|]*\|>', '', text).strip()


@app.post("/v1/audio/transcriptions")
def transcribe(
    file: UploadFile = File(...),
    model: str = Form(default="sensevoice"),
    language: Optional[str] = Form(default=None),
    response_format: Optional[str] = Form(default="json"),
):
    """
    OpenAI-compatible audio transcription endpoint.

    Accepts the same parameters as OpenAI's /v1/audio/transcriptions:
    - file: Audio file (wav, mp3, flac, m4a, ogg, webm)
    - model: Model to use (sensevoice, paraformer, fun-asr-nano)
    - language: Optional language hint
    - response_format: json or verbose_json
    """
    # Validate model
    if model not in MODEL_CONFIGS:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{model}' not found. Available: {list(MODEL_CONFIGS.keys())}"
        )

    suffix = os.path.splitext(file.filename)[1] if file.filename else ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        result = inference_process.transcribe(
            tmp_path,
            model,
            language,
            response_format,
        )
        return JSONResponse(result)
    except TranscriptionCancelled as exc:
        raise HTTPException(status_code=499, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error(f"Transcription error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        os.unlink(tmp_path)


@app.post("/v1/cancel")
def cancel():
    if not inference_process.cancel():
        raise HTTPException(status_code=404, detail="no transcription is running")
    return {"status": "cancelled"}


@app.get("/v1/models")
async def list_models():
    """List available models (OpenAI-compatible)."""
    models = []
    for name in MODEL_CONFIGS:
        models.append({
            "id": name,
            "object": "model",
            "created": 1700000000,
            "owned_by": "funasr",
            "ready": name in inference_process.loaded_models(),
        })
    return JSONResponse({"object": "list", "data": models})


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "device": inference_process.device,
        "models_loaded": inference_process.loaded_models(),
        "models_available": list(MODEL_CONFIGS.keys()),
    }


def main():
    parser = argparse.ArgumentParser(description="FunASR OpenAI-Compatible API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8000, help="Bind port")
    parser.add_argument("--device", default="cuda", help="Device: cuda, cpu, mps")
    parser.add_argument("--model", default="sensevoice", help="Pre-load model at startup")
    args = parser.parse_args()

    inference_process.configure(args.device)
    inference_process.preload(args.model)

    logger.info(f"FunASR API server starting on http://{args.host}:{args.port}")
    logger.info(f"  Device: {inference_process.device}")
    logger.info(f"  Models: {list(MODEL_CONFIGS.keys())}")
    logger.info(f"  Docs:   http://{args.host}:{args.port}/docs")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
