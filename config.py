"""
Loads configuration from .configuration file and exposes typed settings.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

_config_path = Path(__file__).parent / ".configuration"
load_dotenv(dotenv_path=_config_path)


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _get_int(key: str, default: int = 0) -> int:
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


def _get_float(key: str, default: float = 0.0) -> float:
    try:
        return float(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


def _get_list(key: str, default: list[str] | None = None) -> list[str]:
    raw = os.environ.get(key, "")
    if not raw:
        return default or []
    return [item.strip() for item in raw.split(",") if item.strip()]


class Config:
    # Telegram
    TELEGRAM_API_ID: int = _get_int("TELEGRAM_API_ID")
    TELEGRAM_API_HASH: str = _get("TELEGRAM_API_HASH")
    TELEGRAM_PHONE: str = _get("TELEGRAM_PHONE")
    TELEGRAM_SESSION_NAME: str = _get("TELEGRAM_SESSION_NAME", "meta_session")
    TELEGRAM_CHANNELS: list[str] = _get_list("TELEGRAM_CHANNELS")

    # OpenRouter (OpenAI-compatible)
    OPENROUTER_API_KEY: str = _get("OPENROUTER_API_KEY")
    OPENROUTER_MODEL: str = _get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    OPENROUTER_MAX_TOKENS: int = _get_int("OPENROUTER_MAX_TOKENS", 512)
    OPENROUTER_TEMPERATURE: float = _get_float("OPENROUTER_TEMPERATURE", 0.2)
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # News / Trends
    NEWS_API_KEY: str = _get("NEWS_API_KEY")
    NEWS_REFRESH_INTERVAL: int = _get_int("NEWS_REFRESH_INTERVAL_SECONDS", 3600)
    RSS_FEEDS: list[str] = _get_list(
        "RSS_FEEDS",
        [
            "https://feeds.reuters.com/reuters/businessNews",
            "https://feeds.bbci.co.uk/news/technology/rss.xml",
        ],
    )

    # Storage
    STORAGE_DIR: str = _get("STORAGE_DIR", "./data")
    DB_PATH: str = _get("DB_PATH", "./data/meta.db")

    # Web admin
    FEEDBACK_HOST: str = _get("FEEDBACK_SERVER_HOST", "0.0.0.0")
    FEEDBACK_PORT: int = _get_int("FEEDBACK_SERVER_PORT", 8080)

    # Logging
    LOG_LEVEL: str = _get("LOG_LEVEL", "INFO")
    LOG_FILE: str = _get("LOG_FILE", "./data/meta.log")

    # System intervals
    META_DISCOVERY_INTERVAL: int = _get_int("META_DISCOVERY_INTERVAL_SECONDS", 300)
    ADAPTATION_INTERVAL: int = _get_int("ADAPTATION_MONITOR_INTERVAL_SECONDS", 600)
    EVALUATION_STORE_LIMIT: int = _get_int("EVALUATION_STORE_LIMIT", 500)

    @classmethod
    def validate(cls) -> list[str]:
        """Return list of missing required config keys."""
        missing = []
        if not cls.TELEGRAM_API_ID:
            missing.append("TELEGRAM_API_ID")
        if not cls.TELEGRAM_API_HASH:
            missing.append("TELEGRAM_API_HASH")
        if not cls.OPENROUTER_API_KEY:
            missing.append("OPENROUTER_API_KEY")
        return missing


config = Config()
