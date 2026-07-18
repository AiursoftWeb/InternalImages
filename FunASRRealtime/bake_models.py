from funasr import AutoModel

# Mirror the model list in server.py; load on CPU at build time so weights
# are downloaded into MODELSCOPE_CACHE and reused at runtime.
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
