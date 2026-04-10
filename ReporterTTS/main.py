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
import re
import uuid
import time
import json
import wave
import hashlib
import shutil
import logging
import secrets
import platform
import inspect
import subprocess
import threading
from typing import Optional, List
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, Header, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from indextts.infer import IndexTTS

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────
def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

GPU_MEMORY_FRACTION = float(os.getenv("GPU_MEMORY_FRACTION", "0.0"))
tts_lock = threading.Lock()


# ── Configuration ────────────────────────────────────────────────────────────
DATA_DIR = os.getenv("DATA_DIR", "/data")
VOICES_DIR = os.path.join(DATA_DIR, "voices")
OUTPUT_DIR = os.path.join(DATA_DIR, "output_audios")
CACHE_DIR = os.path.join(DATA_DIR, "tts_cache")
CACHE_ENABLED = _env_flag("TTS_CACHE_ENABLED", True)
CACHE_MAX_SIZE = max(1, int(os.getenv("TTS_CACHE_MAX_SIZE", "2000")))

_LRU_INDEX_PATH = os.path.join(CACHE_DIR, "lru_index.json")
_cache_lock = threading.Lock()

# ── OpenAI Compatibility Models ───────────────────────────────────────────────
class OpenAI_TTSRequest(BaseModel):
    model: str = "tts-1"
    input: str
    voice: str
    response_format: Optional[str] = "mp3"
    speed: Optional[float] = 1.0

