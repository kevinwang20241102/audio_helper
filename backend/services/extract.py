import json
import logging
import time
from pathlib import Path

import httpx
from pydantic import BaseModel, ValidationError

from config import settings
from errors import AppError

logger = logging.getLogger(__name__)

EXTRACT_TIMEOUT_SECONDS = 15
PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "extract.txt"
DEFAULT_CATEGORY = "咖啡店"
CATEGORY_ALIASES = {
    "咖啡": "咖啡店",
    "喝咖啡": "咖啡店",
    "咖啡馆": "咖啡店",
    "cafe": "咖啡店",
    "café": "咖啡店",
}
VAGUE_ADDRESSES = {
    "家",
    "我家",
    "你家",
    "他家",
    "家里",
    "家门口",
    "我家附近",
    "公司",
    "单位",
    "办公室",
    "公司附近",
    "这边",
    "那边",
    "这里",
    "那里",
}
VAGUE_PREFIXES = ("我家", "你家", "他家")
CITY_SUFFIXES = ("特别行政区", "自治区", "省", "市")


class ModelExtractResult(BaseModel):
    city_a: str | None
    address_a: str | None
    city_b: str | None
    address_b: str | None
    category: str | None
    party_count: int | None
    incomplete_reason: str | None


class ExtractBusinessData(BaseModel):
    city_a: str
    address_a: str
    city_b: str
    address_b: str
    category: str


def load_extract_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def normalize_city(name: str | None) -> str | None:
    value = _blank_to_none(name)
    if value is None:
        return None
    for suffix in CITY_SUFFIXES:
        if value.endswith(suffix) and len(value) > len(suffix):
            return value[: -len(suffix)]
    return value


def normalize_category(category: str | None) -> str:
    value = _blank_to_none(category)
    if value is None:
        return DEFAULT_CATEGORY
    return CATEGORY_ALIASES.get(value.lower(), CATEGORY_ALIASES.get(value, value))


def is_vague_address(address: str | None) -> bool:
    value = _blank_to_none(address)
    if value is None:
        return True
    if value in VAGUE_ADDRESSES:
        return True
    return any(value.startswith(prefix) for prefix in VAGUE_PREFIXES)


def _model_output_invalid() -> AppError:
    return AppError(
        502,
        "MODEL_OUTPUT_INVALID",
        "信息提取结果格式异常，请稍后重试。",
        "extract",
    )


def parse_model_content(content: str) -> ModelExtractResult:
    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _model_output_invalid() from exc
    if not isinstance(payload, dict):
        raise _model_output_invalid()
    try:
        parsed = ModelExtractResult.model_validate(payload)
    except ValidationError as exc:
        raise _model_output_invalid() from exc
    return parsed.model_copy(
        update={
            "city_a": _blank_to_none(parsed.city_a),
            "address_a": _blank_to_none(parsed.address_a),
            "city_b": _blank_to_none(parsed.city_b),
            "address_b": _blank_to_none(parsed.address_b),
            "category": _blank_to_none(parsed.category),
            "incomplete_reason": _blank_to_none(parsed.incomplete_reason),
        }
    )


def apply_business_rules(parsed: ModelExtractResult, page_city: str) -> ExtractBusinessData:
    if parsed.party_count != 2:
        raise AppError(
            422,
            "PARTY_COUNT_INVALID",
            "第一版只支持两个人碰面，请重新说明你们两个人各自所在的地点。",
            "extract",
        )

    city_a = normalize_city(parsed.city_a) or normalize_city(page_city)
    city_b = normalize_city(parsed.city_b) or normalize_city(page_city)
    address_a = _blank_to_none(parsed.address_a)
    address_b = _blank_to_none(parsed.address_b)
    category = normalize_category(parsed.category)

    if is_vague_address(address_a) or is_vague_address(address_b) or not city_a or not city_b:
        raise AppError(
            422,
            "EXTRACT_INCOMPLETE",
            "地点说得不够具体，请重新说明两个人各自所在的地址。",
            "extract",
        )

    if city_a != city_b:
        raise AppError(
            422,
            "CROSS_CITY",
            "第一版只支持同一座城市内的两个人，请重新说明你们所在的地点。",
            "extract",
        )

    assert city_a and city_b and address_a and address_b
    return ExtractBusinessData(
        city_a=city_a,
        address_a=address_a,
        city_b=city_b,
        address_b=address_b,
        category=category,
    )


def _message_content(payload: dict) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "信息提取服务返回异常，请稍后重试。",
            "extract",
        )
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "信息提取服务返回异常，请稍后重试。",
            "extract",
        )
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise _model_output_invalid()
    return content


async def extract_meetup(text: str, page_city: str) -> ExtractBusinessData:
    if not settings.deepseek_api_key:
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "信息提取服务未配置密钥。",
            "extract",
        )

    user_prompt = (
        "请根据以下输入提取碰面信息，只输出约定 JSON。\n\n"
        f"口述内容：\n{text}\n\n"
        f"页面选定城市：\n{page_city}"
    )
    request_body = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": load_extract_prompt()},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "max_tokens": 1024,
    }
    headers = {
        "Authorization": f"Bearer {settings.deepseek_api_key}",
        "Content-Type": "application/json",
    }

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=EXTRACT_TIMEOUT_SECONDS) as client:
            response = await client.post(
                settings.deepseek_url,
                headers=headers,
                json=request_body,
            )
    except httpx.TimeoutException as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.error("extract timeout elapsed_ms=%s", elapsed_ms)
        raise AppError(
            504,
            "UPSTREAM_TIMEOUT",
            "信息提取超时，请稍后重试。",
            "extract",
        ) from exc
    except httpx.HTTPError as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.error("extract upstream error elapsed_ms=%s", elapsed_ms)
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "信息提取服务异常，请稍后重试。",
            "extract",
        ) from exc

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info("extract http_status=%s elapsed_ms=%s", response.status_code, elapsed_ms)

    if response.status_code >= 500:
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "信息提取服务异常，请稍后重试。",
            "extract",
        )
    if response.status_code in (401, 403):
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "信息提取服务鉴权失败。",
            "extract",
        )
    if response.status_code != 200:
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "信息提取服务异常，请稍后重试。",
            "extract",
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "信息提取服务返回异常，请稍后重试。",
            "extract",
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            502,
            "UPSTREAM_ERROR",
            "信息提取服务返回异常，请稍后重试。",
            "extract",
        )

    parsed = parse_model_content(_message_content(payload))
    return apply_business_rules(parsed, page_city)
