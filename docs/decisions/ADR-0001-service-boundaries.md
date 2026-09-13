# ADR-0001 Service boundaries

Status: accepted (Milestone 0, 2026-09-13)

## Decision
Three deployable units: `apps/web` (Next.js, presentation and identity forwarding only),
`services/api` (FastAPI: authoritative data, migrations, adapters, queue API, answer service
later), `services/worker` (job runner and reading-pipeline stages).  The worker imports the
API package for models, adapters and queue primitives; it never exposes HTTP.  Python jobs
never run inside a web request.

## Consequences
One image serves API, migrate job and worker (command selects the role).  The web app cannot
reach the database; every read goes through typed API routes, so "no tool can reach
candidates" (Section 8) is enforceable at one place.
