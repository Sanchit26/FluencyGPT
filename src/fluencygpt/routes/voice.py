from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from fluencygpt.services.asr_service import transcribe_audio_file
from fluencygpt.services.disfluency_service import detect_disfluencies
from fluencygpt.services.rewrite_service import rewrite_text
from fluencygpt.utils.http import bad_request, server_error

voice_bp = Blueprint("voice", __name__)
log = logging.getLogger(__name__)


@voice_bp.post("/process-audio")
def process_audio():
    """Accept mic-recorded audio, run the full fluency pipeline, return clean text.

    Form-data field: ``audio`` (WAV preferred; WebM/OGG/MP3/M4A accepted if ffmpeg is installed).

    Pipeline: ASR → disfluency detection → LLM rewrite (with rule-based fallback).

    Returns:
        {
            "original_text": "<raw ASR transcript>",
            "clean_text":    "<fluent rewritten text>"
        }

    Notes for frontend integration:
        const formData = new FormData();
        formData.append("audio", blob, "recording.wav");
        const res = await fetch("/process-audio", { method: "POST", body: formData });
        const { original_text, clean_text } = await res.json();
    """

    log.info(
        "process-audio: request received content_type=%s content_length=%s",
        request.content_type,
        request.content_length,
    )

    # --- 1. Validate upload ------------------------------------------------
    if "audio" not in request.files:
        return bad_request("No audio file received")

    audio_file = request.files["audio"]
    if not audio_file or audio_file.filename == "":
        return bad_request("No audio file received")

    log.info(
        "process-audio: upload filename=%s content_type=%s mimetype=%s",
        audio_file.filename,
        audio_file.content_type,
        getattr(audio_file, "mimetype", None),
    )

    # --- 2. ASR (speech-to-text) -------------------------------------------
    try:
        log.info("process-audio: ASR for %s", audio_file.filename)
        asr_result = transcribe_audio_file(audio_file)
    except ValueError as exc:
        # Covers: ASR disabled (ENABLE_ONLINE_ASR!=1), unsupported format, etc.
        log.warning("process-audio: ASR ValueError: %s", exc)
        return jsonify({"error": str(exc), "original_text": "", "clean_text": ""}), 422
    except Exception as exc:  # noqa: BLE001
        log.exception("process-audio: ASR exception")
        return server_error(f"ASR failed: {exc}")

    original_text = (asr_result.get("text") or "").strip()

    if not original_text:
        warning = (asr_result.get("warning") or "").strip()
        message = "ASR failed" if not warning else f"ASR failed: {warning}"
        return jsonify({"error": message, "original_text": "", "clean_text": ""}), 422

    # --- 3. Disfluency detection (informational, feeds into rewrite) -------
    detect_disfluencies(original_text)

    # --- 4. Rewrite (LLM with rule-based fallback) -------------------------
    try:
        rewrite_result = rewrite_text(text=original_text)
        if isinstance(rewrite_result, dict):
            clean_text = (rewrite_result.get("fluent") or "").strip() or original_text
        else:
            # Backward compatibility if rewrite_text is swapped with a legacy string-returning impl.
            clean_text = str(rewrite_result).strip() or original_text
    except Exception:  # noqa: BLE001
        # Graceful degradation: return the raw ASR transcript if rewrite fails.
        clean_text = original_text

    log.info("process-audio: original=%d chars, clean=%d chars", len(original_text), len(clean_text))
    return jsonify({"original_text": original_text, "clean_text": clean_text})
