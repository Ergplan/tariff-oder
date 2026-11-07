"""A case's formats workbook (increment 151): the rule engine's petition fill
(``tariff_api.arr.petition_fill``) inside the client case flow.

A case of a licensee whose filed petition the engine reproduces (a reference filing with a
``fill-map.json``: today UPERC / NPCL) gets:

1. **the layout** — which filing's workbook the fill follows, its years, how many cells a fill
   writes and how many the petitioner enters;
2. **the inputs template** — the filed workbook with every fill-map cell blanked;
3. **an upload** of the petitioner's inputs workbook — checked to be an XLSX laid out as the
   filing (every sheet the fill reads present), stored, and compared with the filed inputs (how
   many input cells are blank, changed or as filed);
4. **the fill**, run as a job (``petition_fill``, about a minute and a half): the filled workbook
   (computed cells green, carried cells blue, a *Fill trace* sheet, a draft header on every
   sheet) and the full report stored as artefacts, the summary on the row.

Everything a fill writes comes from draft rules, none approved, no clause verified: a filled
workbook is a working draft, never a filing (R-APP-4).  The uploaded workbook is data: its text
is never read as instructions, and its formulas are not evaluated — the fill reads the values
the spreadsheet program saved with them.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ..adapters.storage import ObjectStore
from ..errors import AppError
from ..models import ArrCase, PetitionWorkbook, Utility
from ..queue import enqueue

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# an xlsx is a zip: refuse one that inflates past this before any XML is parsed
MAX_UNCOMPRESSED = 400 * 1024 * 1024
DRAFT_HEADER = "WORKING DRAFT - filled from draft rules; nothing verified or approved; not a filing"


def _root() -> Path:
    from ..reference_filings import _root as root

    return root()


def layout_for(utility: Utility) -> str | None:
    """The reference filing whose workbook a fill for this licensee follows: same commission and
    licensee code, with a fill map.  None when the engine cannot fill this licensee's formats."""
    for f in sorted(_root().glob("*.json")):
        d = json.loads(f.read_text())
        if (
            d.get("commission", "").upper() == utility.commission.code.upper()
            and d.get("licensee", "").upper() == utility.code.upper()
            and (_root() / d["id"] / "fill-map.json").exists()
        ):
            return d["id"]
    return None


@lru_cache(maxsize=4)
def _package(package: str) -> dict[str, Any]:
    folder = _root() / package
    manifest = json.loads((_root() / f"{package}.json").read_text())
    fmap = json.loads((folder / "fill-map.json").read_text())
    (book,) = [p for p in folder.glob("*.xlsx") if "Format" in p.name]
    layout = json.loads((folder / "reference.json").read_text())
    return {
        "folder": folder,
        "manifest": manifest,
        "map": fmap["cells"],
        "map_doc": fmap,
        "book": book,
        "layout": layout,
        "kept": _kept_cells(folder, fmap["cells"], layout),
        "labels": column_labels(folder, layout),
    }


ORDER_FIGURE = "the Commission's figure, quoted from an order (an approved or trued-up column): enter it from the order"
TARIFF_RATE = (
    "a tariff rate (the tariff in force or the one proposed): an input, never an average backed out of "
    "revenue ÷ units; enter the rate"
)
OWN_METHOD = (
    "the petitioner computes this figure another way than the draft rules (its reproduction differs from the "
    "filing): enter your own; the fill checks it"
)


def column_labels(folder: Path, layout: dict[str, Any]) -> list[dict[str, Any]]:
    """Every column label of a package: the header reader's (``reference.json``, whose column
    ``index`` counts from 0) and the hand labels (``column-labels.json``, for the columns the reader
    cannot read — a year per sheet, years in row blocks, a voice in the title).  Each: sheet,
    column letter, rows (a range or None for the whole column), fiscal_year, voice, restated, input,
    source."""
    from openpyxl.utils import get_column_letter

    out: list[dict[str, Any]] = []
    sheets = layout.get("sheets", {})
    for sh in sheets.values() if isinstance(sheets, dict) else sheets:
        for c in sh.get("columns", []):
            out.append(
                {
                    "sheet": sh["sheet"],
                    "column": get_column_letter(int(c["index"]) + 1),
                    "rows": None,
                    "fiscal_year": c.get("fiscal_year"),
                    "voice": c.get("voice"),
                    "restated": bool(c.get("restated")),
                    "input": False,
                    "source": "header",
                    "words": c.get("words", ""),
                }
            )
    hand = folder / "column-labels.json"
    if hand.exists():
        for lab in json.loads(hand.read_text())["labels"]:
            for col in lab["columns"]:
                out.append(
                    {
                        "sheet": lab["sheet"],
                        "column": col,
                        "rows": lab.get("rows"),
                        "fiscal_year": lab.get("fiscal_year"),
                        "voice": lab.get("voice"),
                        "restated": bool(lab.get("restated")),
                        "input": bool(lab.get("input")),
                        "source": "hand",
                        "words": lab.get("basis", ""),
                    }
                )
    return out


