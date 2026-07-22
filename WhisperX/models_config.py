import os

# Curated WhisperX model levels baked into the image at build time.
# Edit this list and rebuild to change the offline-available models.
# Any other whisperx model name may still be requested at runtime; it will
# be downloaded on demand (requires network access on first use).
if os.getenv("SINGLE_MODEL", "false").lower() == "true":
    BAKED_MODELS = ["large-v3"]
else:
    BAKED_MODELS = ["small", "medium", "large-v3"]

