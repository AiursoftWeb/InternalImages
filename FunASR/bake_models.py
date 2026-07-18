from funasr import AutoModel

# Bake every model referenced by server.py into the model cache so the
# container never downloads at runtime. We reuse FunASR's AutoModel with the
# exact same model names as server.py, which resolves the ModelScope/HF
# aliases correctly (e.g. "paraformer-zh" is an AutoModel alias, not a raw
# ModelScope repo id like "iic/paraformer-zh", which does not exist).
MODEL_CONFIGS = [
    {
        "model": "iic/SenseVoiceSmall",
        "vad_model": "fsmn-vad",
        "vad_kwargs": {"max_single_segment_time": 30000},
    },
    {
        "model": "paraformer-zh",
        "vad_model": "fsmn-vad",
        "punc_model": "ct-punc",
    },
    {
        "model": "paraformer-en",
        "vad_model": "fsmn-vad",
    },
    {
        "model": "FunAudioLLM/Fun-ASR-Nano-2512",
        "hub": "hf",
        "trust_remote_code": True,
        "vad_model": "fsmn-vad",
        "vad_kwargs": {"max_single_segment_time": 30000},
    },
]

for cfg in MODEL_CONFIGS:
    cfg = dict(cfg)
    cfg["device"] = "cpu"
    cfg["disable_update"] = True
    print(f"Baking model: {cfg['model']}")
    AutoModel(**cfg)

print("FunASR models baked.")
