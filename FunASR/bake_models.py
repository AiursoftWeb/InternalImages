from huggingface_hub import snapshot_download
from modelscope import snapshot_download

# ModelScope-hosted models used by server.py (hub defaults to modelscope).
MS_MODELS = [
    "iic/SenseVoiceSmall",
    "iic/paraformer-zh",
    "iic/paraformer-en",
    "iic/fsmn-vad",
    "iic/ct-punc",
]

for model in MS_MODELS:
    snapshot_download(model)

# Hugging Face-hosted model referenced by server.py with hub="hf".
snapshot_download("FunAudioLLM/Fun-ASR-Nano-2512", repo_type="model")

print("FunASR models baked.")
