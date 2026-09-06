from fastapi import APIRouter, Request

from schemas import AsrData, AsrRequest, AsrResponse
from services.asr import recognize_audio
from services.storage import load_audio

router = APIRouter()


@router.post("/asr", response_model=AsrResponse)
async def asr(request: Request, body: AsrRequest) -> AsrResponse:
    content, _metadata = load_audio(body.audio_id)
    text = await recognize_audio(content)
    return AsrResponse(
        request_id=request.state.request_id,
        data=AsrData(text=text),
    )
