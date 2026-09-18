# exchange/ — orders shared with the engineering session

One folder per commission, one sub-folder per order, holding the JSON export the app
produces (`Download everything as JSON (zip)` on a source page, or
`make admin-dev ARGS=export,<source_id>` which also writes to the export bucket under
`COMMISSION/UTILITY/`).  Unzip the download here, commit and push; the engineering session
reads it from git, so nothing has to be pasted.

```
exchange/
  UPERC/
    NPCL_TariffOrder1-5f900540/
      source.json          state, versions, utility, reviewer, stage summaries
      localisation.json    the record and every region with its reviewer note
      pages/page-0384.json the page's tables as read and its structure cells
      candidates.json      every value with its review_status (proposals, never facts)
      decisions.json       the audit trail of reviewer decisions
      summaries.json       the model's category summaries (grounding-checked)
      findings.json        validator findings
      runs.json            provider calls with tokens and cost
```

Nothing in here is a published fact.  Do not edit the files by hand; re-export instead.
