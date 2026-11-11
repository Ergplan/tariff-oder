"""Librarian: paragraphs from page text, chunks for search, and their embeddings.

Paragraphs are split from each page's text on blank lines and on paragraph numbers ("4.13.9",
"6.2."); a short line without a closing full stop is a heading.  Lines that are mostly numbers
(tables) are not paragraphs: the facts hold them, with their evidence.  A paragraph longer than
the chunk limit is split at sentence ends into several paragraphs, so that each chunk is one or
more whole paragraphs of one page (a chunk never crosses a page).  Chunks are about 200–400
tokens (tokens estimated as 1.3 per word).

Embeddings are BAAI/bge-small-en-v1.5 (384 dimensions) through fastembed, computed locally; each
chunk records the model.  If the model cannot be loaded, chunks are posted without embeddings and
the run note says so.
"""

from __future__ import annotations

import re
from typing import Any

from . import store
from .ingest import Sink
from .runs import Run

VERSION = "librarian 1"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
PARA_NO = re.compile(r"^\s*(\d{1,2}(\.\d{1,3}){1,4}\.?|\(\s?[a-z]{1,4}\s?\)|[a-z]\))\s+\S", re.I)
MIN_TOKENS, MAX_TOKENS = 200, 400


def ntokens(text: str) -> int:
    return int(len(text.split()) * 1.3) + 1


def _numeric_share(line: str) -> float:
    toks = line.split()
    if not toks:
        return 0.0
    return sum(1 for t in toks if re.fullmatch(r"[\d,.()\-–%]+", t)) / len(toks)


def is_heading(text: str) -> bool:
    words = text.split()
    if not words or len(words) > 12 or text.rstrip().endswith((".", ":", ";", ",")):
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    upper = sum(1 for c in letters if c.isupper()) / len(letters)
    titled = sum(1 for w in words if w[:1].isupper() or not w[:1].isalpha()) / len(words)
    return upper > 0.6 or titled > 0.75


def split_paragraphs(text: str) -> list[dict[str, Any]]:
    """[{seq, kind: 'text' | 'heading', text}] in page order."""
    paras: list[list[str]] = []
    cur: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if cur:
                paras.append(cur)
                cur = []
            continue
        if _numeric_share(line) >= 0.5 and len(line.split()) >= 2 or re.fullmatch(r"[\d\s.,()\-–%]+", line):
            if cur:
                paras.append(cur)
                cur = []
            continue  # a table row or a page number
        starts_new = bool(PARA_NO.match(line))
        prev_heading = bool(cur) and len(cur) == 1 and is_heading(cur[0]) and not cur[0].endswith("-")
        if cur and (starts_new or prev_heading):
            paras.append(cur)
            cur = []
        cur.append(line)
    if cur:
        paras.append(cur)
    out: list[dict[str, Any]] = []
    for lines in paras:
        t = re.sub(r"\s+", " ", " ".join(lines)).strip()
        if len(t) < 3:
            continue
        kind = "heading" if is_heading(t) else "text"
        if kind == "text" and ntokens(t) > MAX_TOKENS:
            for piece in _split_long(t):
                out.append({"kind": "text", "text": piece})
        else:
            out.append({"kind": kind, "text": t})
    for i, p in enumerate(out):
        p["seq"] = i + 1
    return out


