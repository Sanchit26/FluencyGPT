# FluencyGPT Technical Logic README

Code-only condensed logic for each subsystem (15-20 lines each).

## 1. Application Initialization

```python
from dotenv import load_dotenv
from flask import Flask
from fluencygpt.config import get_settings
from fluencygpt.routes.api import api_bp
from fluencygpt.routes.voice import voice_bp

def create_app() -> Flask:
   settings = get_settings()
   app = Flask(__name__)
   app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_bytes
   app.register_blueprint(api_bp)
   app.register_blueprint(voice_bp)

   @app.after_request
   def cors(resp):
      resp.headers["Access-Control-Allow-Origin"] = "*"
      resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
      resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
      return resp

   return app
```

## 2. ASR Service Implementation

```python
import os, tempfile, speech_recognition as sr

def transcribe_audio_file(file):
   if os.getenv("ENABLE_ONLINE_ASR", "0") != "1":
      raise ValueError("ASR disabled; set ENABLE_ONLINE_ASR=1")

   data = file.stream.read()
   if not data:
      raise ValueError("Uploaded audio file is empty")

   ext = guess_audio_ext(file, data)             # content-type + byte sniffing
   src_path = write_temp_file(data, ext)         # SpeechRecognition uses file path
   read_path, created = convert_to_wav_if_needed(src_path, ext)

   try:
      r = sr.Recognizer()
      with sr.AudioFile(read_path) as source:
         audio = r.record(source)
      return {"text": r.recognize_google(audio), "engine": "speech_recognition:recognize_google"}
   finally:
      cleanup_temp(src_path, read_path if created else None)
```

## 3. Rule-Based Processing Implementation

```python
import re
FILLERS = {"uh", "um", "er", "erm", "ah"}

def rule_based_clean(text: str) -> str:
   text = normalize_whitespace(text)
   text = re.sub(r"\b([A-Za-z])(?:-\1)+-?([A-Za-z][A-Za-z']*)\b", r"\2", text)  # b-b-because
   toks = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?|\d+(?:\.\d+)?|\S", text)

   out, i = [], 0
   while i < len(toks):
      t = toks[i]
      if t.isalpha() and t.lower() in FILLERS:        # remove fillers
         i += 1; continue
      if i + 1 < len(toks) and t.isalpha() and toks[i + 1].isalpha() and t.lower() == toks[i + 1].lower():
         i += 1; continue                             # collapse repetitions
      t = re.sub(r"([A-Za-z])\1{2,}", r"\1", t)      # sssorry -> sorry
      out.append(t)
      i += 1

   return normalize_whitespace(join_tokens(out))
```

## 4. GPT-Based Models API Integration Implementation

```python
import json, urllib.request

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

def llm_rewrite(text: str, api_key: str, model: str) -> str:
   payload = {
      "model": model,
      "temperature": 0.1,
      "max_tokens": 128,
      "messages": [
         {"role": "system", "content": "Rewrite into fluent English; preserve meaning; output only rewritten text."},
         {"role": "user", "content": text},
      ],
   }
   req = urllib.request.Request(
      OPENROUTER_URL,
      data=json.dumps(payload).encode("utf-8"),
      method="POST",
      headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "X-Title": "FluencyGPT"},
   )
   with urllib.request.urlopen(req, timeout=12) as resp:
      body = json.loads(resp.read().decode("utf-8"))
   return body["choices"][0]["message"]["content"].strip()
```

## 5. Fallback Mechanism Implementation

```python
import os

DEFAULT_MODELS = ["openai/gpt-4o-mini", "meta-llama/llama-3.1-8b-instruct:free", "mistralai/mistral-7b-instruct:free"]

def rewrite_text(text: str) -> dict:
   baseline = rule_based_clean(text)
   api_key = (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
   if not api_key:
      return {"original": text, "fluent": baseline, "engine": "rule-based", "llm_used": False, "llm_reason": "missing_api_key"}

   model = (os.getenv("OPENROUTER_MODEL") or "").strip()
   candidates = [model] if model else DEFAULT_MODELS
   last_error = ""

   for m in candidates:
      try:
         fluent = llm_rewrite(pre_normalize(text), api_key, m)
         if fluent:
            return {"original": text, "fluent": fluent, "engine": "openrouter", "llm_used": True, "llm_model": m}
      except Exception as exc:
         last_error = str(exc)
   return {"original": text, "fluent": baseline, "engine": "rule-based", "llm_used": False, "llm_reason": last_error or "llm_unavailable"}
```

## 6. Configuration Management

```python
import os
from dataclasses import dataclass
from dotenv import load_dotenv

@dataclass(frozen=True)
class Settings:
   host: str = os.getenv("HOST", "127.0.0.1")
   port: int = int(os.getenv("PORT", "5000"))
   max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))

def get_settings() -> Settings:
   return Settings()

def boot():
   load_dotenv(override=False)
   s = get_settings()
   return {
      "host": s.host, "port": s.port, "max_upload_bytes": s.max_upload_bytes,
      "online_asr": os.getenv("ENABLE_ONLINE_ASR", "0"),
      "llm_enabled": bool((os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()),
   }
```

## 7. Testing with pytest

```python
import io
from fluencygpt.app import create_app
from fluencygpt.services.disfluency_service import detect_disfluencies
from fluencygpt.services.rewrite_service import rewrite_text

def test_core_pipeline(monkeypatch):
   app = create_app(); client = app.test_client()
   assert client.get("/health").status_code == 200

   monkeypatch.delenv("ENABLE_ONLINE_ASR", raising=False)
   r = client.post("/process-audio", data={"audio": (io.BytesIO(b"x"), "a.wav")}, content_type="multipart/form-data")
   assert r.status_code in (422, 501)

   d = detect_disfluencies("I I I want to um g g go")
   assert "word_repetition" in [s["type"] for s in d["segments"]]

   monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
   out = rewrite_text("I I want to um go")
   assert out["engine"] == "rule-based" and out["fluent"]
```
