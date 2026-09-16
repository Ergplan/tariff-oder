"""Multi-reader table grids and agreement scoring (Section 6.4).

Two independent readers reconstruct a grid from each table on a page; the grids are paired
by overlap and compared on structure (row/column counts, header detection) and on cell text
after whitespace normalisation.  Agreement is a *routing signal*, never proof of correctness:

* ``high_agreement`` — proceed with the primary grid, keep the secondary for evidence display.
* ``minority_cell_disagreement`` — same structure, a few cells differ: extract from the
  primary but every affected candidate carries ``risk: reader_disagreement``.
* ``structure_disagreement`` — different row/column counts or header rows, or most cells
  differ: the table goes to a reviewer with both grids; nothing is extracted automatically.
* ``primary_missing`` / ``secondary_missing`` — only one reader saw a table.  An all-empty
  grid from one reader (pdfplumber on a vector-drawn page) is failure mode P1 — a parser
  silently returning an empty table — and is recorded as ``empty_grid``, never extracted.

Docling is the specification's intended primary reader; it pulls a large ML stack that could
not be verified in the build environment, so PyMuPDF is primary and pdfplumber secondary
until Docling is measured on real pages (ADR-0009).  Both are pinned and recorded on every
grid.  Bump ``READERS_VERSION`` when pairing or scoring rules change.
"""

from __future__ import annotations

import io
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import pymupdf

READERS_VERSION = "2"
PYMUPDF_VERSION = str(getattr(pymupdf, "__version__", None) or pymupdf.VersionBind)

Strategy = Literal["lines", "lines_strict", "text", "model"]
AgreementClass = Literal[
    "high_agreement",
    "minority_cell_disagreement",
    "structure_disagreement",
    "primary_missing",
    "secondary_missing",
]

THRESHOLDS = {
    "high_agreement_min_cell_equality": 0.98,
    "minority_max_cell_inequality": 0.20,  # above this, treat as structural
    "pair_min_overlap": 0.50,  # IoU of bounding boxes to pair two grids
}

_WS = re.compile(r"\s+")


def normalise_cell(value: Any) -> str:
    """Whitespace-collapsed, stripped text.  Nothing else: no case folding, no number parsing —
    those are normalisation rules with ids of their own (Section 6.7)."""
    if value is None:
        return ""
    return _WS.sub(" ", str(value)).strip()


