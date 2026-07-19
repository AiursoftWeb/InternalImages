from funasr import AutoModel

# Download every model referenced by server.py into MODELSCOPE_CACHE at build
# time so the runtime never fetches weights. We load on CPU here only because
# the build container has no GPU; the cached weights are device-agnostic and
# are reloaded onto CUDA by server.py (--device cuda --ngpu 1) at runtime.
COMMON = dict(ngpu=0, ncpu=4, device="cpu", disable_pbar=True, disable_log=True)

AutoModel(
    model="iic/speech_paraformer-large-contextual_asr_nat-zh-cn-16k-common-vocab8404",
    model_revision="v2.0.4",
    **COMMON,
)
AutoModel(
    model="iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online",
    model_revision="v2.0.4",
    **COMMON,
)
AutoModel(
    model="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
    model_revision="v2.0.4",
    **COMMON,
)
AutoModel(
    model="iic/punc_ct-transformer_zh-cn-common-vad_realtime-vocab272727",
    model_revision="v2.0.4",
    **COMMON,
)
AutoModel(
    model="iic/speech_campplus_sv_zh-cn_16k-common",
    **COMMON,
)

print("FunASR realtime models baked.")
