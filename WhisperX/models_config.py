# Curated WhisperX model levels baked into the image at build time.
# Edit this list and rebuild to change the offline-available models.
# Any other whisperx model name may still be requested at runtime; it will
# be downloaded on demand (requires network access on first use).
BAKED_MODELS = ["small", "medium", "large-v3"]
