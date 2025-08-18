fork by indexTTS

# ReporterTTS

A TTS Server

# Usage

## Docker

Build
```sh
sudo docker build . -t tts
sudo docker run -p 8000:8000 ~/tmp:/app/output_audios --gpus all tts
```

Send request
```sh
POST http://localhost:8000/tts?text=这是一个测试语音
```
