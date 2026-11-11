# ARR database builder

This builds a database of the ARR figures of Indian DISCOMs, read from state commission tariff
orders. Every value keeps its order, its page and the line as printed. Nothing is reviewed.

## Pipeline

```
# 1. find the orders: the commission discovery profiles (packages/discovery-profiles) …
uv run tariff-api library-discover --registry --commission UPERC \
    --years FY2022-23 FY2023-24 FY2024-25 FY2025-26 FY2026-27 --out disc/UPERC.json
#    … for each profiled commission; data/extra-sites.json lists orders found on listing
#    pages of commissions without a profile (DERC, CSERC, MERC), and known-orders.json the
#    orders read in the build session, with their SHA-256.

# 2. download (keeps each file under its SHA-256; a non-PDF answer is recorded, not saved)
cd tools/arrdb
uv run --project ../.. python -m arrdb.scrape --discovery disc --extra data/extra-sites.json \
    --cache CACHE --out data/orders.json

# 3. read the ARR tables and build the SQLite database
uv run --project ../.. python -m arrdb.build --orders data/orders.json --cache CACHE --out arr.sqlite

# 4. measure against the figures people read by hand from the same orders, and record the
#    result in the database (the site shows it)
uv run --project ../.. python -m arrdb.check --db arr.sqlite --repo ../.. --out data/check.json --write
cp arr.sqlite ../../apps/arr-db/data/arr.sqlite
```

The PDFs are not committed. `data/orders.json` lists each order's URL and SHA-256, so the files
can be fetched again and checked.

## How a table is read (`arrdb/reader.py`)

1. Each page's text layer is split into rows (by baseline) and words (with positions).
2. A table is taken when its printed title names the revenue requirement. Tables are skipped
   when they cover only the wires or only the supply business, split the ARR across consumer
   categories, or belong to another company in a combined order (a generation company's,
   say). A table of contents is skipped too.
3. The rows printing the most values set the columns; every other value goes to the column it
   overlaps. A table that continues onto the next page is followed past that page's running
   header.
4. Each column gets a DISCOM, a year and a voice: claimed, approved, approved_earlier (an
   earlier order's approval quoted here) or actual. These come from the header, else the
   title, else the sentence above the table. Each value records which one was used. Headers
   naming a part of the figure (Agriculture, Wires, a power station, a unit) leave the column
   without a voice.
5. Labels wrapped over several lines are joined. A row label is mapped to a canonical head
   (`arrdb/heads.py`), and the printed label is kept beside it.
6. The unit comes from the title or the rows near it. If no unit is printed, it is taken only
   when three or more of the table's figures are printed in Rs crore in another table of the
   same order. Otherwise `value_crore` stays NULL.

`build.py` picks each order's bottom line per DISCOM, year and voice (`arr_headline`). It
prefers the net ARR row of the main summary table. It sets aside a bottom line more than five
times away from the same DISCOM's median, and records the reason.

## Accuracy

`arrdb.check` compares the database with every figure in `packages/order-reproductions` and
`packages/reference-filings` that comes from a table the reader read. These are figures people
read row by row, with page and quote. The latest run is in `data/check.json`. All other orders
are unmeasured.
