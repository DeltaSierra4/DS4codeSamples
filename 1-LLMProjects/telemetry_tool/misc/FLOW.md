# FLOW.md — Usage Telemetry Transport: Plan & Architecture

The plan and architecture for this one build. Read `CLAUDE.md` first for how to behave; this file is the route to follow. Do not improvise a different design mid-task — if reality forces a change, stop, update this file, and get it re-approved before continuing.

## Goal

Let a program running on many user machines send small bits of usage data back to a central place we control, and have that data land reliably even when a given machine is offline for a while. Nothing extra should have to be installed on the user's machine.

## Architecture

    app on device  --HTTPS-->  collector  -->  database / dashboard
         |
         └─ local outbox (retries when the network comes back)

Two independent decisions, already made:

**How the data leaves the machine — direct send + outbox with retry.**
The client posts data over HTTPS on a schedule. Before sending, it writes each record to a small local outbox (an on-disk queue); on success the record is removed, on failure it stays and is retried later with backoff. This is the piece that makes delivery reliable on flaky or frequently-offline networks. A fully separate background helper was considered and rejected as more than this needs.

**Where it lands — a token-protected serverless endpoint + database we own.**
A tiny cloud function receives the POST, checks the token, and writes to a managed database. Chosen over an existing monitoring platform (less control over the schema) and a low-code intake (weakest guarantees). Two concrete targets are in scope; pick one at implementation time and record the choice here:

| Target | Endpoint | Store | Notes |
|---|---|---|---|
| AWS Lambda + DynamoDB | Lambda Function URL | DynamoDB table | Most common owned-serverless setup; IAM + on-demand capacity |
| Cloudflare Workers + D1 | Worker route | D1 (SQLite) or KV | Cheap, global edge, minimal cold start |

The client must not care which one is live: it targets a single configured HTTPS URL and a token. Swapping collectors is a config change, not a code change.

## The decisive constraint

The one thing that decides whether any of this works: **the machine has to be able to reach the collector's URL over the network, through any corporate proxy or firewall.** If machines are usually online, every option is fine. If they are often offline or off-VPN, the outbox + retry is what keeps delivery reliable — so the outbox is not optional, and honoring the system/proxy settings when sending is a first-class requirement, not an afterthought.

## Data contract

Keep the payload small and stable; it is the contract between client and collector, so changes to it require approval (see `CLAUDE.md`).

- A record carries at least: an event name, a timestamp (UTC, ISO-8601), an anonymous install/machine id, the app version, and a small free-form properties object.
- The client POSTs a batch: `{ "records": [ ... ] }` as JSON.
- The collector responds 2xx only when the batch is durably stored; any other response (or no response) means the client keeps the records in the outbox and retries.
- Define the exact JSON schema in Phase 1 and freeze it before Phase 3.

## Security

- Every request carries a **secret token in a request header**; the collector rejects anything without the right token. This is the baseline and the default.
- The token is provisioned out of band and read from the environment / a gitignored config file — never hard-coded (see `CLAUDE.md`).
- Stronger options are available if security review asks for them: signed payloads (HMAC over the body) or mutual-TLS client certificates. Do not build these unless required — pick the lightest mechanism that passes review.

## Build plan (phases)

Follow these in order. Each phase ends green on the full harness gate in `CLAUDE.md` (lint + types + tests) before the next begins. Build your own todo list from these phases and restate the plan back before touching code.

1. **Payload + schema.** Define the record and batch JSON schema and a serializer. Freeze the contract. Tests: schema validation, round-trip serialize/deserialize.
2. **Direct HTTPS send.** Post a batch to a configured URL with the token header, honoring system/proxy settings and a sane timeout. Tests: sends against a **local stub collector**, correct header, correct handling of 2xx vs. error responses.
3. **Local outbox + retry.** Persist records to an on-disk queue before sending; remove on success; retry with backoff on failure; survive process restart. Tests: simulate connection failure and recovery, restart with a non-empty outbox, backoff behavior, no data loss and no duplicate-on-crash beyond an at-least-once guarantee.
4. **Collector endpoint.** Implement the chosen serverless function (Lambda+DynamoDB or Workers+D1): validate the token, validate the payload, write durably, return 2xx only on success. Tests: token rejection, malformed payload rejection, successful store.
5. **End-to-end + hardening.** Wire client to a real deployed collector in a staging config; confirm delivery, offline-then-online recovery, and that no token or PII leaks into logs. Confirm reachability through a proxy. Document the deploy steps and the config (URL + token) the client needs.

## Out of scope for this build

Dashboards/visualization beyond confirming rows land; a background OS service/daemon; the stronger auth mechanisms (unless review requires them); any analytics on the collected data. Keep the surface small — the value here is reliable delivery, not features.

## Recommendation carried over from the design doc

Direct HTTPS send + a local outbox with retry, posting to a small serverless endpoint (function + database) protected by a secret key. Simple, reliable, and nothing extra to install on the user's machine.