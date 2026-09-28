"""All config comes from .env — see .env.example. Never print or log key values."""
import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    hindsight_api_key: str = os.environ.get("HINDSIGHT_API_KEY", "")
    hindsight_base_url: str = os.environ.get("HINDSIGHT_BASE_URL", "")
    hindsight_timeout: float = float(os.environ.get("HINDSIGHT_TIMEOUT", "10"))

    groq_api_key: str = os.environ.get("GROQ_API_KEY", "")
    llm_model_primary: str = os.environ.get("LLM_MODEL_PRIMARY", "openai/gpt-oss-120b")
    llm_model_fallback: str = os.environ.get("LLM_MODEL_FALLBACK", "qwen/qwen3.8-27b")
    llm_timeout: float = float(os.environ.get("LLM_TIMEOUT", "30"))

    frontend_origin: str = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")


@lru_cache
def get_settings() -> Settings:
    return Settings()
