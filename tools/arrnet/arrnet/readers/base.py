"""One interface for every reader.

    class Reader:  name, version;  read(order, pdf_path) -> ParseResult

A ParseResult is the parse row (provider, model, is_real, status, pages_parsed, cost_usd, note),
the tables it found (page, pages, title, unit, unit_from, columns, cells?, markdown?), the values
(the arr_values row shape) and the key parameters (the parameters row shape).  Every value and
parameter has a page and a quote; the Verifier checks both before anything is posted as a value.
``page_texts`` holds the reader's own text of pages that have no text layer (OCR), which the
Verifier uses as the evidence for those pages and says so.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParseResult:
    reader: str
    reader_version: str
    status: str  # ok | partial | failed | skipped
    is_real: bool = True
    provider: str | None = None
    model: str | None = None
    pages_parsed: int = 0
    cost_usd: float = 0.0
    note: str | None = None
    tables: list[dict[str, Any]] = field(default_factory=list)
    values: list[dict[str, Any]] = field(default_factory=list)
    parameters: list[dict[str, Any]] = field(default_factory=list)
    paragraphs: list[dict[str, Any]] = field(default_factory=list)  # {page, seq, kind, topic?, summary}
    page_texts: dict[str, str] = field(default_factory=dict)  # str(page) -> the reader's own text
    pages: list[int] = field(default_factory=list)  # the pages it looked at
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ParseResult:
        return cls(**d)

    def parse_row(self, order_url: str) -> dict[str, Any]:
        row = {
            "order_url": order_url,
            "reader": self.reader,
            "reader_version": self.reader_version,
            "provider": self.provider,
            "model": self.model,
            "is_real": self.is_real,
            "status": self.status,
            "pages_parsed": self.pages_parsed,
            "cost_usd": round(self.cost_usd, 6),
            "note": self.note,
        }
        return {k: v for k, v in row.items() if v is not None}


class Reader:
    name: str = ""
    version: str = ""

    def read(self, order: dict[str, Any], pdf_path: str | Path | None) -> ParseResult:
        raise NotImplementedError

    def skipped(self, reason: str, **kw: Any) -> ParseResult:
        return ParseResult(self.name, self.version, "skipped", note=reason, **kw)
