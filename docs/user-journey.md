# User journeys — the Petition Studio

Two journeys, both starting at the **map of India** (`/client/atlas`).  Every page shows where
you are on the way (India → state → licensee → norms) and links back up.  Day or night mode is
the toggle at the top right; the choice is remembered on that browser.

## A. Drafting an ARR petition

| # | Where | What you see | What you do |
|---|---|---|---|
| 1 | **India** `/client/atlas` | A tile map: one tile per state or union territory, coloured by what is on record — reviewed ARR facts (solid accent), orders being read (outlined), documents located (blue), nothing yet (dashed). A list of states beside it with commissions, licensees, documents and facts. | Click a state. |
| 2 | **State** `/client/states/<code>` | The commission(s), every licensee as a card (documents located, orders read, reviewed facts and up to which year), a summary of the commission's tariff norms, and the five steps of drafting. | Click a discom, or **Start for <discom>**. |
| 3 | **Discom** `/client/licensees/<code>` | Its reviewed ARR history (twelve key lines × the last four years, each the strongest reviewed figure with its order and page), the norms the commission applied to it in its orders, its petitions, and its documents with the official link and how far each has been read. | Read the record; open **All <commission> norms**. |
| 4 | **Norms** `/client/norms/<commission>` | The regulations the commission's ARR mapping names (with control period) and those in the library; the conventions (return on equity or capital employed, the revenue gap before or after subsidy, the loss basis, inclusive totals) and any a reviewer has decided; how each ARR line is formed (carried forward, escalated, quantity × rate, entered by the petitioner …) and which inputs the petitioner supplies; the norms as the orders applied them (loss %, O&M, RoE, IoWC, depreciation, interest), each with order and page. A plan or mapping a reviewer has not confirmed is labelled **working estimate**. | Note the inputs you will need; go back to the discom and **Start a petition**. |
| 5 | **Setup** `/client/cases/new` | Four tiles: annual ARR, MYT control period, true-up, APR; the licensee and years; a live summary. | Create the petition. |
| 6 | **Data** (the petition page, step 1–2) | Data readiness: which base-year figures are reviewed, which are missing. Assumptions: the values the regulations leave to the petitioner (sales, loss trajectory, rates, escalation). | Enter each assumption with its source. |
| 7 | **Formulate** | Every ARR line projected by the plan's method; a line without its inputs is **blocked** with the reason, never filled in. | Unblock lines by supplying inputs. |
| 8 | **Freeze** | The assumption set of this version is locked; revising later keeps it on record. | Freeze. |
| 9 | **Draft** | A draft petition (DOCX) and its formats (XLSX), every number traced to its order and page or to an assumption, watermarked "Draft · not filed". | Download, edit and file it yourself. Nothing is filed by the software. |

## B. Checking old orders

| # | Where | What you do |
|---|---|---|
| 1 | **India** → **State** | As above. |
| 2 | **Discom** | Its **Documents** panel lists every tariff order, true-up, MYT order, petition and regulation by year, with the commission's own link and the reading level (missing, located, acquired, read, reviewed, published). The **Reviewed ARR history** panel shows approved, trued-up and petitioned figures by year. |
| 3 | **Order** `/sources/<id>` | The registered copy: its pages, its ARR reading (chapters, the values read, the identities checked), each value with its page. |
| 4 | **Full history** `/arr/<discom>` | Every line × year × voice × order, with the disallowance (petitioned less approved, same order) computed for display. |
| 5 | **Benchmarks** `/client/benchmarks` | The discom against its peers for a year and a voice. |

## What is a fact and what is not

A number becomes a **fact** only when a reviewer has approved it against its page and it is
published.  Everything else is labelled: a value being read, a proposal, a working-estimate
norm, a fixture (synthetic test data).  The application never invents a tariff value, a norm, a
page number or a citation; where one is missing the page says so.
