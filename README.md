# Reliable Tariff Order Intelligence

Reads Indian electricity retail distribution tariff orders (UPERC/NPCL, KERC/ESCOMs,
GERC/MGVCL first) into published, evidence-backed, human-reviewed tariff facts that analysts
can browse, compare across periods, and query.

**Status:** Milestone 1 (running foundation and provenance) implemented under the `local`
profile; Google Cloud `dev` deployment is prepared as Terraform but **not applied** (no
credentials in the build environment).  See [`docs/BUILD_STATE.md`](docs/BUILD_STATE.md) for
exactly what works, what was tested, and what is blocked.  No tariff number has been
extracted, reviewed, or published.

- Specification: [`docs/spec/master-build-prompt.md`](docs/spec/master-build-prompt.md)
- Working guide for agents and contributors: [`AGENTS.md`](AGENTS.md)
- Architecture: [`docs/architecture.md`](docs/architecture.md) · Deployment: [`docs/deployment.md`](docs/deployment.md)
- Reading-reliability ledger: [`docs/reading-reliability.md`](docs/reading-reliability.md)

## Quick start (local profile, no Docker)

```bash
make install
make ephemeral-postgres            # PostgreSQL 16 + pgvector on :5433
export DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5433/tariff_dev
export LOCAL_USER_ALLOWLIST="admin@example.com:administrator,reviewer@example.com:reviewer,analyst@example.com:analyst"
make migrate seed
make api          # http://127.0.0.1:8000  (OpenAPI at /docs)
make worker       # in a second shell
API_BASE_URL=http://127.0.0.1:8000 LOCAL_WEB_USER=admin@example.com make web   # http://localhost:3000
make test
```

With Docker: `make dev` starts PostgreSQL, migrations, API, worker and web from
`infra/local/docker-compose.yml`.
