from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from typing import Any

import speech_recognition as sr
from werkzeug.datastructures import FileStorage


log = logging.getLogger(__name__)


def _find_ffmpeg() -> str | None:
    """Return the ffmpeg executable path if available on PATH."""

    return shutil.which("ffmpeg")


_MIMETYPE_TO_EXT: dict[str, str] = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/vnd.wave": ".wav",
    "audio/flac": ".flac",
    "audio/x-flac": ".flac",
    "audio/aiff": ".aiff",
    "audio/x-aiff": ".aiff",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/ogg": ".ogg",
    "audio/webm": ".webm",
    "video/webm": ".webm",
    "audio/mp4": ".m4a",
    "video/mp4": ".mp4",
}


def _sniff_extension_from_bytes(data: bytes) -> str | None:
    """Best-effort container sniff from header bytes.

    This is intentionally lightweight (no python-magic dependency).
    Returns a file extension (e.g., ".webm") or None if unknown.
    """

    if len(data) < 12:
        return None

    # WAV: RIFF....WAVE
    if data[0:4] == b"RIFF" and data[8:12] == b"WAVE":
        return ".wav"

    # OGG: OggS
    if data[0:4] == b"OggS":
        return ".ogg"

    # WebM/Matroska: EBML header 1A 45 DF A3
    if data[0:4] == b"\x1aE\xdf\xa3":
        return ".webm"

    # MP3: ID3 tag or frame sync
    if data[0:3] == b"ID3":
        return ".mp3"
    if data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return ".mp3"

    # MP4/M4A: ....ftyp
    if data[4:8] == b"ftyp":
        return ".mp4"

    return None


def _guess_audio_extension(file: FileStorage, data: bytes) -> str:
    """Determine a usable extension for the uploaded audio.

    Prefer Content-Type, then header sniffing, then fall back to filename extension.
    """

    content_type = (file.mimetype or file.content_type or "").split(";")[0].strip().lower()
    if content_type and content_type in _MIMETYPE_TO_EXT:
        return _MIMETYPE_TO_EXT[content_type]

    sniffed = _sniff_extension_from_bytes(data)
    if sniffed:
        return sniffed

    filename = file.filename or "uploaded"
    ext = os.path.splitext(filename)[1].lower()
    return ext or ".wav"


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
            "Upload WAV/AIFF/FLAC, or install ffmpeg to enable WebM/OGG/MP3/M4A conversion."
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

    # Read bytes once and infer the real container type. Do NOT trust the filename extension,
    # because browser MediaRecorder often uploads WebM/OGG but the UI may name it "recording.wav".
    data = file.stream.read()
    if not data:
        raise ValueError("Uploaded audio file is empty")

    ext = _guess_audio_extension(file, data)
    if ext not in {".wav", ".aiff", ".aif", ".flac", ".mp3", ".m4a", ".mp4", ".ogg", ".webm"}:
        raise ValueError("Unsupported audio format. Upload WAV/AIFF/FLAC, or install ffmpeg to decode WebM/OGG/MP3/M4A.")

    recognizer = sr.Recognizer()

    # Write to a temporary file because SpeechRecognition expects a filesystem path.
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp_path = tmp.name
        tmp.write(data)

    converted_path: str | None = None
    try:
        log.info(
            "ASR: content_type=%s guessed_ext=%s bytes=%d",
            (file.mimetype or file.content_type or ""),
            ext,
            len(data),
        )
        read_path, created = _convert_to_wav_if_needed(tmp_path, ext)
        if created:
            converted_path = read_path

        with sr.AudioFile(read_path) as source:
            audio = recognizer.record(source)

        log.info("ASR: recognize_google start")
        text = recognizer.recognize_google(audio)
        log.info("ASR: recognize_google success (%d chars)", len(text or ""))

        return {
            "text": text,
            "engine": "speech_recognition:recognize_google",
        }
    except sr.UnknownValueError:
        log.warning("ASR: UnknownValueError (unintelligible audio)")
        return {
            "text": "",
            "engine": "speech_recognition:recognize_google",
            "warning": "ASR could not understand audio (UnknownValueError)",
        }
    except sr.RequestError as exc:
        log.warning("ASR: RequestError: %s", exc)
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

    enabled = os.getenv("ENABLE_ONLINE_ASR", "0")
    log.info("ASR: ENABLE_ONLINE_ASR=%s", enabled)
    if enabled != "1":
        raise ValueError(
            "ASR is disabled for offline demo mode. "
            "Provide text to /detect, /rewrite, or /pipeline (JSON), or set ENABLE_ONLINE_ASR=1 to enable online ASR."
        )

    return transcribe_audio_file_online(file)
