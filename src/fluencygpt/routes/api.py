from __future__ import annotations

from flask import Blueprint, jsonify, request

from fluencygpt.services.asr_service import transcribe_audio_file
from fluencygpt.services.disfluency_service import detect_disfluencies
from fluencygpt.services.rewrite_service import rewrite_text
from fluencygpt.utils.http import bad_request, server_error

api_bp = Blueprint("api", __name__)


@api_bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@api_bp.post("/asr")
def asr():
    """Accept an audio file and return raw ASR transcript.

    Form-data field: `audio`

    Notes:
    - `SpeechRecognition` works best with WAV PCM.
    - If format is unsupported, an informative error is returned.
    """

    if "audio" not in request.files:
        return bad_request("Missing form-data file field 'audio'")

    audio_file = request.files["audio"]
    if not audio_file or audio_file.filename == "":
        return bad_request("Empty file upload")

    try:
        result = transcribe_audio_file(audio_file)
        return jsonify(result)
    except ValueError as exc:
        return bad_request(str(exc))
    except Exception as exc:  # noqa: BLE001
        return server_error(f"ASR failed: {exc}")


@api_bp.post("/detect")
def detect():
    """Accept text and return detected disfluency segments."""

    payload = request.get_json(silent=True) or {}
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return bad_request("JSON body must include non-empty 'text'")

    include_debug = bool(payload.get("debug"))

    result = detect_disfluencies(text, include_debug=include_debug)
    return jsonify(result)


@api_bp.post("/rewrite")
def rewrite():
    """Accept text and return fluent corrected text.

    JSON: {"text": "...", "hints": {...} (optional) }

    This endpoint performs a small deterministic cleanup, then uses OpenRouter (LLM)
    for meaning-preserving fluency correction, with a rule-based fallback if the API fails.
    """

    payload = request.get_json(silent=True) or {}
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return bad_request("JSON body must include non-empty 'text'")

    hints = payload.get("hints") if isinstance(payload.get("hints"), dict) else None

    try:
        return jsonify(rewrite_text(text=text, hints=hints))
    except ValueError as exc:
        return bad_request(str(exc))
    except Exception as exc:  # noqa: BLE001
        return server_error(f"Rewrite failed: {exc}")


@api_bp.post("/pipeline")
def pipeline():
    """Full pipeline:
    - If `audio` is provided: ASR -> detection -> rewrite
    - Else: text -> detection -> rewrite

    Accepts either:
    - multipart/form-data with file field `audio`
    - application/json with {"text": "..."}
    """

    transcript: str | None = None

    # Case 1: audio upload
    if "audio" in request.files:
        audio_file = request.files["audio"]
        if not audio_file or audio_file.filename == "":
            return bad_request("Empty file upload")
        try:
            asr_result = transcribe_audio_file(audio_file)
            transcript = asr_result.get("text")
        except ValueError as exc:
            return bad_request(str(exc))
        except Exception as exc:  # noqa: BLE001
            return server_error(f"ASR failed: {exc}")

    # Case 2: JSON text
    if transcript is None:
        payload = request.get_json(silent=True) or {}
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return bad_request("Provide either form-data 'audio' or JSON 'text'")
        transcript = text

    detection = detect_disfluencies(transcript)

    try:
        rewrite = rewrite_text(
            text=transcript,
            hints={
                "detected": detection.get("segments"),
                "summary": detection.get("summary"),
            },
        )
    except ValueError as exc:
        return server_error(str(exc))
    except Exception as exc:  # noqa: BLE001
        return server_error(f"Rewrite failed: {exc}")

    return jsonify(
        {
            "asr": {"text": transcript} if "audio" in request.files else None,
            "text": transcript if "audio" not in request.files else None,
            "detection": detection,
            "rewrite": rewrite,
        }
    )


@api_bp.post("/voice")
def voice():
    """Voice mode: audio upload -> ASR -> detection -> fluency rewrite.

    Why SpeechRecognition is used:
    - It's lightweight and a good fit for low-powered demo machines.
    - The resulting ASR transcript is realistic stutter-y input that our deterministic
      detection + rewriting can clean up reliably.

    Note:
    - SpeechRecognition's Google recognizer is an ONLINE recognizer.
    - To keep demos offline-safe by default, ASR is gated behind ENABLE_ONLINE_ASR=1.
    """

    if "audio" not in request.files:
        return bad_request("Missing form-data file field 'audio'")

    audio_file = request.files["audio"]
    if not audio_file or audio_file.filename == "":
        return bad_request("Empty file upload")

    try:
        asr_result = transcribe_audio_file(audio_file)
    except ValueError as exc:
        # Includes offline-disabled mode, unsupported format, and ASR request errors.
        return jsonify({"error": str(exc)}), 501
    except Exception as exc:  # noqa: BLE001
        return server_error(f"ASR failed: {exc}")

    asr_text = (asr_result.get("text") or "").strip()
    detected = detect_disfluencies(asr_text)

    fluent = ""
    if asr_text:
        try:
            fluent = rewrite_text(
                text=asr_text,
                hints={
                    "detected": detected.get("segments"),
                    "summary": detected.get("summary"),
                },
            ).get("fluent", "")
        except ValueError as exc:
            return server_error(str(exc))
        except Exception as exc:  # noqa: BLE001
            return server_error(f"Rewrite failed: {exc}")

    return jsonify(
        {
            "asr_text": asr_text,
            "detected_disfluencies": detected,
            "fluent": fluent,
        }
    )
