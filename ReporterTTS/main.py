#!/usr/bin/env python3
"""
ReporterTTS – Web-based Text-to-Speech service powered by IndexTTS.

Features:
  • Web portal with advanced parameter tuning for TTS generation
  • Voice profile management (upload / list / delete)
  • GPU / CPU auto-detection with system info display
  • Both standard and fast (batched-bucket) inference modes
  • Full GPT-2 sampling parameter exposure
"""

import os
import uuid
import time
import shutil
import logging
import platform
from typing import Optional
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from indextts.infer import IndexTTS

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────
DATA_DIR = os.getenv("DATA_DIR", "/data")
VOICES_DIR = os.path.join(DATA_DIR, "voices")
OUTPUT_DIR = os.path.join(DATA_DIR, "output_audios")

# ── Default generation parameters (IndexTTS best-practice values) ────────────
# These match the defaults used in IndexTTS's own WebUI / source code.
DEFAULTS = {
    "temperature": 1.0,       # Sampling temperature. Higher → more diverse but less stable.
    "top_p": 0.8,             # Nucleus sampling probability mass.
    "top_k": 30,              # Top-K sampling. 0 = disabled.
    "do_sample": True,        # Enable stochastic sampling. False = greedy / beam only.
    "num_beams": 3,           # Beam search width. 1 = no beam search.
    "repetition_penalty": 10.0,  # Penalise repeated mel-tokens strongly to avoid loops.
    "length_penalty": 0.0,    # Encourage longer (>0) or shorter (<0) sequences.
    "max_mel_tokens": 600,    # Hard cap on generated mel tokens per segment.
    "max_text_tokens_per_segment": 120,  # Text segmentation granularity (tokens).
    "fast_mode": True,        # Use batched-bucket fast inference (2-10× speed-up).
    "bucket_size": 4,         # Max batch size per bucket in fast mode.
}


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
tts_model: Optional[IndexTTS] = None
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
        logger.info(
            "  device=%s  fp16=%s  cuda_kernel=%s",
            tts_model.device, tts_model.use_fp16, tts_model.use_cuda_kernel,
        )
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
    """Return system / hardware information and default generation parameters."""
    return {
        **system_info,
        "model_loaded": tts_model is not None,
        "defaults": DEFAULTS,
    }


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


# ── API: Text-to-Speech (full parameter exposure) ───────────────────────────
@app.post("/api/tts")
def generate_speech(
    # ── Required fields ──
    voice: str = Form(...),
    text: str = Form(...),
    # ── GPT-2 sampling parameters ──
    temperature: float = Form(default=DEFAULTS["temperature"]),
    top_p: float = Form(default=DEFAULTS["top_p"]),
    top_k: int = Form(default=DEFAULTS["top_k"]),
    do_sample: bool = Form(default=DEFAULTS["do_sample"]),
    num_beams: int = Form(default=DEFAULTS["num_beams"]),
    repetition_penalty: float = Form(default=DEFAULTS["repetition_penalty"]),
    length_penalty: float = Form(default=DEFAULTS["length_penalty"]),
    max_mel_tokens: int = Form(default=DEFAULTS["max_mel_tokens"]),
    # ── Text segmentation ──
    max_text_tokens_per_segment: int = Form(default=DEFAULTS["max_text_tokens_per_segment"]),
    # ── Inference mode ──
    fast_mode: bool = Form(default=DEFAULTS["fast_mode"]),
    bucket_size: int = Form(default=DEFAULTS["bucket_size"]),
):
    """
    Generate speech from text using the selected voice and generation parameters.

    Returns a WAV audio file. All parameters except ``voice`` and ``text``
    are optional and fall back to sensible defaults derived from IndexTTS
    best-practice values.
    """
    if tts_model is None:
        raise HTTPException(503, "TTS model is not loaded.")

    voice_path = Path(VOICES_DIR) / f"{voice}.wav"
    if not voice_path.exists():
        raise HTTPException(404, f"Voice '{voice}' not found.")

    text = text.strip()
    if not text:
        raise HTTPException(400, "Text cannot be empty.")

    # ── Clamp parameters to safe ranges ──────────────────────────────────
    temperature = max(0.05, min(2.0, temperature))
    top_p = max(0.0, min(1.0, top_p))
    top_k = max(0, min(100, top_k))
    num_beams = max(1, min(10, num_beams))
    repetition_penalty = max(0.1, min(20.0, repetition_penalty))
    length_penalty = max(-2.0, min(2.0, length_penalty))
    max_mel_tokens = max(50, min(2000, max_mel_tokens))
    max_text_tokens_per_segment = max(20, min(300, max_text_tokens_per_segment))
    bucket_size = max(1, min(8, bucket_size))

    generation_kwargs = {
        "do_sample": do_sample,
        "top_p": top_p,
        "top_k": top_k if top_k > 0 else None,
        "temperature": temperature,
        "length_penalty": length_penalty,
        "num_beams": num_beams,
        "repetition_penalty": repetition_penalty,
        "max_mel_tokens": max_mel_tokens,
    }

    unique_filename = f"{uuid.uuid4()}.wav"
    output_path = os.path.join(OUTPUT_DIR, unique_filename)

    try:
        start = time.perf_counter()

        if fast_mode:
            tts_model.infer_fast(
                str(voice_path), text, output_path,
                verbose=False,
                max_text_tokens_per_segment=max_text_tokens_per_segment,
                segments_bucket_max_size=bucket_size,
                **generation_kwargs,
            )
        else:
            tts_model.infer(
                str(voice_path), text, output_path,
                verbose=False,
                max_text_tokens_per_segment=max_text_tokens_per_segment,
                **generation_kwargs,
            )

        duration = time.perf_counter() - start

        if not os.path.exists(output_path):
            raise RuntimeError("Output file was not created.")

        file_size = os.path.getsize(output_path)
        mode_label = "fast" if fast_mode else "standard"
        logger.info(
            "TTS OK [%s]: voice=%s chars=%d dur=%.1fs size=%d "
            "temp=%.2f top_p=%.2f top_k=%s beams=%d rep_pen=%.1f mel_tok=%d seg_tok=%d",
            mode_label, voice, len(text), duration, file_size,
            temperature, top_p, top_k, num_beams,
            repetition_penalty, max_mel_tokens, max_text_tokens_per_segment,
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
