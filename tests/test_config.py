import os
import pytest
from app.core.config import Settings

def test_settings_defaults():
    """Test that settings have proper defaults"""
    settings = Settings()
    assert settings.API_V1_STR == "/api/v1"
    assert settings.PROJECT_NAME == "AI Agent Orchestration Platform"
    assert settings.ALGORITHM == "HS256"
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 30

def test_cors_origins_validator():
    """Test the CORS origins validator"""
    settings = Settings()
    
    # Test single URL
    test_url = "http://localhost:3000"
    origins = settings.assemble_cors_origins(test_url)
    assert isinstance(origins, list)
    assert origins[0] == test_url
    
    # Test list of URLs
    test_urls = ["http://localhost:3000", "https://example.com"]
    origins = settings.assemble_cors_origins(test_urls)
    assert isinstance(origins, list)
    assert len(origins) == 2
    assert origins == test_urls 