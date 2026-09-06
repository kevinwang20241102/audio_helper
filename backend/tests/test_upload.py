from fastapi.testclient import TestClient

from main import app
from services.audio_probe import ProbeResult

client = TestClient(app)


def _patch_storage(monkeypatch, tmp_path):
    monkeypatch.setattr("services.storage.AUDIO_DIR", tmp_path)


def _patch_probe(
    monkeypatch,
    duration_seconds=2.5,
    format_name="matroska,webm",
    codec_name="opus",
):
    monkeypatch.setattr(
        "api.upload.probe_bytes",
        lambda content: ProbeResult(
            format_name=format_name,
            codec_name=codec_name,
            duration_seconds=duration_seconds,
        ),
    )


def test_upload_success_returns_audio_id(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)
    _patch_probe(monkeypatch)
    response = client.post(
        "/upload",
        files={"file": ("clip.webm", b"fake-webm-bytes", "audio/webm")},
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body.get("request_id"), str) and body["request_id"]
    audio_id = body["data"]["audio_id"]
    assert audio_id.startswith("aud_")
    assert (tmp_path / f"{audio_id}.webm").is_file()
    meta = (tmp_path / f"{audio_id}.json").read_text(encoding="utf-8")
    assert "created_at" in meta
    assert "storage" not in audio_id
    assert "\\" not in audio_id
    assert "/" not in audio_id


def test_upload_unsupported_format(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)
    _patch_probe(monkeypatch, format_name="mp3", codec_name="mp3")
    response = client.post(
        "/upload",
        files={"file": ("clip.mp3", b"fake-mp3-bytes", "audio/mpeg")},
    )
    assert response.status_code == 415
    body = response.json()
    assert body["error"]["code"] == "AUDIO_UNSUPPORTED"
    assert body["error"]["stage"] == "upload"
    assert body["error"]["message"]


def test_upload_too_large(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)
    _patch_probe(monkeypatch)
    payload = b"x" * (5 * 1024 * 1024 + 1)
    response = client.post(
        "/upload",
        files={"file": ("clip.webm", payload, "audio/webm")},
    )
    assert response.status_code == 413
    body = response.json()
    assert body["error"]["code"] == "AUDIO_TOO_LARGE"
    assert body["error"]["stage"] == "upload"


def test_upload_duration_too_short(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)
    _patch_probe(monkeypatch, duration_seconds=0.4)
    response = client.post(
        "/upload",
        files={"file": ("clip.webm", b"fake-webm-bytes", "audio/webm")},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "AUDIO_DURATION_INVALID"
    assert body["error"]["stage"] == "upload"


def test_upload_duration_too_long(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)
    _patch_probe(monkeypatch, duration_seconds=61)
    response = client.post(
        "/upload",
        files={"file": ("clip.webm", b"fake-webm-bytes", "audio/webm")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AUDIO_DURATION_INVALID"


def test_upload_duration_unknown(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)
    _patch_probe(monkeypatch, duration_seconds=None)
    response = client.post(
        "/upload",
        files={"file": ("clip.webm", b"fake-webm-bytes", "audio/webm")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AUDIO_DURATION_INVALID"


def test_upload_missing_file_uses_unified_error():
    response = client.post("/upload")
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["stage"] == "upload"
    assert "request_id" in body
