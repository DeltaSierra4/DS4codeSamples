 # Digest Watcher

A lightweight Python tool that runs every morning at 9 AM, scans your Outlook inbox for specific newsletter emails, summarises them into a Markdown digest using an LLM gateway, sends the summary to a Microsoft Teams chat, and uploads the `.md` file to your OneDrive.

---

## 1. What is this tool?

**Digest Watcher** automates the daily chore of reading recurring newsletters. It monitors your Outlook inbox for three categories of unread emails:

| Rule | Match condition |
|---|---|
| {FORUM NAME} Weekly Digest | Subject line is **exactly** `f"{FORUM NAME} Weekly Digest"` |
| Medium Daily Digest | The phrase `"Medium Daily Digest"` appears **anywhere in the email body** |
| News roundup | Subject line **contains** `"News you might have missed"` |

When matching emails are found, the tool:
1. Fetches the full email content via an Outlook MCP server connected to Microsoft Graph
2. Passes the content to a language model (via a LiteLLM-compatible gateway) for summarisation into structured Markdown
3. Sends the summary as a message to a Microsoft Teams chat (defaults to your personal Notes self-chat)
4. Uploads the full `.md` digest file to your OneDrive under a folder called `mcp_testing`

Each email is processed **at most once** — a deduplication file (`sent_ids.json`) records every email ID that has been handled, so re-running the tool never produces duplicate messages.

---

## 2. Steps to use it

### Prerequisites

- **Python 3.11+** — confirm with `python --version`
- Access to a **LiteLLM-compatible gateway** and a personal API key
- Three **MCP servers** with Microsoft 365 delegated access: one for Outlook, one for Teams, one for OneDrive. These must have been previously authenticated (OAuth browser sign-in) at least once.

---

### Step 1 — Install dependencies

```powershell
cd digest_watcher
pip install -r requirements.txt
```

Installs three packages: `mcp` (MCP Python SDK), `requests` (HTTP), and `truststore` (Windows certificate store integration).

---

### Step 2 — Create your config file

```powershell
Copy-Item config.template.json config.json
```

Open `config.json` and fill in the required fields:

```json
{
  "litellm_api_key":  "sk-...",
  "litellm_endpoint": "https://<your-gateway>/v1/chat/completions",
  "model":            "<model-name-as-listed-by-your-gateway>",

  "recipient_display_name": "Your Name",
  "teams_chat_id": "48:notes",

  "ssl_verify": false
}
```

| Field | What to put |
|---|---|
| `litellm_api_key` | Your personal `sk-...` API key from your LiteLLM gateway. **No `Bearer` prefix** — the tool adds that automatically. |
| `litellm_endpoint` | The `/v1/chat/completions` endpoint of your LiteLLM gateway. |
| `model` | The model identifier as returned by `GET /v1/models` on your gateway. |
| `teams_chat_id` | `"48:notes"` sends to your personal Teams Notes (self-chat, visible only to you). To send to a specific DM instead, open that chat in Teams, copy the URL, and paste the ID after `/conversations/`. |
| `ssl_verify` | Set `false` if your gateway uses an internal or self-signed certificate that Python's SSL stack cannot verify. |

> **Never commit `config.json`** — it contains your API key.

---

### Step 3 — First run (triggers browser sign-in)

```powershell
python digest_watcher.py
```

On the first run the tool needs to authenticate to each of the three MCP servers (Outlook, Teams, OneDrive) using your M365 account. A **browser window will open up to three times** — once per server. Sign in with your Microsoft 365 account each time. Tokens are cached in `~/.mcp-auth/digest-watcher/` and reused on every subsequent run; the browser will not open again unless a token expires.

Expected first-run output (no matching emails):
```
[digest_watcher] 2026-07-14 09:00 UTC -- checking since 2026-07-13 09:00 UTC
  Searching for unread matching emails...
  [OAuth] Opening browser for M365 sign-in...
  ...
  0 match(es) found.
  Nothing to process.
```

---

### Step 4 — Register the daily scheduled task

