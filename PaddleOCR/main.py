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
import asyncio

import cv2
import numpy as np
import base64
import fitz
import threading
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from paddleocr import PaddleOCR
import paddle

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
ocr_lock = threading.Lock()
pdf_executor = ThreadPoolExecutor(max_workers=4)
gpu_semaphore = asyncio.Semaphore(1)

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
    try:
        result = ocr_model.ocr(img, cls=True)
    finally:
        if USE_GPU:
            try:
                paddle.device.cuda.empty_cache()
            except Exception as e:
                logger.warning("Failed to clear CUDA cache: %s", e)
    duration = time.perf_counter() - start_time
    
    formatted_res = []
    if result and len(result) > 0 and result[0]:
        for line in result[0]:
            box, (text, score) = line
            formatted_res.append({"points": box, "text": text, "confidence": float(score)})
    
    logger.info("OCR OK: dur=%.3fs lines=%d device=%s", duration, len(formatted_res), model_runtime_device)
    return {"status": "ok", "duration_s": duration, "device": model_runtime_device, "results": formatted_res}

def _run_ocr_on_pdf_page(img: np.ndarray, page_num: int):
    if ocr_model is None: raise HTTPException(503, "OCR model is not loaded.")
    try:
        with ocr_lock:
            result = ocr_model.ocr(img, cls=True)
    finally:
        if USE_GPU:
            try:
                paddle.device.cuda.empty_cache()
            except Exception as e:
                logger.warning("Failed to clear CUDA cache in PDF process: %s", e)
    
    formatted_res = []
    if result and len(result) > 0 and result[0]:
        for line in result[0]:
            box, (text, score) = line
            formatted_res.append({
                "points": box,
                "text": text,
                "confidence": float(score),
                "page_num": page_num
            })
    return formatted_res

def _run_ocr_on_pdf(contents: bytes):
    start_time = time.perf_counter()
    try:
        with fitz.open(stream=contents, filetype="pdf") as doc:
            num_pages = len(doc)
    except Exception:
        raise HTTPException(400, "Invalid or corrupted PDF file.")

    if num_pages > 50:
        raise HTTPException(400, "PDF has too many pages. Maximum allowed is 50 pages.")

    def process_page(page_index: int):
        with fitz.open(stream=contents, filetype="pdf") as thread_doc:
            page = thread_doc.load_page(page_index)
            
            # Check if scanned
            text = page.get_text("text").strip()
            is_scanned = len(text) < 10
            
            res = []
            if is_scanned:
                pix = page.get_pixmap(dpi=150)
                img_data = pix.tobytes("png")
                nparr = np.frombuffer(img_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is not None:
                    page_res = _run_ocr_on_pdf_page(img, page_num=page_index + 1)
                    scale = 150 / 72.0
                    for item in page_res:
                        new_points = [[pt[0] / scale, pt[1] / scale] for pt in item["points"]]
                        item["points"] = new_points
                        res.append(item)
            else:
                blocks = page.get_text("dict")["blocks"]
                for b in blocks:
                    if b.get("type") == 0 and "lines" in b:
                        for line in b["lines"]:
                            line_text = ""
                            last_span = None
                            for span in line["spans"]:
                                if last_span is not None:
                                    gap = span["bbox"][0] - last_span["bbox"][2]
                                    if gap > span.get("size", 10) * 0.2:
                                        line_text += " "
                                line_text += span["text"]
                                last_span = span
                                
                            if line_text.strip():
                                x0, y0, x1, y1 = line["bbox"]
                                box = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
                                res.append({
                                    "points": box,
                                    "text": line_text.strip(),
                                    "confidence": 1.0,
                                    "page_num": page_index + 1
                                })
                    elif b.get("type") == 1:
                        clip_rect = fitz.Rect(b["bbox"])
                        pix = page.get_pixmap(clip=clip_rect, dpi=150)
                        img_data = pix.tobytes("png")
                        nparr = np.frombuffer(img_data, np.uint8)
                        block_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                        if block_img is not None:
                            block_res = _run_ocr_on_pdf_page(block_img, page_num=page_index + 1)
                            scale = 150 / 72.0
                            for item in block_res:
                                new_points = []
                                for pt in item["points"]:
                                    nx = clip_rect.x0 + (pt[0] / scale)
                                    ny = clip_rect.y0 + (pt[1] / scale)
                                    new_points.append([nx, ny])
                                item["points"] = new_points
                                res.append(item)
            return res

    all_results = []
    for i in range(num_pages):
        all_results.extend(process_page(i))

    duration = time.perf_counter() - start_time
    logger.info("PDF OK: dur=%.3fs pages=%d lines=%d device=%s", duration, num_pages, len(all_results), model_runtime_device)
    return {"status": "ok", "duration_s": duration, "device": model_runtime_device, "results": all_results}

@app.post("/api/ocr")
async def do_ocr(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None: raise HTTPException(400, "Invalid image file.")
        
        async with gpu_semaphore:
            return await run_in_threadpool(_run_ocr_on_image, img)
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
        
        async with gpu_semaphore:
            return await run_in_threadpool(_run_ocr_on_image, img)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("OCR failed: %s", e, exc_info=True)
        raise HTTPException(500, f"OCR processing failed: {e}")

@app.post("/api/ocr/pdf")
async def do_ocr_pdf(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        if not contents.startswith(b"%PDF-"):
            raise HTTPException(400, "Not a valid PDF file.")
        async with gpu_semaphore:
            return await run_in_threadpool(_run_ocr_on_pdf, contents)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("PDF OCR failed: %s", e, exc_info=True)
        raise HTTPException(500, f"PDF processing failed: {e}")

@app.post("/api/ocr/pdf/base64")
async def do_ocr_pdf_base64(req: Base64Request):
    try:
        b64_data = req.base64
        if b64_data.startswith("data:"):
            if "," in b64_data:
                b64_data = b64_data.split(",", 1)[1]
            else:
                raise HTTPException(400, "Invalid base64 data URI.")
        
        contents = base64.b64decode(b64_data)
        if not contents.startswith(b"%PDF-"):
            raise HTTPException(400, "Not a valid PDF file.")
        async with gpu_semaphore:
            return await run_in_threadpool(_run_ocr_on_pdf, contents)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("PDF OCR failed: %s", e, exc_info=True)
        raise HTTPException(500, f"PDF processing failed: {e}")

@app.get("/health")
def health_check():
    return {"status": "ok" if ocr_model is not None else "degraded"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