def label_of(labels: list[dict[str, Any]], cell: str) -> dict[str, Any] | None:
    """The label covering ``cell`` ("Sheet!B12"): a hand label with a row range first, then a whole
    column's."""
    sheet, _, ref = cell.rpartition("!")
    m = re.match(r"([A-Z]+)(\d+)", ref)
    col, row = m.group(1), int(m.group(2))
    hits = [lab for lab in labels if lab["sheet"] == sheet and lab["column"] == col]
    ranged = [lab for lab in hits if lab["rows"] and lab["rows"][0] <= row <= lab["rows"][1]]
    whole = [lab for lab in hits if not lab["rows"]]
    return (ranged or whole or [None])[0]


def _kept_cells(folder: Path, fmap: dict[str, Any], layout: dict[str, Any]) -> dict[str, str]:
    """Fill-map cells the inputs template keeps as filed rather than blanking (increments 153–154),
    with the reason: a figure quoted from the Commission's orders (a column labelled ``restated``)
    is the order's, never the draft rules' recomputation; a tariff rate (labelled ``input``) is
    entered, never backed out of revenue ÷ units; and a figure whose reproduction differs from the
    filing (``fill-roundtrip.json``, the known differences) is computed by the petitioner another
    way.  The fill still checks each one and reports a difference; it never overwrites an entered
    figure."""
    labels = column_labels(folder, layout)
    kept: dict[str, str] = {}
    for cell in fmap:
        lab = label_of(labels, cell)
        if lab is None:
            continue
        if lab["input"]:
            kept[cell] = TARIFF_RATE
        elif lab["restated"]:
            kept[cell] = ORDER_FIGURE
    rt = folder / "fill-roundtrip.json"
    if rt.exists():
        for d in json.loads(rt.read_text()).get("runs", {}).get("none_kept", {}).get("differing", []):
            if d.get("known") and d["cell"] in fmap:
                kept.setdefault(d["cell"], OWN_METHOD)
    return dict(sorted(kept.items()))


@lru_cache(maxsize=4)
def _inputs_of_filing(package: str) -> tuple[dict[str, Any], list[str]]:
    """The filed workbook's input cells — every numeric cell the fill map does not write — with
    their filed values, and the workbook's sheet names."""
    import openpyxl

    p = _package(package)
    wb = openpyxl.load_workbook(p["book"], data_only=True, read_only=True)
    fmap = p["map"]
    out: dict[str, Any] = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                v = getattr(c, "value", None)
                if isinstance(v, bool) or not isinstance(v, int | float):
                    continue
                key = f"{ws.title}!{c.coordinate}"
                if key not in fmap:
                    out[key] = v
    names = list(wb.sheetnames)
    wb.close()
    return out, names


def _required_sheets(package: str) -> set[str]:
    return {c.rpartition("!")[0] for c in _package(package)["map"]}


def layout(case: ArrCase, utility: Utility) -> dict[str, Any]:
    """What a fill of this case's formats would follow, or why there is none."""
    package = layout_for(utility)
    if package is None:
        return {
            "available": False,
            "why": (
                f"the engine does not yet reproduce a filed petition of {utility.code} "
                f"({utility.commission.code}): no reference filing with a fill map"
            ),
        }
    p = _package(package)
    years = p["manifest"].get("petition_years") or {}
    kinds = {k: sum(v["kind"] == k for v in p["map"].values()) for k in ("computed", "carried")}
    case_years = {case.base_fy, *(t["fiscal_year"] if isinstance(t, dict) else t for t in case.targets or [])}
    layout_years = {v for k, v in years.items() if k != "note"}
    warnings = []
    if years and not (case_years & layout_years):
        warnings.append(
            f"the workbook's layout is the {years.get('arr')} petition's (true-up {years.get('true_up')}, "
            f"APR {years.get('apr')}, ARR {years.get('arr')}); this case's years "
            f"({', '.join(sorted(case_years))}) are not in it — a fill writes into the layout's year columns, "
            "and moving the bindings a year is not built yet"
        )
    return {
        "available": True,
        "package": package,
        "title": p["manifest"].get("title"),
        "workbook": p["book"].name,
        "years": years,
        "cells_filled": len(p["map"]),
        "cells_computed": kinds["computed"],
        "cells_carried": kinds["carried"],
        "bindings": len(p["map_doc"].get("bindings", [])),
        "bindings_left_out": len(p["map_doc"].get("skipped", [])),
        "sheets": len(_required_sheets(package)),
        "cells_kept": len(p["kept"]),
        "cells_kept_order": sum(v == ORDER_FIGURE for v in p["kept"].values()),
        "cells_kept_own": sum(v == OWN_METHOD for v in p["kept"].values()),
        "cells_kept_rate": sum(v == TARIFF_RATE for v in p["kept"].values()),
        "cells_labelled": sum(label_of(p["labels"], c) is not None for c in p["map"]),
        "narrative_tables": len((_narrative_binding(package) or {}).get("tables", [])),
        "narrative_documents": len({t["document"] for t in (_narrative_binding(package) or {}).get("tables", [])}),
        "warnings": warnings,
        "status": "draft rules, none approved, no clause verified: a filled workbook is a working draft",
    }


