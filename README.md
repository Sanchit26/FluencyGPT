# FluencyGPT (Backend)

Flask-based backend for **FluencyGPT: Automatic Stuttering Correction**.

Demo note (offline + stable):
This repo is structured so the rewrite step can be swapped to an LLM-backed implementation,
but the default is a deterministic, rule-based rewriter to keep the project fully offline and demo-safe.

## Features
- `/health` server status
- `/asr` audio upload → ASR transcript (SpeechRecognition)
- `/detect` text → detected disfluency segments (regex NLP)
- `/rewrite` text → fluent rewrite (rule-based, offline)
- `/pipeline` audio upload OR text → detection + rewrite
- `/voice` audio upload → ASR → detection + rewrite

## Local setup (Windows)

### 1) Create venv + install deps
```powershell
cd c:\Projects\FluencyGPT
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2) Configure environment (optional)
No API keys are required for offline rule-based rewriting.

To enable LLM rewriting via OpenRouter, set in `.env`:
```env
OPENROUTER_API_KEY=your-key
# Optional: force a specific model ID
OPENROUTER_MODEL=openai/gpt-4o-mini
```

### 3) Run the server
Development:
```powershell
./run_dev.ps1
```

Alternative:
```powershell
python -m fluencygpt
```

Production-ish (Windows-friendly):
```powershell
python -m fluencygpt --serve waitress
```

## ASR notes
This backend uses the `SpeechRecognition` library.
- It works best with **WAV PCM** input.
- If you upload MP3/M4A, you typically need conversion (often via FFmpeg). This project keeps dependencies minimal and expects WAV for best reliability.

## API quick examples

Notes:
- For a fully offline demo, use JSON text with `/detect`, `/rewrite`, and `/pipeline`.
- `/asr` is disabled by default; it can be enabled with `ENABLE_ONLINE_ASR=1` (uses online Google recognizer).
- `/voice` is also disabled by default and requires `ENABLE_ONLINE_ASR=1`.

### Health
```bash
curl http://127.0.0.1:5000/health
```

### Detect
```bash
curl -X POST http://127.0.0.1:5000/detect \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"I I I want to um go to the store\"}"
```

### Rewrite
PowerShell:
```powershell
Invoke-WebRequest `
  -Uri http://127.0.0.1:5000/rewrite `
  -Method POST `
  -Headers @{ "Content-Type" = "application/json" } `
  -Body '{ "text": "I I I want to um go to the store" }'
```

Response shape:
- `original`: input text
- `fluent`: rewritten text
- `engine`: `openrouter` or `rule-based`
- `llm_used`: `true` when OpenRouter produced the final output

### ASR
```bash
curl -X POST http://127.0.0.1:5000/asr \
  -F "audio=@sample.wav"
```

### Pipeline
Offline (text-only) PowerShell:
```powershell
Invoke-WebRequest `
  -Uri http://127.0.0.1:5000/pipeline `
  -Method POST `
  -Headers @{ "Content-Type" = "application/json" } `
  -Body '{ "text": "I I I want t t to go home" }'
```

Audio pipeline (requires online ASR):
```powershell
$env:ENABLE_ONLINE_ASR = "1"
# PowerShell 5.1: use curl.exe for multipart form upload
curl.exe -X POST http://127.0.0.1:5000/pipeline -F "audio=@sample.wav"

# PowerShell 7+: you can also use Invoke-RestMethod -Form
# Invoke-RestMethod -Uri http://127.0.0.1:5000/pipeline -Method POST -Form @{ audio = Get-Item .\sample.wav }
```

### Voice
WAV (preferred):
```powershell
$env:ENABLE_ONLINE_ASR = "1"
# PowerShell 5.1: use curl.exe for multipart form upload
curl.exe -X POST http://127.0.0.1:5000/voice -F "audio=@sample.wav"

# PowerShell 7+: you can also use Invoke-RestMethod -Form
# Invoke-RestMethod -Uri http://127.0.0.1:5000/voice -Method POST -Form @{ audio = Get-Item .\sample.wav }
```

MP3 (allowed if ffmpeg is installed for conversion):
```powershell
$env:ENABLE_ONLINE_ASR = "1"
curl.exe -X POST http://127.0.0.1:5000/voice -F "audio=@sample.mp3"
```

