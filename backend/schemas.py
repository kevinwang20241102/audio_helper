from pydantic import BaseModel, Field


class HealthData(BaseModel):
    status: str = Field(examples=["ok"])


class HealthResponse(BaseModel):
    request_id: str
    data: HealthData


class UploadData(BaseModel):
    audio_id: str = Field(examples=["aud_7c9e0e1a2b3c4d5e6f7a8b9c0d1e2f3"])


class UploadResponse(BaseModel):
    request_id: str
    data: UploadData
