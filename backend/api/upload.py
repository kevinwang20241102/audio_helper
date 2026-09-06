from fastapi import APIRouter, File, Request, UploadFile

from errors import AppError
from schemas import UploadData, UploadResponse
from services.audio_probe import MAX_FILE_BYTES, probe_bytes, validate_probe
from services.storage import persist_upload

router = APIRouter()


@router.post("/upload", response_model=UploadResponse)
async def upload(
    request: Request,
    file: UploadFile = File(...),
) -> UploadResponse:
    content = await file.read(MAX_FILE_BYTES + 1)
    if not content:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            "录音文件为空，请重新录制。",
            "upload",
        )
    if len(content) > MAX_FILE_BYTES:
        raise AppError(
            413,
            "AUDIO_TOO_LARGE",
            "录音文件超过 5MB，请缩短录音后重试。",
            "upload",
        )

    probe = probe_bytes(content)
    validate_probe(probe)
    audio_id = persist_upload(content, probe, file.filename)
    return UploadResponse(
        request_id=request.state.request_id,
        data=UploadData(audio_id=audio_id),
    )
