#!/usr/bin/env python3
"""
ReporterTTS – Web-based Text-to-Speech service powered by IndexTTS.

Features:
  • Web portal for voice management and TTS generation
  • REST API for programmatic access
  • GPU / CPU auto-detection with system info display
"""

import os
import uuid
import time
import shutil
import logging
import platform
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from indextts.infer import IndexTTS

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────
OUTPUT_DIR = "output_audios"
VOICES_DIR = os.getenv("VOICES_DIR", "voices")


# ── System Information ───────────────────────────────────────────────────────
def get_system_info() -> dict:
    """Detect hardware and return a summary dict."""
    info: dict = {
        "platform": platform.platform(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "device": "CPU",
        "gpu_name": None,
        "gpu_count": 0,
        "cuda_version": None,
        "gpu_memory": None,
    }
    try:
        import torch

        if torch.cuda.is_available():
            info["device"] = "CUDA (GPU)"
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["gpu_count"] = torch.cuda.device_count()
            info["cuda_version"] = torch.version.cuda
            total = torch.cuda.get_device_properties(0).total_mem
            info["gpu_memory"] = f"{total / (1024**3):.1f} GB"
    except ImportError:
        info["device"] = "CPU (PyTorch unavailable)"
    return info


# ── Application ──────────────────────────────────────────────────────────────
tts_model = None
system_info: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global tts_model, system_info

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(VOICES_DIR, exist_ok=True)

    system_info = get_system_info()
    logger.info("System info: %s", system_info)

    try:
        model_dir = "checkpoints"
        cfg_path = "checkpoints/config.yaml"
        if not os.path.exists(model_dir) or not os.path.exists(cfg_path):
            raise FileNotFoundError("Model directory or config file not found.")
        tts_model = IndexTTS(model_dir=model_dir, cfg_path=cfg_path)
        logger.info("IndexTTS model initialized successfully!")
    except Exception as e:
        logger.error("IndexTTS model initialization failed: %s", e)
        tts_model = None

    yield


app = FastAPI(title="ReporterTTS", lifespan=lifespan)


# ── Serve Web Portal ─────────────────────────────────────────────────────────
_html_cache: str | None = None


def _load_html() -> str:
    global _html_cache
    if _html_cache is None:
        html_path = Path(__file__).with_name("index.html")
        _html_cache = html_path.read_text(encoding="utf-8")
    return _html_cache


@app.get("/", response_class=HTMLResponse)
def web_portal():
    """Serve the single-page web portal."""
    return _load_html()


# ── API: System Info ─────────────────────────────────────────────────────────
@app.get("/api/system")
def api_system():
    """Return system / hardware information."""
    return {**system_info, "model_loaded": tts_model is not None}


# ── API: Voice Management ───────────────────────────────────────────────────
@app.get("/api/voices")
def list_voices():
    """List all available voice profiles."""
    voices = []
    for f in sorted(Path(VOICES_DIR).glob("*.wav")):
        voices.append(
            {
                "name": f.stem,
                "filename": f.name,
                "size_kb": round(f.stat().st_size / 1024, 1),
            }
        )
    return voices


@app.post("/api/voices")
async def upload_voice(name: str = Form(...), file: UploadFile = File(...)):
    """Upload a new voice profile (.wav file)."""
    if not file.filename or not file.filename.lower().endswith(".wav"):
        raise HTTPException(400, "Only .wav files are supported.")

    safe_name = "".join(c for c in name if c.isalnum() or c in "-_").strip()
    if not safe_name:
        raise HTTPException(400, "Invalid voice name (use alphanumeric, dash, underscore).")

    dest = Path(VOICES_DIR) / f"{safe_name}.wav"
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)

    logger.info("Voice uploaded: %s → %s", safe_name, dest)
    return {"status": "ok", "name": safe_name}


@app.delete("/api/voices/{name}")
def delete_voice(name: str):
    """Delete a voice profile by name."""
    path = Path(VOICES_DIR) / f"{name}.wav"
    if not path.exists():
        raise HTTPException(404, "Voice not found.")
    path.unlink()
    logger.info("Voice deleted: %s", name)
    return {"status": "ok"}


# ── API: Text-to-Speech ─────────────────────────────────────────────────────
@app.post("/api/tts")
def generate_speech(voice: str = Form(...), text: str = Form(...)):
    """Generate speech from text using the selected voice profile."""
    if tts_model is None:
        raise HTTPException(503, "TTS model is not loaded.")

    voice_path = Path(VOICES_DIR) / f"{voice}.wav"
    if not voice_path.exists():
        raise HTTPException(404, f"Voice '{voice}' not found.")

    text = text.strip()
    if not text:
        raise HTTPException(400, "Text cannot be empty.")

    unique_filename = f"{uuid.uuid4()}.wav"
    output_path = os.path.join(OUTPUT_DIR, unique_filename)

    try:
        start = time.perf_counter()
        tts_model.infer(str(voice_path), text, output_path)
        duration = time.perf_counter() - start

        if not os.path.exists(output_path):
            raise RuntimeError("Output file was not created.")

        file_size = os.path.getsize(output_path)
        logger.info(
            "TTS OK: voice=%s len=%d dur=%.1fs size=%d",
            voice, len(text), duration, file_size,
        )
        return FileResponse(
            output_path, media_type="audio/wav", filename=f"tts_{voice}.wav"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("TTS failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Speech generation failed: {e}")


# ── API: Health ──────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok" if tts_model is not None else "degraded"}
