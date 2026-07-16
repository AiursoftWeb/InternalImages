import os
import shutil
import tempfile

import whisperx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

app = FastAPI()
model = None


@app.on_event("startup")
def load_model():
    global model
    model = whisperx.load_model(
        os.getenv("WHISPERX_MODEL", "small"),
        os.getenv("WHISPERX_DEVICE", "cpu"),
        compute_type=os.getenv("WHISPERX_COMPUTE_TYPE", "int8"),
    )


@app.get("/health")
def health():
    if model is None:
        raise HTTPException(status_code=503, detail="model is loading")
    return {"status": "ok"}


@app.post("/v1/audio/transcriptions")
def transcribe(
    file: UploadFile = File(...),
    response_format: str = Form("json"),
):
    if model is None:
        raise HTTPException(status_code=503, detail="model is loading")
    with tempfile.NamedTemporaryFile(suffix=os.path.splitext(file.filename or "audio")[1]) as audio_file:
        shutil.copyfileobj(file.file, audio_file)
        audio_file.flush()
        result = model.transcribe(whisperx.load_audio(audio_file.name))
    if response_format == "json":
        return {"text": " ".join(segment["text"].strip() for segment in result["segments"])}
    return {
        "text": " ".join(segment["text"].strip() for segment in result["segments"]),
        "language": result.get("language"),
        "segments": result["segments"],
    }
