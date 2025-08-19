"""
log format:

2025-08-19 02:59:15,199 - INFO - Incoming TTS request from IP: 172.17.0.1. Text: '好想狠狠地狂吸入你的痔疮'
2025-08-19 02:59:15,199 - INFO - Generating speech for text from IP: 172.17.0.1. Output path: output_audios/ed48f346-d73a-4a00-a55c-f61c81aaec1c.wav
2025-08-19 02:59:28,718 - INFO - Successfully generated speech file at output_audios/ed48f346-d73a-4a00-a55c-f61c81aaec1c.wav for request from IP: 172.17.0.1.
"""

import os
import uuid
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from indextts.infer import IndexTTS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

OUTPUT_DIR = "output_audios"

try:
    model_dir = "checkpoints"
    cfg_path = "checkpoints/config.yaml"
    if not os.path.exists(model_dir) or not os.path.exists(cfg_path):
        raise FileNotFoundError("Model directory or config file not found.")

    tts = IndexTTS(model_dir=model_dir, cfg_path=cfg_path)
    logger.info("IndexTTS model initialized successfully!")
except Exception as e:
    logger.error(f"IndexTTS model initialization failed: {e}")
    tts = None

@app.on_event("startup")
def create_output_directory():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    logger.info(f"Creating or confirming directory: {OUTPUT_DIR}")

@app.post("/tts")
def generate_speech(text: str, request: Request):
    """
    Accepts a string, calls indextts to generate a speech file, and returns the file.
    """
    client_ip = request.client.host
    logger.info(f"Incoming TTS request from IP: {client_ip}. Text: '{text}'")

    if tts is None:
        logger.error(f"TTS service unavailable for request from IP: {client_ip}.")
        raise HTTPException(status_code=503, detail="TTS service is currently unavailable, model initialization failed.")

    unique_filename = f"{uuid.uuid4()}.wav"
    output_path = os.path.join(OUTPUT_DIR, unique_filename)
    voice = "input.wav"

    if not os.path.exists(voice):
        logger.error(f"Reference audio file '{voice}' not found for request from IP: {client_ip}.")
        raise HTTPException(status_code=400, detail=f"Reference audio file '{voice}' does not exist.")

    try:
        logger.info(f"Generating speech for text from IP: {client_ip}. Output path: {output_path}")
        tts.infer(voice, text, output_path)

        if not os.path.exists(output_path):
            logger.error(f"Speech file generation failed for request from IP: {client_ip}. File not created.")
            raise HTTPException(status_code=500, detail="Speech file generation failed.")

        logger.info(f"Successfully generated speech file at {output_path} for request from IP: {client_ip}.")
        return FileResponse(path=output_path, media_type="audio/wav", filename="speech.wav")

    except Exception as e:
        logger.error(f"An error occurred during speech generation for request from IP: {client_ip}. Error: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred during speech generation: {e}")

@app.get("/health")
def health_check():
    """
    Health check endpoint to confirm if the service is running.
    """
    return JSONResponse(status_code=200, content={"status": "ok"})
