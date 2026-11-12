#!/usr/bin/env bash
# The Mac mini as the ARR Network's primary database and agent engine (operator's choice,
# 2026-11-12): Postgres + pgvector here hold the master copy; the agents (Docling, embeddings,
# readers) run here and write through a local copy of the application's ingest API; Neon stays
# the public read copy the Vercel site uses, refreshed by publish.sh.
#
# Run from the repository root on the Mac mini:  bash deploy/macmini/setup.sh
# Idempotent.  Never writes a secret into the repository: the local ingest token goes to
# ~/.arrnet/env (mode 600).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PG=postgresql@17
DB=arrnet
PORT=5432
CONF="$HOME/.arrnet"
mkdir -p "$CONF"; chmod 700 "$CONF"

command -v brew >/dev/null || { echo "Homebrew is required: https://brew.sh"; exit 1; }
brew install "$PG" pgvector node@22 uv >/dev/null
brew services start "$PG" >/dev/null
export PATH="$(brew --prefix "$PG")/bin:$(brew --prefix node@22)/bin:$PATH"

for _ in $(seq 1 30); do pg_isready -q -p "$PORT" && break; sleep 1; done
createdb -p "$PORT" "$DB" 2>/dev/null || true
psql -p "$PORT" -d "$DB" -qc "CREATE EXTENSION IF NOT EXISTS vector" >/dev/null

# the local ingest token: generated once, kept outside the repository
if [ ! -f "$CONF/env" ]; then
  umask 077
  {
    echo "export DATABASE_URL=postgresql://$(whoami)@127.0.0.1:$PORT/$DB"
    echo "export INGEST_TOKEN=$(openssl rand -hex 32)"
    echo "export INGEST_URL=http://127.0.0.1:3100"
    echo "export ARRNET_STATE=$CONF/state"
    echo "export ARRNET_PDF_DIR=$CONF/pdf"
    echo "# export NEON_DATABASE_URL=...   # for publish.sh: the Neon connection string (Neon console)"
  } > "$CONF/env"
fi
# shellcheck disable=SC1091
source "$CONF/env"
mkdir -p "$ARRNET_STATE" "$ARRNET_PDF_DIR"

# the application, built against the local database (its ingest API is the agents' only door)
cd "$REPO/apps/arr-network"
npm ci --no-audit --no-fund
npm run build
printf 'DATABASE_URL=%s\nINGEST_TOKEN=%s\n' "$DATABASE_URL" "$INGEST_TOKEN" > .env.local
chmod 600 .env.local

# the agents
cd "$REPO/tools/arrnet"
uv venv --python 3.12 .venv >/dev/null
uv pip install --python .venv/bin/python -e ".[docling,embed]" >/dev/null

cat <<MSG
Set up.  Next:
  1. Start the application:   (cd apps/arr-network && npm run start)       # http://127.0.0.1:3100
  2. Apply the schema:        source ~/.arrnet/env && curl -s -X POST -H "Authorization: Bearer \$INGEST_TOKEN" \$INGEST_URL/api/ingest/migrate
  3. Run the agents:          source ~/.arrnet/env && tools/arrnet/.venv/bin/python -I -m arrnet.run all --download
  4. Publish to Neon:         add NEON_DATABASE_URL to ~/.arrnet/env, then bash deploy/macmini/publish.sh
MSG
