"""Runtime configuration.

One settings object for both deployment profiles (``gcp`` and ``local``).  The profile
selects platform adapters; it never changes application behaviour.  Combinations that
would let a local-only adapter run in the cloud are rejected at startup
(see :meth:`Settings.validate_profile`).
"""

from __future__ import annotations

import enum
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DeploymentProfile(str, enum.Enum):
    gcp = "gcp"
    local = "local"


class StorageBackend(str, enum.Enum):
    filesystem = "filesystem"
    gcs = "gcs"


class SecretsBackend(str, enum.Enum):
    env = "env"
    secret_manager = "secret_manager"


class IdentityBackend(str, enum.Enum):
    local = "local"
    iap = "iap"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=None, extra="ignore")

    deployment_profile: DeploymentProfile = DeploymentProfile.local
    environment_name: str = "local"

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/tariff_dev"
    database_pool_size: int = 5

    # Object storage
    object_store_backend: StorageBackend = StorageBackend.filesystem
    object_store_root: str = "./.data/object-store"
    source_bucket: str = ""
    artefact_bucket: str = ""
    export_bucket: str = ""

    # Secrets
    secrets_backend: SecretsBackend = SecretsBackend.env
    gcp_project_id: str = ""

    # Identity
    identity_backend: IdentityBackend = IdentityBackend.local
    local_user_allowlist: str = Field(
        default="",
        description="Comma-separated `email:role` entries accepted by the local identity adapter",
    )
    iap_audience: str = ""

    # Limits (Section 6.13) - hitting a limit stops with a typed reason, never lowers verification
    max_upload_bytes: int = 64 * 1024 * 1024
    max_pages_per_job: int = 1000
    job_lease_seconds: int = 60
    job_heartbeat_seconds: int = 15
    job_max_attempts: int = 3
    inventory_checkpoint_every_pages: int = 25

    # Reading (Milestone 2b).  Defaults chosen from measurements on fixtures; recorded on artefacts.
    ocr_engine: str = "tesseract"
    ocr_lang: str = "eng"
    ocr_dpi: int = 300
    ocr_psm: int = 4  # measured: psm 6 misses 8pt table cells (recall 0.15); psm 4 reads all (1.00)
    ocr_min_confidence: float = 60.0  # mean word confidence below this flags `ocr_low_confidence`
    primary_reader: str = "pymupdf"  # Docling once measured on real pages (ADR-0009)

    # Provenance / evaluation
    golden_manifest_path: str = "tests/golden/manifest.json"

    # Extraction provider (Section 6.8) and cost limits (Section 6.13).  `fixture` is the
    # default everywhere: a real provider run needs an explicit backend and a key in the
    # secrets adapter, and is reported separately from fixture runs.
    provider_backend: Literal["fixture", "anthropic"] = "fixture"
    anthropic_model: str = "claude-sonnet-5"
    provider_price_in_per_mtok: float = 3.0
    provider_price_out_per_mtok: float = 15.0
    provider_timeout_seconds: float = 120.0
    provider_fixture_perturbations_path: str | None = None
    image_channel_enabled: bool = True
    image_channel_dpi: int = 110
    provider_max_cost_per_order_usd: float = 5.0
    provider_max_tokens_per_order: int = 2_000_000

    # Review workflow (Section 7.2).  Second review is a policy, not a reviewer's choice:
    # material conditions, formula components and corrections of channel disagreements always
    # need a second reviewer; the first order from any utility routes everything to second
    # review.  Evidence must have been rendered to the deciding reviewer within the window.
    second_review_material: bool = True
    second_review_first_order: bool = True
    evidence_view_max_age_seconds: int = 8 * 3600
    evidence_render_dpi: int = 110

    # Telemetry
    log_format: str = "json"  # json | text
    log_level: str = "INFO"
    service_name: str = "tariff-api"

    @field_validator("local_user_allowlist")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    def validate_profile(self) -> None:
        """Reject adapter combinations that violate the portability contract (Section 3.2)."""
        if self.deployment_profile == DeploymentProfile.gcp:
            problems = []
            if self.identity_backend == IdentityBackend.local:
                problems.append("identity_backend=local is forbidden under DEPLOYMENT_PROFILE=gcp")
            if self.object_store_backend == StorageBackend.filesystem:
                problems.append("object_store_backend=filesystem is forbidden under gcp")
            if self.secrets_backend == SecretsBackend.env:
                problems.append("secrets_backend=env is forbidden under gcp")
            if not self.gcp_project_id:
                problems.append("gcp_project_id is required under gcp")
            if not (self.source_bucket and self.artefact_bucket):
                problems.append("source_bucket and artefact_bucket are required under gcp")
            if problems:
                raise RuntimeError("Invalid gcp profile configuration: " + "; ".join(problems))

    def allowlist_entries(self) -> dict[str, str]:
        entries: dict[str, str] = {}
        for raw in self.local_user_allowlist.split(","):
            raw = raw.strip()
            if not raw:
                continue
            email, _, role = raw.partition(":")
            entries[email.strip().lower()] = role.strip() or "analyst"
        return entries


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.validate_profile()
    return s


def reset_settings_cache() -> None:
    get_settings.cache_clear()
