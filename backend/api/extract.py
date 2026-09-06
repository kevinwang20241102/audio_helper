from fastapi import APIRouter, Request

from schemas import ExtractData, ExtractRequest, ExtractResponse
from services.extract import extract_meetup

router = APIRouter()


@router.post("/extract", response_model=ExtractResponse)
async def extract(request: Request, body: ExtractRequest) -> ExtractResponse:
    result = await extract_meetup(body.text, body.city)
    return ExtractResponse(
        request_id=request.state.request_id,
        data=ExtractData(
            city_a=result.city_a,
            address_a=result.address_a,
            city_b=result.city_b,
            address_b=result.address_b,
            category=result.category,
        ),
    )
