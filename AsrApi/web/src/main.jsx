import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/roboto/400.css'
import '@fontsource/roboto/500.css'
import '@fontsource/roboto/700.css'
import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined'
import DescriptionOutlinedIcon from '@mui/icons-material/DescriptionOutlined'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import GraphicEqOutlinedIcon from '@mui/icons-material/GraphicEqOutlined'
import PlayArrowRoundedIcon from '@mui/icons-material/PlayArrowRounded'
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

function App() {
  const [token, setToken] = useState('')
  const [model, setModel] = useState('funasr')
  const [language, setLanguage] = useState('')
  const [file, setFile] = useState(null)
  const [result, setResult] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function transcribe() {
    if (!file || !token) {
      setError('请选择音频文件并填写 API Token。')
      return
    }

    setError('')
    setResult('')
    setSubmitting(true)
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
    } catch (requestError) {
      setError(requestError.message || '无法连接到服务。')
    } finally {
      setSubmitting(false)
    }
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
            </Paper>

            <Paper elevation={0} sx={{ p: { xs: 3, sm: 4 }, border: '1px solid', borderColor: 'divider' }}>
              <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
                <DescriptionOutlinedIcon color="primary" />
                <Typography variant="h6" fontWeight={700}>API 接口说明</Typography>
              </Stack>
              <Stack spacing={1}>
                <ApiEndpoint method="GET" path="/healthz" description="检查网关是否正在运行，无需认证。" example="curl http://localhost:8080/healthz" />
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