@dataclass
class TableGrid:
    reader: str
    reader_version: str
    page_index: int
    ordinal: int
    strategy: str
    bbox: tuple[float, float, float, float]
    rows: list[list[str]]
    header_rows: int = 0

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def col_count(self) -> int:
        return max((len(r) for r in self.rows), default=0)

    @property
    def is_empty(self) -> bool:
        return not any(cell for row in self.rows for cell in row)

    def normalised(self) -> TableGrid:
        """Cells whitespace-normalised; rows and columns that are entirely empty dropped (the
        whitespace strategy emits spacer rows).  Header count is clamped to what survives."""
        rows = [[normalise_cell(c) for c in r] for r in self.rows]
        width = max((len(r) for r in rows), default=0)
        rows = [r + [""] * (width - len(r)) for r in rows]
        keep_cols = [c for c in range(width) if any(r[c] for r in rows)]
        rows = [[r[c] for c in keep_cols] for r in rows if any(r)]
        return TableGrid(
            reader=self.reader,
            reader_version=self.reader_version,
            page_index=self.page_index,
            ordinal=self.ordinal,
            strategy=self.strategy,
            bbox=self.bbox,
            rows=rows,
            header_rows=min(self.header_rows, len(rows)),
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.update(row_count=self.row_count, col_count=self.col_count, is_empty=self.is_empty)
        return d


# ------------------------------------------------------------------ readers


def read_tables_pymupdf(page: pymupdf.Page, page_index: int, strategy: Strategy = "lines") -> list[TableGrid]:
    finder = page.find_tables(strategy=strategy)
    grids: list[TableGrid] = []
    for i, t in enumerate(finder.tables):
        rows = [[normalise_cell(c) for c in row] for row in t.extract()]
        header_rows = 1 if (t.header is not None and not getattr(t.header, "external", False) and rows) else 0
        grids.append(
            TableGrid(
                reader="pymupdf",
                reader_version=PYMUPDF_VERSION,
                page_index=page_index,
                ordinal=i,
                strategy=strategy,
                bbox=tuple(float(v) for v in t.bbox),
                rows=rows,
                header_rows=header_rows,
            )
        )
    return grids


def _no_borderless_fill(o: dict[str, Any]) -> bool:
    """pdfplumber's analogue of PyMuPDF's `lines_strict`: drop filled shapes with no stroke —
    a shaded heading cell is drawn as such a shape, inset from the cell border, and its
    edges would otherwise be read as extra column rulings."""
    return not (o.get("object_type") in ("rect", "curve") and o.get("fill") and not o.get("stroke"))


def read_tables_pdfplumber(pdf_bytes: bytes, page_index: int, strategy: Strategy = "lines") -> list[TableGrid]:
    import pdfplumber

    settings = (
        {} if strategy in ("lines", "lines_strict") else {"vertical_strategy": "text", "horizontal_strategy": "text"}
    )
    grids: list[TableGrid] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[page_index - 1]
        if strategy == "lines_strict":
            page = page.filter(_no_borderless_fill)
        for i, t in enumerate(page.find_tables(table_settings=settings)):
            rows = [[normalise_cell(c) for c in row] for row in t.extract()]
            grids.append(
                TableGrid(
                    reader="pdfplumber",
                    reader_version=pdfplumber.__version__,
                    page_index=page_index,
                    ordinal=i,
                    strategy=strategy,
                    bbox=tuple(float(v) for v in t.bbox),
                    rows=rows,
                    header_rows=1 if rows else 0,  # pdfplumber has no header detection; first row assumed
                )
            )
    return grids


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if inter <= 0:
        return 0.0
    area = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / area if area > 0 else 0.0


def prefer_strict(loose: list[TableGrid], strict: list[TableGrid]) -> list[TableGrid]:
    """Per table, the ruled-lines reading that ignores borderless fills (`lines_strict`) when
    one covers the same area, else the plain ruled-lines reading.  Word-exported tariff
    tables shade their heading row with a filled rectangle inset from the borders; read
    with fills as rulings, a three-column table arrives as nine (NPCL page 384: heading in
    one sub-column, number in the next, the energy cell then bound to "Fixed Charge").  A
    table whose borders *are* filled shapes has no strict twin and keeps the plain reading,
    so nothing is lost.  Ordinals follow the plain reading's order."""
    out: list[TableGrid] = []
    for i, g in enumerate(loose):
        twin = max(strict, key=lambda s: _iou(g.bbox, s.bbox), default=None)
        if twin is not None and _iou(g.bbox, twin.bbox) >= 0.5 and not twin.is_empty:
            chosen = twin
        else:
            chosen = g
        out.append(
            TableGrid(
                reader=chosen.reader,
                reader_version=chosen.reader_version,
                page_index=chosen.page_index,
                ordinal=i,
                strategy=chosen.strategy,
                bbox=chosen.bbox,
                rows=chosen.rows,
                header_rows=chosen.header_rows,
            )
        )
    return out


# ------------------------------------------------------------------ agreement


@dataclass
class GridAgreement:
    page_index: int
    primary_ordinal: int | None
    secondary_ordinal: int | None
    classification: AgreementClass
    score: float
    structure_match: bool
    header_match: bool
    cell_equality: float
    disagreeing_cells: list[dict[str, Any]] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ix0, iy0, ix1, iy1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    if inter == 0:
        return 0.0
    area = lambda r: max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])  # noqa: E731
    union = area(a) + area(b) - inter
    return inter / union if union else 0.0


