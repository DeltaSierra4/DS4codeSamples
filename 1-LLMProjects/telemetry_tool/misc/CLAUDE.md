# CLAUDE.md — Usage Telemetry Transport

Standing behavior and the harness for this project. This file is human-authored and human-owned; do not rewrite it on your own. If a rule here is wrong for the task in front of you, stop and say so — do not silently work around it.

Read this file and `FLOW.md` before writing any code. `FLOW.md` is the plan for the current build; this file is how you are expected to behave while executing it.

## What we are building

A small telemetry client that runs on many user machines and sends short bits of usage data back to a central collector we own. The agreed architecture (see `FLOW.md`) is **direct HTTPS send + a local outbox with retry**, posting to a **token-protected serverless endpoint backed by a database**. The client is the sensitive part: it runs on other people's machines, so correctness, quietness, and reliability matter more than features.

## The four guardrails

These exist because a language model cannot reliably judge its own output at the moment it writes it — the same pass that produces the code also produces its confidence in the code. These rules are the second set of eyes standing in for that gap. Follow all four on every change.

1. **No silent assumptions.** When a requirement is ambiguous — the payload schema, the flush interval, the retry/backoff policy, the endpoint URL, which auth mechanism, what counts as a permanent vs. retryable failure — stop and ask. State the assumption you would otherwise make and wait. Never pick a default and run with it, especially for anything that touches the network, disk, or the payload contract.
2. **Build the smallest thing that works.** The chosen design is deliberately minimal. Do not add speculative abstraction, plugin layers, config frameworks, or queuing systems the task did not ask for. No new third-party dependency without approval — justify why the standard library will not do first.
3. **Surgical changes only.** Touch only the files the current `FLOW.md` phase names. Do not refactor, rename, reformat, or delete code you were not asked to change and do not fully understand. If a change seems to require touching unrelated code, stop and explain why before doing it.
4. **Never grade your own work.** A change is "done" only when the verify commands below pass — not when you feel confident it is correct. Do not report success on the basis of having written the code. Run the harness, paste the real output, and only then move on.

## The harness — how "done" is defined

"Done" is not a judgment call; it is whatever these commands say. The examples below are Python (the reference client lives on each user machine and Python ships broadly), but the rule is language-neutral: **every phase ends with a lint pass, a type/static-check pass, and a test pass, and a change that fails any of them is not done.** If this project's real toolchain differs from the examples, use the real one and update this section — do not invent commands.

Reference commands (Python client):

    # format + lint
    ruff format . && ruff check .

    # static types
    mypy src/

    # tests (unit + the integration test against a local stub collector)
    pytest -q

    # run the whole gate in one shot before declaring a phase done
    ruff check . && mypy src/ && pytest -q

Rules for the harness:

- Every new behavior ships with a test. Network sending, outbox persistence, and retry logic are tested against a **local stub collector**, never a live endpoint.
- Retry/backoff and offline behavior must be covered by tests that simulate connection failure — this is the reliability claim of the whole design, so it is not optional.
- Secrets (the collector token) never appear in code, tests, logs, or fixtures. Read them from the environment / a config file that is gitignored. A test that would print or commit a token is a failing test.
- If you cannot run a command, say so plainly. Do not describe what you assume the output would be.

## Loop / Auto-mode limits

Once `FLOW.md` and this file are settled, most of the build can run hands-off. You may proceed without asking, one `FLOW.md` phase at a time, **as long as** each phase ends green on the full harness gate above.

Stop and get explicit approval before you:

- change the payload schema, the endpoint contract, or the auth mechanism;
- add or upgrade a third-party dependency;
- touch anything involving the token, credentials, or how data leaves the machine;
- delete or rewrite existing files, or make a change that spans phases FLOW.md keeps separate;
- start a phase whose harness cannot yet be run (say so instead of coding blind).

Do not loop indefinitely trying to make tests pass. After two failed attempts at the same failure, stop and report what you have tried.

## A note on Codex / other agents

Claude Code loads this file automatically. Codex and most other agents look for `AGENTS.md`. If this repo needs to support both, keep the real instructions in one file and make the other a one-line import of it, rather than maintaining two copies that drift apart.