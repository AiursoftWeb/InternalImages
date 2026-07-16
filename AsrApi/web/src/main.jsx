import { useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/roboto/400.css'
import '@fontsource/roboto/500.css'
import '@fontsource/roboto/700.css'
import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined'
import DescriptionOutlinedIcon from '@mui/icons-material/DescriptionOutlined'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import GraphicEqOutlinedIcon from '@mui/icons-material/GraphicEqOutlined'
import MicRoundedIcon from '@mui/icons-material/MicRounded'
import PlayArrowRoundedIcon from '@mui/icons-material/PlayArrowRounded'
import StopRoundedIcon from '@mui/icons-material/StopRounded'
import {
  Alert,
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Container,
  CssBaseline,
  Divider,
  FormControl,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  ThemeProvider,
  Typography,
  createTheme,
} from '@mui/material'

const theme = createTheme({
  palette: {
    primary: { main: '#4058c7' },
    secondary: { main: '#5b63d9' },
    background: { default: '#f7f8ff', paper: '#ffffff' },
  },
  shape: { borderRadius: 16 },
  typography: { fontFamily: 'Roboto, Arial, sans-serif' },
})

function defaultRealtimeUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.hostname}:10095`
}

function resampleAudio(samples, sourceRate, targetRate) {
  if (sourceRate === targetRate) return samples
  const outputLength = Math.round(samples.length * targetRate / sourceRate)
  const output = new Float32Array(outputLength)
  const ratio = sourceRate / targetRate
  for (let index = 0; index < outputLength; index += 1) {
    const sourceIndex = index * ratio
    const before = Math.floor(sourceIndex)
    const after = Math.min(before + 1, samples.length - 1)
    const blend = sourceIndex - before
    output[index] = samples[before] * (1 - blend) + samples[after] * blend
  }
  return output
}

function encodePcm(samples) {
  const output = new Int16Array(samples.length)
  for (let index = 0; index < samples.length; index += 1) {
    output[index] = Math.max(-1, Math.min(1, samples[index])) * 0x7fff
  }
  return output.buffer
}

async function startMicrophone(onAudio) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } })
  const audioContext = new AudioContext({ sampleRate: 16000 })
  const source = audioContext.createMediaStreamSource(stream)
  const processor = audioContext.createScriptProcessor(1024, 1, 1)
  const silentGain = audioContext.createGain()
  silentGain.gain.value = 0
  processor.onaudioprocess = (event) => {
    const samples = event.inputBuffer.getChannelData(0)
    const pcm = encodePcm(resampleAudio(samples, audioContext.sampleRate, 16000))
    onAudio(pcm)
  }
  source.connect(processor)
  processor.connect(silentGain)
  silentGain.connect(audioContext.destination)

  return () => {
    processor.disconnect()
    silentGain.disconnect()
    source.disconnect()
    stream.getTracks().forEach((track) => track.stop())
    audioContext.close()
  }
}

function App() {
  const [token, setToken] = useState('')
  const [model, setModel] = useState('funasr')
  const [language, setLanguage] = useState('')
  const [file, setFile] = useState(null)
  const [result, setResult] = useState('')
  const [durationMs, setDurationMs] = useState(null)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [realtimeUrl, setRealtimeUrl] = useState(defaultRealtimeUrl)
  const [realtimeToken, setRealtimeToken] = useState('')
  const [realtimeStatus, setRealtimeStatus] = useState('未连接')
  const [realtimePartial, setRealtimePartial] = useState('')
  const [realtimeFinal, setRealtimeFinal] = useState('')
  const [realtimeError, setRealtimeError] = useState('')
  const microphoneRef = useRef(null)
  const socketRef = useRef(null)
  const stoppingRealtimeRef = useRef(false)

  async function transcribe() {
    if (!file || !token) {
      setError('请选择音频文件并填写 API Token。')
      return
    }

    setError('')
    setResult('')
    setDurationMs(null)
    setSubmitting(true)
    const startedAt = performance.now()
    const formData = new FormData()
    formData.append('file', file)
    formData.append('model', model)
    if (language) formData.append('language', language)

    try {
      const response = await fetch('/v1/audio/transcriptions', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      })
      const body = await response.text()
      if (!response.ok) {
        throw new Error(readError(body) || `请求失败（HTTP ${response.status}）`)
      }
      setResult(readText(body) || body)
      setDurationMs(performance.now() - startedAt)
    } catch (requestError) {
      setError(requestError.message || '无法连接到服务。')
    } finally {
      setSubmitting(false)
    }
  }

  async function startRealtime() {
    if (!realtimeToken) {
      setRealtimeError('请填写实时服务 Token。')
      return
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setRealtimeError('当前浏览器不支持麦克风采集。')
      return
    }

    setRealtimeError('')
    setRealtimePartial('')
    setRealtimeFinal('')
    setRealtimeStatus('连接中…')
    stoppingRealtimeRef.current = false
    let socket
    try {
      socket = new WebSocket(realtimeUrl, ['binary', `bearer.${realtimeToken}`])
    } catch (connectionError) {
      setRealtimeError(connectionError.message || '实时服务地址无效。')
      setRealtimeStatus('未连接')
      return
    }
    socket.binaryType = 'arraybuffer'
    socketRef.current = socket

    socket.onopen = async () => {
      socket.send(JSON.stringify({
        mode: '2pass',
        audio_fs: 16000,
        chunk_size: [5, 10, 5],
        chunk_interval: 10,
        wav_name: 'microphone',
        is_speaking: true,
      }))
      try {
        microphoneRef.current = await startMicrophone((pcm) => {
          if (socket.readyState === WebSocket.OPEN) socket.send(pcm)
        })
        setRealtimeStatus('正在实时识别')
      } catch (microphoneError) {
        stoppingRealtimeRef.current = true
        socket.close()
        setRealtimeError(microphoneError.message || '无法访问麦克风。')
      }
    }

    socket.onmessage = (event) => {
      const message = JSON.parse(event.data)
      if (message.is_final) {
        setRealtimeFinal(message.text || '')
        stoppingRealtimeRef.current = true
        socket.close()
        return
      }
      setRealtimePartial(message.text || '')
    }

    socket.onerror = () => {
      setRealtimeError('无法连接实时识别服务。请检查服务地址和 Token。')
    }

    socket.onclose = () => {
      microphoneRef.current?.()
      microphoneRef.current = null
      socketRef.current = null
      setRealtimeStatus('未连接')
      if (!stoppingRealtimeRef.current) {
        setRealtimeError('实时服务已断开连接。')
      }
    }
  }

  function stopRealtime() {
    const socket = socketRef.current
    if (socket?.readyState === WebSocket.OPEN) {
      stoppingRealtimeRef.current = true
      socket.send(JSON.stringify({ is_speaking: false }))
    }
    microphoneRef.current?.()
    microphoneRef.current = null
    setRealtimeStatus('正在结束…')
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ minHeight: '100vh', py: { xs: 3, md: 7 }, background: 'radial-gradient(circle at top right, #e2e7ff 0, transparent 33%), #f7f8ff' }}>
        <Container maxWidth="md">
          <Stack spacing={4}>
            <Box>
              <Chip label="ASR API" color="primary" size="small" sx={{ mb: 2, fontWeight: 700 }} />
              <Typography variant="h3" component="h1" sx={{ fontWeight: 700, letterSpacing: '-0.04em' }}>
                Speech to text, simply.
              </Typography>
              <Typography color="text.secondary" sx={{ mt: 1, maxWidth: 580 }}>
                上传音频，使用已部署的 WhisperX 或 FunASR 模型快速体验语音识别。
              </Typography>
            </Box>

            <Card elevation={0} sx={{ border: '1px solid', borderColor: 'divider' }}>
              <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
                <Stack spacing={3}>
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    <GraphicEqOutlinedIcon color="primary" />
                    <Typography variant="h6" fontWeight={700}>开始识别</Typography>
                  </Stack>
                  <TextField label="API Token" type="password" value={token} onChange={(event) => setToken(event.target.value)} fullWidth autoComplete="off" helperText="仅用于本次请求，不会被保存。" />
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                    <FormControl fullWidth>
                      <InputLabel id="model-label">识别模型</InputLabel>
                      <Select labelId="model-label" label="识别模型" value={model} onChange={(event) => setModel(event.target.value)}>
                        <MenuItem value="funasr">FunASR</MenuItem>
                        <MenuItem value="whisperx">WhisperX</MenuItem>
                      </Select>
                    </FormControl>
                    <TextField label="语言（可选）" value={language} onChange={(event) => setLanguage(event.target.value)} fullWidth placeholder="例如 zh、en" />
                  </Stack>
                  <Button component="label" variant="outlined" color="primary" startIcon={<CloudUploadOutlinedIcon />} sx={{ minHeight: 88, borderStyle: 'dashed', justifyContent: 'flex-start', px: 3, textTransform: 'none' }}>
                    <Box textAlign="left">
                      <Typography fontWeight={600}>{file ? file.name : '选择音频文件'}</Typography>
                      <Typography variant="body2" color="text.secondary">支持服务端接受的音频格式，文件上限 100 MiB</Typography>
                    </Box>
                    <input hidden type="file" accept="audio/*" onChange={(event) => setFile(event.target.files?.[0] || null)} />
                  </Button>
                  {error && <Alert severity="error">{error}</Alert>}
                  <Button variant="contained" size="large" onClick={transcribe} disabled={submitting} startIcon={<PlayArrowRoundedIcon />} sx={{ alignSelf: 'flex-start', px: 3 }}>
                    {submitting ? '识别中…' : '开始识别'}
                  </Button>
                  {submitting && <LinearProgress />}
                </Stack>
              </CardContent>
            </Card>

            <Paper elevation={0} sx={{ p: { xs: 3, sm: 4 }, border: '1px solid', borderColor: 'divider' }}>
              <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
                <DescriptionOutlinedIcon color="primary" />
                <Typography variant="h6" fontWeight={700}>识别结果</Typography>
              </Stack>
              <Divider sx={{ mb: 2 }} />
              <Typography component="pre" sx={{ m: 0, minHeight: 88, whiteSpace: 'pre-wrap', fontFamily: 'inherit', color: result ? 'text.primary' : 'text.secondary' }}>
                {result || '识别后的文本会显示在这里。'}
              </Typography>
              {durationMs !== null && (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                  耗时：{(durationMs / 1000).toFixed(2)} 秒
                </Typography>
              )}
            </Paper>

            <Card elevation={0} sx={{ border: '1px solid', borderColor: 'divider' }}>
              <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
                <Stack spacing={3}>
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    <MicRoundedIcon color="primary" />
                    <Typography variant="h6" fontWeight={700}>实时麦克风识别</Typography>
                    <Chip label={realtimeStatus} size="small" color={realtimeStatus === '正在实时识别' ? 'success' : 'default'} />
                  </Stack>
                  <TextField label="实时服务地址" value={realtimeUrl} onChange={(event) => setRealtimeUrl(event.target.value)} fullWidth helperText="默认连接当前主机的 10095 端口。需要部署 funasr-realtime。" />
                  <TextField label="实时服务 Token" type="password" value={realtimeToken} onChange={(event) => setRealtimeToken(event.target.value)} fullWidth autoComplete="off" helperText="仅用于连接 funasr-realtime，不会被保存。" />
                  {realtimeError && <Alert severity="error">{realtimeError}</Alert>}
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                    <Button variant="contained" onClick={startRealtime} disabled={realtimeStatus !== '未连接'} startIcon={<MicRoundedIcon />}>
                      连接麦克风
                    </Button>
                    <Button variant="outlined" color="error" onClick={stopRealtime} disabled={realtimeStatus !== '正在实时识别'} startIcon={<StopRoundedIcon />}>
                      停止识别
                    </Button>
                  </Stack>
                  <Paper variant="outlined" sx={{ p: 2, bgcolor: 'grey.50' }}>
                    <Typography variant="overline" color="text.secondary">增量文本</Typography>
                    <Typography sx={{ minHeight: 28, whiteSpace: 'pre-wrap' }}>{realtimePartial || '等待语音输入…'}</Typography>
                    <Divider sx={{ my: 1.5 }} />
                    <Typography variant="overline" color="text.secondary">最终文本</Typography>
                    <Typography sx={{ minHeight: 28, whiteSpace: 'pre-wrap' }}>{realtimeFinal || '句末校正结果会显示在这里。'}</Typography>
                  </Paper>
                </Stack>
              </CardContent>
            </Card>

            <Paper elevation={0} sx={{ p: { xs: 3, sm: 4 }, border: '1px solid', borderColor: 'divider' }}>
              <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
                <DescriptionOutlinedIcon color="primary" />
                <Typography variant="h6" fontWeight={700}>API 接口说明</Typography>
              </Stack>
              <Stack spacing={1}>
                <ApiEndpoint method="GET" path="/healthz" description="检查网关是否正在运行，无需认证。" example="curl http://localhost:8080/healthz" />
                <ApiEndpoint method="WS" path="ws://<host>:10095" description="连接 funasr-realtime，先发送配置 JSON，再连续发送 16 kHz、单声道、16-bit PCM 音频帧。" example={'Authorization: Bearer <ASR_REALTIME_TOKEN>\nSec-WebSocket-Protocol: binary\n\n{"mode":"2pass","audio_fs":16000,"chunk_size":[5,10,5],"chunk_interval":10,"is_speaking":true}\n\n{"is_speaking":false}'} />
                <ApiEndpoint method="GET" path="/v1/models" description="获取可用的语音识别模型列表。" example={'curl http://localhost:8080/v1/models \\\n  -H "Authorization: Bearer <ASR_API_TOKEN>"'} />
                <ApiEndpoint method="GET" path="/v1/system" description="获取网关及上游模型服务的运行状态。" example={'curl http://localhost:8080/v1/system \\\n  -H "Authorization: Bearer <ASR_API_TOKEN>"'} />
                <ApiEndpoint method="POST" path="/v1/audio/transcriptions" description="上传音频并使用指定模型返回转写结果。" example={'curl http://localhost:8080/v1/audio/transcriptions \\\n  -H "Authorization: Bearer <ASR_API_TOKEN>" \\\n  -F file=@meeting.wav \\\n  -F model=funasr'} />
              </Stack>
            </Paper>
          </Stack>
        </Container>
      </Box>
    </ThemeProvider>
  )
}

function ApiEndpoint({ method, path, description, example }) {
  return (
    <Accordion disableGutters elevation={0} sx={{ border: '1px solid', borderColor: 'divider', borderRadius: '8px !important', '&:before': { display: 'none' } }}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Chip label={method} color={method === 'POST' ? 'primary' : 'default'} size="small" sx={{ fontWeight: 700 }} />
          <Typography component="code" fontFamily="monospace" fontWeight={700}>{path}</Typography>
        </Stack>
      </AccordionSummary>
      <AccordionDetails>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>{description}</Typography>
        <Box component="pre" sx={{ m: 0, p: 2, overflowX: 'auto', borderRadius: 2, bgcolor: 'grey.100', fontFamily: 'monospace', fontSize: 13, whiteSpace: 'pre-wrap' }}>
          {example}
        </Box>
      </AccordionDetails>
    </Accordion>
  )
}

function readText(body) {
  try {
    return JSON.parse(body).text
  } catch {
    return ''
  }
}

function readError(body) {
  try {
    return JSON.parse(body).error
  } catch {
    return ''
  }
}

createRoot(document.getElementById('root')).render(<App />)
