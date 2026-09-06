import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from services.audio_probe import ProbeResult

_BACKEND_DIR = Path(__file__).resolve().parent.parent
AUDIO_DIR = _BACKEND_DIR / "storage" / "audio"


def persist_upload(
    content: bytes,
    probe: ProbeResult,
    original_filename: str | None,
) -> str:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    audio_id = f"aud_{uuid4().hex}"
    media_path = AUDIO_DIR / f"{audio_id}.webm"
    meta_path = AUDIO_DIR / f"{audio_id}.json"
    created_at = datetime.now(timezone.utc).isoformat()
    media_path.write_bytes(content)
    metadata = {
        "audio_id": audio_id,
        "created_at": created_at,
        "duration_seconds": probe.duration_seconds,
        "size_bytes": len(content),
        "format_name": probe.format_name,
        "codec_name": probe.codec_name,
        "original_filename": original_filename,
    }
    meta_path.write_text(
        json.dumps(metadata, ensure_ascii=False),
        encoding="utf-8",
    )
    return audio_id


def persist_upload(
    content: bytes,
    probe: ProbeResult,
    original_filename: str | None,
) -> str:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    audio_id = f"aud_{uuid4().hex}"
    media_path = AUDIO_DIR / f"{audio_id}.webm"
    meta_path = AUDIO_DIR / f"{audio_id}.json"
    created_at = datetime.now(timezone.utc).isoformat()
    media_path.write_bytes(content)
    metadata = {
        "audio_id": audio_id,
        "created_at": created_at,
        "duration_seconds": probe.duration_seconds,
        "size_bytes": len(content),
        "format_name": probe.format_name,
        "codec_name": probe.codec_name,
        "original_filename": original_filename,
    }
    meta_path.write_text(
        json.dumps(metadata, ensure_ascii=False),
        encoding="utf-8",
    )
    return audio_id