def _package_for(utility: Utility) -> str:
    package = layout_for(utility)
    if package is None:
        raise AppError("not_found", f"no formats workbook the engine can fill for {utility.code}")
    return package


@lru_cache(maxsize=4)
def template_bytes(package: str) -> bytes:
    """The inputs template: the filed workbook (values) with the fill-map cells blanked — except
    the kept cells (``_kept_cells``: the Commission's figures and the petitioner's own methods),
    left as filed and shaded yellow — and two sheets saying so."""
    import openpyxl
    from openpyxl.styles import PatternFill

    from .petition_fill import inputs_template, to_bytes

    p = _package(package)
    kept = p["kept"]
    wb = inputs_template(openpyxl.load_workbook(p["book"], data_only=True), [c for c in p["map"] if c not in kept])
    yellow = PatternFill("solid", start_color="FFF2CC", end_color="FFF2CC")
    for cell in kept:
        sheet, _, ref = cell.rpartition("!")
        wb[sheet][ref].fill = yellow
    ws = wb.create_sheet("About this template")
    for line in (
        "Inputs template for a petition fill (working draft).",
        f"Layout: {p['manifest'].get('title')} — workbook {p['book'].name}.",
        f"{len(p['map']) - len(kept)} cells are blank: the fill computes them from the rest.  The other figures are "
        "the filing's own as filed; replace them with the petition's inputs.",
        f"{len(kept)} cells the fill could compute are kept as filed and shaded yellow (sheet 'Kept cells'): the "
        "Commission's figures quoted from its orders, and figures the petitioner computes another way.  Replace "
        "them with the order's figure or your own; the fill checks them and never overwrites them.",
        "Figures entered in a blank cell are kept and checked, never overwritten.",
        "Every rule is a draft; nothing is verified or approved; the filled workbook is not a filing.",
    ):
        ws.append([line])
    ks = wb.create_sheet("Kept cells")
    ks.append(["cell", "filed figure", "why it is kept"])
    for cell, why in kept.items():
        sheet, _, ref = cell.rpartition("!")
        ks.append([cell, wb[sheet][ref].value, why])
    return to_bytes(wb)


def _check_xlsx(data: bytes) -> None:
    if not data.startswith(b"PK"):
        raise AppError("validation_failed", "not an XLSX workbook")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            inflated = sum(i.file_size for i in z.infolist())
    except zipfile.BadZipFile as e:
        raise AppError("validation_failed", "not an XLSX workbook (not a valid zip)") from e
    if "xl/workbook.xml" not in names:
        raise AppError("validation_failed", "not an XLSX workbook (no xl/workbook.xml)")
    if any(n.startswith("xl/vbaProject") for n in names):
        raise AppError("validation_failed", "a workbook with macros is not accepted; save it as .xlsx")
    if inflated > MAX_UNCOMPRESSED:
        raise AppError("source_too_large", "the workbook inflates past the limit")


def _compare_inputs(package: str, wb: Any) -> dict[str, Any]:
    """How the uploaded inputs differ from the filing's: input cells blank, changed, as filed;
    fill-map cells already entered (kept and checked); formula cells with no saved value."""
    filed, _ = _inputs_of_filing(package)
    fmap = _package(package)["map"]
    blank = changed = same = 0
    blank_cells: list[str] = []
    for key, v in filed.items():
        sheet, _, ref = key.rpartition("!")
        u = wb[sheet][ref].value if sheet in wb.sheetnames else None
        if u is None or (isinstance(u, str) and not u.strip()):
            blank += 1
            if len(blank_cells) < 50:
                blank_cells.append(key)
        elif isinstance(u, int | float) and not isinstance(u, bool) and abs(float(u) - float(v)) <= 1e-9:
            same += 1
        else:
            changed += 1
    entered = sum(
        1
        for key in fmap
        if (s := key.rpartition("!")[0]) in wb.sheetnames and wb[s][key.rpartition("!")[2]].value is not None
    )
    return {
        "input_cells": len(filed),
        "inputs_blank": blank,
        "inputs_changed": changed,
        "inputs_as_filed": same,
        "blank_examples": blank_cells,
        "fill_cells_entered": entered,
    }


