import base64
import logging
import time

import httpx

from config import settings
from errors import AppError

logger = logging.getLogger(__name__)

MAX_ASR_PAYLOAD_BYTES = 10 * 1024 * 1024
ASR_TIMEOUT_SECONDS = 18


def encode_audio_data_uri(content: bytes) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    data_uri = f"data:audio/webm;base64,{encoded}"
    if len(data_uri.encode("utf-8")) > MAX_ASR_PAYLOAD_BYTES:
        raise AppError(
            413,
            "AUDIO_TOO_LARGE",
            "编码后的录音超过识别服务限制，请缩短录音后重试。",
            "asr",
        )
    return data_uri


def _extract_text(payload: dict) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "语音识别服务返回异常，请稍后重试。",
            "asr",
        )
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "语音识别服务返回异常，请稍后重试。",
            "asr",
        )
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts).strip()
    raise AppError(
        502,
        "UPSTREAM_ERROR",
        "语音识别服务返回异常，请稍后重试。",
        "asr",
    )


async def recognize_audio(content: bytes) -> str:
    if not settings.bailian_api_key:
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "语音识别服务未配置密钥。",
            "asr",
        )

    data_uri = encode_audio_data_uri(content)
    payload = {
        "model": settings.asr_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": data_uri},
                    }
                ],
            }
        ],
        "stream": False,
        "asr_options": {
            "language": "zh",
            "enable_itn": False,
        },
    }
    headers = {
        "Authorization": f"Bearer {settings.bailian_api_key}",
        "Content-Type": "application/json",
    }

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=ASR_TIMEOUT_SECONDS) as client:
            response = await client.post(
                settings.asr_url,
                headers=headers,
                json=payload,
            )
    except httpx.TimeoutException as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.error("asr timeout elapsed_ms=%s", elapsed_ms)
        raise AppError(
            504,
            "UPSTREAM_TIMEOUT",
            "语音识别超时，请稍后重试。",
            "asr",
        ) from exc
    except httpx.HTTPError as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.error("asr upstream error elapsed_ms=%s", elapsed_ms)
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "语音识别服务异常，请稍后重试。",
            "asr",
        ) from exc

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info("asr http_status=%s elapsed_ms=%s", response.status_code, elapsed_ms)

    if response.status_code >= 500:
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "语音识别服务异常，请稍后重试。",
            "asr",
        )
    if response.status_code == 401 or response.status_code == 403:
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "语音识别服务鉴权失败。",
            "asr",
        )
    if response.status_code != 200:
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "语音识别服务异常，请稍后重试。",
            "asr",
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "语音识别服务返回异常，请稍后重试。",
            "asr",
        ) from exc

    if not isinstance(body, dict):
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "语音识别服务返回异常，请稍后重试。",
            "asr",
        )

    text = _extract_text(body)
    if not text:
        raise AppError(
            422,
            "ASR_EMPTY",
            "没有听清你说的内容，请重新录音。",
            "asr",
        )
    return text
