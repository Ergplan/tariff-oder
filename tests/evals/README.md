# Evaluation runner

Placeholder until Milestone 2.  The runner will execute golden-corpus acceptance checks
(Parts D.3/E.3/F.3) and synthetic fixtures on every parser, profile, prompt, validator or
normalization change and report per-stage metrics with denominators
(`docs/evaluation-plan.md`).  Real-source runs require the bytes referenced in
`tests/golden/manifest.json`, which are not committed.