```powershell
powershell -ExecutionPolicy Bypass -File schedule_task.ps1
```

This creates a Windows Task Scheduler entry `\DigestWatcher-DailyDigest` that runs `digest_watcher.py` every day at **9:00 AM** under your own user account.

---

### Pausing and resuming

**Pause** (stops the 9 AM trigger, keeps the task definition):
```powershell
powershell -ExecutionPolicy Bypass -File pause_task.ps1
```

**Resume** (re-enables the existing task, no re-registration needed):
```powershell
powershell -ExecutionPolicy Bypass -File schedule_task.ps1
```

---

### Resetting for manual testing

To force the tool to re-check emails from the past 24+ hours (useful for testing):

```powershell
# Reset the time window — keeps deduplication intact
python -c "import json,pathlib; pathlib.Path('state.json').write_text(json.dumps({'last_run':'2026-07-13T00:00:00'}), encoding='utf-8')"
python digest_watcher.py
```

> **Do not delete `sent_ids.json`** — that file is your duplicate-send guard. Deleting it will cause the tool to re-send emails it has already processed.

---

## 3. How the tool works

### Architecture overview

```
Windows Task Scheduler (9 AM)
        │
        ▼
digest_watcher.py
        │
        ├── Outlook MCP server  ──► Microsoft Graph (Outlook)
        │       search_emails, get_email_by_id
        │
        ├── LiteLLM gateway  ──► Language model
        │       Summarise email bodies into Markdown
        │
        ├── Teams MCP server  ──► Microsoft Graph (Teams)
        │       send_chat_message → teams_chat_id
        │
        └── OneDrive MCP server  ──► Microsoft Graph (OneDrive)
                list_files, create_folder, upload_file → mcp_testing/
```

### Authentication layers

The tool uses **two independent auth layers**, both managed automatically after the first run:

1. **LiteLLM API key** (`x-litellm-api-key` header) — identifies you to the LLM gateway. Stored in `config.json`.
2. **M365 OAuth tokens** — identifies you to Microsoft Graph (so the MCP servers can read your mail, send Teams messages, and write to your OneDrive). Obtained via browser sign-in on first run; cached per-server in `~/.mcp-auth/digest-watcher/`. If a token expires mid-run, the tool detects the embedded 401 error in the tool response, deletes the stale cache file, and re-authenticates automatically.

### Email matching (three rules)

Emails are searched using Outlook KQL via the `search_emails` MCP tool, then filtered client-side:

| Rule | KQL query | Client-side gate |
|---|---|---|
| 1 | `subject:{FORUM NAME} Weekly Digest isread:false` | Subject must be **exactly** `f"{FORUM NAME} Weekly Digest"` |
| 2 | `Medium Daily Digest isread:false` | Body must contain `"Medium Daily Digest"` (requires full body fetch) |
| 3 | `subject:News you might have missed isread:false` | Subject must **contain** `"News you might have missed"` |

Rule 2 requires a two-phase check: the KQL search finds candidates, `get_email_by_id` fetches the full body, then the body is scanned for the phrase.

### Deduplication

Two files track state:

| File | Purpose | Reset-safe? |
|---|---|---|
| `state.json` | Stores `last_run` timestamp to define the search window | Yes — can be reset for testing |
| `sent_ids.json` | Stores every email ID that has been fully processed and sent | **No** — never delete; this is the duplicate-send guard |

After a successful end-to-end run (summary sent to Teams **and** uploaded to OneDrive), the processed email IDs are appended to `sent_ids.json`. Any subsequent run — even with a manually reset `state.json` — will skip those IDs.

### Output

On each run with matching emails:
- A Markdown file `digest-YYYY-MM-DD.md` is uploaded to `mcp_testing/` in your OneDrive
- A Teams message is sent to the configured `teams_chat_id` with an inline HTML summary and a reference to the OneDrive file

The Markdown format per email:
```markdown
## <Subject line>

- Key topic 1
- Key topic 2
- ...

**TL;DR** One-line summary
```