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

    @property
    def frontend_origins(self) -> list[str]:
        """FRONTEND_ORIGIN as a comma-separated list (deploy readiness: prod + preview
        URLs, etc.) -- a single origin with no comma still works, unchanged."""
        return [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


# --- security settings -------------------------------------------------------------------
# Read from the environment at call time (not cached at import) so tests can patch them and a
# restart is never needed to pick a value up. Values are secrets: never log or return them.
def app_env() -> str:
    return os.environ.get("APP_ENV", "development").strip().lower()


def is_production() -> bool:
    return app_env() == "production"


def admin_api_key() -> str:
    return os.environ.get("ADMIN_API_KEY", "")


def ingest_api_key() -> str:
    return os.environ.get("INGEST_API_KEY", "")


def trusted_proxy_hops() -> int:
    """How many reverse-proxy hops append to X-Forwarded-For (0 = use the socket peer)."""
    try:
        return max(0, int(os.environ.get("RATE_LIMIT_TRUSTED_HOPS", "0")))
    except ValueError:
        return 0


def max_live_incidents() -> int:
    try:
        return max(1, int(os.environ.get("MAX_LIVE_INCIDENTS", "200")))
    except ValueError:
        return 200

