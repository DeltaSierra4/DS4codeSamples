#!/usr/bin/env python3
"""Client side, called by a plugin hook.

Job: append ONE quantitative JSON event to the local outbox and exit fast.
No network, no retry, no blocking. Sub-millisecond and offline-safe.

Usage from a hook (either form works):
    # pass metrics as a JSON object
    python3 emit.py --event build_finished --data '{"duration_ms": 812, "files": 5}'

    # or pipe a JSON object on stdin
    echo '{"duration_ms": 812}' | python3 emit.py --event build_finished
"""
import argparse
import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import config


def get_install_id() -> str:
    """Return a random opaque install ID, creating it once on first use.

    This is unlinkable to any person or machine identity. It only lets the
    collector group events from the same install and dedupe retries.
    """
    path = config.INSTALL_ID_PATH
    try:
        with open(path, "r") as f:
            val = f.read().strip()
            if val:
                return val
    except FileNotFoundError:
        pass
    val = uuid.uuid4().hex  # 128 bits of randomness, no host info
    # Write atomically-ish; best effort, never fatal to the hook.
    try:
        with open(path, "w") as f:
            f.write(val)
    except OSError:
        pass
    return val


def build_event(event_type: str, data: dict) -> dict:
    return {
        "event_id": uuid.uuid4().hex,          # dedupe key for retries
        "schema_version": config.SCHEMA_VERSION,
        "event_type": event_type,
        "install_id": get_install_id(),         # random opaque ID
        "ts": time.time(),                      # client unix timestamp
        "metrics": data,                        # the quantitative payload
    }


def append_to_outbox(event: dict) -> None:
    line = json.dumps(event, separators=(",", ":"), sort_keys=True)
    with open(config.OUTBOX_PATH, "a") as f:
        f.write(line + "\n")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--event", required=True, help="event_type, e.g. build_finished")
    p.add_argument("--data", help="JSON object of quantitative metrics")
    args = p.parse_args()

    raw = args.data if args.data is not None else sys.stdin.read()
    if not raw or not raw.strip():
        data = {}
    else:
        data = json.loads(raw)
    if not isinstance(data, dict):
        print("metrics payload must be a JSON object", file=sys.stderr)
        return 2

    append_to_outbox(build_event(args.event, data))
    return 0


if __name__ == "__main__":
    # Never let telemetry crash the user's action: swallow errors, exit 0.
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        print(f"telemetry emit skipped: {e}", file=sys.stderr)
        sys.exit(0)