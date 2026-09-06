import json

from fastapi.testclient import TestClient

from errors import AppError
from main import app
from services.extract import ModelExtractResult, apply_business_rules, parse_model_content

client = TestClient(app)


COMPLETE_MODEL = {
    "city_a": "杭州",
    "address_a": "杭州东站",
    "city_b": "杭州",
    "address_b": "西湖龙翔桥地铁站",
    "category": "咖啡店",
    "party_count": 2,
    "incomplete_reason": None,
}


def _patch_extract(monkeypatch, payload):
    async def fake_extract(text: str, page_city: str):
        parsed = parse_model_content(
            payload if isinstance(payload, str) else json.dumps(payload)
        )
        return apply_business_rules(parsed, page_city)

    monkeypatch.setattr("api.extract.extract_meetup", fake_extract)


def test_extract_success_returns_five_business_fields(monkeypatch):
    _patch_extract(monkeypatch, COMPLETE_MODEL)
    response = client.post(
        "/extract",
        json={
            "text": "我在杭州东站，朋友在西湖龙翔桥地铁站，帮我们找个中间的咖啡店。",
            "city": "杭州",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data == {
        "city_a": "杭州",
        "address_a": "杭州东站",
        "city_b": "杭州",
        "address_b": "西湖龙翔桥地铁站",
        "category": "咖啡店",
    }
    assert "party_count" not in data
    assert "incomplete_reason" not in data


def test_extract_missing_fields_uses_unified_error():
    response = client.post("/extract", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["stage"] == "extract"


def test_extract_page_city_fills_missing_spoken_city(monkeypatch):
    _patch_extract(
        monkeypatch,
        {
            **COMPLETE_MODEL,
            "city_a": None,
            "city_b": None,
            "address_a": "东站",
            "address_b": "龙翔桥地铁站",
        },
    )
    response = client.post(
        "/extract",
        json={"text": "我在东站，朋友在龙翔桥地铁站，找个咖啡店。", "city": "杭州"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["city_a"] == "杭州"
    assert response.json()["data"]["city_b"] == "杭州"


def test_extract_spoken_city_not_overwritten_by_page_city():
    parsed = ModelExtractResult(
        city_a="杭州",
        address_a="杭州东站",
        city_b="杭州",
        address_b="西湖龙翔桥地铁站",
        category="咖啡店",
        party_count=2,
        incomplete_reason=None,
    )
    result = apply_business_rules(parsed, "上海")
    assert result.city_a == "杭州"
    assert result.city_b == "杭州"


def test_extract_normalizes_coffee_category():
    parsed = ModelExtractResult(
        city_a="杭州",
        address_a="杭州东站",
        city_b="杭州",
        address_b="西湖龙翔桥地铁站",
        category="喝咖啡",
        party_count=2,
        incomplete_reason=None,
    )
    assert apply_business_rules(parsed, "杭州").category == "咖啡店"


def test_extract_defaults_missing_category_to_coffee():
    parsed = ModelExtractResult(
        city_a="杭州",
        address_a="杭州东站",
        city_b="杭州",
        address_b="西湖龙翔桥地铁站",
        category=None,
        party_count=2,
        incomplete_reason=None,
    )
    assert apply_business_rules(parsed, "杭州").category == "咖啡店"


def test_extract_same_city_with_shi_suffix():
    parsed = ModelExtractResult(
        city_a="杭州市",
        address_a="杭州东站",
        city_b="杭州",
        address_b="西湖龙翔桥地铁站",
        category="咖啡店",
        party_count=2,
        incomplete_reason=None,
    )
    result = apply_business_rules(parsed, "杭州")
    assert result.city_a == "杭州"
    assert result.city_b == "杭州"


def test_extract_vague_home_address_is_incomplete(monkeypatch):
    _patch_extract(
        monkeypatch,
        {
            **COMPLETE_MODEL,
            "address_a": "我家",
            "incomplete_reason": "address_a 含糊，未给出可定位地址",
        },
    )
    response = client.post(
        "/extract",
        json={"text": "我在我家，朋友在西湖龙翔桥地铁站，找个咖啡店。", "city": "杭州"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EXTRACT_INCOMPLETE"
    assert response.json()["error"]["stage"] == "extract"


def test_extract_missing_address_is_incomplete(monkeypatch):
    _patch_extract(
        monkeypatch,
        {**COMPLETE_MODEL, "address_b": None, "incomplete_reason": "缺少 address_b"},
    )
    response = client.post(
        "/extract",
        json={"text": "我在杭州东站，朋友也在杭州，找个咖啡店。", "city": "杭州"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EXTRACT_INCOMPLETE"


def test_extract_party_count_invalid(monkeypatch):
    _patch_extract(
        monkeypatch,
        {
            **COMPLETE_MODEL,
            "city_b": None,
            "address_b": None,
            "party_count": 1,
            "incomplete_reason": "只提到一个人的位置",
        },
    )
    response = client.post(
        "/extract",
        json={"text": "我在杭州东站，帮我找个咖啡店。", "city": "杭州"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PARTY_COUNT_INVALID"


def test_extract_cross_city(monkeypatch):
    _patch_extract(
        monkeypatch,
        {
            **COMPLETE_MODEL,
            "city_b": "上海",
            "address_b": "上海虹桥站",
        },
    )
    response = client.post(
        "/extract",
        json={"text": "我在杭州东站，朋友在上海虹桥站，找个咖啡店。", "city": "杭州"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "CROSS_CITY"
    assert "同一座城市" in body["error"]["message"]


def test_extract_invalid_json_is_model_error_not_incomplete():
    try:
        parse_model_content("{not-json")
        assert False, "expected AppError"
    except AppError as exc:
        assert exc.status_code == 502
        assert exc.code == "MODEL_OUTPUT_INVALID"
        assert "没说清" not in exc.message
        assert "不够具体" not in exc.message


def test_extract_missing_model_field_is_model_error_not_incomplete():
    try:
        parse_model_content(
            '{"city_a":"杭州","address_a":"杭州东站","city_b":"杭州",'
            '"address_b":"西湖龙翔桥地铁站","category":"咖啡店","party_count":2}'
        )
        assert False, "expected AppError"
    except AppError as exc:
        assert exc.code == "MODEL_OUTPUT_INVALID"


def test_extract_wrong_field_type_is_model_error_not_incomplete():
    try:
        parse_model_content(
            '{"city_a":"杭州","address_a":"杭州东站","city_b":"杭州",'
            '"address_b":"西湖龙翔桥地铁站","category":"咖啡店",'
            '"party_count":"两人","incomplete_reason":null}'
        )
        assert False, "expected AppError"
    except AppError as exc:
        assert exc.code == "MODEL_OUTPUT_INVALID"


def test_extract_timeout_returns_504(monkeypatch):
    async def fake_extract(_text: str, _city: str):
        raise AppError(504, "UPSTREAM_TIMEOUT", "信息提取超时，请稍后重试。", "extract")

    monkeypatch.setattr("api.extract.extract_meetup", fake_extract)
    response = client.post(
        "/extract",
        json={"text": "我在杭州东站，朋友在西湖龙翔桥地铁站。", "city": "杭州"},
    )
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "UPSTREAM_TIMEOUT"


def test_extract_upstream_error_returns_502(monkeypatch):
    async def fake_extract(_text: str, _city: str):
        raise AppError(502, "UPSTREAM_ERROR", "信息提取服务异常，请稍后重试。", "extract")

    monkeypatch.setattr("api.extract.extract_meetup", fake_extract)
    response = client.post(
        "/extract",
        json={"text": "我在杭州东站，朋友在西湖龙翔桥地铁站。", "city": "杭州"},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "UPSTREAM_ERROR"