def _formulas_without_values(data: bytes) -> int:
    """Formula cells saved without a value (a workbook written by a program that does not compute):
    the fill sees them as blank."""
    import openpyxl

    f = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
    v = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    n = 0
    for wsf in f.worksheets:
        wsv = v[wsf.title]
        for rf, rv in zip(wsf.iter_rows(), wsv.iter_rows(), strict=False):
            for cf, cv in zip(rf, rv, strict=False):
                if isinstance(getattr(cf, "value", None), str) and cf.value.startswith("=") and cv.value is None:
                    n += 1
    f.close()
    v.close()
    return n


def store_inputs(
    session: Any, storage: ObjectStore, case: ArrCase, utility: Utility, *, filename: str, data: bytes, actor: str
) -> PetitionWorkbook:
    """Validate and store an uploaded inputs workbook."""
    import openpyxl

    package = _package_for(utility)
    if not data:
        raise AppError("validation_failed", "the file is empty")
    _check_xlsx(data)
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    except Exception as e:  # noqa: BLE001 - any parse failure is the upload's
        raise AppError("validation_failed", f"the workbook could not be read: {type(e).__name__}") from e
    missing = sorted(_required_sheets(package) - set(wb.sheetnames))
    if missing:
        raise AppError(
            "validation_failed",
            f"the workbook is not laid out as {_package(package)['book'].name}: "
            f"{len(missing)} sheet(s) the fill writes are missing ({', '.join(missing[:8])}"
            f"{'…' if len(missing) > 8 else ''})",
        )
    summary = {"inputs": _compare_inputs(package, wb), "formulas_without_values": _formulas_without_values(data)}
    row = PetitionWorkbook(
        id=uuid.uuid4(),
        case_id=case.id,
        role="inputs",
        package=package,
        filename=(Path(filename or "inputs.xlsx").name or "inputs.xlsx")[:300],
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
        status="stored",
        summary=summary,
        created_by=actor,
    )
    row.object_key = f"petition/{utility.code}/{case.id}/{row.id}/inputs.xlsx"
    storage.put(ObjectStore.ARTEFACTS, row.object_key, data, XLSX)
    session.add(row)
    session.flush()
    return row


def workbooks(session: Any, case: ArrCase) -> list[PetitionWorkbook]:
    q = select(PetitionWorkbook).where(PetitionWorkbook.case_id == case.id).order_by(PetitionWorkbook.created_at)
    return list(session.execute(q).scalars())


def workbook(session: Any, case: ArrCase, workbook_id: uuid.UUID) -> PetitionWorkbook:
    w = session.get(PetitionWorkbook, workbook_id)
    if w is None or w.case_id != case.id:
        raise AppError("not_found", "workbook not found")
    return w


def request_fill(session: Any, case: ArrCase, inputs: PetitionWorkbook, *, actor: str) -> PetitionWorkbook:
    """Queue a fill of an uploaded inputs workbook; returns the (queued) filled workbook row."""
    if inputs.role != "inputs":
        raise AppError("validation_failed", "only an inputs workbook can be filled")
    stem = Path(inputs.filename).stem
    row = PetitionWorkbook(
        id=uuid.uuid4(),
        case_id=case.id,
        role="filled",
        package=inputs.package,
        filename=f"{stem}-filled.xlsx"[:300],
        inputs_id=inputs.id,
        status="queued",
        created_by=actor,
    )
    session.add(row)
    session.flush()
    job, _ = enqueue(
        session,
        job_type="petition_fill",
        payload={"workbook_id": str(row.id)},
        idempotency_key=f"petition_fill:{row.id}",
        max_attempts=1,
        created_by=actor,
    )
    row.job_id = job.id
    return row


def _narrative_binding(package: str) -> dict[str, Any] | None:
    path = _package(package)["folder"] / "narrative" / "summary-tables.json"
    return json.loads(path.read_text()) if path.exists() else None


