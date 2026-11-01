"""Evaluation (milestone 13, R-ACC-7): the ARR reading of a commission's order measured against the
licensee's own filed petition.  Read-only: replays the structure channel over the order's
proposed chapters (as the reading preview does) and writes nothing to the database.

The order restates the petitioner's claims ("petitioned") and its own decisions; the petition's
filed formats hold the claims exactly.  For every value the reference has — a *placed* row, a
year, a voice — the order's reading is classified:

- ``match``          same line, year and voice; the value agrees at the displayed precision
- ``value_differs``  same line, year and voice; a different number (the order may print a revised
                     claim from an additional submission — not necessarily a reading error)
- ``sum_of_rows``    same line, year and voice; the order's number is the sum of the reference
                     rows proposed for that line (the commission prints one total the petition
                     splits — a convention for the mapping's ``total_includes``)
- ``sign_differs``   same line, year and voice; the same magnitude with the opposite sign (a
                     gap printed as a positive shortfall by one and a negative surplus by the other)
- ``voice_differs``  same line and year, same number, another voice (the order calls the
                     petitioner's audited figures "claimed", or the reverse)
- ``elsewhere``      the number was read for that year, but under another line
                     (an attribution question on one side or the other)
- ``not_read``       nothing for that line, year and voice, and the number nowhere that year

Only the years and voices the order prints are compared (the denominator); the rest are
counted as ``out_of_scope``.

Recall here is **line recall against the petitioner's figures**, on unreviewed placements on
both sides: an indicator for the reviewer, not an accuracy claim.

Run inside the worker container (it needs the order's stored grids):

    python tests/evals/reference_vs_order.py <order source id> <reference.json> [--sheet ARR]
"""

from __future__ import annotations

import argparse
import collections
import json
import uuid
from decimal import Decimal


def order_candidates(sid: uuid.UUID) -> list[dict]:
    import pymupdf
    from sqlalchemy import select

    from tariff_api.adapters import build_adapters
    from tariff_api.adapters.storage import ObjectStore
    from tariff_api.arr.chapters import part_from_note
    from tariff_api.arr.extract import GridIn, read_grids
    from tariff_api.arr.taxonomy import Placer, load_mapping, load_taxonomy
    from tariff_api.config import get_settings
    from tariff_api.db import init_db, session_scope
    from tariff_api.models import ArrChapter, SourceDocument, TableGridRecord
    from tariff_api.services.sources import licensees_of
    from tariff_worker.stages.grid import _lines_around

    init_db(get_settings())
    storage = build_adapters(get_settings()).storage
    tax = load_taxonomy()
    with session_scope() as s:
        src = s.get(SourceDocument, sid)
        mapping = load_mapping(src.utility.commission.code, fallback=True)
        placer = Placer(tax, mapping, src.utility.licensee_kind)
        chapters = [
            (c.ordinal, c.branch, c.page_start, c.page_end, part_from_note(c.note), c.status == "excluded")
            for c in s.execute(
                select(ArrChapter).where(ArrChapter.source_id == sid).order_by(ArrChapter.ordinal)
            ).scalars()
        ]
        grids = {
            (g.page_index, g.ordinal): g.object_key
            for g in s.execute(
                select(TableGridRecord).where(TableGridRecord.source_id == sid, TableGridRecord.is_primary.is_(True))
            ).scalars()
        }
        lic = {u.code: [u.name, *(u.aliases or [])] for u in licensees_of(s, src)}
        utility = src.utility.code
        doc = pymupdf.open(stream=storage.get(ObjectStore.SOURCES, src.object_key), filetype="pdf")
    out = []
    for ordinal, branch, a, b, part, excluded in chapters:
        if excluded:
            continue
        gs = []
        for (page, o), key in sorted(grids.items()):
            if a <= page <= b:
                g = json.loads(storage.get(ObjectStore.ARTEFACTS, key))["grid"]
                above, _ = _lines_around(doc[page - 1], g["bbox"])
                gs.append(GridIn(page, o, g["rows"], int(g.get("header_rows") or 0), above))
        res, _ = read_grids(
            gs,
            taxonomy=tax,
            mapping=mapping,
            placer=placer,
            source_id=str(sid),
            utility=utility,
            part=part,
            licensees=lic if len(lic) > 1 else None,
            branch=branch,
        )
        for c in res.candidates:
            if c.canonical_value is None:
                continue
            out.append(
                {
                    "line": c.line_code,
                    "year": c.fiscal_year,
                    "voice": c.value_type,
                    "value": str(c.canonical_value),
                    "unit": c.canonical_unit,
                    "page": c.evidence[0].page_index if c.evidence else None,
                    "category": c.category_code or "",
                    "chapter": ordinal,
                }
            )
    return out


