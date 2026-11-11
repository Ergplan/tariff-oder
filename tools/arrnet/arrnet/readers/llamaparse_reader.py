"""Reader: LlamaParse (LlamaCloud parse API v2, https://api.cloud.llamaindex.ai), key in
``LLAMA_CLOUD_API_KEY``.  Written against developers.llamaindex.ai (read 2026-11-11):

    POST /api/v2/parse/upload   multipart: file, configuration = JSON
                                {"tier", "version": "latest", "page_ranges": {"target_pages": "1,3,5-10"}}
                                -> {"id", "status", ...}
    GET  /api/v2/parse/{id}?expand=markdown,usage
                                -> {"job": {"id", "status": PENDING|RUNNING|COMPLETED|FAILED|CANCELLED,
                                    "error_message", "usage"?: {"credits"}},
                                    "markdown": {"pages": [{"page_number", "success", "markdown"}]}}

Only the selected pages are sent for parsing (``target_pages``, 1-based), to keep the cost down:
the same selection as the Docling reader.  The markdown tables of those pages are read with the
shared interpretation (:mod:`arrnet.readers.interpret`).  Cost is the job's credits at the
policy's price; when the API has not reported credits yet, it is estimated from the tier's
credits per page and the note says so.

With no key the reader returns ``skipped`` with the reason; it never produces output of its own.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
import pymupdf

from .. import store
from ..arrdb_bridge import TITLE, stage_of
from ..reference import aliases as all_aliases
from ..reference import reader_kind, reading_groups
from ..spend import Budget, BudgetExceeded, policy
from .base import ParseResult, Reader
from .docling_reader import select_pages
from .interpret import grid_to_table, group_for, markdown_tables, tables_to_rows

BASE = "https://api.cloud.llamaindex.ai"
VERSION = "llamaparse-v2 reader 1"
DONE = {"COMPLETED", "FAILED", "CANCELLED"}


def page_ranges(pages: list[int]) -> str:
    out, start, prev = [], None, None
    for p in sorted(pages):
        if start is None:
            start = prev = p
        elif p == prev + 1:
            prev = p
        else:
            out.append(f"{start}" if start == prev else f"{start}-{prev}")
            start = prev = p
    if start is not None:
        out.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ",".join(out)


def tables_from_pages(
    md_pages: list[tuple[int, str]],
    licensees: list[str],
    aliases: dict[str, list[str]],
    kind: str = "discom",
    groups: list[tuple[list[str], str]] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """arrdb-shaped tables from (page, markdown) pairs; a titled pipe table, or the continuation of
    one at the top of the next page with the same number of columns."""
    raw: list[dict[str, Any]] = []
    for pg, md in md_pages:
        lines = md.splitlines()
        for start, grid in markdown_tables(md):
            before = [x.strip("# *").strip() for x in lines[max(0, start - 6) : start] if x.strip()]
            title = next((t for t in reversed(before) if TITLE.match(t)), "")
            if not title and grid and grid[0] and TITLE.match(grid[0][0]) and not any(grid[0][1:]):
                title, grid = grid[0][0], grid[1:]  # the title printed as the table's first row
            width = max((len(r) for r in grid), default=0)
            first_on_page = not any(TITLE.match(t) for t in before) and all(
                not ln.lstrip().startswith("|") for ln in lines[:start]
            )
            if not title and raw and raw[-1]["last_page"] == pg - 1 and first_on_page and width == raw[-1]["width"]:
                raw[-1]["grid"].extend(grid[1:] if grid and not any(re.search(r"\d", c) for c in grid[0]) else grid)
                raw[-1]["row_pages"] = raw[-1]["row_pages"] + [pg] * (len(raw[-1]["grid"]) - len(raw[-1]["row_pages"]))
                raw[-1]["last_page"] = pg
                continue
            raw.append(
                {
                    "title": title,
                    "page": pg,
                    "last_page": pg,
                    "grid": grid,
                    "row_pages": [pg] * len(grid),
                    "width": width,
                    "above": " ".join(before[-3:]),
                }
            )
    tables = []
    for r in raw:
        glic = group_for(r["title"], groups or [(licensees, kind)], aliases) if r["title"] else None
        if glic is None:
            continue
        t = grid_to_table(
            r["grid"],
            title=r["title"],
            page=r["page"],
            row_pages=r["row_pages"],
            licensees=glic,
            aliases=aliases,
            above=r["above"],
        )
        if t:
            t["unit_from"] = "printed with the table" if t["unit"] else None
            t["cells"] = r["grid"]
            tables.append(t)
    return tables, len(raw)


class LlamaParseReader(Reader):
    name = "llamaparse"
    version = VERSION

    def __init__(
        self,
        api_key: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        is_real: bool = True,
        budget: Budget | None = None,
        pol: dict[str, Any] | None = None,
        sleep=time.sleep,
        max_total_pages: int | None = None,
        reuse_raw: bool = True,
    ) -> None:
        self.reuse_raw = reuse_raw
        self.pages_left = max_total_pages  # a page allowance across the orders of one run
        self.key = api_key if api_key is not None else os.environ.get("LLAMA_CLOUD_API_KEY")
        self.transport, self.is_real, self.sleep = transport, is_real, sleep
        self.pol = pol or policy()
        self.budget = budget or Budget(self.pol)

    def read(self, order: dict[str, Any], pdf_path: str | Path | None) -> ParseResult:
        if not self.key:
            return self.skipped("LLAMA_CLOUD_API_KEY is not set", is_real=self.is_real, provider="llamaindex")
        if not pdf_path:
            return self.skipped("the order's file is not in the cache", is_real=self.is_real, provider="llamaindex")
        lp = self.pol["llamaparse"]
        tier = lp["tier"]
        lic = list(order.get("licensees") or [])
        al = all_aliases()
        aliases = {k: al.get(k, []) for k in lic}
        n_pages = len(pymupdf.open(str(pdf_path)))
        kind = reader_kind(order)
        cap = int(lp["max_pages_per_order"])
        if self.pages_left is not None:
            cap = min(cap, self.pages_left)
        if cap <= 0:
            return self.skipped("the run's page allowance is used up", is_real=self.is_real, provider="llamaindex")
        pages, why = select_pages(
            order,
            n_pages,
            cap,
            lic,
            aliases,
            int(lp.get("max_ocr_pages_per_order", 0)),
            neighbours=int(lp.get("neighbours", 0)),
            kind=kind,
        )
        pages = pages[:cap]
        if not pages:
            return ParseResult(
                self.name,
                self.version,
                "ok",
                is_real=self.is_real,
                provider="llamaindex",
                note="no page to parse: no ARR table title found",
            )
        per_page = lp["credits_per_page"][tier] * lp["usd_per_1000_credits"] / 1000.0
        estimate = len(pages) * per_page
        t0 = time.monotonic()
        cfg = {"tier": tier, "version": "latest", "page_ranges": {"target_pages": page_ranges(pages)}}
        sha = order.get("sha256") or ""
        raw = store.read(sha, "llamaparse_raw") if self.reuse_raw and sha else None
        if (
            raw
            and raw.get("is_real") == self.is_real
            and raw.get("configuration") == cfg
            and (raw.get("response") or {}).get("job", {}).get("status") == "COMPLETED"
        ):
            # the same pages in the same tier were parsed before: read the kept response, no new call
            d, job_id, reused = raw["response"], raw["job_id"], True
            status = "COMPLETED"
        else:
            reused = False
            out = self._call(pdf_path, cfg, pages, estimate)
            if isinstance(out, ParseResult):
                return out
            d, job_id, status = out
            if sha:
                store.write(
                    sha,
                    "llamaparse_raw",
                    {"configuration": cfg, "job_id": job_id, "response": d, "is_real": self.is_real},
                )
        job = d.get("job") or {}
        usage = job.get("usage") or d.get("usage") or {}
        credits = usage.get("credits")
        # the API reports credits, not money: the parse records cost_usd 0 and the credits; the spend
        # ledger keeps the policy-price equivalent so that the daily cap still counts it
        equiv = credits * lp["usd_per_1000_credits"] / 1000.0 if credits is not None else estimate
        cost = 0.0
        cost_note = (
            f"; the API reported {credits} credits (about ${equiv:.4f} at the policy price; not a billed amount)"
            if credits is not None
            else f"; the API reported no credits yet (estimate ${estimate:.4f})"
        )
        if self.is_real and not reused:
            self.budget.record(
                "llamaparse",
                "llamaindex",
                tier,
                equiv,
                is_real=True,
                job_id=job_id,
                credits=credits,
                estimated_from_credits=True,
                order_url=order["url"],
            )
        if status != "COMPLETED":
            res = self._failed(f"job {status}: {job.get('error_message')}{cost_note}", pages)
            return res
        md_pages = []
        selected = set(pages)
        got = [p for p in (d.get("markdown") or {}).get("pages", []) if p.get("success", True)]
        numbers = [int(p["page_number"]) for p in got]
        # target_pages keeps the document's page numbers; if the API numbered the selection from 1, map back
        remap = bool(numbers) and not set(numbers) <= selected and max(numbers) <= len(pages)
        for p in got:
            n = int(p["page_number"])
            md_pages.append((pages[n - 1] if remap else n, p.get("markdown") or ""))
        tables, found = tables_from_pages(md_pages, lic, aliases, kind, reading_groups(order))
        trows, vrows = tables_to_rows(tables, order.get("arr_year"), stage_of)
        return ParseResult(
            self.name,
            self.version,
            "ok" if len(got) == len(pages) else "partial",
            is_real=self.is_real,
            provider="llamaindex",
            model=tier,
            pages_parsed=len(got),
            cost_usd=cost,
            tables=trows,
            values=vrows,
            page_texts={str(p): md for p, md in md_pages},
            pages=pages,
            seconds=time.monotonic() - t0,
            note=(
                f"{len(got)} of {len(pages)} pages parsed ({why['why']}); {found} tables, {len(trows)} ARR tables, "
                f"{len(vrows)} values{cost_note}"
            ),
            extra={
                "job_id": job_id,
                "reused_kept_response": reused,
                "credits": credits,
                "usd_equivalent": equiv,
                "page_numbers_remapped": remap,
            },
        )

    def _call(self, pdf_path, cfg: dict[str, Any], pages: list[int], estimate: float):
        """Upload with the configuration, poll the job; (response, job id, status) or a failed result."""
        lp = self.pol["llamaparse"]
        try:
            if self.is_real:
                self.budget.reserve("llamaparse", estimate)
        except BudgetExceeded as e:
            return self.skipped(f"budget: {e}", is_real=self.is_real, provider="llamaindex")
        with httpx.Client(
            base_url=BASE, transport=self.transport, timeout=180, headers={"Authorization": f"Bearer {self.key}"}
        ) as c:
            try:
                with open(pdf_path, "rb") as f:
                    r = c.post(
                        "/api/v2/parse/upload",
                        files={"file": (Path(pdf_path).name, f, "application/pdf")},
                        data={"configuration": json.dumps(cfg)},
                    )
                if r.status_code >= 400:
                    return self._failed(f"upload refused: HTTP {r.status_code}: {r.text[:300]}", pages)
                job_id = r.json()["id"]
                if self.pages_left is not None:
                    self.pages_left -= len(pages)
                deadline = time.monotonic() + float(lp.get("timeout_seconds", 900))
                while True:
                    g = c.get(f"/api/v2/parse/{job_id}", params={"expand": "markdown,usage"})
                    if g.status_code >= 400:
                        return self._failed(f"status refused: HTTP {g.status_code}: {g.text[:300]}", pages)
                    d = g.json()
                    status = (d.get("job") or {}).get("status")
                    if status in DONE:
                        return d, job_id, status
                    if time.monotonic() > deadline:
                        return self._failed(f"job {job_id} not finished in time (last status {status})", pages)
                    self.sleep(float(lp.get("poll_seconds", 5)))
            except httpx.HTTPError as e:
                return self._failed(f"{type(e).__name__}: {e}"[:300], pages)

    def _failed(self, why: str, pages: list[int]) -> ParseResult:
        return ParseResult(
            self.name, self.version, "failed", is_real=self.is_real, provider="llamaindex", note=why, pages=pages
        )
