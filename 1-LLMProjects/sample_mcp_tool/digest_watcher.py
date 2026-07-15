 """
digest_watcher.py
Runs at 9 AM daily (via Windows Task Scheduler).

Scans the inbox for UNREAD emails matching:
  - Subject exactly equal to "{FORUM NAME} Weekly Digest"
  - Subject containing "Medium Daily Digest"

For each match: summarises into a .md string, then:
  1. Sends the summary to Vincent Yang (US) via Teams 1:1 DM
  2. Uploads the .md to your OneDrive under mcp_testing/

Auth: Two-layer auth, both automatic after first run:
      1. x-litellm-api-key  — Your LiteLLM gateway key (from config.json)
      2. M365 OAuth token   — obtained via browser sign-in on first run per
         server, then cached in ~/.mcp-auth/digest-watcher/. The MCP SDK
         handles refresh automatically.

First run: a browser window will open 1–3 times (once per MCP server).
           Sign in with your M365 account. Tokens are cached for future runs.

Setup:
  1. pip install -r requirements.txt
  2. Copy config.template.json -> config.json and fill in litellm_api_key
  3. python digest_watcher.py          (smoke-test / first run)
  4. powershell -File schedule_task.ps1  (register 9 AM daily task)
"""

import asyncio
import base64
import json
import re
import sys
import webbrowser
import threading
import datetime
import pathlib
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Any

import httpx
import requests
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.auth import OAuthClientProvider
from mcp.client.auth.oauth2 import OAuthClientMetadata, OAuthToken, OAuthClientInformationFull

# If you have SSL, patch Python's ssl module to use the Windows certificate store.
# This makes httpx and requests trust any internal CA without any manual cert export.
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass  # non-Windows or truststore unavailable; falls back to certifi

# Server URLs (sourced from mcp.json)
OUTLOOK_URL  = "https://YOUR.URL/outlookmcp"
TEAMS_URL    = "https://YOUR.URL/teamsmcp"
ONEDRIVE_URL = "https://YOUR.URL/onedrivemcp"

# ssl_verify=False, default for cases not resolvable via Python ssl/anyio.
_ssl_verify: bool = False

# OAuth token cache — stored outside the project directory for security
_HERE           = pathlib.Path(__file__).parent
OAUTH_CACHE_DIR = pathlib.Path.home() / ".mcp-auth" / "digest-watcher"
OAUTH_CALLBACK_PORT = 8492  # localhost port for the one-time OAuth redirect

# Scopes requested per MCP server (union of what the tools need)
_SCOPES = {
    OUTLOOK_URL:  "openid profile User.Read Mail.Read Mail.ReadWrite",
    TEAMS_URL:    "openid profile User.Read Chat.Read Chat.ReadWrite ChatMessage.Read ChatMessage.Send",
    ONEDRIVE_URL: "openid profile User.Read Files.Read Files.ReadWrite",
}

CONFIG_PATH   = _HERE / "config.json"
STATE_PATH    = _HERE / "state.json"
SENT_IDS_PATH = _HERE / "sent_ids.json"  # separate from state.json so resets don't clear it

# Name of forum or company you subscribe to. Here I'm using Medium.com as an example.
FORUM NAME = "Medium"


# --- Config / state -----------------------------------------------------------

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(
            f"[ERROR] config.json not found at {CONFIG_PATH}.\n"
            "Copy config.template.json -> config.json and fill in your values."
        )
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def load_state() -> dict:
    return json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_sent_ids() -> set[str]:
    """Load the set of already-processed email IDs (never reset with state.json)."""
    if SENT_IDS_PATH.exists():
        return set(json.loads(SENT_IDS_PATH.read_text(encoding="utf-8")))
    return set()


def save_sent_ids(ids: set[str]) -> None:
    SENT_IDS_PATH.write_text(json.dumps(sorted(ids), indent=2), encoding="utf-8")


# --- OAuth helpers ------------------------------------------------------------

