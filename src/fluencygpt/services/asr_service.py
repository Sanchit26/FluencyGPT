from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Any

import speech_recognition as sr
from werkzeug.datastructures import FileStorage


def _find_ffmpeg() -> str | None:
    """Return the ffmpeg executable path if available on PATH."""

    return shutil.which("ffmpeg")


def _convert_to_wav_if_needed(src_path: str, src_ext: str) -> tuple[str, bool]:
    """Convert audio to WAV (PCM) if needed.

    SpeechRecognition's AudioFile supports WAV/AIFF/FLAC.
    For MP3/M4A we optionally use ffmpeg if present on PATH.

    Returns:
    - (read_path, created_temp) where created_temp indicates the returned path is a temp file
      that the caller must delete.
    """

    if src_ext in {".wav", ".aiff", ".aif", ".flac"}:
        return src_path, False

    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        raise ValueError(
            "Unsupported audio format for decoding without extra tools. "
            "Upload WAV/AIFF/FLAC, or install ffmpeg to enable MP3/M4A conversion."
        )

    out_fd, out_path = tempfile.mkstemp(suffix=".wav")
    os.close(out_fd)

    try:
        # Convert to mono 16kHz WAV for robust recognition.
        subprocess.run(
            [ffmpeg, "-y", "-i", src_path, "-ac", "1", "-ar", "16000", out_path],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:  # noqa: BLE001
        try:
            os.remove(out_path)
        except OSError:
            pass
        raise ValueError(f"Audio conversion failed (ffmpeg): {exc}") from exc

    return out_path, True


def transcribe_audio_file_online(file: FileStorage) -> dict[str, Any]:
    """Transcribe an uploaded audio file using SpeechRecognition + Google recognizer.

    Important constraint note:
    - SpeechRecognition's `recognize_google` is an ONLINE recognizer.
    - This is appropriate for demos on low-powered laptops because it avoids heavy local models.

    Audio handling:
    - WAV/AIFF/FLAC are supported directly.
    - MP3/M4A are accepted only if ffmpeg is installed (for conversion).
    """

    filename = file.filename or "uploaded"
    ext = os.path.splitext(filename)[1].lower()

    if ext not in {".wav", ".aiff", ".aif", ".flac", ".mp3", ".m4a"}:
        raise ValueError("Unsupported audio format. Please upload WAV (preferred), AIFF, FLAC, or MP3.")

    recognizer = sr.Recognizer()

    # Write to a temporary file because SpeechRecognition expects a filesystem path.
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp_path = tmp.name
        data = file.stream.read()
        if not data:
            raise ValueError("Uploaded audio file is empty")
        tmp.write(data)

    converted_path: str | None = None
    try:
        read_path, created = _convert_to_wav_if_needed(tmp_path, ext)
        if created:
            converted_path = read_path

        with sr.AudioFile(read_path) as source:
            audio = recognizer.record(source)

        text = recognizer.recognize_google(audio)

        return {
            "text": text,
            "engine": "speech_recognition:recognize_google",
        }
    except sr.UnknownValueError:
        return {
            "text": "",
            "engine": "speech_recognition:recognize_google",
            "warning": "ASR could not understand audio (UnknownValueError)",
        }
    except sr.RequestError as exc:
        raise ValueError(f"ASR request failed: {exc}")
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        if converted_path:
            try:
                os.remove(converted_path)
            except OSError:
                pass


def transcribe_audio_file(file: FileStorage) -> dict[str, Any]:
    """Transcribe an uploaded audio file using SpeechRecognition.

    Implementation notes (important for reproducibility):
    - SpeechRecognition works reliably with WAV PCM.
    - For other formats (mp3/m4a), users should convert to WAV before upload.
        Offline demo behavior:
        - By default, this endpoint is DISABLED to keep the project fully offline and demo-safe.
        - If you explicitly enable it with ENABLE_ONLINE_ASR=1, it will use
            SpeechRecognition's Google Web Speech API backend (requires internet access).

    Returns:
    - text: recognized transcript
    - engine: recognizer backend
    - sample_rate_hz: if available
    """

    if os.getenv("ENABLE_ONLINE_ASR", "0") != "1":
        raise ValueError(
            "ASR is disabled for offline demo mode. "
            "Provide text to /detect, /rewrite, or /pipeline (JSON), or set ENABLE_ONLINE_ASR=1 to enable online ASR."
        )

    return transcribe_audio_file_online(file)
