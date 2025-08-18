# FROM hub.aiursoft.cn/pytorch/pytorch:2.7.0-cuda12.6-cudnn9-devel

# RUN apt update
# RUN apt install -y curl git ffmpeg
# RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# WORKDIR /app
# COPY checkpoints .
# COPY pyproject.toml .
# COPY requirements.txt .
# COPY setup.py .
# COPY tools .
# COPY indextts .
# COPY tests .
# COPY MANIFEST.in .
# COPY README.md .

# RUN . "$HOME/.local/bin/env" \
# 	&& uv --version \
# 	&& uv venv tts \
# 	&& . "tts/bin/activate" \
# 	&& uv pip install uvicorn fastapi \
# 	&& uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118 \
# 	&& uv pip install -e .

# RUN . "$HOME/.local/bin/env" \
# 	&& export HF_ENDPOINT="https://hf-mirror.com" \
# 	&& . "tts/bin/activate" \
# 	&& hf download IndexTeam/IndexTTS-1.5 config.yaml bigvgan_discriminator.pth bigvgan_generator.pth bpe.model dvae.pth gpt.pth unigram_12000.vocab --local-dir checkpoints

# COPY --chmod=755 . .

# EXPOSE 8000
# CMD ["/app/tts/bin/uvicorn","main:app","--host","0.0.0.0","--port", "8000"]

FROM hub.aiursoft.cn/aiursoft/internalimages/nvidia:latest

RUN apt-get update && apt-get install -y ffmpeg git curl
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
WORKDIR /app

ADD "https://api.github.com/repos/JingyunLiang/SwinIR/commits?per_page=1" latest_commit
RUN git clone https://github.com/index-tts/index-tts.git

RUN cd index-tts

RUN . "$HOME/.local/bin/env" \
	&& uv --version \
	&& uv venv tts \
	&& . "tts/bin/activate" \
	&& uv pip install uvicorn fastapi \
	&& uv pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118 \
	&& uv pip install -e .

RUN . "$HOME/.local/bin/env" \
	&& export HF_ENDPOINT="https://hf-mirror.com" \
	&& . "tts/bin/activate" \
	&& hf download IndexTeam/IndexTTS-1.5 config.yaml bigvgan_discriminator.pth bigvgan_generator.pth bpe.model dvae.pth gpt.pth unigram_12000.vocab --local-dir checkpoints

COPY --chmod=755 . .

EXPOSE 8000
CMD ["/app/tts/bin/uvicorn","main:app","--host","0.0.0.0","--port", "8000"]
