"""The Extractor answered by session agents instead of the Anthropic API.

There is no API key in this deployment, so the Extractor's exact requests (the same system
prompt, the same page selection, the same delimited page text and the same JSON schema as
``readers/llm_extractor.py``) are written out as packets; agents of the coding session that runs
this repository read each packet and write a reply that follows the schema; the replies are then
fed back through the unchanged Extractor (``_take``: unknown codes, utilities, pages and
paragraphs dropped; numbers parsed from ``value_printed``), and the unchanged Verifier checks
every quote against the page's text layer before anything is stored.

    python -I -m arrnet.session_extract prepare DIR [--only UPERC] [--manifest F ...] [--more N]
    python -I -m arrnet.session_extract check DIR KEY [KEY ...]     # a reply, before it is used
    python -I -m arrnet.session_extract status DIR
    python -I -m arrnet.run read --reader llm --replies DIR [--only UPERC] ...

Provenance is never blurred: the parse is recorded with provider ``claude-code-session`` and
model ``session agent``, at no API cost, and never as an Anthropic API run.  A packet with no
reply is a page not read (the parse is ``partial``), never a guess.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from . import manifest, store
from .librarian import split_paragraphs
from .readers import llm_extractor as lx
from .readers.base import ParseResult

PROVIDER = "claude-code-session"
MODEL = "session agent"


def key_of(system: str, message: str) -> str:
    return hashlib.sha256((system + "\x00" + message).encode("utf-8")).hexdigest()[:20]


class FileClient:
    """The shape of ``anthropic.Anthropic().messages`` that the Extractor uses, answered from
    reply files written by session agents."""

    def __init__(self, d: str | Path) -> None:
        self.dir = Path(d)
        self.messages = self

    def _key(self, req: dict[str, Any]) -> str:
        return key_of(req["system"], req["messages"][0]["content"])

    def count_tokens(self, **req: Any) -> SimpleNamespace:
        return SimpleNamespace(input_tokens=len(req["messages"][0]["content"]) // 4)

    def create(self, **req: Any) -> SimpleNamespace:
        k = self._key(req)
        p = self.dir / "replies" / f"{k}.json"
        if not p.exists():
            raise FileNotFoundError(f"no reply for packet {k}")
        text = p.read_text(encoding="utf-8")
        usage = SimpleNamespace(
            input_tokens=len(req["messages"][0]["content"]) // 4,
            output_tokens=len(text) // 4,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        )
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn", usage=usage)


is_contents = lx.is_contents
DIRECTIVE = re.compile(r"\b(directs?|directed|directive|direction)\b", re.I)


def score(text: str) -> float:
    """How much a page is worth reading: key-parameter terms, directives and printed figures."""
    figures = len(re.findall(r"\d[\d,]*\.\d+", text))
    return 2 * len(lx.KEY_PAGES.findall(text)) + 3 * len(DIRECTIVE.findall(text)) + min(figures, 60) / 10


def choose_more(order: dict[str, Any], pages: list[dict[str, Any]], n: int, taken: set[int]) -> list[int]:
    """Round 2: the best-scoring pages not yet taken, never a contents page."""
    cands = [
        (score(p["text"]), p["page"])
        for p in pages
        if p["has_text_layer"] and p["page"] not in taken and not is_contents(p["text"]) and score(p["text"]) >= 4
    ]
    return sorted(pg for _, pg in sorted(cands, reverse=True)[:n])


def _index(d: Path) -> list[dict[str, Any]]:
    p = Path(d) / "index.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def extractor(d: str | Path) -> lx.Extractor:
    """The Extractor answered from ``d``: it reads exactly the pages that were packeted (every
    round), so a reply is never asked for a page nobody was given."""
    index = _index(Path(d))

    def choose(order: dict[str, Any], pages: list[dict[str, Any]], cap: int) -> list[int]:
        mine = sorted({x["page"] for x in index if x["order_url"] == order["url"]})
        return mine if index else lx._choose_pages(order, pages, cap)

    return lx.Extractor(FileClient(d), is_real=True, provider=PROVIDER, model=MODEL, priced=False, choose=choose)


def packets(
    order: dict[str, Any], ex: lx.Extractor, more: int = 0, taken: set[int] | None = None
) -> list[dict[str, Any]]:
    """The requests the Extractor would send for this order, one per target page (``more``:
    round 2, that many further pages beyond ``taken``)."""
    doc = store.read(order.get("sha256") or "", "pages")
    if not doc:
        return []
    pages = doc["pages"]
    by_page = {p["page"]: p for p in pages}
    out = []
    chosen = (
        choose_more(order, pages, more, taken or set())
        if more
        else lx._choose_pages(order, pages, int(ex.pol["extractor"]["max_pages_per_order"]))
    )
    for pg in chosen:
        p = by_page[pg]
        if not p["has_text_layer"]:
            continue
        nxt = by_page.get(pg + 1)
        paras = split_paragraphs(p["text"])
        msg = lx.user_message(order, pg, p["text"], (pg + 1, nxt["text"]) if nxt else None, paras, ex.params)
        out.append({"key": key_of(lx.SYSTEM, msg), "order_url": order["url"], "sha256": order["sha256"],
                    "page": pg, "message": msg})  # fmt: skip
    return out


def prepare(d: Path, orders: list[dict[str, Any]], more: int = 0) -> list[dict[str, Any]]:
    """Write the packets.  ``more``: a further round of that many pages per order, added to the
    existing index (pages already packeted are never sent again)."""
    ex = extractor(d)
    old = _index(d) if more else []
    (d / "packets").mkdir(parents=True, exist_ok=True)
    (d / "replies").mkdir(parents=True, exist_ok=True)
    sch = lx.schema(ex.heads, [p["code"] for p in ex.params])
    (d / "schema.json").write_text(json.dumps(sch, indent=1), encoding="utf-8")
    (d / "system.txt").write_text(lx.SYSTEM, encoding="utf-8")
    index = list(old)
    uniq, _ = manifest.unique_files(orders)
    for o in uniq:
        taken = {x["page"] for x in old if x["order_url"] == o["url"]}
        for pk in packets(o, ex, more, taken):
            (d / "packets" / f"{pk['key']}.txt").write_text(pk["message"], encoding="utf-8")
            index.append(
                {k: pk[k] for k in ("key", "order_url", "sha256", "page")}
                | {"licensees": o.get("licensees"), "round": 2 if more else 1}
            )
    (d / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    return index


def check(d: Path, key: str) -> dict[str, Any]:
    """Validate one reply against the schema, then through the Extractor's own filter and the
    Verifier's evidence test; report what would be kept and what would be rejected."""
    import jsonschema

    from .verifier import PageIndex, evidence

    idx = {x["key"]: x for x in json.loads((d / "index.json").read_text(encoding="utf-8"))}
    if key not in idx:
        return {"key": key, "ok": False, "error": "no such packet"}
    meta = idx[key]
    p = d / "replies" / f"{key}.json"
    if not p.exists():
        return {"key": key, "ok": False, "error": "no reply file"}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        jsonschema.validate(data, json.loads((d / "schema.json").read_text(encoding="utf-8")))
    except (ValueError, jsonschema.ValidationError) as e:
        return {"key": key, "ok": False, "error": f"{type(e).__name__}: {str(e)[:400]}"}
    ex = extractor(d)
    order = {"url": meta["order_url"], "sha256": meta["sha256"], "licensees": meta.get("licensees")}
    doc = store.read(meta["sha256"], "pages")
    text = next(pp["text"] for pp in doc["pages"] if pp["page"] == meta["page"])
    seqs = {x["seq"] for x in split_paragraphs(text) if x["kind"] == "text"}
    out = ParseResult("llm", ex.version, "ok")
    ex._take(order, meta["page"], data, seqs, out)
    pidx = PageIndex(doc["pages"])
    bad = []
    for kind, items in (("line", out.values), ("parameter", out.parameters)):
        for x in items:
            ok, why, _ = evidence(x, pidx, {})
            if not ok:
                bad.append({"kind": kind, "label": x.get("label"), "value_printed": x.get("value_printed"), "why": why})
    return {
        "key": key,
        "ok": True,
        "kept": {"lines": len(out.values), "parameters": len(out.parameters), "paragraphs": len(out.paragraphs)},
        "dropped_by_filter": out.extra.get("dropped", 0),
        "fail_evidence": bad[:20],
        "fail_evidence_count": len(bad),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m arrnet.session_extract")
    ap.add_argument("step", choices=["prepare", "check", "status"])
    ap.add_argument("dir")
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--only")
    ap.add_argument("--manifest", action="append")
    ap.add_argument("--more", type=int, default=0, help="prepare: a further round of N pages per order")
    a = ap.parse_args(argv)
    d = Path(a.dir)
    if a.step == "prepare":
        orders = manifest.select(manifest.load(a.manifest), a.only, None)
        before = len(_index(d)) if a.more else 0
        index = prepare(d, orders, a.more)
        print(json.dumps({"packets": len(index), "new": len(index) - before,
                          "orders": len({x["order_url"] for x in index})}))  # fmt: skip
    elif a.step == "check":
        for k in a.keys:
            print(json.dumps(check(d, k)))
    else:
        index = json.loads((d / "index.json").read_text(encoding="utf-8"))
        done = sum(1 for x in index if (d / "replies" / f"{x['key']}.json").exists())
        print(json.dumps({"packets": len(index), "replied": done}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