def close(a: Decimal, b: Decimal, places: int) -> bool:
    return abs(a - b) <= Decimal(1).scaleb(-places) / 2 + Decimal("0.000001")


def compare(reference: dict, sheet: str, cands: list[dict]) -> dict:
    (sh,) = [x for x in reference["sheets"] if x["sheet"] == sheet]
    by_key = collections.defaultdict(list)
    by_year = collections.defaultdict(list)
    for c in cands:
        if c["category"]:
            continue
        by_key[(c["line"], c["year"], c["voice"])].append(c)
        by_year[c["year"]].append(c)
    in_scope = {(c["year"], c["voice"]) for c in cands if not c["category"]}
    # the reference rows proposed for each line, summed by year and voice (for sum_of_rows)
    row_sums: dict[tuple, Decimal] = collections.defaultdict(Decimal)
    for row in sh["rows"]:
        for cell in row["cells"]:
            if row["line_code"] and cell["state"] == "value" and cell["displayed"] is not None:
                row_sums[(row["line_code"], cell["fiscal_year"], cell["voice"])] += Decimal(cell["displayed"])
    results = []
    out_of_scope = 0
    for row in sh["rows"]:
        if not row["line_code"]:
            continue
        for cell in row["cells"]:
            if cell["state"] != "value" or cell["displayed"] is None:
                continue
            want = Decimal(cell["displayed"])
            places = max(0, -want.as_tuple().exponent)
            if want == 0:
                continue  # a zero row says nothing about reading
            if (cell["fiscal_year"], cell["voice"]) not in in_scope:
                out_of_scope += 1
                continue
            key = (row["line_code"], cell["fiscal_year"], cell["voice"])
            same = by_key.get(key, [])
            hit = next((c for c in same if close(Decimal(c["value"]), want, places)), None)
            year_hits = [c for c in by_year.get(cell["fiscal_year"], []) if close(Decimal(c["value"]), want, places)]
            summed = next((c for c in same if close(Decimal(c["value"]), row_sums[key], 2)), None)
            other_voice = next((c for c in year_hits if c["line"] == row["line_code"]), None)
            if hit:
                kind, at = "match", hit
            elif signed := next((c for c in same if close(-Decimal(c["value"]), want, places)), None):
                kind, at = "sign_differs", signed
            elif summed:
                kind, at = "sum_of_rows", summed
            elif other_voice:
                kind, at = "voice_differs", other_voice
            elif same:
                kind, at = "value_differs", same[0]
            else:
                at = year_hits[0] if year_hits else None
                kind = "elsewhere" if at else "not_read"
            results.append(
                {
                    "row": row["label"][:70],
                    "line": row["line_code"],
                    "year": cell["fiscal_year"],
                    "voice": cell["voice"],
                    "words": cell["words"].replace("\n", " "),
                    "reference": cell["displayed"],
                    "result": kind,
                    "order_value": at["value"] if at else None,
                    "order_line": at["line"] if at else None,
                    "order_voice": at["voice"] if at else None,
                    "order_page": at["page"] if at else None,
                }
            )
    counts = collections.Counter(r["result"] for r in results)
    by_voice = collections.defaultdict(collections.Counter)
    for r in results:
        by_voice[f"{r['year']} {r['voice']}"][r["result"]] += 1
    return {
        "sheet": sheet,
        "compared": len(results),
        "out_of_scope": out_of_scope,
        "counts": dict(counts),
        "by_year_voice": {k: dict(v) for k, v in sorted(by_voice.items())},
        "results": results,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source_id")
    ap.add_argument("reference")
    ap.add_argument("--sheet", default="ARR")
    ap.add_argument("--out")
    args = ap.parse_args()
    cands = order_candidates(uuid.UUID(args.source_id))
    rep = compare(json.load(open(args.reference)), args.sheet, cands)
    rep["order_candidates"] = len(cands)
    print(json.dumps({k: v for k, v in rep.items() if k != "results"}, indent=1))
    for r in rep["results"]:
        if r["result"] != "match":
            print(
                f"  {r['result']:13} {r['year']} {r['voice']:13} {r['line']:16} ref {r['reference']:>10}  "
                f"order {r['order_value'] or '-':>12} {r['order_line'] or ''} {r['order_voice'] or ''} p.{r['order_page']}  | {r['row'][:40]}"
            )
    if args.out:
        open(args.out, "w").write(json.dumps(rep, indent=1) + "\n")


if __name__ == "__main__":
    main()
