"""Evaluate a reference filing against a commission's filing checklist (R-PKG-1).

    uv run python scripts/filing_checklist.py uperc-npcl-fy2026-27 --checklist uperc/myt-2025

Checks the checklist's quotes against its regulation PDF (when the PDF is in the repository), then
writes ``checklist.json`` beside the reference: each item evidenced / partly / mentioned /
not found / outside the package, with where each piece of evidence was found.  Evidence found is
not compliance — the reviewer decides.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api" / "src"))

from tariff_api.arr.checklist import check_quotes, docx_text, evaluate, load_checklist  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    ap.add_argument("--checklist", required=True)
    args = ap.parse_args()
    import openpyxl

    data = load_checklist(json.loads((ROOT / "packages" / "filing-checklists" / f"{args.checklist}.json").read_text()))
    pdf = ROOT / data["regulation"]["path"]
    problems = check_quotes(data, pdf) if pdf.exists() else ["regulation PDF not in the repository"]
    for p in problems:
        print(p, file=sys.stderr)
    if problems:
        return 1
    folder = ROOT / "packages" / "reference-filings" / args.package
    ref = json.loads((folder.parent / f"{args.package}.json").read_text())
    formats = next(d["name"] for d in ref["documents"] if d.get("role") == "formats")
    sheets = openpyxl.load_workbook(folder / formats, read_only=True).sheetnames
    texts = {p.name: docx_text(p) for p in sorted(folder.glob("*.docx"))}
    items = evaluate(data, ref["documents"], sheets, texts)
    print(dict(collections.Counter(i["result"] for i in items)))
    for i in items:
        print(f"  {i['result']:16} {i['id']:16} {i['requirement'][:70]}")
    report = {
        "checklist": data["id"],
        "version": data["version"],
        "status": data["status"],
        "scope": data["scope"],
        "regulation": data["regulation"],
        "quotes_checked": len(data["items"]),
        "items": items,
    }
    (folder / "checklist.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