def fill_narrative(package: str, wb: Any) -> tuple[bytes, dict[str, Any]] | None:
    """The filing's narrative documents with their bound summary tables filled from ``wb``
    (``narrative_fill``), as one ZIP with the report; None when the layout binds no narrative."""
    from .narrative_fill import fill_narrative as fill_tables

    binding = _narrative_binding(package)
    if binding is None:
        return None
    folder = _package(package)["folder"]
    docs = {t["document"]: (folder / t["document"]).read_bytes() for t in binding["tables"]}
    out, rep = fill_tables(binding, wb, docs)
    report = rep.as_dict()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in out.items():
            z.writestr(name, data)
        z.writestr("narrative-tables-report.json", json.dumps(report, ensure_ascii=False, indent=1))
    return buf.getvalue(), report


def fill_workbook(package: str, data: bytes) -> tuple[bytes, dict[str, Any], bytes | None]:
    """Fill an inputs workbook laid out as ``package``: the filled bytes, the full report (with
    the narrative tables' report under ``narrative``) and the filled narrative documents (a ZIP,
    or None when the layout binds no narrative)."""
    import openpyxl

    from . import petition_fill as pf
    from .rules import load_rules

    p = _package(package)
    rules = load_rules(p["manifest"]["commission"])
    bindings, _ = pf.fill_bindings(p["folder"])
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    rep = pf.fill(wb, p["layout"], bindings, rules, package, targets=set(p["map"]))
    narrative = fill_narrative(package, wb)
    pf.mark(wb, rep)
    for ws in wb.worksheets:
        ws.oddHeader.center.text = DRAFT_HEADER
    report = rep.as_dict()
    if narrative is not None:
        report["narrative"] = narrative[1]
    return pf.to_bytes(wb), report, narrative[0] if narrative else None


def run_fill(session_scope: Any, storage: ObjectStore, workbook_id: uuid.UUID) -> dict[str, Any]:
    """The ``petition_fill`` job's work: read the inputs, fill, store the filled workbook and the
    report, record the summary.  A failure is recorded on the row."""
    with session_scope() as s:
        row = s.get(PetitionWorkbook, workbook_id)
        if row is None:
            raise AppError("not_found", "workbook no longer exists")
        if row.status == "filled":
            return {"status": "already filled"}
        inputs = s.get(PetitionWorkbook, row.inputs_id)
        case = s.get(ArrCase, row.case_id)
        utility = s.get(Utility, case.utility_id)
        package, key, prefix = row.package, inputs.object_key, f"petition/{utility.code}/{case.id}/{row.id}"
        row.status, row.error = "running", None
    try:
        data = storage.get(ObjectStore.ARTEFACTS, key)
        filled, report, narrative = fill_workbook(package, data)
    except Exception as exc:  # noqa: BLE001 - every failure is recorded on the row
        with session_scope() as s:
            row = s.get(PetitionWorkbook, workbook_id)
            row.status, row.error = "failed", f"{type(exc).__name__}: {exc}"[:2000]
        raise
    blob = json.dumps(report, ensure_ascii=False, indent=1).encode()
    storage.put(ObjectStore.ARTEFACTS, f"{prefix}/filled.xlsx", filled, XLSX)
    storage.put(ObjectStore.ARTEFACTS, f"{prefix}/report.json", blob, "application/json")
    if narrative is not None:
        storage.put(ObjectStore.ARTEFACTS, f"{prefix}/narrative.zip", narrative, "application/zip")
    with session_scope() as s:
        row = s.get(PetitionWorkbook, workbook_id)
        row.object_key, row.report_key = f"{prefix}/filled.xlsx", f"{prefix}/report.json"
        row.sha256, row.size_bytes = hashlib.sha256(filled).hexdigest(), len(filled)
        row.summary = {**report["summary"], "status": report["status"]}
        if "narrative" in report:
            row.summary["narrative"] = report["narrative"]["summary"]
        row.status = "filled"
        return {"status": "filled", **{k: v for k, v in report["summary"].items() if k != "by_sheet"}}


def narrative_zip(storage: ObjectStore, row: PetitionWorkbook) -> bytes:
    """The filled narrative documents of a filled workbook (a ZIP)."""
    if row.role != "filled" or not row.object_key or not (row.summary or {}).get("narrative"):
        raise AppError("not_found", "no narrative tables: the workbook has not been filled, or its layout binds none")
    return storage.get(ObjectStore.ARTEFACTS, row.object_key.rsplit("/", 1)[0] + "/narrative.zip")


def report(storage: ObjectStore, row: PetitionWorkbook) -> dict[str, Any]:
    if row.role != "filled" or not row.report_key:
        raise AppError("not_found", "no report: the workbook has not been filled")
    return json.loads(storage.get(ObjectStore.ARTEFACTS, row.report_key))
