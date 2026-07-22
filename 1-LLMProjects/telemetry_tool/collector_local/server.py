#!/usr/bin/env python3
"""Fully-local collector: stdlib HTTP server + SQLite. No infra needed.

Validates the secret key, parses a JSON batch, inserts rows. Dedupes on
event_id so retried batches don't create duplicates.

Run:
    TELEMETRY_SECRET=dev-local-secret-change-me python3 server.py
Then browse the data:
    sqlite3 telemetry.db 'select * from events;'
"""
import json
import os
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import config

DB_PATH = os.environ.get(
    "TELEMETRY_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "telemetry.db"),
)


def init_db() -> None:
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            event_id       TEXT PRIMARY KEY,   -- dedupe key
            schema_version INTEGER,
            event_type     TEXT,
            install_id     TEXT,               -- random opaque ID
            ts             REAL,               -- client timestamp
            received_ts    REAL,               -- server timestamp
            metrics        TEXT                -- JSON quantitative payload
        )
        """
    )
    con.commit()
    con.close()


def insert_events(events: list[dict]) -> int:
    con = sqlite3.connect(DB_PATH)
    inserted = 0
    now = __import__("time").time()
    for e in events:
        try:
            con.execute(
                "INSERT OR IGNORE INTO events "
                "(event_id, schema_version, event_type, install_id, ts, received_ts, metrics) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    e.get("event_id"),
                    e.get("schema_version"),
                    e.get("event_type"),
                    e.get("install_id"),
                    e.get("ts"),
                    now,
                    json.dumps(e.get("metrics", {})),
                ),
            )
            inserted += con.total_changes and 1 or 0
        except sqlite3.Error:
            continue
    con.commit()
    con.close()
    return inserted


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict) -> None:
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") != "/ingest":
            return self._send(404, {"error": "not found"})
        if self.headers.get("X-Telemetry-Key") != config.SECRET_KEY:
            return self._send(401, {"error": "bad key"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            events = body.get("events", [])
            if not isinstance(events, list):
                raise ValueError("events must be a list")
        except (ValueError, json.JSONDecodeError) as e:
            return self._send(400, {"error": str(e)})
        n = insert_events(events)
        self._send(200, {"accepted": len(events), "inserted": n})

    def log_message(self, *args):  # silence default logging
        pass


def main() -> int:
    init_db()
    port = int(os.environ.get("TELEMETRY_PORT", 8787))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"local collector on http://127.0.0.1:{port}/ingest  db={DB_PATH}", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())