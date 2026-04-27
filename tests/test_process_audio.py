import io

from fluencygpt.app import create_app


def test_process_audio_requires_audio_field():
    app = create_app()
    client = app.test_client()
    resp = client.post("/process-audio")
    assert resp.status_code == 400
    assert "audio" in resp.get_json()["error"].lower()


def test_process_audio_rejects_empty_upload():
    app = create_app()
    client = app.test_client()
    resp = client.post(
        "/process-audio",
        data={"audio": (io.BytesIO(b""), "")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400


def test_process_audio_returns_error_when_asr_disabled(monkeypatch):
    """Without ENABLE_ONLINE_ASR=1 the endpoint should return a 422 with an error message."""
    monkeypatch.delenv("ENABLE_ONLINE_ASR", raising=False)

    app = create_app()
    client = app.test_client()

    resp = client.post(
        "/process-audio",
        data={"audio": (io.BytesIO(b"fake-wav-bytes"), "recording.wav")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 422
    body = resp.get_json()
    assert "error" in body
    assert "original_text" in body
    assert "clean_text" in body


def test_process_audio_returns_string_clean_text_when_rewrite_returns_dict(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(
        "fluencygpt.routes.voice.transcribe_audio_file",
        lambda _file: {"text": "I I want to go"},
    )
    monkeypatch.setattr(
        "fluencygpt.routes.voice.rewrite_text",
        lambda text: {"original": text, "fluent": "I want to go", "llm_used": True},
    )

    resp = client.post(
        "/process-audio",
        data={"audio": (io.BytesIO(b"fake-webm-bytes"), "recording.webm")},
        content_type="multipart/form-data",
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["original_text"] == "I I want to go"
    assert body["clean_text"] == "I want to go"
