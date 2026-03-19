#!/usr/bin/env python3
"""
PaddleOCR – Web-based OCR service powered by PaddlePaddle (v3 / paddlex API).
"""

import os
import time
import secrets
import logging
import platform
from typing import Optional, List
from pathlib import Path
from contextlib import asynccontextmanager

import cv2
import numpy as np
import base64
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from paddleocr import PaddleOCR

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────
def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None: return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

USE_GPU = _env_flag("USE_GPU", False)
OCR_ACCESS_TOKEN = os.getenv("OCR_ACCESS_TOKEN", "").strip()
AUTH_REQUIRED = bool(OCR_ACCESS_TOKEN)

# ── Application ──────────────────────────────────────────────────────────────
ocr_model: Optional[PaddleOCR] = None
system_info: dict = {}
model_runtime_device: str = "CPU"

def get_system_info() -> dict:
    """Detect hardware and return a summary dict."""
    info = {
        "platform": platform.platform(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "device": "CPU",
        "gpu_name": None,
        "gpu_count": 0,
        "cuda_version": None,
    }
    try:
        import paddle
        if paddle.is_compiled_with_cuda() and paddle.device.is_compiled_with_cuda():
            info["gpu_count"] = paddle.device.cuda.device_count()
            if info["gpu_count"] > 0:
                info["gpu_name"] = paddle.device.cuda.get_device_name(0)
            info["cuda_version"] = paddle.version.cuda()
            info["device"] = "CUDA (GPU)"
    except Exception:
        pass
    return info

@asynccontextmanager
async def lifespan(app: FastAPI):
    global ocr_model, model_runtime_device, system_info
    system_info = get_system_info()
    
    try:
        # Detect if hardware supports CUDA before trying to use it
        use_gpu = False
        if USE_GPU and system_info["device"].startswith("CUDA"):
            use_gpu = True
        
        # Initialize PaddleOCR
        # We explicitly disable mkldnn and ir_optim to avoid SIGILL on some CPUs
        ocr_model = PaddleOCR(
            use_textline_orientation=True, 
            lang="ch", 
            use_gpu=use_gpu,
            enable_mkldnn=False,
            ir_optim=False
        )
        model_runtime_device = "GPU" if use_gpu else "CPU"
        logger.info("PaddleOCR model initialized on: %s", model_runtime_device)
    except Exception as e:
        logger.error("PaddleOCR initialization failed: %s", e)
        ocr_model = None
    yield

app = FastAPI(title="PaddleOCR-API", lifespan=lifespan)

def _is_authorized_bearer(authorization: str | None) -> bool:
    if not AUTH_REQUIRED: return True
    if not authorization: return False
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer": return False
    return secrets.compare_digest(token, OCR_ACCESS_TOKEN)

@app.middleware("http")
async def access_token_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/") and not _is_authorized_bearer(request.headers.get("Authorization")):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)

@app.get("/", response_class=HTMLResponse)
def web_portal():
    html_path = Path(__file__).with_name("index.html")
    html = html_path.read_text(encoding="utf-8") if html_path.exists() else "<h1>PaddleOCR API</h1>"
    auth_flag_script = f"<script>const __OCR_AUTH_REQUIRED__ = {'true' if AUTH_REQUIRED else 'false'};</script>"
    return html.replace("</head>", f"{auth_flag_script}</head>", 1)

@app.get("/api/system")
def api_system():
    return {
        **system_info,
        "model_loaded": ocr_model is not None,
        "model_runtime_device": model_runtime_device,
        "use_gpu_config": USE_GPU,
        "auth_required": AUTH_REQUIRED,
    }

class Base64Request(BaseModel):
    base64: str

def _run_ocr_on_image(img: np.ndarray):
    if ocr_model is None: raise HTTPException(503, "OCR model is not loaded.")
    start_time = time.perf_counter()
    result = ocr_model.ocr(img, cls=True)
    duration = time.perf_counter() - start_time
    
    formatted_res = []
    if result and len(result) > 0 and result[0]:
        for line in result[0]:
            box, (text, score) = line
            formatted_res.append({"points": box, "text": text, "confidence": float(score)})
    
    logger.info("OCR OK: dur=%.3fs lines=%d device=%s", duration, len(formatted_res), model_runtime_device)
    return {"status": "ok", "duration_s": duration, "device": model_runtime_device, "results": formatted_res}

@app.post("/api/ocr")
async def do_ocr(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None: raise HTTPException(400, "Invalid image file.")
        
        return _run_ocr_on_image(img)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("OCR failed: %s", e, exc_info=True)
        raise HTTPException(500, f"OCR processing failed: {e}")

@app.post("/api/ocr/base64")
async def do_ocr_base64(req: Base64Request):
    try:
        b64_data = req.base64
        if b64_data.startswith("data:image"):
            if "," in b64_data:
                b64_data = b64_data.split(",", 1)[1]
            else:
                raise HTTPException(400, "Invalid base64 data URI.")
        
        contents = base64.b64decode(b64_data)
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None: raise HTTPException(400, "Invalid image base64.")
        
        return _run_ocr_on_image(img)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("OCR failed: %s", e, exc_info=True)
        raise HTTPException(500, f"OCR processing failed: {e}")

@app.get("/health")
def health_check():
    return {"status": "ok" if ocr_model is not None else "degraded"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