def compare_grids(primary: TableGrid, secondary: TableGrid, thresholds: dict[str, Any] | None = None) -> GridAgreement:
    t = {**THRESHOLDS, **(thresholds or {})}
    p, s = primary.normalised(), secondary.normalised()
    structure = (p.row_count, p.col_count) == (s.row_count, s.col_count)
    header = p.header_rows == s.header_rows
    disagreeing: list[dict[str, Any]] = []
    if structure and p.row_count:
        total = p.row_count * p.col_count
        for r in range(p.row_count):
            for c in range(p.col_count):
                if p.rows[r][c] != s.rows[r][c]:
                    disagreeing.append({"row": r, "col": c, "primary": p.rows[r][c], "secondary": s.rows[r][c]})
        equality = 1.0 - len(disagreeing) / total if total else 1.0
    else:
        equality = 0.0

    if not structure:
        cls: AgreementClass = "structure_disagreement"
        note = f"primary {p.row_count}x{p.col_count} vs secondary {s.row_count}x{s.col_count}"
        risks = ["reader_disagreement", "structure_disagreement"]
    elif equality >= t["high_agreement_min_cell_equality"] and header:
        cls, note, risks = "high_agreement", "", []
    elif (1.0 - equality) <= t["minority_max_cell_inequality"]:
        cls = "minority_cell_disagreement"
        note = f"{len(disagreeing)} cells differ" + ("" if header else "; header row detection differs")
        risks = ["reader_disagreement"]
    else:
        cls = "structure_disagreement"
        note = f"{len(disagreeing)} of {p.row_count * p.col_count} cells differ"
        risks = ["reader_disagreement", "structure_disagreement"]
    score = round((0.5 if structure else 0.0) + (0.1 if header else 0.0) + 0.4 * equality, 4)
    return GridAgreement(
        page_index=primary.page_index,
        primary_ordinal=primary.ordinal,
        secondary_ordinal=secondary.ordinal,
        classification=cls,
        score=score,
        structure_match=structure,
        header_match=header,
        cell_equality=round(equality, 4),
        disagreeing_cells=disagreeing[:50],
        risk_tags=risks,
        note=note,
    )


def score_agreement(
    primary: list[TableGrid], secondary: list[TableGrid], thresholds: dict[str, Any] | None = None
) -> list[GridAgreement]:
    """Pair grids by bounding-box overlap and compare each pair; report unpaired grids from
    either side.  An unpaired grid that is entirely empty is the silent-empty-table failure."""
    t = {**THRESHOLDS, **(thresholds or {})}
    results: list[GridAgreement] = []
    used: set[int] = set()
    for pg in primary:
        best, best_iou = None, 0.0
        for sg in secondary:
            if sg.ordinal in used:
                continue
            iou = _iou(pg.bbox, sg.bbox)
            if iou > best_iou:
                best, best_iou = sg, iou
        if best is not None and best_iou >= t["pair_min_overlap"]:
            used.add(best.ordinal)
            results.append(compare_grids(pg, best, thresholds))
        else:
            results.append(
                GridAgreement(
                    page_index=pg.page_index,
                    primary_ordinal=pg.ordinal,
                    secondary_ordinal=None,
                    classification="secondary_missing",
                    score=0.0,
                    structure_match=False,
                    header_match=False,
                    cell_equality=0.0,
                    risk_tags=["reader_disagreement", "secondary_missing"],
                    note="only the primary reader found this table",
                )
            )
    for sg in secondary:
        if sg.ordinal in used:
            continue
        empty = sg.normalised().is_empty
        results.append(
            GridAgreement(
                page_index=sg.page_index,
                primary_ordinal=None,
                secondary_ordinal=sg.ordinal,
                classification="primary_missing",
                score=0.0,
                structure_match=False,
                header_match=False,
                cell_equality=0.0,
                risk_tags=["reader_disagreement", "primary_missing"] + (["empty_grid"] if empty else []),
                note=(
                    "secondary reader returned a grid with no text in any cell (silent empty table)"
                    if empty
                    else "only the secondary reader found this table"
                ),
            )
        )
    return results


# ------------------------------------------------------------------ Docling (optional third reader)

DOCLING_MODEL_REPOS = ("docling-project/docling-layout-heron", "docling-project/docling-models")


