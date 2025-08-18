import os
import uuid  
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from indextts.infer import IndexTTS

app = FastAPI()

OUTPUT_DIR = "output_audios"

try:
    model_dir = "checkpoints"
    cfg_path = "checkpoints/config.yaml"
    if not os.path.exists(model_dir) or not os.path.exists(cfg_path):
        raise FileNotFoundError("Model directory or config file not found.")

    tts = IndexTTS(model_dir=model_dir, cfg_path=cfg_path)
    print("IndexTTS model initialized successfully!")
except Exception as e:
    print(f"IndexTTS model initialization failed: {e}")
    tts = None

@app.on_event("startup")
def create_output_directory():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Creating or confirming directory: {OUTPUT_DIR}")

@app.post("/tts")
def generate_speech(text: str):
    """
    Accepts a string, calls indextts to generate a speech file, and returns the file.
    """
    if tts is None:
        raise HTTPException(status_code=503, detail="TTS service is currently unavailable, model initialization failed.")

    unique_filename = f"{uuid.uuid4()}.wav"
    output_path = os.path.join(OUTPUT_DIR, unique_filename)
    voice = "input.wav"

    if not os.path.exists(voice):
        raise HTTPException(status_code=400, detail=f"Reference audio file '{voice}' does not exist.")

    try:
        tts.infer(voice, text, output_path)

        if not os.path.exists(output_path):
            raise HTTPException(status_code=500, detail="Speech file generation failed.")

        return FileResponse(path=output_path, media_type="audio/wav", filename="speech.wav")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred during speech generation: {e}")

@app.get("/health")
def health_check():
    """
    Health check endpoint to confirm if the service is running.
    """
    return JSONResponse(status_code=200, content={"status": "ok"})