import io

from fluencygpt.app import create_app


def test_voice_requires_audio_file():
    app = create_app()
    client = app.test_client()
    resp = client.post("/voice")
    assert resp.status_code == 400


def test_voice_returns_501_when_asr_disabled(monkeypatch):
    # /voice is intentionally demo-safe: online ASR is opt-in.
    monkeypatch.delenv("ENABLE_ONLINE_ASR", raising=False)

    app = create_app()
    client = app.test_client()

    resp = client.post(
        "/voice",
        data={"audio": (io.BytesIO(b"not-a-real-wav"), "sample.wav")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 501
