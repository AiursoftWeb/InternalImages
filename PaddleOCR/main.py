#!/usr/bin/env python3
"""
PaddleOCR – Web-based OCR service powered by PaddlePaddle.
"""

import os
import time
import secrets
import logging
import platform
from typing import Optional
from pathlib import Path
from contextlib import asynccontextmanager

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from paddleocr import PaddleOCR

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────
OCR_ACCESS_TOKEN = os.getenv("OCR_ACCESS_TOKEN", "").strip()
AUTH_REQUIRED = bool(OCR_ACCESS_TOKEN)

# ── Application ──────────────────────────────────────────────────────────────
ocr_model: Optional[PaddleOCR] = None
system_info: dict = {}

def get_system_info() -> dict:
    info = {
        "platform": platform.platform(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "device": "CPU",
    }
    try:
        import paddle
        if paddle.is_compiled_with_cuda() and paddle.device.is_compiled_with_cuda():
            info["device"] = "CUDA (GPU)"
    except ImportError:
        pass
    return info

@asynccontextmanager
async def lifespan(app: FastAPI):
    global ocr_model, system_info
    system_info = get_system_info()
    logger.info("System info: %s", system_info)
    
    try:
        # Initialize PaddleOCR with CPU mode (v3 API)
        # We explicitly disable mkldnn due to a known bug with pir::ArrayAttribute in recent builds
        ocr_model = PaddleOCR(use_textline_orientation=True, lang="ch", enable_mkldnn=False)
        logger.info("PaddleOCR model (CPU) initialized successfully!")
    except Exception as e:
        logger.error("PaddleOCR initialization failed: %s", e)
        ocr_model = None
    yield

app = FastAPI(title="PaddleOCR-API", lifespan=lifespan)

def _is_authorized_bearer(authorization: str | None) -> bool:
    if not AUTH_REQUIRED:
        return True
    if not authorization:
        return False
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    return secrets.compare_digest(token, OCR_ACCESS_TOKEN)

@app.middleware("http")
async def access_token_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and not _is_authorized_bearer(request.headers.get("Authorization")):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)

# ── Serve Web Portal ─────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def web_portal():
    html_path = Path(__file__).with_name("index.html")
    if not html_path.exists():
        return "<h1>PaddleOCR API</h1><p>index.html not found.</p>"
    html = html_path.read_text(encoding="utf-8")
    auth_flag_script = f"<script>const __OCR_AUTH_REQUIRED__ = {'true' if AUTH_REQUIRED else 'false'};</script>"
    return html.replace("</head>", f"{auth_flag_script}</head>", 1)

# ── API: System Info ─────────────────────────────────────────────────────────
@app.get("/api/system")
def api_system():
    return {
        **system_info,
        "model_loaded": ocr_model is not None,
        "auth_required": AUTH_REQUIRED,
    }

# ── API: OCR ────────────────────────────────────────────────────────────────
@app.post("/api/ocr")
async def do_ocr(file: UploadFile = File(...)):
    if ocr_model is None:
        raise HTTPException(503, "OCR model is not loaded.")
    
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(400, "Invalid image file.")
            
        start_time = time.perf_counter()
        
        # In PaddleOCR v3 (paddlex), we use predict() and it returns an iterator of OCRResult
        result_gen = ocr_model.predict(img)
        result = list(result_gen)
        duration = time.perf_counter() - start_time
        
        # Flatten and clean the result for JSON response
        formatted_res = []
        if result and len(result) > 0:
            res_item = result[0]
            # Provide fallbacks as not all images will contain text
            texts = res_item['rec_texts'] if 'rec_texts' in res_item else []
            scores = res_item['rec_scores'] if 'rec_scores' in res_item else []
            polys = res_item['rec_polys'] if 'rec_polys' in res_item else []
            
            for i in range(len(texts)):
                poly = polys[i]
                formatted_res.append({
                    "points": poly.tolist() if hasattr(poly, 'tolist') else poly,
                    "text": texts[i],
                    "confidence": float(scores[i])
                })
        
        logger.info("OCR OK: file=%s dur=%.3fs lines=%d", file.filename, duration, len(formatted_res))
        return {
            "status": "ok",
            "duration_s": duration,
            "results": formatted_res
        }
    except Exception as e:
        logger.error("OCR failed: %s", e, exc_info=True)
        raise HTTPException(500, f"OCR processing failed: {e}")

@app.get("/health")
def health_check():
    return {"status": "ok" if ocr_model is not None else "degraded"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
