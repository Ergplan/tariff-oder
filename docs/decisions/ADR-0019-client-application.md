# ADR-0019 The client application: organisations, the regulatory library, ARR cases

Status: accepted (2026-11-01).  Builds on ADR-0017 and ADR-0018.

## Context

The operator asked (2026-11-01) for the product to become a **client application**: every
state's tariff orders, true-ups, MYT orders and MYT/ARR petitions for the past three years
available in one library, and a client able to **start an ARR process** for a licensee from
inside the application and carry it to a draft petition.

Two facts shape the answer:

1. The documents have to be **acquired** from the commissions' websites.  From the cloud
   build session most commission sites are unreachable (2026-11-01: UPERC, CERC and the
   Forum of Regulators answer; KERC, GERC, MERC, TNERC and DERC do not); the operator's VM
   has open egress.  Acquisition must therefore be a job that runs wherever the network
   allows, never a one-off script, and the library must say honestly what is missing.
2. A number is a **fact** only after it is read, reviewed by a person and published
   (AGENTS.md rule 1).  "Available" therefore has levels, and every screen shows them.

## Decision

### Two audiences, one application

| | Regulatory desk (internal) | Client (organisation) |
| --- | --- | --- |
| Who | platform roles analyst / reviewer / administrator | members of an organisation (owner / editor / viewer) |
| Owns | the shared corpus: sources, readings, reviews, published facts, the library | its ARR cases, assumption sets, formulations, filing drafts |
| Sees | everything in the corpus; client workspaces only as administrator (audited) | the published corpus (read-only) and its own workspace |

- `organisations` and `organisation_members` (email, role).  A client user is a platform
  `analyst` (read-only on the corpus) with one or more memberships.  Platform
  administrators create organisations and add owners; owners add members.
- **Org-owned objects** carry `organisation_id`: `arr_cases`, `arr_assumption_sets`,
  `arr_formulations` (drafts inherit through their formulation).  A null organisation is a
  desk object (as in Increment A: platform reviewers).  Access is decided in one place
  (`tariff_api.workspace`): viewer reads, editor writes, owner manages members; another
  organisation's object answers **404**, never 403, so ids leak nothing.

### The regulatory library

- `library_entries`: one expected or known document — commission, licensee (null for a
  commission-wide document such as a regulation), `document_kind` (`tariff_order`,
  `arr_true_up_order`, `myt_order`, `mid_term_review`, `arr_petition`, `myt_petition`,
  `regulation`, `regulation_amendment`), `fiscal_year` (or `""` for the current control
  period), the official URL, and a status: `expected` → `located` (URL known) →
  `acquired` (registered as a source) or `failed` (with the error).
- **Expected slots are expectations, not data**: `seed` creates them for every distribution
  and transmission licensee × year × kind so coverage gaps are visible from day one; they
  carry no URL and no number.
- **Acquisition** is the worker job `acquire_library_entry`: fetch the URL (PDF only, size
  capped), register it through the same path as an upload (hash, dedup, golden manifest,
  `order_type` from the kind, licensee from the entry), link the source.  A blocked
  network is a recorded failure, retried later from a host with egress.
- **Coverage** is computed, per state → commission → licensee → year → kind, from the
  entries and the linked sources' reading state: `missing`, `located`, `acquired`, `read`
  (tariff or ARR track past extraction), `reviewed` (decisions taken), `published`.

### ARR cases

An `arr_cases` row is a client's ARR process for one licensee: filing kind
(`annual_arr`: the next year's ARR as petitioned; `myt`: every year of a control period),
base year, target years, its assumption set, formulations and drafts, and a status
(`setup` → `assumptions` → `formulated` → `frozen` → `drafted` → `closed`).  **Readiness**
is computed for the case: the plan's base facts present or missing (and whether the order
that would print them is in the library, acquired, read or reviewed), the parameters the
plan needs per target year and which are supplied.  The case drives the Increment A engine;
it adds no arithmetic of its own.

## Consequences

- Migration `0016_client_application`.
- The web app gains a client shell (`/client`: dashboard, library, licensee, cases, case
  wizard) beside the desk pages; the desk gains the library administration page.
- True-up and APR filings (actuals against approvals) are a later case kind: they need
  audited accounts as an input source, which no case kind reads yet.
- Organisation isolation is tested at the API (another organisation's case, assumption
  set, formulation and draft are 404).

## Amendment (increment 32, 2026-11-01): discovery profiles

Finding the official URL of each order is per commission and changes when a site changes, so
it is data: `packages/discovery-profiles/<commission>.v<n>.json` lists the commission's
listing pages and how to page through them (`static`, or `aspnet_year_select` for WebForms
year filters), plus phrases that stand for several licensees ("State Discoms").  The engine
behaves like a browser (posts only what a browser posts, one request at a time) and only
**proposes**: a person ticks proposals before anything is recorded, and acquisition stays a
separate job.  A profile is `draft` until the operator has checked it against the site.

