# ADR-0009 Table readers and OCR engine for Milestone 2

Status: accepted (2026-09-13), provisional on Docling measurement

## Decision

- **Readers**: PyMuPDF `find_tables` is the primary reader and pdfplumber the secondary.  The
  specification names Docling as the intended primary; it pulls a large ML stack (torch and
  model downloads) that the build environment could not install or verify, and it must be
  measured on real pages before it can be trusted with that role.  The reader interface
  (`tariff_api.readers.TableGrid`, `score_agreement`) is what the rest of the pipeline sees,
  so Docling slots in as a third reader without changing consumers.  Both current readers are
  pinned and their versions recorded on every grid and artefact.
- **Strategy**: ruling-line detection first; the whitespace ("text") strategy only on pages
  triage already classed `table`/`mixed` and only when rulings find nothing.  Measured: the
  text strategy hallucinates a 63×19 "table" on an ordinary prose page, and its grid
  boundaries are loose (it sweeps every column-aligned line, banner included).  On an unruled
  KERC-style table both readers produce identical 9×4 grids, which is the signal that makes it
  safe to use.
- **Agreement classes** (Section 6.4): `high_agreement` (same structure, ≥98% cells equal),
  `minority_cell_disagreement` (same structure, ≤20% cells differ → `reader_disagreement`
  risk), `structure_disagreement` (route to reviewer, nothing extracted), `primary_missing` /
  `secondary_missing` (one reader only).  A grid with no text in any cell carries `empty_grid`:
  measured on the vector-drawn fixture page, pdfplumber returns a 20×6 grid of empty cells and
  PyMuPDF returns nothing — failure mode P1, "a parser silently returns an empty table".
- **OCR**: tesseract 5 as a subprocess with TSV output, so every word carries a confidence and
  a box.  Defaults `dpi=300`, `psm=4`, chosen by measurement against a rasterised page with a
  known text layer: psm 6 reads 15% of the words (it treats the page as one block and skips
  8 pt table cells); psm 4, 11 and 12 read 100% at 200 dpi already.  psm 4 keeps paragraph
  and line structure, which the heading inventory needs.  A page with zero OCR words is
  flagged `ocr_no_text` and stays unreadable — never a guessed table.  OCR text never replaces
  a text layer: where both exist, token-Jaccard agreement is stored, and < 0.5 flags
  `ocr_layer_disagreement`.
- **Grids from OCR word boxes are not attempted.**  An OCR'd page that triage classed as a
  table is flagged `grid_from_ocr_pending` and listed for review.  Building reliable grids from
  word boxes is its own piece of work and belongs with the Docling measurement.

## Consequences

- The KERC vector-drawn charge tables (E.2 hazard 1) will be OCR'd but not gridded until the
  next increment; they are visible as pending, not silently skipped.
- `tesseract-ocr` is a system dependency of the Python image and of CI.
- A stage re-run cancels the queued downstream stage jobs of that source; the re-run stage
  chains them again on completion.  Without this the parse job triage had chained ran first
  against the rolled-back state and failed (found by the re-run test).
- Where OCR and a text layer disagree, or where readers disagree structurally, the page reaches
  a reviewer with both representations.  No threshold in this ADR lowers verification.

## Limitation recorded

A single-glyph substitution in a text layer (an en dash rendered as a middle dot) is below the
text-quality detector's threshold: glyph coverage stays 1.0 and the dictionary hit rate is
unaffected.  Such pages are caught only where readers or OCR disagree with the layer.  Found
while building the fixture; recorded in the reliability ledger under D2.

## Addendum (2026-09-16): Docling installed as an optional third reader; measurement pending

- **Installed and adapted, not yet trusted.**  `tariff-api[docling]` (optional extra, never in
  the default image) brings Docling 2.128 with torch 2.14; about 6 GB.  `readers.read_tables_docling`
  runs the layout and TableFormer models over a whole document and converts every
  `TableItem` (cells with row/column offsets and spans, provenance page and box) into the
  pipeline's `TableGrid` with `strategy=model`, spans repeated into every covered position and
  boxes moved to the top-left origin the other readers use (`grids_from_docling_tables`, pure
  and unit-tested).  Nothing consumes these grids yet: Docling becomes a reader of record only
  after the measurement below is recorded here with numbers.
- **What blocked the measurement in the build environment.**  The package installed from
  PyPI (the CPU-only torch index at download.pytorch.org is refused by the egress policy, so
  the CUDA build was pulled and runs on CPU).  On first use Docling fetches its models from
  huggingface.co, which the environment cannot reach at all; the run failed before touching a
  page.  So the fixture measurement has not happened.  `tariff-api reader-measure --pdf <file>`
  exists for the machine that can: it prints per page how many grids each of the three readers
  finds, their shapes, and how Docling's grids agree with PyMuPDF's under `score_agreement`.
- **Decision rule for promotion.**  Docling replaces pdfplumber as the secondary reader (or
  PyMuPDF as the primary) only if, on the three real orders' schedule and network-charge pages,
  it finds every ruled table the current readers find, produces `high_agreement` with PyMuPDF on
  at least as many grids as pdfplumber does, and reads the unruled KERC-style charge tables
  that neither current reader grids.  Runtime per 570-page order and the image size are
  recorded alongside.  Until then the two current readers stay as they are.
