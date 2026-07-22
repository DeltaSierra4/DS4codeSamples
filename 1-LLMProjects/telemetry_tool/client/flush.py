#!/usr/bin/env python3
"""Flusher, run by a scheduled task (cron / launchd / Task Scheduler).

Reads the outbox, drops events that are too old, batches the rest, and POSTs
each batch to the collector with the secret key header. Only removes events
the collector confirmed it accepted, so a failed send is retried next run.

Run:
    python3 flush.py
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import config


def read_outbox() -> list[dict]:
    if not os.path.exists(config.OUTBOX_PATH):
        return []
    events = []
    with open(config.OUTBOX_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # skip corrupt line rather than block everything
    return events


def drop_stale(events: list[dict]) -> list[dict]:
    cutoff = time.time() - config.MAX_EVENT_AGE_DAYS * 86400
    return [e for e in events if e.get("ts", 0) >= cutoff]


def rewrite_outbox(events: list[dict]) -> None:
    tmp = config.OUTBOX_PATH + ".tmp"
    with open(tmp, "w") as f:
        for e in events:
            f.write(json.dumps(e, separators=(",", ":"), sort_keys=True) + "\n")
    os.replace(tmp, config.OUTBOX_PATH)


def post_batch(batch: list[dict]) -> bool:
    body = json.dumps({"events": batch}).encode("utf-8")
    req = urllib.request.Request(
        config.COLLECTOR_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Telemetry-Key": config.SECRET_KEY,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False


def main() -> int:
    events = read_outbox()
    if not events:
        return 0

    kept = drop_stale(events)
    remaining = list(kept)
    sent_any = False

    for i in range(0, len(kept), config.BATCH_SIZE):
        batch = kept[i:i + config.BATCH_SIZE]
        if post_batch(batch):
            # Remove the ones we just delivered.
            ids = {e["event_id"] for e in batch}
            remaining = [e for e in remaining if e["event_id"] not in ids]
            sent_any = True
        else:
            # Stop on first failure; leave the rest for the next run.
            break

    rewrite_outbox(remaining)
    print(f"flushed; {len(remaining)} event(s) still pending", file=sys.stderr)
    return 0 if sent_any or not kept else 1


if __name__ == "__main__":
    sys.exit(main())