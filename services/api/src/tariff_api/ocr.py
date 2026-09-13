"""OCR for pages triage marked ``ocr_recommended`` (Section 6.3: image-only pages, vector-drawn
tables with no text layer, damaged text layers).

Tesseract is driven as a subprocess with TSV output so every word carries a confidence and a
box; the engine version is recorded on the artefact.  OCR text never silently replaces a text
layer: where both exist, their agreement is measured and stored, and a low agreement on a
page that *has* a text layer is a finding for a reviewer, not something to resolve here.

Defaults (``ocr_dpi=300``, ``ocr_psm=4``) were chosen by measurement on the fixtures: page
segmentation mode 6 misses 8 pt table cells entirely (recall 0.15 against the text layer);
modes 4, 11 and 12 read every word.  Mode 4 keeps paragraph and line structure on prose
pages, which the heading inventory relies on.  Bump ``OCR_VERSION`` when parsing or
assembly rules change.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import pymupdf

OCR_VERSION = "1"
ENGINE = "tesseract"


class OcrUnavailable(RuntimeError):
    """The OCR engine is not installed or cannot run.  A typed, retryable job failure — never a
    silent skip of the page."""


@lru_cache(maxsize=1)
def tesseract_version() -> str | None:
    if shutil.which("tesseract") is None:
        return None
    try:
        out = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    first = (out.stdout or out.stderr).splitlines()[0] if (out.stdout or out.stderr) else ""
    m = re.search(r"tesseract\s+v?([0-9][0-9.]*)", first)
    return m.group(1) if m else (first.strip() or "unknown")


@dataclass
class OcrWord:
    text: str
    conf: float
    left: int
    top: int
    width: int
    height: int
    block: int
    par: int
    line: int


@dataclass
class OcrResult:
    engine: str
    engine_version: str
    lang: str
    dpi: int
    psm: int
    words: list[OcrWord] = field(default_factory=list)
    text: str = ""
    mean_confidence: float = 0.0
    word_count: int = 0
    low_confidence: bool = True

    def to_dict(self, *, include_words: bool = True) -> dict[str, Any]:
        d = asdict(self)
        if not include_words:
            d.pop("words")
        return d


def rasterise(page: pymupdf.Page, dpi: int) -> bytes:
    return page.get_pixmap(dpi=dpi).tobytes("png")


def run_tesseract(png: bytes, *, lang: str, psm: int, timeout: int = 180) -> str:
    version = tesseract_version()
    if version is None:
        raise OcrUnavailable("tesseract binary not found on PATH")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "page.png"
        path.write_bytes(png)
        try:
            proc = subprocess.run(
                ["tesseract", str(path), "stdout", "-l", lang, "--psm", str(psm), "tsv"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise OcrUnavailable(f"tesseract timed out after {timeout}s") from e
        except OSError as e:
            raise OcrUnavailable(str(e)) from e
    if proc.returncode != 0:
        raise OcrUnavailable(f"tesseract exited {proc.returncode}: {proc.stderr.strip()[:300]}")
    return proc.stdout


def parse_tsv(tsv: str) -> list[OcrWord]:
    """Tesseract's TSV: level, page, block, par, line, word, left, top, width, height, conf, text.
    Only level-5 rows (words) with real text and a confidence are kept; conf == -1 marks
    non-word structure rows."""
    words: list[OcrWord] = []
    for row in tsv.splitlines()[1:]:
        parts = row.split("\t")
        if len(parts) != 12 or parts[0] != "5":
            continue
        text = parts[11].strip()
        if not text or parts[10] == "-1":
            continue
        try:
            words.append(
                OcrWord(
                    text=text,
                    conf=float(parts[10]),
                    left=int(parts[6]),
                    top=int(parts[7]),
                    width=int(parts[8]),
                    height=int(parts[9]),
                    block=int(parts[2]),
                    par=int(parts[3]),
                    line=int(parts[4]),
                )
            )
        except ValueError:
            continue
    return words


def assemble_text(words: list[OcrWord]) -> str:
    """Words → lines (same block/par/line) → paragraphs, preserving tesseract's reading order."""
    lines: list[str] = []
    current_key: tuple[int, int, int] | None = None
    current: list[str] = []
    last_par: tuple[int, int] | None = None
    for w in words:
        key = (w.block, w.par, w.line)
        if key != current_key:
            if current:
                lines.append(" ".join(current))
            if last_par is not None and (w.block, w.par) != last_par:
                lines.append("")
            current, current_key, last_par = [], key, (w.block, w.par)
        current.append(w.text)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines).strip()


def ocr_page(page: pymupdf.Page, *, lang: str, dpi: int, psm: int, min_confidence: float) -> OcrResult:
    words = parse_tsv(run_tesseract(rasterise(page, dpi), lang=lang, psm=psm))
    mean = round(sum(w.conf for w in words) / len(words), 2) if words else 0.0
    return OcrResult(
        engine=ENGINE,
        engine_version=tesseract_version() or "unknown",
        lang=lang,
        dpi=dpi,
        psm=psm,
        words=words,
        text=assemble_text(words),
        mean_confidence=mean,
        word_count=len(words),
        low_confidence=(not words) or mean < min_confidence,
    )


_TOKEN = re.compile(r"[a-z0-9]{2,}")


def text_agreement(layer_text: str, ocr_text: str) -> float:
    """Jaccard similarity of the two token sets.  1.0 when OCR and the text layer read the
    same words; near 0 when the layer is glyph soup or the OCR saw nothing."""
    a = set(_TOKEN.findall(layer_text.lower()))
    b = set(_TOKEN.findall(ocr_text.lower()))
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return round(len(a & b) / len(a | b), 4)
