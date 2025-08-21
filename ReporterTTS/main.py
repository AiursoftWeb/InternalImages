#!/usr/bin/env python3
import os
import uuid
import time
import signal
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvloop
from clickhouse_connect import get_client
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from indextts.infer import IndexTTS

# === Logging setup ===
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s %(message)s')
logger = logging.getLogger(__name__)

# === Configuration ===
OUTPUT_DIR = "output_audios"
# ClickHouse Logger Configuration (using the same env var names)
CH_URL = os.getenv('CLICKHOUSE_URL', 'http://clickhouse:8123')
CH_USER = os.getenv('CLICKHOUSE_USER', 'default')
CH_PASS = os.getenv('CLICKHOUSE_PASSWORD', '')
CH_DB = os.getenv('CLICKHOUSE_DATABASE', 'logs')
CH_TABLE = os.getenv('CLICKHOUSE_TABLE', 'tts_requests')
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '1000'))
FLUSH_INTERVAL = float(os.getenv('FLUSH_INTERVAL_SEC', '2'))

# Columns in ClickHouse order for tts_requests table
COLUMNS = [
    'ts', 'request_id', 'client_ip', 'request_text', 'reference_voice',
    'duration_ms', 'is_success', 'status_code', 'error_message',
    'output_filesize_bytes', 'output_filename'
]

# === ClickHouse Async Logger ===
class AsyncTTSLogger:
    _instance = None

    def __init__(self):
        self.queue = asyncio.Queue(maxsize=50000)
        self.stop_event = asyncio.Event()
        self.flusher_task = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def create_ch_client(self):
        secure = CH_URL.startswith('https')
        parts = CH_URL.split('://')[-1].split(':')
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 8123
        logger.debug("Creating ClickHouse client to %s:%d (secure=%s)", host, port, secure)
        return get_client(host=host, port=port, username=CH_USER, password=CH_PASS, database=CH_DB, secure=secure)

    async def flusher(self):
        client = self.create_ch_client()
        batch, last_flush = [], time.time()
        while not self.stop_event.is_set():
            try:
                item = await asyncio.wait_for(self.queue.get(), timeout=FLUSH_INTERVAL)
                batch.append(item)
            except asyncio.TimeoutError:
                pass # This is expected, to allow periodic flushing

            now = time.time()
            if batch and (len(batch) >= BATCH_SIZE or now - last_flush >= FLUSH_INTERVAL):
                try:
                    logger.info("Flushing %d TTS logs to ClickHouse", len(batch))
                    client.insert(CH_TABLE, batch, column_names=COLUMNS)
                except Exception as e:
                    logger.error("ClickHouse insert failed: %s", e)
                finally:
                    batch.clear()
                    last_flush = now
        
        # Final flush on shutdown
        if batch:
            try:
                logger.info("Final flush of %d TTS logs", len(batch))
                client.insert(CH_TABLE, batch, column_names=COLUMNS)
            except Exception as e:
                logger.error("Final ClickHouse insert failed: %s", e)

    def log(self, record: dict):
        """Formats and queues a log record."""
        row = (
            record.get('ts'),
            record.get('request_id'),
            record.get('client_ip', ''),
            record.get('request_text', ''),
            record.get('reference_voice', ''),
            record.get('duration_ms', 0.0),
            1 if record.get('is_success') else 0,
            record.get('status_code', 500),
            record.get('error_message', ''),
            record.get('output_filesize_bytes', 0),
            record.get('output_filename', '')
        )
        try:
            self.queue.put_nowait(row)
        except asyncio.QueueFull:
            logger.warning("Log queue is full. Discarding TTS log.")

    def start(self):
        if not self.flusher_task:
            loop = asyncio.get_event_loop()
            self.flusher_task = loop.create_task(self.flusher())
            logger.info("Async TTS logger started.")

    async def shutdown(self):
        if self.flusher_task:
            logger.info("Shutting down async TTS logger...")
            self.stop_event.set()
            # Wait for the flusher to finish processing the queue
            await self.flusher_task
            logger.info("Async TTS logger shut down.")

# === FastAPI Application ===
tts_model = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global tts_model
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    logger.info("Creating or confirming directory: %s", OUTPUT_DIR)
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
    
    # Start the logger
    uvloop.install()
    AsyncTTSLogger.get_instance().start()
    
    yield
    
    # Shutdown
    await AsyncTTSLogger.get_instance().shutdown()

app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware to log request details to ClickHouse."""
    request_id = uuid.uuid4()
    start_time = time.perf_counter()
    
    # Initialize log info on request state
    request.state.log_info = {
        "ts": datetime.now(timezone.utc),
        "request_id": request_id,
        "client_ip": request.client.host if request.client else "unknown",
    }
    
    response = await call_next(request)
    
    duration_ms = (time.perf_counter() - start_time) * 1000
    
    # The endpoint should have populated the rest of the log_info
    log_payload = request.state.log_info
    log_payload['duration_ms'] = duration_ms
    log_payload['status_code'] = response.status_code
    
    # Send to the async logger
    AsyncTTSLogger.get_instance().log(log_payload)
    
    return response

@app.post("/tts")
def generate_speech(request: Request, text: str):
    """
    Accepts a string, calls indextts to generate a speech file, and returns the file.
    All relevant info is logged via middleware.
    """
    if tts_model is None:
        request.state.log_info.update({
            "is_success": False,
            "error_message": "TTS service unavailable: model not initialized.",
            "request_text": text,
        })
        raise HTTPException(status_code=503, detail="TTS service is currently unavailable, model initialization failed.")

    unique_filename = f"{uuid.uuid4()}.wav"
    output_path = os.path.join(OUTPUT_DIR, unique_filename)
    voice = "input.wav"

    if not os.path.exists(voice):
        request.state.log_info.update({
            "is_success": False,
            "error_message": f"Reference audio file '{voice}' does not exist.",
            "request_text": text,
            "reference_voice": voice,
        })
        raise HTTPException(status_code=400, detail=f"Reference audio file '{voice}' does not exist.")

    try:
        tts_model.infer(voice, text, output_path)

        if not os.path.exists(output_path):
            raise RuntimeError("Speech file generation failed, output file not found.")
        
        file_size = os.path.getsize(output_path)

        # Log success info to request.state for the middleware
        request.state.log_info.update({
            "is_success": True,
            "error_message": "",
            "request_text": text,
            "reference_voice": voice,
            "output_filesize_bytes": file_size,
            "output_filename": unique_filename,
        })
        
        return FileResponse(path=output_path, media_type="audio/wav", filename="speech.wav")

    except Exception as e:
        # Log failure info to request.state for the middleware
        request.state.log_info.update({
            "is_success": False,
            "error_message": str(e),
            "request_text": text,
            "reference_voice": voice,
        })
        logger.error("An error occurred during speech generation: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred during speech generation: {e}")

@app.get("/health")
def health_check():
    """Health check endpoint to confirm if the service is running."""
    status = "ok" if tts_model is not None else "degraded"
    return JSONResponse(status_code=200, content={"status": status})

# To run this app:
# uvicorn your_filename:app --host 0.0.0.0 --port 8000