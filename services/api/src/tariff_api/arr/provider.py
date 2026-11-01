"""The ARR model channel (ADR-0018): the independent second reading of a chapter, from page
images, compared field by field with the rules over the grids.  Increment A ships the
fixture implementation only (labelled fixture on every run and candidate); the Anthropic
implementation is written in Increment B against the real NPCL pages, behind this same
interface."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Settings
from .schema import ARR_SCHEMA_VERSION, ArrExtractionOutput

ARR_PROMPT_VERSION = "arr-0"


@dataclass
class ArrChannelResult:
    channel: str  # image
    output: ArrExtractionOutput
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    input_hash: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    is_fixture: bool
    raw: dict[str, Any] = field(default_factory=dict)


class ArrChannelUnavailable(RuntimeError):
    def __init__(self, message: str, *, retry: bool = False) -> None:
        super().__init__(message)
        self.retry = retry


class ArrImageChannel:
    name = "base"
    model = "none"
    is_fixture = False

    def read_chapter(self, structure: ArrExtractionOutput, images: list[bytes]) -> ArrChannelResult:
        raise NotImplementedError


class FixtureArrImageChannel(ArrImageChannel):
    """Deterministic: echoes the structure channel's reading, optionally perturbed (tests
    only: ``{"arr_image": [{"key_contains": ..., "drop": true | "set": {...}}]}``), so
    comparison and routing are exercised without a model.  Cost is zero."""

    name = "fixture"
    model = "fixture-arr-echo"
    is_fixture = True

    def __init__(self, perturbations_path: str | None = None) -> None:
        self._perturb: dict[str, Any] = {}
        if perturbations_path and Path(perturbations_path).is_file():
            self._perturb = json.loads(Path(perturbations_path).read_text())

    def read_chapter(self, structure: ArrExtractionOutput, images: list[bytes]) -> ArrChannelResult:
        out = ArrExtractionOutput.model_validate(structure.model_dump())
        applied: list[str] = []
        for rule in self._perturb.get("arr_image", []):
            needle = (rule.get("key_contains") or "").lower()
            for c in list(out.candidates):
                if needle and needle in c.key().lower():
                    if rule.get("drop"):
                        out.candidates.remove(c)
                        applied.append(f"drop:{c.key()}")
                        continue
                    for f, v in (rule.get("set") or {}).items():
                        setattr(c, f, v)
                        applied.append(f"set:{c.key()}:{f}={v}")
        h = hashlib.sha256()
        for img in images:
            h.update(img)
        return ArrChannelResult(
            "image",
            out,
            self.name,
            self.model,
            ARR_PROMPT_VERSION,
            ARR_SCHEMA_VERSION,
            h.hexdigest() if images else hashlib.sha256(b"no-images").hexdigest(),
            sum(len(i) for i in images) // 750,
            len(out.model_dump_json()) // 4,
            0.0,
            True,
            {"fixture": True, "perturbations_applied": applied, "images": len(images)},
        )


class AnthropicArrImageChannel(ArrImageChannel):
    """Written in Increment B, on the real NPCL ARR pages.  Until then a configured live
    provider refuses rather than fall back silently to the fixture."""

    name = "anthropic"

    def read_chapter(self, structure: ArrExtractionOutput, images: list[bytes]) -> ArrChannelResult:
        raise ArrChannelUnavailable(
            "the ARR image channel for the live provider is built in Increment B; run with PROVIDER_BACKEND=fixture"
        )


def build_arr_channel(settings: Settings) -> ArrImageChannel:
    if settings.provider_backend == "fixture":
        return FixtureArrImageChannel(settings.provider_fixture_perturbations_path)
    return AnthropicArrImageChannel()
