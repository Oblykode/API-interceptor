"""Central application configuration."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    _HAS_PYDANTIC_SETTINGS = True
except ImportError:  # pragma: no cover - dependency fallback
    BaseSettings = BaseModel  # type: ignore[assignment]
    SettingsConfigDict = dict  # type: ignore[assignment]
    _HAS_PYDANTIC_SETTINGS = False


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    proxy_host: str = Field(default="127.0.0.1")
    proxy_port: int = Field(default=8081, ge=1, le=65535)
    ui_host: str = Field(default="127.0.0.1")
    ui_port: int = Field(default=8082, ge=1, le=65535)
    ui_base_url: str | None = None

    intercept_enabled_default: bool = Field(
        default=True,
        validation_alias=AliasChoices("INTERCEPT_ENABLED_DEFAULT", "INTERCEPT_ENABLED"),
    )
    intercept_all_default: bool = Field(
        default=False,
        validation_alias=AliasChoices("INTERCEPT_ALL_DEFAULT", "INTERCEPT_ALL"),
    )
    target_ips: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("TARGET_IPS", "INTERCEPT_TARGETS"),
    )
    ignored_hosts: list[str] = Field(
        default_factory=lambda: ["detectportal.firefox.com"],
        validation_alias=AliasChoices("IGNORED_HOSTS", "FILTERED_HOSTS"),
    )

    max_flows_memory: int = Field(
        default=1000,
        ge=10,
        validation_alias=AliasChoices("MAX_FLOWS_MEMORY", "MAX_FLOWS"),
    )
    flow_retention_minutes: int = Field(default=60, ge=1, le=60 * 24 * 14)
    sqlite_path: str = "data/interceptor.db"

    poll_interval_s: float = Field(default=0.25, gt=0)
    max_wait_s: float = Field(default=60.0 * 5, gt=0)

    ws_client_queue_size: int = Field(default=200, ge=10)
    ws_heartbeat_s: float = Field(default=20.0, gt=0)

    api_request_timeout_s: float = Field(default=10.0, gt=0)
    api_retry_count: int = Field(default=3, ge=0, le=10)
    api_retry_backoff_s: float = Field(default=0.25, gt=0)

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_traffic: bool = False

    @field_validator("target_ips", mode="before")
    @classmethod
    def _parse_target_ips(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("[") and raw.endswith("]"):
                # Support JSON-style env value, e.g. TARGET_IPS=["a","b"].
                try:
                    import json

                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [item.strip() for item in raw.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @field_validator("ignored_hosts", mode="before")
    @classmethod
    def _parse_ignored_hosts(cls, value: object) -> list[str]:
        if value is None:
            return ["detectportal.firefox.com"]
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("[") and raw.endswith("]"):
                try:
                    import json

                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        deduped = []
                        seen: set[str] = set()
                        for item in parsed:
                            host = str(item).strip().lower()
                            if host and host not in seen:
                                seen.add(host)
                                deduped.append(host)
                        return deduped
                except Exception:
                    pass
            return [item.strip().lower() for item in raw.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            deduped = []
            seen: set[str] = set()
            for item in value:
                host = str(item).strip().lower()
                if host and host not in seen:
                    seen.add(host)
                    deduped.append(host)
            return deduped
        return ["detectportal.firefox.com"]

    @field_validator("sqlite_path")
    @classmethod
    def _normalize_sqlite_path(cls, value: str) -> str:
        path = Path(value).expanduser()
        return str(path)

    @model_validator(mode="after")
    def _set_ui_base_url(self) -> "Settings":
        if not self.ui_base_url:
            self.ui_base_url = f"http://{self.ui_host}:{self.ui_port}"
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    if _HAS_PYDANTIC_SETTINGS:
        return Settings()

    dotenv_values = _load_dotenv(Path(".env"))
    payload: dict[str, object] = {}
    for field_name in Settings.model_fields:
        env_name = field_name.upper()
        value = os.getenv(env_name)
        if value is None and env_name in dotenv_values:
            value = dotenv_values[env_name]
        # Compatibility aliases for fallback mode without pydantic-settings.
        if value is None:
            alias_candidates = _legacy_env_aliases(field_name)
            for alias in alias_candidates:
                value = os.getenv(alias)
                if value is None and alias in dotenv_values:
                    value = dotenv_values[alias]
                if value is not None:
                    break
        if value is not None:
            payload[field_name] = value
    return Settings(**payload)


def _load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def reset_settings_cache() -> None:
    """Clear cached settings, useful for tests or dynamic env reload."""
    get_settings.cache_clear()


def _legacy_env_aliases(field_name: str) -> tuple[str, ...]:
    alias_map = {
        "max_flows_memory": ("MAX_FLOWS",),
        "intercept_all_default": ("INTERCEPT_ALL",),
        "intercept_enabled_default": ("INTERCEPT_ENABLED",),
        "target_ips": ("INTERCEPT_TARGETS",),
        "ignored_hosts": ("FILTERED_HOSTS",),
    }
    return alias_map.get(field_name, ())
