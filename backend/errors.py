from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, stage: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.stage = stage


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def error_body(request: Request, code: str, message: str, stage: str) -> dict:
    return {
        "request_id": _request_id(request),
        "error": {
            "code": code,
            "message": message,
            "stage": stage,
        },
    }


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(request, exc.code, exc.message, exc.stage),
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    path = request.url.path.strip("/")
    stage = path.split("/")[0] if path else "unknown"
    return JSONResponse(
        status_code=422,
        content=error_body(
            request,
            "VALIDATION_ERROR",
            "请求缺少必要字段或字段类型不正确。",
            stage,
        ),
    )
