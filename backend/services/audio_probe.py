import json
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from errors import AppError

MAX_FILE_BYTES = 5 * 1024 * 1024
MIN_DURATION_SECONDS = 1.0
MAX_DURATION_SECONDS = 60.0
PROBE_TIMEOUT_SECONDS = 3


@dataclass
class ProbeResult:
    format_name: str
    codec_name: str
    duration_seconds: float | None


@lru_cache(maxsize=1)
def resolve_ffprobe() -> str | None:
    from config import settings

    configured = (settings.ffprobe_path or "").strip()
    if configured:
        configured_path = Path(configured)
        if configured_path.is_file():
            return str(configured_path)

    found = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if found:
        return found

    winget_root = (
        Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    )
    if winget_root.is_dir():
        matches = sorted(winget_root.glob("Gyan.FFmpeg*/ffmpeg-*/bin/ffprobe.exe"))
        if matches:
            return str(matches[-1])
    return None


def ffprobe_available() -> bool:
    return resolve_ffprobe() is not None


def _ffprobe_bin() -> str:
    path = resolve_ffprobe()
    if not path:
        raise AppError(
            503,
            "PROBE_UNAVAILABLE",
            "服务器缺少音频探测工具 ffprobe，请安装 FFmpeg 后重试。",
            "upload",
        )
    return path


def probe_bytes(content: bytes) -> ProbeResult:
    if not ffprobe_available():
        raise AppError(
            503,
            "PROBE_UNAVAILABLE",
            "服务器缺少音频探测工具 ffprobe，请安装 FFmpeg 后重试。",
            "upload",
        )

    from services.storage import AUDIO_DIR

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = AUDIO_DIR / f".probe_{uuid4().hex}.webm"
    try:
        tmp_path.write_bytes(content)
        return probe_audio(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def probe_audio(path: Path) -> ProbeResult:
    command = [
        _ffprobe_bin(),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        completed = _run_ffprobe(command)
    except subprocess.TimeoutExpired as exc:
        raise AppError(
            504,
            "UPSTREAM_TIMEOUT",
            "音频探测超时，请稍后重试。",
            "upload",
        ) from exc
    except OSError as exc:
        raise AppError(
            503,
            "PROBE_UNAVAILABLE",
            "服务器缺少音频探测工具 ffprobe，请安装 FFmpeg 后重试。",
            "upload",
        ) from exc

    stdout = _decode_ffprobe_output(completed.stdout)
    if completed.returncode != 0:
        raise AppError(
            415,
            "AUDIO_UNSUPPORTED",
            "录音格式不受支持，请使用支持 WebM/Opus 的浏览器重新录制。",
            "upload",
        )

    try:
        payload = json.loads(stdout or "{}")
    except json.JSONDecodeError as exc:
        raise AppError(
            415,
            "AUDIO_UNSUPPORTED",
            "录音格式不受支持，请使用支持 WebM/Opus 的浏览器重新录制。",
            "upload",
        ) from exc

    format_info = payload.get("format") or {}
    streams = payload.get("streams") or []
    audio_streams = [item for item in streams if item.get("codec_type") == "audio"]
    if not audio_streams:
        raise AppError(
            415,
            "AUDIO_UNSUPPORTED",
            "录音格式不受支持，请使用支持 WebM/Opus 的浏览器重新录制。",
            "upload",
        )

    format_name = str(format_info.get("format_name") or "")
    codec_name = str(audio_streams[0].get("codec_name") or "")
    duration = _parse_duration(format_info.get("duration"))
    if duration is None:
        duration = _parse_duration(audio_streams[0].get("duration"))
    if duration is None:
        duration = _duration_from_packet_timestamps(path)

    return ProbeResult(
        format_name=format_name,
        codec_name=codec_name,
        duration_seconds=duration,
    )


def validate_probe(probe: ProbeResult) -> None:
    format_name = probe.format_name.lower()
    if "webm" not in format_name and "matroska" not in format_name:
        raise AppError(
            415,
            "AUDIO_UNSUPPORTED",
            "录音格式不受支持，请使用支持 WebM/Opus 的浏览器重新录制。",
            "upload",
        )
    if probe.codec_name.lower() != "opus":
        raise AppError(
            415,
            "AUDIO_UNSUPPORTED",
            "录音编码不受支持，请使用 WebM/Opus。",
            "upload",
        )
    if probe.duration_seconds is None:
        raise AppError(
            422,
            "AUDIO_DURATION_INVALID",
            "无法确认录音时长，请重新录制。",
            "upload",
        )
    if not (MIN_DURATION_SECONDS <= probe.duration_seconds <= MAX_DURATION_SECONDS):
        raise AppError(
            422,
            "AUDIO_DURATION_INVALID",
            "录音时长需在 1—60 秒之间，请重新录制。",
            "upload",
        )


def _parse_duration(value: object) -> float | None:
    if value is None or value == "" or value == "N/A":
        return None
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return None
    if duration <= 0:
        return None
    return duration


def _duration_from_packet_timestamps(path: Path) -> float | None:
    pts_times = _packet_floats(path, "pts_time")
    if len(pts_times) >= 2:
        return max(pts_times[-1] - pts_times[0], 0.0) or None
    if len(pts_times) == 1 and pts_times[0] > 0:
        return pts_times[0]

    duration_times = _packet_floats(path, "duration_time")
    if duration_times:
        total = sum(duration_times)
        return total if total > 0 else None
    return None


def _packet_floats(path: Path, field: str) -> list[float]:
    command = [
        _ffprobe_bin(),
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        f"packet={field}",
        "-of",
        "csv=p=0",
        str(path),
    ]
    try:
        completed = _run_ffprobe(command)
    except (OSError, subprocess.TimeoutExpired):
        return []

    values: list[float] = []
    for line in _decode_ffprobe_output(completed.stdout).splitlines():
        token = line.strip().rstrip(",")
        if not token or token == "N/A":
            continue
        try:
            values.append(float(token))
        except ValueError:
            continue
    return values


def _run_ffprobe(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        capture_output=True,
        timeout=PROBE_TIMEOUT_SECONDS,
        check=False,
    )


def _decode_ffprobe_output(raw: bytes | None) -> str:
    if not raw:
        return ""
    return raw.decode("utf-8", errors="replace")