class _FileTokenStorage:
    """Persists OAuthToken + OAuthClientInformationFull to a JSON file."""

    def __init__(self, path: pathlib.Path) -> None:
        self._path = path

    def _load(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    async def get_tokens(self) -> OAuthToken | None:
        d = self._load()
        return OAuthToken(**d["tokens"]) if "tokens" in d else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        d = self._load()
        d["tokens"] = tokens.model_dump(mode="json")
        self._save(d)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        d = self._load()
        return OAuthClientInformationFull(**d["client_info"]) if "client_info" in d else None

    async def set_client_info(self, info: OAuthClientInformationFull) -> None:
        d = self._load()
        d["client_info"] = info.model_dump(mode="json")
        self._save(d)


# One pending OAuth callback at a time (sequential tool calls, no concurrency issue)
_oauth_callback: asyncio.Future | None = None


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        params = parse_qs(urlparse(self.path).query)
        code  = params.get("code",  [None])[0]
        state = params.get("state", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h2>Authorization complete \xe2\x80\x94 you can close this window.</h2>")
        global _oauth_callback
        if _oauth_callback and not _oauth_callback.done():
            loop = _oauth_callback.get_loop()
            loop.call_soon_threadsafe(_oauth_callback.set_result, (code, state))

    def log_message(self, *args: Any) -> None:
        pass  # suppress access log noise


async def _redirect_handler(url: str) -> None:
    print(f"\n  [OAuth] Opening browser for M365 sign-in...")
    print(f"  If the browser doesn't open automatically, visit:\n  {url}\n")
    webbrowser.open(url)


async def _callback_handler() -> tuple[str, str | None]:
    global _oauth_callback
    loop = asyncio.get_event_loop()
    _oauth_callback = loop.create_future()

    server = HTTPServer(("localhost", OAUTH_CALLBACK_PORT), _OAuthCallbackHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        code, state = await _oauth_callback
        return code, state
    finally:
        server.shutdown()


_oauth_providers: dict[str, OAuthClientProvider] = {}


def _get_oauth_provider(server_url: str) -> OAuthClientProvider:
    if server_url not in _oauth_providers:
        server_name = server_url.rstrip("/").split("/")[-1]
        storage = _FileTokenStorage(OAUTH_CACHE_DIR / f"{server_name}.json")
        metadata = OAuthClientMetadata(
            redirect_uris=[f"http://localhost:{OAUTH_CALLBACK_PORT}/callback"],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope=_SCOPES.get(server_url, "openid profile"),
            token_endpoint_auth_method="client_secret_post",
            client_name="digest-watcher",
        )
        _oauth_providers[server_url] = OAuthClientProvider(
            server_url=server_url,
            client_metadata=metadata,
            storage=storage,
            redirect_handler=_redirect_handler,
            callback_handler=_callback_handler,
        )
    return _oauth_providers[server_url]


# --- MCP call helper ----------------------------------------------------------

def _make_httpx_client(
    headers: dict | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """httpx client factory for streamablehttp_client. Uses _ssl_verify from config."""
    return httpx.AsyncClient(
        verify=_ssl_verify,
        headers=headers or {},
        timeout=timeout,
        auth=auth,
    )


def _is_token_expired(text: str) -> bool:
    return "401" in text and "Unauthorized" in text


def _refresh_token(server_url: str) -> None:
    """Delete the cached OAuth token and evict the provider so next call re-auths."""
    server_name = server_url.rstrip("/").split("/")[-1]
    token_file  = OAUTH_CACHE_DIR / f"{server_name}.json"
    if token_file.exists():
        token_file.unlink()
    _oauth_providers.pop(server_url, None)
    print(f"  [Auth] Token expired for {server_name} — refreshing (browser may open)...")


async def mcp_call(server_url: str, api_key: str, tool: str, args: dict,
                   _retry: bool = True) -> Any:
    """Call one tool on an MCP HTTP server and return the parsed result."""
    headers = {"x-litellm-api-key": f"Bearer {api_key}"}
    async with streamablehttp_client(
        server_url,
        headers=headers,
        httpx_client_factory=_make_httpx_client,
        auth=_get_oauth_provider(server_url),
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)

            if result.isError:
                # Some servers surface 401 as isError=True with the message in content.
                if _retry and _is_token_expired(str(result.content)):
                    _refresh_token(server_url)
                    return await mcp_call(server_url, api_key, tool, args, _retry=False)
                raise RuntimeError(f"MCP tool '{tool}' returned an error: {result.content}")

            raw = result.content[0].text if result.content else "{}"
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return raw

            # Other servers (e.g. onedrivemcp) surface 401 as isError=False but
            # with {"error": "... 401 Unauthorized ..."} in the JSON body.
            if isinstance(parsed, dict) and _is_token_expired(str(parsed.get("error", ""))):
                if _retry:
                    _refresh_token(server_url)
                    return await mcp_call(server_url, api_key, tool, args, _retry=False)
                raise RuntimeError(f"MCP tool '{tool}' returned a 401 after token refresh: {parsed}")

            return parsed


def _extract_list(data: Any, *keys: str) -> list:
    """Pull a list from a dict result, trying several common key names."""
    if isinstance(data, list):
        return data
    for k in keys:
        if isinstance(data, dict) and k in data and isinstance(data[k], list):
            return data[k]
    return []


# --- Email search -------------------------------------------------------------

async def fetch_matching_emails(api_key: str, since: datetime.datetime,
                                already_processed: set[str] | None = None) -> list[dict]:
    """
    Run two KQL searches, merge, de-duplicate, and date-filter.

    Rule 1 — {FORUM NAME} Weekly Digest : subject must equal exactly "{FORUM NAME} Weekly Digest"
    Rule 2 — Medium Daily Digest: phrase can appear ANYWHERE in the email
                                  (body, subject, etc.); body check is done
                                  after full bodies are fetched in run().
    """
    already_processed = already_processed or set()
    queries = [
        f"subject:{FORUM NAME} Weekly Digest isread:false",          # rule 1 candidates
        "Medium Daily Digest isread:false",                # rule 2: full-text search
        "subject:News you might have missed isread:false", # rule 3 candidates
    ]

    seen: set[str] = set()
    candidates: list[dict] = []
    rule2_ids: set[str] = set()   # emails that came from the full-text search

    for q_idx, q in enumerate(queries):
        data = await mcp_call(OUTLOOK_URL, api_key, "search_emails", {"query": q, "top": 50})
        for email in _extract_list(data, "emails", "messages", "value"):
            eid = email.get("id") or email.get("messageId")
            if eid and eid not in seen:
                seen.add(eid)
                candidates.append(email)
            if eid and q_idx == 1:
                rule2_ids.add(eid)

    matched = []
    for email in candidates:
        subj = (email.get("subject") or "").strip()
        eid  = email.get("id") or email.get("messageId")

        # Skip emails already sent in a previous run
        if eid in already_processed:
            continue

        # Content gate:
        #   rule 1 — subject exactly "{FORUM NAME} Weekly Digest"
        #   rule 2 — any email from the full-text search (body check deferred)
        #   rule 3 — subject contains "News you might have missed"
        is_rule1 = (subj == f"{FORUM NAME} Weekly Digest")
        is_rule2 = eid in rule2_ids
        is_rule3 = "News you might have missed" in subj
        if not (is_rule1 or is_rule2 or is_rule3):
            continue

        # Date gate: received strictly after `since`
        raw_date = email.get("date") or email.get("receivedDateTime") or ""
        if raw_date:
            try:
                received = datetime.datetime.fromisoformat(
                    raw_date.replace("Z", "+00:00").split(".")[0]
                ).replace(tzinfo=None)
                if received <= since:
                    continue
            except ValueError:
                pass  # keep if we cannot parse the date

        matched.append(email)

    return matched


async def fetch_email_bodies(api_key: str, emails: list[dict]) -> list[dict]:
    """Enrich each email with its full body via get_email_by_id."""
    enriched = []
    for email in emails:
        eid = email.get("id") or email.get("messageId")
        if not eid:
            enriched.append(email)
            continue
        try:
            full = await mcp_call(OUTLOOK_URL, api_key, "get_email_by_id", {"message_id": eid})
            enriched.append(full if isinstance(full, dict) else email)
        except Exception as exc:
            print(f"    [WARN] Could not fetch body for email {eid}: {exc}")
            enriched.append(email)
    return enriched


# --- Summarisation ------------------------------------------------------------

def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s{2,}", " ", text).strip()


def summarize(config: dict, emails: list[dict]) -> str:
    combined = ""
    for email in emails:
        body_obj  = email.get("body") or {}
        body_raw  = body_obj.get("content") if isinstance(body_obj, dict) else str(body_obj)
        body_text = _strip_html(body_raw or email.get("bodyPreview", ""))[:8000]

        from_obj  = email.get("from") or {}
        from_addr = (
            from_obj.get("emailAddress", {}).get("address")
            if isinstance(from_obj, dict) else str(from_obj)
        )

        combined += (
            f"\n\n---\n"
            f"**Subject:** {email.get('subject', '')}\n"
            f"**From:** {from_addr}\n"
            f"**Received:** {email.get('receivedDateTime', email.get('date', ''))}\n\n"
            f"{body_text}\n"
        )

    payload = {
        "model": config.get("model", "claude-sonnet-4-5"),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a concise newsletter digest summarizer. "
                    "For each email, produce a clean Markdown section with: "
                    "an ## heading using the email subject, "
                    "a bullet list of the 5-8 most important topics or links, "
                    "and a bold **TL;DR** line. Keep each section under 200 words."
                ),
            },
            {"role": "user", "content": f"Summarize these digest emails into Markdown:\n{combined}"},
        ],
        "max_tokens": 2048,
    }
    r = requests.post(
        config["litellm_endpoint"],
        headers={
            "Authorization": f"Bearer {config['litellm_api_key']}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
        verify=_ssl_verify,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# --- Teams helpers ------------------------------------------------------------

async def find_1on1_chat(api_key: str, recipient_name: str) -> str | None:
    """Find an existing 1:1 Teams DM with `recipient_name`; returns chat ID or None."""
    me      = await mcp_call(TEAMS_URL, api_key, "whoami", {})
    # whoami returns the AAD object GUID in "id".
    # list_chats members use "userId" for the AAD GUID and a different "id" for the
    # conversation-member blob — they are NOT the same value. Always compare against
    # "userId", and fall back to display-name equality to skip the current user.
    my_aad_id = (me.get("id") or "").lower()
    my_name   = (me.get("displayName") or "").lower()

    skip_token = None
    while True:
        args: dict = {"expand": "members", "top": 50}
        if skip_token:
            args["skip_token"] = skip_token

        data  = await mcp_call(TEAMS_URL, api_key, "list_chats", args)
        chats = _extract_list(data, "chats", "value")

        for chat in chats:
            if chat.get("chatType") != "oneOnOne":
                continue
            for member in (chat.get("members") or []):
                # "userId" is the AAD GUID; "id" is the conversation-member blob (different).
                user_id = (member.get("userId") or "").lower()
                dname   = (member.get("displayName") or "").lower()

                # Skip the current user: match by AAD GUID OR by exact display name
                is_me = (user_id and user_id == my_aad_id) or (my_name and dname == my_name)
                if is_me:
                    continue

                if recipient_name.lower() in dname:
                    return chat["id"]

        skip_token = data.get("skip_token") if isinstance(data, dict) else None
        if not skip_token:
            break

    return None


def _md_to_html(md: str) -> str:
    out = []
    for line in md.split("\n"):
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        line = re.sub(r"\*(.+?)\*",     r"<i>\1</i>",  line)
        line = re.sub(r"`(.+?)`",        r"<code>\1</code>", line)
        if line.startswith("## "):
            line = f"<h2>{line[3:]}</h2>"
        elif line.startswith("# "):
            line = f"<h1>{line[2:]}</h1>"
        elif line.startswith(("- ", "* ")):
            line = f"<li>{line[2:]}</li>"
        elif line.strip() == "---":
            line = "<hr/>"
        else:
            line = line + "<br/>"
        out.append(line)
    return "\n".join(out)


async def send_teams_dm(
    api_key: str, chat_id: str, summary_md: str, date_str: str, filename: str
) -> None:
    preamble = (
        f"<b>Daily Digest -- {date_str}</b>&nbsp;|&nbsp;"
        f"Full file on OneDrive: <code>mcp_testing/{filename}</code><br/><hr/>"
    )
    await mcp_call(TEAMS_URL, api_key, "send_chat_message", {
        "chat_id":      chat_id,
        "content":      preamble + _md_to_html(summary_md),
        "content_type": "html",
    })


# --- OneDrive helpers ---------------------------------------------------------

async def get_or_create_mcp_testing_folder(api_key: str) -> str:
    """Return the ID of /mcp_testing, creating it at the root if absent."""
    data  = await mcp_call(ONEDRIVE_URL, api_key, "list_files", {"folder_id": None})
    items = _extract_list(data, "items", "value")
    for item in items:
        # Accept any item named mcp_testing — folder facet presence is not guaranteed
        # by all onedrivemcp response shapes.
        if item.get("name") == "mcp_testing":
            return item["id"]

    result = await mcp_call(ONEDRIVE_URL, api_key, "create_folder", {
        "parent_folder_id": None,
        "folder_name":      "mcp_testing",
    })
    # The create_folder response can nest the ID in several ways depending on whether
    # the folder was freshly created or already existed.
    folder_id = (
        result.get("id")
        or result.get("folder_id")
        or (result.get("folder") or {}).get("id")
        or (result.get("item") or {}).get("id")
    )
    if folder_id:
        return folder_id

    # Last resort: re-list and find it by name (handles conflict / already-exists responses)
    data  = await mcp_call(ONEDRIVE_URL, api_key, "list_files", {"folder_id": None})
    items = _extract_list(data, "items", "value")
    for item in items:
        if item.get("name") == "mcp_testing":
            return item["id"]

    raise RuntimeError("Could not find or create the mcp_testing folder in OneDrive.")


async def upload_md(api_key: str, folder_id: str, filename: str, content: str) -> None:
    content_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    await mcp_call(ONEDRIVE_URL, api_key, "upload_file", {
        "folder_id":      folder_id,
        "filename":       filename,
        "content_base64": content_b64,
    })


# --- Main ---------------------------------------------------------------------

async def run() -> None:
    global _ssl_verify
    config  = load_config()
    state   = load_state()
    api_key = config["litellm_api_key"]
    _ssl_verify = config.get("ssl_verify", True)

    now_utc = datetime.datetime.utcnow()
    since = (
        datetime.datetime.fromisoformat(state["last_run"])
        if state.get("last_run")
        else now_utc - datetime.timedelta(hours=24)
    )

    print(
        f"[digest_watcher] {now_utc.strftime('%Y-%m-%d %H:%M')} UTC"
        f" -- checking since {since.strftime('%Y-%m-%d %H:%M')} UTC"
    )

    # 1. Find unread matching emails
    print("  Searching for unread matching emails...")
    sent_ids = load_sent_ids()
    emails = await fetch_matching_emails(api_key, since, sent_ids)
    print(f"  {len(emails)} match(es) found.")

    if not emails:
        print("  Nothing to process.")
        save_state({"last_run": now_utc.isoformat()})
        return

    # 2. Fetch full bodies
    print("  Fetching full email content...")
    emails = await fetch_email_bodies(api_key, emails)

    # 2b. Content filter after body fetch
    #   rule 1: exact subject match (no body check needed)
    #   rule 2: body must contain "Medium Daily Digest"
    #   rule 3: subject contains "News you might have missed" (no body check needed)
    filtered = []
    for email in emails:
        subj = (email.get("subject") or "").strip()
        if subj == "{FORUM NAME} Weekly Digest":
            filtered.append(email)   # rule 1
        elif "News you might have missed" in subj:
            filtered.append(email)   # rule 3
        else:
            body_raw = (email.get("body") or {}).get("content") or email.get("bodyPreview") or ""
            if "Medium Daily Digest" in _strip_html(body_raw):
                filtered.append(email)  # rule 2
    emails = filtered

    if not emails:
        print("  No emails passed the content filter after body check.")
        save_state({"last_run": now_utc.isoformat()})
        return

    # 3. Summarise
    print("  Summarising via LiteLLM...")
    summary_md = summarize(config, emails)

    date_str = now_utc.strftime("%Y-%m-%d")
    filename = f"digest-{date_str}.md"
    full_md  = (
        f"# Daily Digest -- {date_str}\n"
        f"_Generated {now_utc.strftime('%Y-%m-%d %H:%M')} UTC"
        f" -- {len(emails)} source email(s)_\n\n---\n\n"
        + summary_md
    )

    # 4. Teams DM
    recipient_name = config.get("recipient_display_name", "Vincent Yang")
    chat_id        = config.get("teams_chat_id")  # optional shortcut in config

    if not chat_id:
        print(f"  Looking up 1:1 Teams DM with '{recipient_name}'...")
        chat_id = await find_1on1_chat(api_key, recipient_name)

    if chat_id:
        print("  Sending Teams message...")
        await send_teams_dm(api_key, chat_id, summary_md, date_str, filename)
        print("  Teams message sent.")
    else:
        print(
            f"  [WARN] No existing 1:1 chat found with '{recipient_name}'.\n"
            "         Open a DM with them in Teams first, then re-run.\n"
            "         Or paste the chat ID into config.json as 'teams_chat_id'."
        )

    # 5. Upload to OneDrive mcp_testing/
    print("  Resolving OneDrive mcp_testing/ folder...")
    folder_id = await get_or_create_mcp_testing_folder(api_key)
    print(f"  Uploading {filename} to mcp_testing/...")
    await upload_md(api_key, folder_id, filename, full_md)
    print("  OneDrive upload complete.")

    # Persist the processed IDs and update last_run
    new_ids = {e.get("id") or e.get("messageId") for e in emails if e.get("id") or e.get("messageId")}
    save_sent_ids(sent_ids | new_ids)
    save_state({"last_run": now_utc.isoformat()})
    print("  Done.")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()