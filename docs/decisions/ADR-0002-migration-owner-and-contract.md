# ADR-0002 Migration owner and API contract source

Status: accepted (Milestone 0)

## Decision
`services/api` (SQLAlchemy 2 models + hand-written Alembic migrations) is the only schema
owner.  The API's OpenAPI document (`tariff-api openapi`) is the single contract; TypeScript
types are generated into `packages/contracts/src/api.d.ts` with openapi-typescript and CI
fails on drift (`packages/contracts/scripts/check-drift.mjs`).

## Alternatives rejected
Prisma/Drizzle in the web app (second schema definition); hand-written TS types (drift).
