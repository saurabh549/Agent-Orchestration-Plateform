import os
from typing import List, Optional
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "AI Agent Orchestration Platform"
    
    # JWT settings
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "secret-key-for-dev-only")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS
    CORS_ORIGINS: List[AnyHttpUrl] = []
    
    @field_validator("CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: str | List[str]) -> List[AnyHttpUrl]:
        if isinstance(v, str) and not v.startswith("["):
            return [v]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)
    
    # Database
    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL", "sqlite:///./test.db"
    )
    
    # Copilot Studio Direct Line API
    DIRECT_LINE_SECRET: str = os.environ.get("DIRECT_LINE_SECRET", "")
    
    # Semantic Kernel
    OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
    OPENAI_ENDPOINT: str = os.environ.get("OPENAI_ENDPOINT", "")
    AZURE_OPENAI_API_KEY: Optional[str] = os.environ.get("AZURE_OPENAI_API_KEY", "")
    AZURE_OPENAI_ENDPOINT: Optional[str] = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    GEMINI_API_KEY: Optional[str] = os.environ.get("GEMINI_API_KEY", "")
    
    # Observability
    OTEL_EXPORTER_OTLP_ENDPOINT: str = os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT", ""
    )
    PROMETHEUS_ENDPOINT: str = "/metrics"

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings() 