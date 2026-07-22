#!/usr/bin/env bash
# End-to-end test of the local loop. Uses a local-disk workdir because SQLite
# does not work reliably on cloud-synced folders (OneDrive/Dropbox/network).
set -euo pipefail
cd "$(dirname "$0")"

WORK="${TELEMETRY_TEST_DIR:-/tmp/timmyproject_test}"
rm -rf "$WORK" && mkdir -p "$WORK"

export TELEMETRY_SECRET=dev-local-secret-change-me
export TELEMETRY_OUTBOX="$WORK/outbox.jsonl"
export TELEMETRY_INSTALL_ID_FILE="$WORK/.install_id"
export TELEMETRY_DB="$WORK/telemetry.db"
export TELEMETRY_COLLECTOR_URL="http://127.0.0.1:8787/ingest"

python3 collector_local/server.py &
SRV=$!
trap "kill $SRV 2>/dev/null || true" EXIT
sleep 1

python3 client/emit.py --event build_finished --data '{"duration_ms": 812, "files": 5}'
python3 client/emit.py --event build_finished --data '{"duration_ms": 640, "files": 3}'
echo '{"duration_ms": 1200, "files": 9}' | python3 client/emit.py --event build_finished
echo "outbox before flush: $(wc -l < "$TELEMETRY_OUTBOX") event(s)"

python3 client/flush.py
python3 client/emit.py --event build_finished --data '{"duration_ms": 999, "files": 1}'
python3 client/flush.py
echo "outbox after flush: $(wc -l < "$TELEMETRY_OUTBOX" 2>/dev/null || echo 0) event(s)"

python3 - <<'PY'
import sqlite3, os
c=sqlite3.connect(os.environ["TELEMETRY_DB"])
print("rows in DB:", c.execute("select count(*) from events").fetchone()[0])
print("distinct install_ids (expect 1):",
      c.execute("select count(distinct install_id) from events").fetchone()[0])
for r in c.execute("select event_type, round(ts,2), metrics from events order by ts"):
    print("  ", r)
PY
echo "OK"