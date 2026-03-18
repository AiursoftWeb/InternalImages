#!/usr/bin/env python3
import os
import time
import secrets
import logging
from pathlib import Path
from contextlib import asynccontextmanager

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import HTMLResponse, JSONResponse
from paddleocr import PaddleOCR

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(asctime)s %(message)s")
logger = logging.getLogger(__name__)

OCR_ACCESS_TOKEN = os.getenv("OCR_ACCESS_TOKEN", "").strip()
AUTH_REQUIRED = bool(OCR_ACCESS_TOKEN)

ocr_model = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global ocr_model
    # Exhaustive attempts to initialize whatever PaddleOCR class this is
    configs = [
        {"lang": "ch", "use_gpu": True, "use_angle_cls": True},
        {"lang": "ch", "use_gpu": True},
        {"lang": "ch"},
        {}
    ]
    
    for cfg in configs:
        try:
            logger.info("Attempting PaddleOCR init with: %s", cfg)
            ocr_model = PaddleOCR(**cfg)
            logger.info("PaddleOCR initialized successfully with: %s", cfg)
            break
        except Exception as e:
            logger.warning("Failed with %s: %s", cfg, e)
    
    if ocr_model is None:
        logger.error("All PaddleOCR initialization attempts failed.")
    yield

app = FastAPI(title="PaddleOCR-API-GPU", lifespan=lifespan)

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
    return html.replace("</head>", f"<script>const __OCR_AUTH_REQUIRED__ = {'true' if AUTH_REQUIRED else 'false'};</script></head>", 1)

@app.post("/api/ocr")
async def do_ocr(file: UploadFile = File(...)):
    if ocr_model is None: raise HTTPException(503, "OCR model is not loaded.")
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None: raise HTTPException(400, "Invalid image file.")
        
        start_time = time.perf_counter()
        # Some versions use ocr(), some use predict()
        result = None
        for method_name in ["ocr", "predict"]:
            method = getattr(ocr_model, method_name, None)
            if method:
                try:
                    result = method(img, cls=True) if method_name == "ocr" else list(method(img))
                    break
                except Exception as e:
                    logger.warning("Method %s failed: %s", method_name, e)
        
        duration = time.perf_counter() - start_time
        if result is None: raise HTTPException(500, "Failed to run inference.")
        
        formatted_res = []
        # Basic parsing for typical PaddleOCR output
        if isinstance(result, list) and len(result) > 0:
            res_data = result[0]
            if isinstance(res_data, list): # Standard paddleocr [ [[box], [text, score]], ... ]
                for line in res_data:
                    box, (text, score) = line
                    formatted_res.append({"points": box, "text": text, "confidence": float(score)})
            elif isinstance(res_data, dict): # paddlex / newer format
                texts = res_data.get('rec_texts', [])
                scores = res_data.get('rec_scores', [])
                polys = res_data.get('rec_polys', [])
                for i in range(len(texts)):
                    formatted_res.append({"points": polys[i].tolist() if hasattr(polys[i], 'tolist') else polys[i], 
                                         "text": texts[i], "confidence": float(scores[i])})

        logger.info("OCR OK: dur=%.3fs lines=%d", duration, len(formatted_res))
        return {"status": "ok", "duration_s": duration, "results": formatted_res}
    except Exception as e:
        logger.error("OCR failed: %s", e, exc_info=True)
        raise HTTPException(500, f"OCR processing failed: {e}")

@app.get("/health")
def health_check():
    return {"status": "ok" if ocr_model is not None else "degraded"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
