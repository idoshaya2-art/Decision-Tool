from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


TRUE_VALUES = {"1", "true", "yes", "on"}


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def _as_positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


@dataclass(frozen=True)
class AppConfig:
    backend: str
    app_env: str
    supabase_url: str
    supabase_secret_key: str
    supabase_bucket: str
    access_user: str
    access_password: str
    require_auth: bool
    max_upload_bytes: int
    max_restore_bytes: int
    openai_agent_enabled: bool
    openai_api_key: str
    openai_model: str
    openai_max_output_tokens: int

    @classmethod
    def from_env(cls) -> "AppConfig":
        app_env = os.getenv("APP_ENV", "production" if os.getenv("RENDER") else "development").lower()
        backend = os.getenv("INTOPIA_BACKEND", "supabase").lower()
        default_auth = app_env == "production"
        return cls(
            backend=backend,
            app_env=app_env,
            supabase_url=os.getenv("SUPABASE_URL", "").strip().rstrip("/"),
            supabase_secret_key=(
                os.getenv("SUPABASE_SECRET_KEY", "").strip()
                or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
            ),
            supabase_bucket=os.getenv("SUPABASE_BUCKET", "intopia-files").strip() or "intopia-files",
            access_user=os.getenv("APP_ACCESS_USER", "intopia").strip() or "intopia",
            access_password=os.getenv("APP_ACCESS_PASSWORD", ""),
            require_auth=_as_bool(os.getenv("APP_REQUIRE_AUTH"), default_auth),
            max_upload_bytes=_as_positive_int(os.getenv("MAX_UPLOAD_MB"), 10) * 1024 * 1024,
            max_restore_bytes=_as_positive_int(os.getenv("MAX_RESTORE_MB"), 100) * 1024 * 1024,
            openai_agent_enabled=_as_bool(os.getenv("OPENAI_AGENT_ENABLED"), False),
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_model=os.getenv("OPENAI_MODEL", "").strip(),
            openai_max_output_tokens=_as_positive_int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS"), 1200),
        )

    def validation_errors(self) -> list[str]:
        errors: list[str] = []
        if self.backend not in {"supabase", "memory"}:
            errors.append("INTOPIA_BACKEND must be 'supabase' (or 'memory' in tests).")
        if self.backend == "supabase":
            if not self.supabase_url.startswith("https://"):
                errors.append("SUPABASE_URL is missing or invalid.")
            if not self.supabase_secret_key:
                errors.append("SUPABASE_SECRET_KEY is missing.")
        if self.backend == "memory" and self.app_env != "test":
            errors.append("The memory backend is permitted only when APP_ENV=test.")
        if self.require_auth and not self.access_password:
            errors.append("APP_ACCESS_PASSWORD is required when APP_REQUIRE_AUTH=true.")
        return errors

    def public_status(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "app_env": self.app_env,
            "supabase_url_configured": bool(self.supabase_url),
            "supabase_secret_configured": bool(self.supabase_secret_key),
            "storage_bucket": self.supabase_bucket,
            "authentication_required": self.require_auth,
            "access_password_configured": bool(self.access_password),
            "max_upload_mb": self.max_upload_bytes // (1024 * 1024),
            "max_restore_mb": self.max_restore_bytes // (1024 * 1024),
            "decision_agent_enabled": self.openai_agent_enabled,
            "decision_agent_configured": bool(self.openai_api_key and self.openai_model),
            "decision_agent_model": self.openai_model if self.openai_agent_enabled else "",
        }


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return AppConfig.from_env()


def reset_config_cache() -> None:
    get_config.cache_clear()