def _split_long(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.;:])\s+(?=[A-Z(\d])", text)
    pieces, cur = [], ""
    for s in sentences:
        if cur and ntokens(cur + " " + s) > MAX_TOKENS:
            pieces.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        pieces.append(cur)
    out = []
    for p in pieces:  # a sentence longer than the limit: cut by words
        if ntokens(p) <= MAX_TOKENS:
            out.append(p)
            continue
        words = p.split()
        step = int(MAX_TOKENS / 1.3) - 1
        out.extend(" ".join(words[i : i + step]) for i in range(0, len(words), step))
    return out


def chunk_page(paras: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """[{paragraph_seq (first paragraph), text}]: consecutive paragraphs of one page joined until
    the chunk reaches MIN_TOKENS, never past MAX_TOKENS."""
    chunks: list[dict[str, Any]] = []
    cur: list[dict[str, Any]] = []
    size = 0
    for p in paras:
        n = ntokens(p["text"])
        if cur and size + n > MAX_TOKENS:
            chunks.append({"paragraph_seq": cur[0]["seq"], "text": "\n\n".join(x["text"] for x in cur)})
            cur, size = [], 0
        cur.append(p)
        size += n
        if size >= MIN_TOKENS:
            chunks.append({"paragraph_seq": cur[0]["seq"], "text": "\n\n".join(x["text"] for x in cur)})
            cur, size = [], 0
    if cur:
        chunks.append({"paragraph_seq": cur[0]["seq"], "text": "\n\n".join(x["text"] for x in cur)})
    return chunks


_EMBEDDER: Any = None
_EMBED_ERROR: str | None = None


def embedder() -> tuple[Any, str | None]:
    global _EMBEDDER, _EMBED_ERROR
    if _EMBEDDER is None and _EMBED_ERROR is None:
        try:
            from fastembed import TextEmbedding

            _EMBEDDER = TextEmbedding(EMBED_MODEL)
        except Exception as e:  # not installed, or the model cannot be downloaded
            _EMBED_ERROR = f"embedding model unavailable ({type(e).__name__}: {str(e)[:200]})"
    return _EMBEDDER, _EMBED_ERROR


def index_order(order: dict[str, Any], sink: Sink, *, embed: bool = True) -> dict[str, Any]:
    sha = order["sha256"]
    run = Run("librarian", VERSION, order_url=order["url"])
    doc = store.read(sha, "pages")
    if not doc:
        run.post(sink, "skipped", "no page text (run the courier first)")
        return {"skipped": True}
    llm = store.read(sha, "llm") or {}
    classes = {}
    if llm.get("is_real") and llm.get("status") in ("ok", "partial"):
        classes = {(p["page"], p["seq"]): p for p in llm.get("paragraphs", [])}
    paragraphs, chunks = [], []
    for pg in doc["pages"]:
        if not pg["has_text_layer"]:
            continue  # OCR text is the reader's, not the order's text layer; not indexed as paragraphs
        paras = split_paragraphs(pg["text"])
        for p in paras:
            row = {"order_url": order["url"], "page": pg["page"], "seq": p["seq"], "kind": p["kind"], "text": p["text"]}
            c = classes.get((pg["page"], p["seq"]))
            if c and p["kind"] == "text":
                row.update({"kind": c["kind"], "kind_by": "llm", "summary": c.get("summary")})
                if c.get("topic"):
                    row["topic"] = c["topic"]
            paragraphs.append(row)
        for c in chunk_page(paras):
            chunks.append({"order_url": order["url"], "page": pg["page"], **c})
    note = []
    model, err = embedder() if embed else (None, "embeddings not requested")
    if model is not None and chunks:
        vecs = list(model.embed([c["text"] for c in chunks], batch_size=64))
        for c, v in zip(chunks, vecs, strict=True):
            c["embedding"] = [round(float(x), 6) for x in v]
            c["embedding_model"] = EMBED_MODEL
        note.append(f"embedded with {EMBED_MODEL}")
    elif err:
        note.append(f"chunks posted without embeddings: {err}")
    rp = sink.post("paragraphs", paragraphs)
    rc = sink.post("chunks", chunks)
    stats = {
        "paragraphs": len(paragraphs),
        "headings": sum(1 for p in paragraphs if p["kind"] == "heading"),
        "chunks": len(chunks),
        "embedded": sum(1 for c in chunks if "embedding" in c),
        "classified": sum(1 for p in paragraphs if p.get("kind_by")),
    }
    store.write(sha, "index", stats)
    run.post(
        sink,
        "ok" if not (rp.rejected or rc.rejected) else "partial",
        f"{stats['paragraphs']} paragraphs, {stats['chunks']} chunks; " + "; ".join(note),
        rows_written=rp.written + rc.written,
        rows_rejected=len(rp.rejected) + len(rc.rejected),
    )
    return stats
