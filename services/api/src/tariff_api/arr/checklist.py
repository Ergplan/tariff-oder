"""Filing checklists as versioned data (R-PKG-1).

A checklist (``packages/filing-checklists/<commission>/<id>.json``) lists what a commission's
regulations require a petition to contain or to have been done, each item with its clause, page
and a verbatim quote of the regulation, the proceedings it applies to, and the evidence that would
show it in a filing: a document of the package, a sheet of its formats workbook, or text in its
DOCX documents (a ``statement`` — a dated or sworn fact — or only a ``mention``); an item a filing's
documents cannot show (a portal filing, a fee, a public notice) is ``outside``.

``evaluate`` reports, per item, ``evidenced`` (every piece of evidence found, none of it a mere
mention), ``partly`` (something missing, or a part only mentioned), ``mentioned`` (only mentions
found), ``not_found`` or ``outside_package``, with where each piece
was found.  Evidence found is not compliance: the reviewer decides with the documents in hand.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

KINDS = {"document", "sheet", "text", "outside"}
ITEM_KEYS = {"id", "clause", "page", "quote", "requirement", "proceedings", "evidence", "note"}


def load_checklist(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a checklist: its regulation named by hash, each item's clause, page and quote, and
    evidence of a known kind with its reason.  Raises ``ValueError`` naming the item."""
    if not (data.get("regulation") or {}).get("sha256"):
        raise ValueError("a checklist names its regulation by SHA-256")
    seen: set[str] = set()
    for it in data.get("items", []):
        unknown = set(it) - ITEM_KEYS
        missing = {"id", "clause", "page", "quote", "requirement", "proceedings", "evidence"} - set(it)
        if unknown or missing:
            raise ValueError(f"{it.get('id')}: unknown {sorted(unknown)} / missing {sorted(missing)}")
        if it["id"] in seen:
            raise ValueError(f"{it['id']}: duplicate id")
        seen.add(it["id"])
        if not it["evidence"]:
            raise ValueError(f"{it['id']}: no evidence named")
        for e in it["evidence"]:
            if e.get("kind") not in KINDS or not e.get("why"):
                raise ValueError(f"{it['id']}: evidence needs a known kind and its reason")
            if e["kind"] == "text":
                if e.get("weight") not in ("statement", "mention"):
                    raise ValueError(f"{it['id']}: text evidence is a statement or a mention")
                re.compile(e["ref"])
    return data


def check_quotes(data: dict[str, Any], pdf: Path) -> list[str]:
    """Each item's quote found on its page of the regulation (whitespace-normalised, PyMuPDF's
    text) and the PDF the checklist names (its hash).  Returns the problems."""
    import hashlib

    import pymupdf

    if hashlib.sha256(pdf.read_bytes()).hexdigest() != data["regulation"]["sha256"]:
        return ["the PDF is not the checklist's regulation"]

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    with pymupdf.open(pdf) as doc:
        pages = {i + 1: norm(p.get_text()) for i, p in enumerate(doc)}
    return [
        f"{it['id']}: quote not on page {it['page']}"
        for it in data["items"]
        if norm(it["quote"]) not in pages.get(it["page"], "")
    ]


def docx_text(path: Path) -> str:
    """A DOCX's paragraphs and table cells as one whitespace-normalised text (untrusted data)."""
    import docx

    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs] + [c.text for t in d.tables for r in t.rows for c in r.cells]
    return re.sub(r"\s+", " ", " ".join(parts))


def evaluate(
    data: dict[str, Any], documents: list[dict[str, Any]], sheets: list[str], texts: dict[str, str]
) -> list[dict[str, Any]]:
    """Each item against a filing: ``documents`` (the package's list, a document present when it
    is hashed), the formats workbook's ``sheets`` and the DOCX ``texts`` (name → text)."""
    present = [d["name"] for d in documents if d.get("sha256")]
    out: list[dict[str, Any]] = []
    for it in data["items"]:
        found: list[dict[str, Any]] = []
        for e in it["evidence"]:
            rec: dict[str, Any] = {"kind": e["kind"], "ref": e.get("ref"), "why": e["why"], "weight": e.get("weight")}
            if e["kind"] == "document":
                # "Appendix-I" is not "Appendix-II": the reference ends where a letter or digit would
                pat = re.compile(re.escape(e["ref"]) + r"(?![A-Za-z0-9])")
                hit = next((n for n in present if pat.search(n)), None)
                rec["found"], rec["where"] = hit is not None, hit
            elif e["kind"] == "sheet":
                rec["found"], rec["where"] = e["ref"] in sheets, e["ref"] if e["ref"] in sheets else None
            elif e["kind"] == "text":
                rec["found"], rec["where"] = False, None
                for name, text in sorted(texts.items()):
                    m = re.search(e["ref"], text, re.I)
                    if m:
                        rec["found"] = True
                        rec["where"] = name
                        rec["context"] = text[max(0, m.start() - 100) : m.end() + 60]
                        break
            else:
                rec["found"] = None
            found.append(rec)
        inside = [f for f in found if f["kind"] != "outside"]
        hits = [f for f in inside if f["found"]]
        weak = [f for f in inside if f.get("weight") == "mention"]
        if not inside:
            result = "outside_package"
        elif not hits:
            result = "not_found"
        elif all(f.get("weight") == "mention" for f in hits):
            result = "mentioned"
        elif len(hits) == len(inside) and not weak:
            result = "evidenced"
        else:
            result = "partly"  # something missing, or a part only mentioned
        out.append(
            {k: it.get(k) for k in ("id", "clause", "page", "quote", "requirement", "proceedings", "note")}
            | {"result": result, "evidence": found}
        )
    return out
