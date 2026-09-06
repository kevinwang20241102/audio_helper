import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from main import app
from services.audio_probe import ProbeResult
from services.storage import persist_upload

client = TestClient(app)


def _patch_storage(monkeypatch, tmp_path):
    monkeypatch.setattr("services.storage.AUDIO_DIR", tmp_path)


def _save_clip(tmp_path, created_at=None):
    probe = ProbeResult(
        format_name="matroska,webm",
        codec_name="opus",
        duration_seconds=2.5,
    )
    audio_id = persist_upload(b"fake-webm-bytes", probe, "clip.webm")
    if created_at is not None:
        meta_path = tmp_path / f"{audio_id}.json"
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        metadata["created_at"] = created_at
        meta_path.write_text(json.dumps(metadata), encoding="utf-8")
    return audio_id


def test_asr_success_returns_recognized_text(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)
    audio_id = _save_clip(tmp_path)

    async def fake_recognize(content: bytes) -> str:
        assert content == b"fake-webm-bytes"
        return "我在杭州东站，朋友在西湖龙翔桥地铁站。"

    monkeypatch.setattr("api.asr.recognize_audio", fake_recognize)
    response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["text"] == "我在杭州东站，朋友在西湖龙翔桥地铁站。"
    assert body["request_id"]


def test_asr_missing_audio_id_uses_unified_error():
    response = client.post("/asr", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["stage"] == "asr"


def test_asr_unknown_id_returns_404(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)
    response = client.post(
        "/asr",
        json={"audio_id": "aud_ffffffffffffffffffffffffffffffff"},
    )
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "AUDIO_ID_NOT_FOUND"
    assert body["error"]["stage"] == "asr"


def test_asr_expired_id_returns_404(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)
    expired = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    audio_id = _save_clip(tmp_path, created_at=expired)
    response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "AUDIO_ID_NOT_FOUND"


def test_asr_empty_text_returns_422(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)
    audio_id = _save_clip(tmp_path)

    async def fake_recognize(_content: bytes) -> str:
        from errors import AppError

        raise AppError(422, "ASR_EMPTY", "没有听清你说的内容，请重新录音。", "asr")

    monkeypatch.setattr("api.asr.recognize_audio", fake_recognize)
    response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ASR_EMPTY"


def test_asr_timeout_returns_504(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)
    audio_id = _save_clip(tmp_path)

    async def fake_recognize(_content: bytes) -> str:
        from errors import AppError

        raise AppError(504, "UPSTREAM_TIMEOUT", "语音识别超时，请稍后重试。", "asr")

    monkeypatch.setattr("api.asr.recognize_audio", fake_recognize)
    response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "UPSTREAM_TIMEOUT"


def test_asr_upstream_error_returns_502(monkeypatch, tmp_path):
    _patch_storage(monkeypatch, tmp_path)
    audio_id = _save_clip(tmp_path)

    async def fake_recognize(_content: bytes) -> str:
        from errors import AppError

        raise AppError(502, "UPSTREAM_ERROR", "语音识别服务异常，请稍后重试。", "asr")

    monkeypatch.setattr("api.asr.recognize_audio", fake_recognize)
    response = client.post("/asr", json={"audio_id": audio_id})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "UPSTREAM_ERROR"


def test_encode_rejects_oversized_base64(monkeypatch):
    from errors import AppError
    from services.asr import encode_audio_data_uri

    monkeypatch.setattr("services.asr.MAX_ASR_PAYLOAD_BYTES", 16)
    try:
        encode_audio_data_uri(b"0123456789")
        assert False, "expected AppError"
    except AppError as exc:
        assert exc.status_code == 413
        assert exc.code == "AUDIO_TOO_LARGE"
        assert exc.stage == "asr"
