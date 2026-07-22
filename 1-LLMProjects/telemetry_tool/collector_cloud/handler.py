"""Cloud collector variant: a serverless function + Postgres.

Same contract as the local server (POST /ingest, X-Telemetry-Key header,
{"events": [...]} body, dedupe on event_id) so the client and flusher need
NO changes to switch targets -- you only point TELEMETRY_COLLECTOR_URL at the
deployed function URL.

This is deliberately framework-light: `handle(method, path, headers, body)`
returns (status, json). The two thin wrappers below adapt it to AWS Lambda +
API Gateway or a GCP/Azure HTTP function. Fill in the placeholders marked TODO.

Dependencies for real use: psycopg[binary]  (pip install "psycopg[binary]")
"""
import json
import os
import time

# --- Configuration (set these as env vars / secrets in your platform) --------
# TODO: point at your managed Postgres. Never hardcode credentials; read from
#       the platform's secret manager.
DATABASE_URL = os.environ.get("DATABASE_URL")  # e.g. postgres://user:pw@host/db
SECRET_KEY = os.environ.get("TELEMETRY_SECRET")  # must match the client's key

# TODO (for end user): confirm data classification + retention policy for this table
#             before sending real traffic.

DDL = """
CREATE TABLE IF NOT EXISTS events (
    event_id       TEXT PRIMARY KEY,
    schema_version INTEGER,
    event_type     TEXT,
    install_id     TEXT,
    ts             DOUBLE PRECISION,
    received_ts    DOUBLE PRECISION,
    metrics        JSONB
);
"""

INSERT = """
INSERT INTO events
    (event_id, schema_version, event_type, install_id, ts, received_ts, metrics)
VALUES (%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (event_id) DO NOTHING;
"""


def _connect():
    import psycopg  # imported lazily so local dev doesn't need it installed
    return psycopg.connect(DATABASE_URL)


def _ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()


def _insert(conn, events: list[dict]) -> int:
    now = time.time()
    inserted = 0
    with conn.cursor() as cur:
        for e in events:
            cur.execute(
                INSERT,
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
            inserted += cur.rowcount
    conn.commit()
    return inserted


def handle(method: str, path: str, headers: dict, body: str):
    """Core, platform-agnostic handler. Returns (status_code, dict)."""
    if method != "POST" or path.rstrip("/") != "/ingest":
        return 404, {"error": "not found"}

    # Header lookup is case-insensitive across platforms.
    key = None
    for k, v in (headers or {}).items():
        if k.lower() == "x-telemetry-key":
            key = v
            break
    if not SECRET_KEY or key != SECRET_KEY:
        return 401, {"error": "bad key"}

    try:
        payload = json.loads(body or "{}")
        events = payload.get("events", [])
        if not isinstance(events, list):
            raise ValueError("events must be a list")
    except (ValueError, json.JSONDecodeError) as e:
        return 400, {"error": str(e)}

    conn = _connect()
    try:
        _ensure_schema(conn)  # in production, run once via migration instead
        n = _insert(conn, events)
    finally:
        conn.close()
    return 200, {"accepted": len(events), "inserted": n}


# --- AWS Lambda + API Gateway (HTTP API v2) wrapper --------------------------
def lambda_handler(event, context):
    status, obj = handle(
        method=event.get("requestContext", {}).get("http", {}).get("method", "POST"),
        path=event.get("rawPath", "/ingest"),
        headers=event.get("headers", {}),
        body=event.get("body", ""),
    )
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(obj),
    }


# --- GCP Cloud Functions / Azure Functions (Flask-like request) wrapper ------
def http_function(request):
    status, obj = handle(
        method=request.method,
        path=request.path,
        headers=dict(request.headers),
        body=request.get_data(as_text=True),
    )
    return (json.dumps(obj), status, {"Content-Type": "application/json"})