# ── TTS Cache (LRU) ──────────────────────────────────────────────────────────
def _build_cache_key(
    voice: str,
    text: str,
    temperature: float,
    top_p: float,
    top_k: int,
    do_sample: bool,
    num_beams: int,
    repetition_penalty: float,
    length_penalty: float,
    max_mel_tokens: int,
    max_text_tokens_per_segment: int,
    fast_mode: bool,
    bucket_size: int,
    speech_rate: float,
) -> str:
    """Build a deterministic SHA-256 cache key from all generation parameters."""
    payload = json.dumps(
        {
            "voice": voice,
            "text": text,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "do_sample": do_sample,
            "num_beams": num_beams,
            "repetition_penalty": repetition_penalty,
            "length_penalty": length_penalty,
            "max_mel_tokens": max_mel_tokens,
            "max_text_tokens_per_segment": max_text_tokens_per_segment,
            "fast_mode": fast_mode,
            "bucket_size": bucket_size,
            "speech_rate": speech_rate,
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_lru_index() -> list[str]:
    """Load the persisted LRU key list (oldest first) from disk.
    Must be called while holding _cache_lock."""
    try:
        with open(_LRU_INDEX_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return []


def _save_lru_index(keys: list[str]) -> None:
    """Persist the LRU key list to disk.
    Must be called while holding _cache_lock."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = _LRU_INDEX_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(keys, f)
        os.replace(tmp, _LRU_INDEX_PATH)
    except Exception as e:
        logger.warning("Failed to persist LRU index: %s", e)


def _get_cached_audio(cache_key: str) -> Optional[str]:
    """Return the cached WAV path on a hit and promote it to MRU position."""
    if not CACHE_ENABLED:
        return None
    cached_path = os.path.join(CACHE_DIR, f"{cache_key}.wav")
    if not os.path.isfile(cached_path):
        return None
    # Promote to most-recently-used position
    with _cache_lock:
        keys = _load_lru_index()
        if cache_key in keys:
            keys.remove(cache_key)
        keys.append(cache_key)
        _save_lru_index(keys)
    return cached_path


def _store_in_cache(cache_key: str, source_path: str) -> Optional[str]:
    """Copy a generated WAV into the cache dir and enforce LRU size limit."""
    if not CACHE_ENABLED:
        return None
    os.makedirs(CACHE_DIR, exist_ok=True)
    cached_path = os.path.join(CACHE_DIR, f"{cache_key}.wav")
    try:
        shutil.copy2(source_path, cached_path)
    except Exception as e:
        logger.warning("Failed to store TTS cache entry %s: %s", cache_key[:12], e)
        return None

    with _cache_lock:
        keys = _load_lru_index()
        # Remove if already present (overwrite scenario)
        if cache_key in keys:
            keys.remove(cache_key)
        keys.append(cache_key)
        # Evict oldest entries until within size limit
        while len(keys) > CACHE_MAX_SIZE:
            oldest = keys.pop(0)
            old_file = os.path.join(CACHE_DIR, f"{oldest}.wav")
            try:
                os.remove(old_file)
                logger.info("LRU evicted cache entry: %s", oldest[:12])
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.warning("Failed to evict cache file %s: %s", oldest[:12], e)
        _save_lru_index(keys)

    return cached_path


def _get_cache_stats() -> dict:
    """Return cache directory statistics."""
    if not os.path.isdir(CACHE_DIR):
        return {
            "enabled": CACHE_ENABLED,
            "max_size": CACHE_MAX_SIZE,
            "total_files": 0,
            "total_size_mb": 0.0,
        }
    files = list(Path(CACHE_DIR).glob("*.wav"))
    total_size = sum(f.stat().st_size for f in files)
    return {
        "enabled": CACHE_ENABLED,
        "max_size": CACHE_MAX_SIZE,
        "total_files": len(files),
        "total_size_mb": round(total_size / (1024 * 1024), 2),
    }


LOW_VRAM_MODE = _env_flag("LOW_VRAM_MODE", False)
TTS_ACCESS_TOKEN = os.getenv("TTS_ACCESS_TOKEN", "").strip()
AUTH_REQUIRED = bool(TTS_ACCESS_TOKEN)

# ── Default generation parameters (IndexTTS best-practice values) ────────────
# These match the defaults used in IndexTTS's own WebUI / source code.
DEFAULTS = {
    "temperature": 1.0,       # Sampling temperature. Higher → more diverse but less stable.
    "top_p": 0.8,             # Nucleus sampling probability mass.
    "top_k": 30,              # Top-K sampling. 0 = disabled.
    "do_sample": True,        # Enable stochastic sampling. False = greedy / beam only.
    "num_beams": 2,           # Beam search width. 1 = no beam search.
    "repetition_penalty": 10.0,  # Penalise repeated mel-tokens strongly to avoid loops.
    "length_penalty": 0.0,    # Encourage longer (>0) or shorter (<0) sequences.
    "max_mel_tokens": 600,    # Hard cap on generated mel tokens per segment.
    "max_text_tokens_per_segment": 120,  # Text segmentation granularity (tokens).
    "fast_mode": True,        # Use batched-bucket fast inference (2-10× speed-up).
    "bucket_size": 1,         # Max batch size per bucket in fast mode.
    "speech_rate": 1.2,       # Output speaking rate multiplier (0.5–2.0).
}

if LOW_VRAM_MODE:
    DEFAULTS.update(
        {
            "do_sample": False,
            "num_beams": 1,
            "max_mel_tokens": 360,
            "max_text_tokens_per_segment": 80,
            "fast_mode": False,
            "bucket_size": 1,
        }
    )


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
            if GPU_MEMORY_FRACTION > 0.0 and GPU_MEMORY_FRACTION <= 1.0:
                torch.cuda.set_per_process_memory_fraction(GPU_MEMORY_FRACTION)
            info["device"] = "CUDA (GPU)"
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["gpu_count"] = torch.cuda.device_count()
            info["cuda_version"] = torch.version.cuda
            props = torch.cuda.get_device_properties(0)
            total = getattr(props, "total_memory", None)
            if total is None:
                total = getattr(props, "total_mem", 0)
            info["gpu_memory"] = f"{total / (1024**3):.1f} GB"
    except ImportError:
        info["device"] = "CPU (PyTorch unavailable)"
    return info


def sanitize_indextts_config(cfg_path: str) -> list[str]:
    """Remove unsupported GPT config keys for current installed IndexTTS code."""
    try:
        import yaml
    except Exception:
        logger.warning("PyYAML is unavailable, cannot sanitize config: %s", cfg_path)
        return []

    if not os.path.exists(cfg_path):
        return []

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    gpt_cfg = cfg.get("gpt")
    if not isinstance(gpt_cfg, dict):
        return []

    try:
        from indextts.gpt.model import UnifiedVoice
    except Exception:
        logger.warning("Cannot import indextts.gpt.model.UnifiedVoice, skip config sanitize.")
        return []

    supported_args = set(inspect.signature(UnifiedVoice.__init__).parameters)
    supported_args.discard("self")

    removed = [k for k in list(gpt_cfg.keys()) if k not in supported_args]
    if not removed:
        return []

    for key in removed:
        gpt_cfg.pop(key, None)

    backup_path = f"{cfg_path}.bak"
    if not os.path.exists(backup_path):
        shutil.copyfile(cfg_path, backup_path)

    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)

    return removed


def _build_atempo_filter(rate: float) -> str:
    """Build ffmpeg atempo chain for arbitrary rate."""
    filters: list[str] = []
    remain = rate
    while remain > 2.0:
        filters.append("atempo=2.0")
        remain /= 2.0
    while remain < 0.5:
        filters.append("atempo=0.5")
        remain /= 0.5
    filters.append(f"atempo={remain:.4f}")
    return ",".join(filters)


def apply_speech_rate_inplace(wav_path: str, speech_rate: float) -> None:
    """Adjust output WAV speaking speed in place using ffmpeg."""
    if abs(speech_rate - 1.0) < 1e-3:
        return

    tmp_path = f"{wav_path}.rate.wav"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", wav_path,
        "-filter:a", _build_atempo_filter(speech_rate),
        tmp_path,
    ]
    subprocess.run(cmd, check=True)
    os.replace(tmp_path, wav_path)


def convert_audio(input_path: str, output_path: str, format: str):
    """Convert audio file to requested format using ffmpeg."""
    # OpenAI: mp3, opus, aac, flac, wav, pcm
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", input_path]
    if format == "mp3":
        cmd.extend(["-codec:a", "libmp3lame", "-qscale:a", "2"])
    elif format == "opus":
        cmd.extend(["-codec:a", "libopus"])
    elif format == "aac":
        cmd.extend(["-codec:a", "aac"])
    elif format == "flac":
        cmd.extend(["-codec:a", "flac"])
    elif format == "wav":
        pass  # Already wav
    elif format == "pcm":
        cmd.extend(["-f", "s16le", "-acodec", "pcm_s16le"])
    else:
        # Fallback to simple conversion based on extension
        pass

    cmd.append(output_path)
    subprocess.run(cmd, check=True)


def cleanup_output_audios():
    """Delete files older than 1 hour in OUTPUT_DIR to prevent disk leakage."""
    try:
        now = time.time()
        for f in Path(OUTPUT_DIR).iterdir():
            if f.is_file() and (now - f.stat().st_mtime > 3600):
                f.unlink()
    except Exception as e:
        logger.error("Cleanup of %s failed: %s", OUTPUT_DIR, e)


def _is_cuda_oom(error: Exception) -> bool:
    message = str(error).lower()
    return "out of memory" in message and "cuda" in message


# ── Text chunking for robust long-text TTS ────────────────────────────────────
# Split on Chinese/English sentence-ending punctuation.
# The lookbehind keeps the punctuation attached to the preceding sentence.
_SENT_BOUNDARY_RE = re.compile(
    r'(?<=[。！？!?；;])\s*'   # after Chinese / English sentence-enders
    r'|(?<=\.)\s+'              # after English period followed by whitespace
    r'|\n+'                     # on newlines
)


def _split_text_into_chunks(text: str, max_chars: int = 120) -> list[str]:
    """
    Split *text* at natural sentence boundaries for chunked TTS generation.
    Punctuation stays attached to the preceding sentence so prosody is preserved.
    Short adjacent fragments are merged up to *max_chars* to avoid over-splitting.
    """
    raw_parts = _SENT_BOUNDARY_RE.split(text)
    chunks: list[str] = []
    current = ""
    for part in raw_parts:
        part = part.strip()
        if not part:
            continue
        if not current:
            current = part
        elif len(current) + len(part) <= max_chars:
            # Merge short fragments into one chunk
            current += part
        else:
            chunks.append(current)
            current = part
    if current:
        chunks.append(current)
    return chunks


def _concat_wav_files(wav_paths: list[str], output_path: str) -> None:
    """
    Concatenate one or more WAV files into *output_path* using the stdlib wave
    module (no ffmpeg dependency, no re-encoding).
    All input files must share the same sample rate / channels / width.
    """
    if not wav_paths:
        raise ValueError("No WAV files to concatenate.")
    if len(wav_paths) == 1:
        shutil.copy2(wav_paths[0], output_path)
        return

    with wave.open(wav_paths[0], "rb") as first:
        params = first.getparams()

    with wave.open(output_path, "wb") as out_wav:
        out_wav.setparams(params)
        for path in wav_paths:
            with wave.open(path, "rb") as w:
                out_wav.writeframes(w.readframes(w.getnframes()))


# ── Application ──────────────────────────────────────────────────────────────
tts_model: Optional[IndexTTS] = None
system_info: dict = {}
model_runtime_device: Optional[str] = None
cuda_fallback_to_cpu: bool = False
model_init_error: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global tts_model, system_info, model_runtime_device, cuda_fallback_to_cpu, model_init_error

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(VOICES_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    system_info = get_system_info()
    logger.info("System info: %s", system_info)
    model_runtime_device = None
    cuda_fallback_to_cpu = False
    model_init_error = None

    try:
        model_dir = "checkpoints"
        cfg_path = "checkpoints/config.yaml"
        if not os.path.exists(model_dir) or not os.path.exists(cfg_path):
            raise FileNotFoundError("Model directory or config file not found.")

        def _init_tts(init_kwargs: dict) -> IndexTTS:
            try:
                return IndexTTS(**init_kwargs)
            except TypeError as e:
                if "unexpected keyword argument" in str(e):
                    removed_keys = sanitize_indextts_config(cfg_path)
                    if removed_keys:
                        logger.warning(
                            "Patched incompatible config keys: %s; retrying model init.",
                            ", ".join(removed_keys),
                        )
                        return IndexTTS(**init_kwargs)
                raise

        def _is_cuda_init_error(error: Exception) -> bool:
            msg = str(error).lower()
            tokens = ["cuda", "cudnn", "cublas", "nvml", "nvidia", "driver"]
            return any(token in msg for token in tokens)

        base_kwargs = {
            "model_dir": model_dir,
            "cfg_path": cfg_path,
            "use_cuda_kernel": False if LOW_VRAM_MODE else None,
        }

        if system_info.get("device", "").startswith("CUDA"):
            gpu_kwargs = {**base_kwargs, "device": "cuda", "use_fp16": True}
            try:
                if GPU_MEMORY_FRACTION > 0.0 and GPU_MEMORY_FRACTION <= 1.0:
                    import torch
                    torch.cuda.set_per_process_memory_fraction(GPU_MEMORY_FRACTION)
                tts_model = _init_tts(gpu_kwargs)
                model_runtime_device = "cuda"
            except Exception as cuda_error:
                if not _is_cuda_init_error(cuda_error):
                    raise
                logger.warning("CUDA initialization failed, fallback to CPU. reason=%s", cuda_error)
                cpu_kwargs = {**base_kwargs, "device": "cpu", "use_fp16": False, "use_cuda_kernel": False}
                tts_model = _init_tts(cpu_kwargs)
                model_runtime_device = "cpu"
                cuda_fallback_to_cpu = True
                model_init_error = str(cuda_error)
        else:
            cpu_kwargs = {**base_kwargs, "device": "cpu", "use_fp16": False, "use_cuda_kernel": False}
            tts_model = _init_tts(cpu_kwargs)
            model_runtime_device = "cpu"

        logger.info("IndexTTS model initialized successfully!")
        logger.info(
            "  device=%s  fp16=%s  cuda_kernel=%s",
            tts_model.device, tts_model.use_fp16, tts_model.use_cuda_kernel,
        )
    except Exception as e:
        logger.error("IndexTTS model initialization failed: %s", e)
        model_init_error = str(e)
        tts_model = None

    yield


app = FastAPI(title="ReporterTTS", lifespan=lifespan)


def _is_authorized_bearer(authorization: str | None) -> bool:
    if not AUTH_REQUIRED:
        return True
    if not authorization:
        return False
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    return secrets.compare_digest(token, TTS_ACCESS_TOKEN)


@app.middleware("http")
async def access_token_middleware(request: Request, call_next):
    path = request.url.path
    is_protected_call = path.startswith("/api/") or path.startswith("/v1/")
    if is_protected_call and not _is_authorized_bearer(request.headers.get("Authorization")):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


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
    html = _load_html()
    auth_flag_script = (
        "<script>const __TTS_AUTH_REQUIRED__ = "
        f"{'true' if AUTH_REQUIRED else 'false'};"
        "</script>"
    )
    if "</head>" in html:
        html = html.replace("</head>", f"{auth_flag_script}</head>", 1)
    return html


# ── API: System Info ─────────────────────────────────────────────────────────
@app.get("/api/system")
def api_system():
    """Return system / hardware information and default generation parameters."""
    return {
        **system_info,
        "model_loaded": tts_model is not None,
        "model_runtime_device": model_runtime_device,
        "cuda_fallback_to_cpu": cuda_fallback_to_cpu,
        "model_init_error": model_init_error,
        "low_vram_mode": LOW_VRAM_MODE,
        "auth_required": AUTH_REQUIRED,
        "defaults": DEFAULTS,
        "cache": _get_cache_stats(),
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
    safe_name = "".join(c for c in name if c.isalnum() or c in "-_").strip()
    if not safe_name:
        raise HTTPException(400, "Invalid voice name (use alphanumeric, dash, underscore).")
    path = Path(VOICES_DIR) / f"{safe_name}.wav"
    if not path.exists():
        raise HTTPException(404, "Voice not found.")
    path.unlink()
    logger.info("Voice deleted: %s", safe_name)
    return {"status": "ok"}


# ── API: Text-to-Speech (full parameter exposure) ───────────────────────────
def _perform_tts(
    voice: str,
    text: str,
    temperature: float = DEFAULTS["temperature"],
    top_p: float = DEFAULTS["top_p"],
    top_k: int = DEFAULTS["top_k"],
    do_sample: bool = DEFAULTS["do_sample"],
    num_beams: int = DEFAULTS["num_beams"],
    repetition_penalty: float = DEFAULTS["repetition_penalty"],
    length_penalty: float = DEFAULTS["length_penalty"],
    max_mel_tokens: int = DEFAULTS["max_mel_tokens"],
    max_text_tokens_per_segment: int = DEFAULTS["max_text_tokens_per_segment"],
    fast_mode: bool = DEFAULTS["fast_mode"],
    bucket_size: int = DEFAULTS["bucket_size"],
    speech_rate: float = DEFAULTS["speech_rate"],
) -> tuple[str, bool]:
    """Core TTS generation logic. Returns (path_to_WAV, cache_hit)."""
    if tts_model is None:
        raise HTTPException(503, "TTS model is not loaded.")

    safe_voice = "".join(c for c in voice if c.isalnum() or c in "-_").strip()
    if not safe_voice:
        raise HTTPException(400, "Invalid voice name (use alphanumeric, dash, underscore).")

    voice_path = Path(VOICES_DIR) / f"{safe_voice}.wav"
    if not voice_path.exists():
        raise HTTPException(404, f"Voice '{safe_voice}' not found.")

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
    speech_rate = max(0.5, min(2.0, speech_rate))

    # ── Cache lookup ─────────────────────────────────────────────────────
    cache_key = _build_cache_key(
        safe_voice, text, temperature, top_p, top_k, do_sample, num_beams,
        repetition_penalty, length_penalty, max_mel_tokens,
        max_text_tokens_per_segment, fast_mode, bucket_size, speech_rate,
    )
    cached = _get_cached_audio(cache_key)
    if cached is not None:
        logger.info(
            "TTS CACHE HIT: voice=%s chars=%d key=%s",
            safe_voice, len(text), cache_key[:12],
        )
        return cached, True

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

    # ── Helper: infer a single text chunk → wav_path ─────────────────────
    def _run_infer(chunk_text: str, dest_path: str, use_fast: bool, seg_tokens: int,
                   bucket: int, kwargs: dict) -> None:
        if use_fast:
            tts_model.infer_fast(
                str(voice_path), chunk_text, dest_path,
                verbose=False,
                max_text_tokens_per_segment=seg_tokens,
                segments_bucket_max_size=bucket,
                **kwargs,
            )
        else:
            tts_model.infer(
                str(voice_path), chunk_text, dest_path,
                verbose=False,
                max_text_tokens_per_segment=seg_tokens,
                **kwargs,
            )

    def _infer_with_oom_fallback(chunk_text: str, dest_path: str) -> None:
        """Run inference for one chunk, falling back to low-VRAM settings on OOM."""
        try:
            with tts_lock:
                _run_infer(chunk_text, dest_path, fast_mode, max_text_tokens_per_segment,
                           bucket_size, generation_kwargs)
        except Exception as infer_error:
            if not _is_cuda_oom(infer_error):
                raise
            logger.warning("CUDA OOM detected, retrying with low-VRAM fallback settings.")
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            fallback_kwargs = dict(generation_kwargs)
            fallback_kwargs.update({
                "do_sample": False,
                "num_beams": 1,
                "max_mel_tokens": min(max_mel_tokens, 280),
            })
            with tts_lock:
                _run_infer(chunk_text, dest_path, False,
                           min(max_text_tokens_per_segment, 64), 1, fallback_kwargs)

    try:
        # ── Split text into sentence-level chunks ────────────────────────
        chunks = _split_text_into_chunks(text)
        logger.info(
            "TTS split: voice=%s total_chars=%d chunks=%d",
            safe_voice, len(text), len(chunks),
        )

        start = time.perf_counter()

        if len(chunks) <= 1:
            # Fast path: single chunk, write directly to output_path
            _infer_with_oom_fallback(chunks[0] if chunks else text, output_path)
        else:
            # Multi-chunk path: generate each chunk to a temp file, then concat
            chunk_paths: list[str] = []
            try:
                for i, chunk in enumerate(chunks):
                    chunk_path = os.path.join(OUTPUT_DIR, f"{uuid.uuid4()}.chunk{i}.wav")
                    _infer_with_oom_fallback(chunk, chunk_path)
                    if not os.path.exists(chunk_path):
                        raise RuntimeError(f"Chunk {i} output file was not created: {chunk!r}")
                    chunk_paths.append(chunk_path)
                    logger.info(
                        "TTS chunk %d/%d OK: chars=%d file=%s",
                        i + 1, len(chunks), len(chunk), os.path.basename(chunk_path),
                    )
                _concat_wav_files(chunk_paths, output_path)
            finally:
                # Always clean up temp chunk files
                for p in chunk_paths:
                    try:
                        os.remove(p)
                    except FileNotFoundError:
                        pass

        duration = time.perf_counter() - start

        # speech_rate applied once on the final concatenated file
        apply_speech_rate_inplace(output_path, speech_rate)

        if not os.path.exists(output_path):
            raise RuntimeError("Output file was not created.")

        file_size = os.path.getsize(output_path)
        mode_label = "fast" if fast_mode else "standard"
        logger.info(
            "TTS OK [%s]: voice=%s chars=%d chunks=%d dur=%.1fs size=%d "
            "temp=%.2f top_p=%.2f top_k=%s beams=%d rep_pen=%.1f mel_tok=%d seg_tok=%d rate=%.2f",
            mode_label, safe_voice, len(text), len(chunks), duration, file_size,
            temperature, top_p, top_k, num_beams,
            repetition_penalty, max_mel_tokens, max_text_tokens_per_segment, speech_rate,
        )

        # ── Store result in cache ────────────────────────────────────────
        _store_in_cache(cache_key, output_path)

        return output_path, False
    except HTTPException:
        raise
    except Exception as e:
        logger.error("TTS failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Speech generation failed: {e}")


@app.post("/api/tts")
def api_tts(
    background_tasks: BackgroundTasks,
    # ── Required fields ──
    voice: str = Form(...),
    text: str = Form(...),
    # ... rest of params ...
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
    speech_rate: float = Form(default=DEFAULTS["speech_rate"]),
):
    """
    Generate speech from text using the selected voice and generation parameters.
    Returns a WAV audio file.
    """
    background_tasks.add_task(cleanup_output_audios)
    output_path, cache_hit = _perform_tts(
        voice, text, temperature, top_p, top_k, do_sample, num_beams,
        repetition_penalty, length_penalty, max_mel_tokens,
        max_text_tokens_per_segment, fast_mode, bucket_size, speech_rate,
    )
    return FileResponse(
        output_path,
        media_type="audio/wav",
        filename=f"tts_{voice}.wav",
        headers={"X-TTS-Cache": "hit" if cache_hit else "miss"},
    )


# ── API: OpenAI Compatible Speech ─────────────────────────────────────────────
@app.post("/v1/audio/speech")
async def openai_speech(request: OpenAI_TTSRequest, background_tasks: BackgroundTasks):
    """
    OpenAI-compatible TTS endpoint.
    See: https://platform.openai.com/docs/api-reference/audio/createSpeech
    """
    background_tasks.add_task(cleanup_output_audios)
    # 1. Voice mapping
    available_voices = [f.stem for f in Path(VOICES_DIR).glob("*.wav")]
    if not available_voices:
        raise HTTPException(503, "No voice profiles available on this server.")

    selected_voice = request.voice
    # If the requested voice doesn't exist, try case-insensitive or fallback
    if selected_voice not in available_voices:
        for v in available_voices:
            if v.lower() == selected_voice.lower():
                selected_voice = v
                break
        else:
            selected_voice = available_voices[0]
            logger.info("OpenAI API: Requested voice '%s' not found, using fallback: %s", request.voice, selected_voice)

    # 2. Perform TTS (using defaults for parameters not in OpenAI spec)
    wav_path, _cache_hit = _perform_tts(
        voice=selected_voice,
        text=request.input,
        speech_rate=request.speed or 1.0,
    )

    # 3. Format conversion
    fmt = (request.response_format or "mp3").lower()
    if fmt == "wav":
        return FileResponse(wav_path, media_type="audio/wav")

    # For other formats, convert using ffmpeg
    ext = fmt if fmt != "pcm" else "raw"
    converted_path = f"{wav_path}.{ext}"
    try:
        convert_audio(wav_path, converted_path, fmt)
    except Exception as e:
        logger.error("Format conversion failed: %s", e)
        raise HTTPException(500, f"Audio conversion to {fmt} failed.")

    # MIME types
    mime_map = {
        "mp3": "audio/mpeg",
        "opus": "audio/opus",
        "aac": "audio/aac",
        "flac": "audio/flac",
        "pcm": "audio/l16",
    }
    media_type = mime_map.get(fmt, f"audio/{fmt}")

    return FileResponse(converted_path, media_type=media_type)


# ── API: Cache Management ────────────────────────────────────────────────────
@app.get("/api/cache")
def api_cache_stats():
    """Return TTS cache statistics."""
    return _get_cache_stats()


@app.delete("/api/cache")
def api_cache_clear():
    """Clear all cached TTS audio files and reset the LRU index."""
    if not os.path.isdir(CACHE_DIR):
        return {"status": "ok", "deleted": 0}
    files = list(Path(CACHE_DIR).glob("*.wav"))
    count = 0
    for f in files:
        try:
            f.unlink()
            count += 1
        except Exception as e:
            logger.warning("Failed to delete cache file %s: %s", f.name, e)
    with _cache_lock:
        try:
            os.remove(_LRU_INDEX_PATH)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning("Failed to delete LRU index: %s", e)
    logger.info("Cache cleared: %d files deleted.", count)
    return {"status": "ok", "deleted": count}


# ── API: Health ──────────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok" if tts_model is not None else "degraded"}
