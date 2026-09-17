# ADR-0016 The model's feedback loop over rule-read candidates; Haystack for retrieval

Status: accepted (2026-09-17)

## Decision

- **A third pass per category, after the deterministic channels.**  For every schedule
  category (and every network family) the model is shown the candidates the rules read and
  the category's own passages, and returns per candidate a verdict (`supported`,
  `contradicted`, `uncertain`), a confidence in [0, 1], the consumer sub-category the value
  applies to in the order's own words, a one-sentence meaning, and a verbatim quote; plus
  the sub-categories it can see in the text.  Stored on the candidate as `assessment`
  (schema 2, assessment prompt 1) and shown in the review workspace as "Model check".
- **Grounding is mechanical.**  Every quote must be a verbatim span of the category's pages
  (whitespace-insensitive).  An item whose quote is not found is stored with
  `grounded=False`, tagged `assessment_ungrounded`, and its sub-category is not applied.
  The model can therefore add doubt and meaning but cannot add support it did not find.
- **Doubt only raises scrutiny.**  Confidence below 0.6 tags `model_low_confidence` and
  routes to individual review (a high rule confidence becomes medium); a `contradicted`
  verdict tags `model_contradicted`, routes to individual review and sets confidence low.
  No assessment ever changes a value, a unit or a state; the reviewer decides.
- **Sub-categories.**  A grounded sub-category fills an empty `applicability.rate_block`
  (the lettered consumer block).  The rules already read the block above a table from the
  page text; the model's reading covers the cases the rules miss, and is visible as such.
- **Haystack is adopted here, for retrieval.**  The category's pages become paragraph
  passages in an in-memory document store; a BM25 retriever picks the top passages per
  candidate (query: category, component, block, row and column labels, the printed text)
  and those passages, not the whole chapter, go into the prompt.  Haystack's document and
  retriever abstractions are the ones Milestone 7 builds its hybrid retrieval on, so the
  dependency is taken now; the model call itself goes through the project's provider adapter
  so cost, tokens, prompt versions and fixture labelling stay in one place.  Haystack's
  own generators are not used.
- **Fixture mode** runs the same loop with a template: confidence from what the rules
  already know, the sub-category from the rate block or row label, the meaning as a
  sentence, the quote the row label as printed.  Every artefact and candidate says which.

## Consequences

- Each order costs one extra model call per category and family (bounded by the order
  budget); the run record lists them as channel `assessment`.
- Reviewers see three signals per value: the readers' agreement, the validators' findings,
  and the model's verdict with confidence, each labelled by origin.
- The category summary (ADR-0015 addendum in BUILD_STATE) and the assessment are the two
  generated texts in the system; both are grounding-checked, neither is published.

## Addendum (2026-09-17): which channel is which

The first real run made the division of labour explicit.  The **rules** are the structure
channel for every backend: they read every cell and clause of the approved regions and cite
them; they cannot skip a row, and they cost nothing.  The **model** is used three times, all
on the provider adapter: (1) the image channel, reading the page images a few pages per call
as the independent second reading that the comparison and routing rely on; (2) the
assessment loop of this ADR, where **Haystack** (an in-memory document store and BM25
retriever over the region's own page text) selects the passages the model sees for each
category so its verdict, confidence, sub-category and quote are grounded in that text;
(3) the category summaries, grounded the same way.  The model never supplies the value the
reviewer approves: it agrees or disagrees with the rules' reading, scores it, names the
sub-category and explains it.
