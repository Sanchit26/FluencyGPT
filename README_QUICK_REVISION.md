# FluencyGPT Quick Revision README

## Project in Simple Words
FluencyGPT is a Flask-based speech-fluency correction project. It accepts either typed text or recorded audio, converts speech to text (ASR), detects disfluencies like repetitions/fillers/broken starts, and rewrites the sentence into fluent English. It runs offline-friendly with rule-based logic, and can optionally use OpenRouter LLM rewriting when an API key is configured. The frontend is a single HTML page and the backend exposes clean JSON APIs.

## One-Line File Guide (All Project Files)

### Root Files
- `.env` - Local runtime environment variables (API keys, host/port, ASR toggle, limits).
- `.env.example` - Template env file showing what variables you should configure.
- `app.py` - Root launcher that adds `src` to path and starts the Flask app.
- `FrontendUI.html` - Browser UI for typing/recording speech and showing cleaned output.
- `pyproject.toml` - Project metadata and tool settings (pytest/format config).
- `pytest.ini` - Pytest configuration with `src` path setup.
- `README.md` - Main project documentation and API usage examples.
- `README_QUICK_REVISION.md` - Quick explanation + full file map for fast revision.
- `requirements.txt` - Python dependency list for the project.
- `run_dev.ps1` - Windows script to start the backend in development mode.
- `run_tests.ps1` - Windows script to run all automated tests.
- `TestAudio.wav` - Sample audio file for testing/demo input.

### Root Package Shim (for easy `python -m fluencygpt`)
- `fluencygpt/__init__.py` - Shim package that points Python to the real `src/fluencygpt` code.
- `fluencygpt/__main__.py` - Shim entrypoint that forwards execution to `src/fluencygpt/__main__.py`.

### Main Backend Package (`src/fluencygpt`)
- `src/fluencygpt/__init__.py` - Marks the backend as a Python package.
- `src/fluencygpt/__main__.py` - Main CLI entrypoint (`python -m fluencygpt`) with server options.
- `src/fluencygpt/app.py` - Flask app factory, blueprint registration, CORS, and frontend route.
- `src/fluencygpt/config.py` - Reads environment settings into a structured config object.

### Routes
- `src/fluencygpt/routes/__init__.py` - Route package marker and module description.
- `src/fluencygpt/routes/api.py` - Core API endpoints (`/health`, `/detect`, `/rewrite`, `/pipeline`, etc.).
- `src/fluencygpt/routes/voice.py` - Voice endpoint (`/process-audio`) for mic audio pipeline.

### Services
- `src/fluencygpt/services/__init__.py` - Service package marker and description.
- `src/fluencygpt/services/asr_service.py` - Audio decoding/conversion + speech-to-text logic.
- `src/fluencygpt/services/disfluency_service.py` - Rule-based disfluency detector with span metadata.
- `src/fluencygpt/services/rewrite_service.py` - Fluency rewrite engine (rule-based + optional OpenRouter LLM).

### Utilities
- `src/fluencygpt/utils/__init__.py` - Utility package marker and description.
- `src/fluencygpt/utils/http.py` - Shared HTTP JSON error helpers.
- `src/fluencygpt/utils/text.py` - Shared text normalization helpers.

### Tests
- `tests/test_disfluency_detector.py` - Verifies detection of required disfluency types.
- `tests/test_health.py` - Verifies health endpoint returns success.
- `tests/test_process_audio.py` - Verifies voice-audio pipeline behavior and error handling.
- `tests/test_rewrite_service.py` - Verifies rewrite rules, LLM usage path, and fallback behavior.
- `tests/test_voice.py` - Verifies `/voice` endpoint validation and ASR-disabled behavior.

## Note on Excluded Files
Generated/runtime folders like `.venv`, `.pytest_cache`, `__pycache__`, `.git`, and `.vscode` are intentionally not listed above because they are environment/tooling artifacts, not core project source files.
