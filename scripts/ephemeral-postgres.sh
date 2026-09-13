#!/usr/bin/env bash
# Start/stop a throwaway PostgreSQL 16 cluster with pgvector on port 5433 without Docker.
# Needs the postgresql-16 and postgresql-16-pgvector packages (Debian/Ubuntu) on PATH.
# Used by CI-less environments and by `make ephemeral-postgres`.
set -euo pipefail
ACTION=${1:-start}
PGBIN=${PGBIN:-/usr/lib/postgresql/16/bin}
DATA=${PGDATA_EPHEMERAL:-/var/lib/postgresql/tariff/data}
PORT=${PGPORT_EPHEMERAL:-5433}
RUNAS=${PGUSER_OS:-postgres}

run_as() { if [ "$(id -u)" = "0" ]; then su "$RUNAS" -c "$*"; else bash -c "$*"; fi; }

case "$ACTION" in
  start)
    if [ ! -f "$DATA/PG_VERSION" ]; then
      mkdir -p "$(dirname "$DATA")"
      [ "$(id -u)" = "0" ] && chown "$RUNAS" "$(dirname "$DATA")"
      run_as "$PGBIN/initdb -D $DATA -A trust -U postgres" >/dev/null
    fi
    run_as "$PGBIN/pg_ctl -D $DATA -o '-p $PORT -k /tmp' -l $(dirname "$DATA")/pg.log start" >/dev/null
    for i in $(seq 1 20); do
      if "$PGBIN/pg_isready" -h 127.0.0.1 -p "$PORT" >/dev/null 2>&1; then break; fi; sleep 0.5
    done
    for db in tariff_test tariff_dev; do
      psql -h 127.0.0.1 -p "$PORT" -U postgres -tc "select 1 from pg_database where datname='$db'" | grep -q 1 \
        || psql -h 127.0.0.1 -p "$PORT" -U postgres -c "create database $db" >/dev/null
    done
    echo "postgres ready: postgresql+psycopg://postgres@127.0.0.1:$PORT/tariff_test"
    ;;
  stop)
    run_as "$PGBIN/pg_ctl -D $DATA stop" ;;
  *) echo "usage: $0 start|stop"; exit 2 ;;
esac
