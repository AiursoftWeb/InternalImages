import os
import uuid  # 导入 uuid 模块
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from indextts.infer import IndexTTS

# 创建 FastAPI 实例
app = FastAPI()

# 定义输出文件夹路径
OUTPUT_DIR = "output_audios"

# 初始化 IndexTTS 模型
try:
    # 确保模型目录和配置文件存在
    model_dir = "checkpoints"
    cfg_path = "checkpoints/config.yaml"
    if not os.path.exists(model_dir) or not os.path.exists(cfg_path):
        raise FileNotFoundError("Model directory or config file not found.")

    tts = IndexTTS(model_dir=model_dir, cfg_path=cfg_path)
    print("IndexTTS 模型初始化成功！")
except Exception as e:
    print(f"IndexTTS 模型初始化失败: {e}")
    tts = None

# 在应用启动时创建输出文件夹
@app.on_event("startup")
def create_output_directory():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"创建或确认文件夹: {OUTPUT_DIR}")

@app.post("/tts")
def generate_speech(text: str):
    """
    接受一段字符串，调用 indextts 生成语音文件，并返回该文件。
    """
    if tts is None:
        raise HTTPException(status_code=503, detail="TTS 服务暂不可用，模型初始化失败。")

    # 使用 uuid 生成唯一的文件名
    unique_filename = f"{uuid.uuid4()}.wav"
    output_path = os.path.join(OUTPUT_DIR, unique_filename)
    voice = "input.wav"

    # 检查参考音频文件是否存在
    if not os.path.exists(voice):
        raise HTTPException(status_code=400, detail=f"参考音频文件 '{voice}' 不存在。")

    try:
        # 调用 indextts 生成语音
        tts.infer(voice, text, output_path)

        # 检查生成的文件是否存在
        if not os.path.exists(output_path):
            raise HTTPException(status_code=500, detail="语音文件生成失败。")

        # 返回生成的音频文件
        return FileResponse(path=output_path, media_type="audio/wav", filename="speech.wav")

    except Exception as e:
        # 处理生成过程中的异常
        raise HTTPException(status_code=500, detail=f"语音生成过程中出现错误: {e}")
