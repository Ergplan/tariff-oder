#!/usr/bin/env bash
# Publish the Mac mini's ARR Network database to Neon (the public read copy behind the Vercel site).
#
# One transaction on Neon: every data table is emptied and refilled from a data-only dump of the
# local database, then committed — visitors see the old data until the commit, never a half-loaded
# one.  The schema is not touched: both sides must have applied the same migrations, which is
# checked first.  Reviews are people's decisions: facts' review fields travel with the data and
# are never set here.
#
#   source ~/.arrnet/env && bash deploy/macmini/publish.sh            # needs NEON_DATABASE_URL
set -euo pipefail
: "${DATABASE_URL:?source ~/.arrnet/env first}"
: "${NEON_DATABASE_URL:?add NEON_DATABASE_URL (the Neon connection string) to ~/.arrnet/env}"

local_v=$(psql "$DATABASE_URL" -Atc "SELECT string_agg(version, ',' ORDER BY version) FROM schema_migrations")
neon_v=$(psql "$NEON_DATABASE_URL" -Atc "SELECT string_agg(version, ',' ORDER BY version) FROM schema_migrations")
if [ "$local_v" != "$neon_v" ]; then
  echo "schema differs: local [$local_v] vs Neon [$neon_v]; apply migrations on both first" >&2
  exit 1
fi

tables=$(psql "$DATABASE_URL" -Atc "SELECT string_agg(quote_ident(tablename), ', ') FROM pg_tables
  WHERE schemaname = 'public' AND tablename <> 'schema_migrations'")
dump=$(mktemp -t arrnet-publish.XXXXXX.sql)
trap 'rm -f "$dump"' EXIT
{
  echo "SET statement_timeout = 0;"
  echo "TRUNCATE $tables RESTART IDENTITY CASCADE;"
  pg_dump "$DATABASE_URL" --data-only --no-owner --no-privileges --exclude-table=schema_migrations
} > "$dump"
echo "publishing $(du -h "$dump" | cut -f1) to Neon in one transaction ..."
psql "$NEON_DATABASE_URL" -v ON_ERROR_STOP=1 --single-transaction -q -f "$dump"
psql "$NEON_DATABASE_URL" -Atc "SELECT 'facts ' || count(*) FROM facts UNION ALL SELECT 'pages ' || count(*) FROM pages
  UNION ALL SELECT 'database ' || pg_size_pretty(pg_database_size(current_database()))"
