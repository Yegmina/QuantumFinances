from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    source_base_url: str | None
    source_snapshot_manifest_url: str | None
    source_snapshot_urls: tuple[str, ...]
    openai_api_key: str | None
    openai_model: str
    request_timeout_seconds: float = 90.0

    @property
    def has_external_source(self) -> bool:
        return bool(self.source_base_url or self.source_snapshot_manifest_url or self.source_snapshot_urls)

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)


def get_settings() -> Settings:
    raw_urls = os.getenv("SOURCE_SNAPSHOT_URLS", "")
    urls = tuple(part.strip() for part in raw_urls.split(",") if part.strip())
    return Settings(
        source_base_url=os.getenv("SOURCE_BASE_URL") or None,
        source_snapshot_manifest_url=os.getenv("SOURCE_SNAPSHOT_MANIFEST_URL") or None,
        source_snapshot_urls=urls,
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL") or "gpt-5.5",
        request_timeout_seconds=float(os.getenv("QUANTUMFINANCES_REQUEST_TIMEOUT_SECONDS") or 90),
    )
