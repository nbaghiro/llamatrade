"""Environment-driven telemetry configuration.

All knobs are read from environment variables (the project convention — no
config files at runtime). Tracing degrades to a no-op when no OTLP endpoint is
set, so local dev and tests need zero configuration.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelemetrySettings(BaseSettings):
    """Resolved telemetry settings for a single service/process."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore", case_sensitive=False)

    environment: str = Field(default="development", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    # "json" for prod, "text" for local readability.
    log_format: str = Field(default="json", alias="LOG_FORMAT")

    metrics_enabled: bool = Field(default=True, alias="TELEMETRY_METRICS_ENABLED")
    tracing_enabled: bool = Field(default=True, alias="TELEMETRY_TRACING_ENABLED")

    # OTLP/HTTP traces endpoint. Unset → tracing exports nothing (no-op).
    otlp_endpoint: str | None = Field(default=None, alias="OTEL_EXPORTER_OTLP_ENDPOINT")
    traces_sampler: str = Field(default="parentbased_traceidratio", alias="OTEL_TRACES_SAMPLER")
    traces_sampler_arg: float = Field(default=0.1, alias="OTEL_TRACES_SAMPLER_ARG")

    # Optional build identity (resource attributes); falls back to args at init.
    service_version: str | None = Field(default=None, alias="SERVICE_VERSION")
    git_sha: str | None = Field(default=None, alias="GIT_SHA")

    @property
    def json_logs(self) -> bool:
        return self.log_format.lower() == "json"

    @property
    def export_traces(self) -> bool:
        return self.tracing_enabled and self.otlp_endpoint is not None


def load_settings() -> TelemetrySettings:
    """Read telemetry settings from the environment."""
    return TelemetrySettings()