def docling_available() -> tuple[bool, str]:
    """Whether the optional Docling reader can run here.  Docling itself installs from PyPI
    (about 6 GB with torch); its layout and table-structure models are fetched from
    huggingface.co on first use, which some build environments block.  The answer says
    which of the two is missing so the operator knows what to fix."""
    try:
        import docling  # noqa: F401
    except ImportError:
        return False, "docling is not installed (uv sync --extra docling)"
    try:
        from docling.utils.model_downloader import download_models  # noqa: F401
    except ImportError:
        pass
    return True, "installed"


def _docling_converter(artifacts_path: str | None = None):
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    opts = PdfPipelineOptions(do_ocr=False, do_table_structure=True, artifacts_path=artifacts_path)
    opts.table_structure_options.do_cell_matching = True
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})


def grids_from_docling_tables(
    tables: list[Any], reader_version: str, page_heights: dict[int, float] | None = None
) -> list[TableGrid]:
    """Convert Docling `TableItem`s (`data.table_cells` with row/col offsets and spans, `prov`
    with page number and bbox) into the pipeline's `TableGrid`s.  Spanned cells are repeated
    into every position they cover, which is how the other readers present merged cells.
    Pure function so it is testable without models."""
    grids: list[TableGrid] = []
    ordinals: dict[int, int] = {}
    for t in tables:
        prov = t.prov[0] if getattr(t, "prov", None) else None
        if prov is None:
            continue
        page = int(prov.page_no)
        data = t.data
        rows = [["" for _ in range(int(data.num_cols))] for _ in range(int(data.num_rows))]
        header_rows = 0
        for cell in data.table_cells:
            txt = normalise_cell(cell.text)
            for r in range(int(cell.start_row_offset_idx), int(cell.end_row_offset_idx)):
                for c in range(int(cell.start_col_offset_idx), int(cell.end_col_offset_idx)):
                    if 0 <= r < len(rows) and 0 <= c < len(rows[r]):
                        rows[r][c] = txt
            if getattr(cell, "column_header", False):
                header_rows = max(header_rows, int(cell.end_row_offset_idx))
        bb = prov.bbox
        # Docling boxes are bottom-left origin on the PDF page; the other readers use top-left
        height = (page_heights or {}).get(page)
        if height is not None and getattr(bb.coord_origin, "value", str(bb.coord_origin)).upper().endswith(
            "BOTTOMLEFT"
        ):
            bbox = (float(bb.l), float(height - bb.t), float(bb.r), float(height - bb.b))
        else:
            bbox = (float(bb.l), float(bb.t), float(bb.r), float(bb.b))
        ordinal = ordinals.get(page, 0)
        ordinals[page] = ordinal + 1
        grids.append(
            TableGrid(
                reader="docling",
                reader_version=reader_version,
                page_index=page,
                ordinal=ordinal,
                strategy="model",
                bbox=bbox,
                rows=rows,
                header_rows=header_rows if header_rows else (1 if rows else 0),
            )
        )
    return grids


def read_tables_docling(
    pdf_bytes: bytes, *, artifacts_path: str | None = None
) -> tuple[list[TableGrid], dict[str, Any]]:
    """Run Docling over a whole document (it lays out every page in one pass) and return
    the grids of every page plus run facts (version, seconds, pages).  Raises ImportError
    when Docling is absent; model-download failures surface as the underlying exception so
    the operator sees the blocked host."""
    import importlib.metadata as md
    import tempfile
    import time

    from docling.datamodel.base_models import InputFormat  # noqa: F401 - import check

    version = md.version("docling")
    t0 = time.time()
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()
        res = _docling_converter(artifacts_path).convert(tmp.name)
    doc = res.document
    heights = {}
    for no, page in (doc.pages or {}).items():
        size = getattr(page, "size", None)
        if size is not None:
            heights[int(no)] = float(size.height)
    grids = grids_from_docling_tables(list(doc.tables), version, heights)
    return grids, {
        "reader": "docling",
        "reader_version": version,
        "seconds": round(time.time() - t0, 1),
        "pages": len(heights),
    }
