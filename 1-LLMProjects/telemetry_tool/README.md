# telemetry transport tool — anonymous telemetry prototype

Small bits of **quantitative JSON** are emitted by plugin hooks on many
machines, shipped to a collector we control, and land in a **database**.
Sources stay anonymous via a **random opaque install ID** (128-bit UUID,
unlinkable to any person or machine; used only to group events and dedupe).

## Flow

```
plugin hook --> client/emit.py --> outbox.jsonl  (append-only, local, offline-safe)
                                        |
             scheduled task --> client/flush.py  (batch + HTTPS POST + secret key)
                                        |
                                        v
                    collector  -->  database
        local:  collector_local/server.py  (SQLite,   zero infra)
        cloud:  collector_cloud/handler.py (Postgres, serverless)
```

The client and flusher are identical for both targets. To switch, point
`TELEMETRY_COLLECTOR_URL` at the deployed function URL.

## Design choices

- **Hooks never send.** A hook fires and exits; it can't hold a retry loop.
  `emit.py` only appends one line and returns — sub-ms, offline-safe, and it
  swallows its own errors so telemetry never breaks the user's action.
- **Outbox + retry** in `flush.py` (run on a schedule) is what makes delivery
  reliable on flaky/offline networks. It removes only events the collector
  confirmed, so failures are retried next run.
- **Dedupe on `event_id`** so retried batches don't double-count.
- **Ceilings** (`MAX_OUTBOX_BYTES`, `MAX_EVENT_AGE_DAYS`) stop a permanently
  offline machine from filling the disk.
- **`schema_version`** on every event so the shape can evolve.

## Event shape

```json
{
  "event_id": "b1c2...",        // random, dedupe key
  "schema_version": 1,
  "event_type": "build_finished",
  "install_id": "9f8e...",       // random opaque ID (anonymous)
  "ts": 1752710400.12,           // client unix time
  "metrics": { "duration_ms": 812, "files": 5 }   // the quantitative payload
}
```

## Run the local demo

```bash
# 1. start the collector (terminal A)
TELEMETRY_SECRET=dev-local-secret-change-me python3 collector_local/server.py

# 2. emit some events (terminal B) — this is what a hook would call
python3 client/emit.py --event build_finished --data '{"duration_ms": 812, "files": 5}'
python3 client/emit.py --event build_finished --data '{"duration_ms": 640, "files": 3}'

# 3. flush the outbox to the collector
TELEMETRY_SECRET=dev-local-secret-change-me python3 client/flush.py

# 4. inspect the database
sqlite3 collector_local/telemetry.db 'select event_type, install_id, metrics from events;'
```

`test_e2e.sh` runs all of that automatically.

## Security note

The `X-Telemetry-Key` header is a shared secret — fine to start, but on user
machines it is extractable, so treat it as "keeps casual noise out," not real
authentication. If event integrity ever matters, upgrade to short-lived tokens
or signed payloads (see doc §3).

## Deploying the cloud variant

1. Provision managed Postgres; set `DATABASE_URL` + `TELEMETRY_SECRET` as
   platform secrets (never hardcode).
2. Deploy `collector_cloud/handler.py` (`lambda_handler` for AWS,
   `http_function` for GCP/Azure). `pip install "psycopg[binary]"`.
3. **END USER TODO:** data-classification + retention sign-off before real traffic.
4. Point clients at the function URL via `TELEMETRY_COLLECTOR_URL`.

## Note on storage location

SQLite (the local collector's DB) and the outbox must live on a **real local
disk**, not a cloud-synced folder (OneDrive/Dropbox/network share) — those can
raise `disk I/O error`. `test_e2e.sh` uses a local temp dir for this reason. In
production the outbox belongs somewhere like the user's app-data/cache dir.

## The CLAUDE.md and FLOW.md

The CLAUDE.md and FLOW.md files used to process the workflow are shared in the `misc`
directory for your interest. Feel free to use it as reference.