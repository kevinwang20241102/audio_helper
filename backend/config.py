from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    backend_host: str = "127.0.0.1"
    backend_port: int = 8003
    cors_origins: str = "http://localhost:5175"

    bailian_api_key: str = ""
    deepseek_api_key: str = ""
    amap_api_key: str = ""

    asr_model: str = "qwen3-asr-flash"
    asr_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    tts_model: str = "qwen3-tts-flash"
    tts_url: str = (
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    )
    tts_voice: str = "Cherry"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_url: str = "https://api.deepseek.com/chat/completions"
    amap_geo_url: str = "https://restapi.amap.com/v3/geocode/geo"
    amap_around_url: str = "https://restapi.amap.com/v3/place/around"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
