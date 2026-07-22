"""Shared configuration for the telemetry prototype.

Nothing here is secret by itself; the real secret is supplied via the
TELEMETRY_SECRET env var at runtime. Values below are safe defaults for
the fully-local demo.
"""
import os

# Where the client writes events and the flusher reads them.
OUTBOX_PATH = os.environ.get(
    "TELEMETRY_OUTBOX",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outbox.jsonl"),
)

# File that stores this machine's random opaque install ID (created once).
INSTALL_ID_PATH = os.environ.get(
    "TELEMETRY_INSTALL_ID_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".install_id"),
)

# Collector endpoint the flusher POSTs to.
COLLECTOR_URL = os.environ.get("TELEMETRY_COLLECTOR_URL", "http://127.0.0.1:8787/ingest")

# Shared secret sent in the X-Telemetry-Key header. Override in real deploys.
SECRET_KEY = os.environ.get("TELEMETRY_SECRET", "dev-local-secret-change-me")

# Schema version stamped on every event. Bump when the event shape changes.
SCHEMA_VERSION = 1

# Safety ceilings so a permanently-offline machine can't fill the disk.
MAX_OUTBOX_BYTES = int(os.environ.get("TELEMETRY_MAX_OUTBOX_BYTES", 5 * 1024 * 1024))  # 5 MB
MAX_EVENT_AGE_DAYS = int(os.environ.get("TELEMETRY_MAX_EVENT_AGE_DAYS", 7))

# How many events the flusher sends per HTTP request.
BATCH_SIZE = int(os.environ.get("TELEMETRY_BATCH_SIZE", 100))