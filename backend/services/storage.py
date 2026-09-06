import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from errors import AppError
from services.audio_probe import ProbeResult

_BACKEND_DIR = Path(__file__).resolve().parent.parent
AUDIO_DIR = _BACKEND_DIR / "storage" / "audio"
AUDIO_TTL = timedelta(hours=24)
AUDIO_ID_PATTERN = re.compile(r"^aud_[0-9a-f]{32}$")


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


def load_audio(audio_id: str) -> tuple[bytes, dict]:
    if not AUDIO_ID_PATTERN.fullmatch(audio_id or ""):
        raise AppError(
            404,
            "AUDIO_ID_NOT_FOUND",
            "录音不存在或已过期，请重新上传。",
            "asr",
        )

    media_path = AUDIO_DIR / f"{audio_id}.webm"
    meta_path = AUDIO_DIR / f"{audio_id}.json"
    if not media_path.is_file() or not meta_path.is_file():
        raise AppError(
            404,
            "AUDIO_ID_NOT_FOUND",
            "录音不存在或已过期，请重新上传。",
            "asr",
        )

    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        created_at = datetime.fromisoformat(str(metadata["created_at"]))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError(
            404,
            "AUDIO_ID_NOT_FOUND",
            "录音不存在或已过期，请重新上传。",
            "asr",
        ) from exc

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created_at > AUDIO_TTL:
        raise AppError(
            404,
            "AUDIO_ID_NOT_FOUND",
            "录音不存在或已过期，请重新上传。",
            "asr",
        )

    return media_path.read_bytes(), metadata
