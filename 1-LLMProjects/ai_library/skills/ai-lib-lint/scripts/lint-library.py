#!/usr/bin/env python3
"""
lint-library.py — the only detector in ai-lib, and the only thing that walks the tree.

Reads an ai-lib library and emits ONE json document that is simultaneously:

  * the INVENTORY  — every topic, document, capture, and all their frontmatter, verbatim
  * the FINDINGS   — every place the tree disagrees with SCHEMA.md

Both live in the same file on purpose. `index-library.py`, `build-library.py` and
`build-compare.py` all read this json and NEVER walk the tree themselves, so the four
scripts can never disagree about what the library contains. One walker, many consumers.

READ-ONLY. It never writes into `topics/`. `patch-library.py` is the only writer of page
fixes and it re-detects nothing; it consumes the findings carrying `autofix: true`.

THE TWO RULES THAT MATTER MOST, and why they are here rather than in a prompt:

  1. EVERY CLAIM CARRIES A MARKER. `CLM-UNMARKED` is the highest-severity finding this
     script produces, because an unmarked claim is indistinguishable from a traceable one
     and destroys the only property that makes the library worth having. A prompt can ask
     for markers; only a checker can prove they are there.

  2. NO CAPTURE OUTSIDE ITS LINK PLAN. `CAP-UNAUTHORIZED` is the audit that makes the
     one-hop limit real (SCHEMA.md § 6.2). A script cannot do the fetching, so it cannot
     physically stop a second hop — but it can prove after the fact that every URL fetched
     was authorized by a plan generated from a source document. A capture whose URL is in
     no plan is the signature of a second-hop fetch.

Findings carry a stable `rule` id, a `severity`, an `autofix` flag and, where the detector
can compute the sanctioned fix, a `derived` map. The patcher is FORBIDDEN from deriving
anything itself.

Severity is about consequence, not tidiness:
    error  an answer built on this page would be untraceable or wrong
    warn   an answer built on this page would be incomplete or misleading
    info   worth a human's attention; nothing downstream breaks

Stdlib only. No pyyaml, no install step.

Invocation:
    python3 lint-library.py --library <root> --out output/_library-data.json
    python3 lint-library.py --library <root>              # json to stdout

Exit codes:
    0  successful scan, however many findings it produced
    1  hard error — the library root is absent, or holds neither SCHEMA.md nor topics/
"""

import argparse
import datetime
import json
import os
import re
import sys

SCHEMA_VERSION = 1

DOC_SECTIONS = [
    "Snapshot", "Problem & Context", "Method", "Key Claims", "Evidence",
    "Limitations", "Connections", "Open Questions", "From Linked Pages",
    "Additional capture",
]
TOPIC_SECTIONS = ["Snapshot", "What Belongs Here", "Key Documents", "Themes", "Gaps",
                  "Additional capture"]
CAPTURE_SECTIONS = ["Metadata", "What was taken", "Not taken"]
CAPTURE_QUARANTINE = "From Linked Pages"
OPEN_SECTION = "Additional capture"
PLACEHOLDERS = {"_none recorded._", "_none._", "_tbd._", "none recorded.", "_n/a._"}

REQUIRED_DOC = ["title", "doc_id", "topic", "publication_type", "authority",
                "source_file", "source_type", "retrieved", "created", "last_updated",
                "updated_by", "extraction_confidence", "status"]
REQUIRED_DOC_LISTS = ["aka", "authors", "tags", "models", "builds_on", "related",
                      "supersedes", "superseded_by"]
REQUIRED_DOC_INTS = ["claim_count", "located_claim_count", "benchmark_count",
                     "links_authorized", "links_followed", "links_declined"]
REQUIRED_TOPIC = ["title", "topic", "category", "node_type", "created", "last_updated",
                  "updated_by", "status"]
REQUIRED_CAPTURE = ["title", "category", "topic", "parent_doc", "source_url",
                    "link_class", "depth", "accessed", "fetch_status", "created",
                    "last_updated", "updated_by", "status"]

ENUMS = {
    "publication_type": ["blog-post", "announcement", "model-card", "documentation",
                         "paper", "preprint", "report", "whitepaper", "tutorial",
                         "benchmark", "standard", "thesis", "book-chapter",
                         "transcript", "newsletter", "other"],
    "authority": ["first-party", "peer-reviewed", "preprint", "institutional",
                  "secondary", "community"],
    "source_type": ["pdf", "txt"],
    "maturity": ["foundational", "established", "emerging", "speculative", "superseded"],
    "reproducibility": ["code-released", "data-released", "both", "neither", "n/a"],
    "extraction_confidence": ["high", "medium", "low"],
    "status": ["active", "superseded", "draft"],
    "node_type": ["branch", "leaf"],
    "link_class": ["paper", "preprint", "code", "documentation", "blog-post", "dataset",
                   "benchmark", "announcement", "video", "other"],
    "fetch_status": ["ok", "partial", "paywalled", "not-found", "blocked", "js-required"],
    "category": ["topic", "capture", "synthesis"],
    "updated_by": ["ai-lib-setup", "ai-lib-ingest", "ai-lib-refresh", "ai-lib-list",
                   "ai-lib-query", "ai-lib-compare", "ai-lib-lint", "practitioner"],
}
CLAIM_TYPES = ["empirical", "methodological", "architectural", "capability",
               "limitation", "normative", "forecast"]
BOOL_FIELDS = ["has_limitations"]
DATE_FIELDS = ["published", "retrieved", "accessed", "created", "last_updated"]
INT_FIELDS = REQUIRED_DOC_INTS + ["pages", "document_count", "depth", "year"]
QUOTED_FIELDS = ["doc_id", "parent_doc"]

NON_PAGE_FILES = {"schema.md", "index.md", "log.md", "readme.md", "agents.md",
                  "claude.md", "taxonomy.md", "library-config.md"}

# Kept in step with new-page.py's table: an acronym rendered "Ai" leaks into index.md,
# every HTML deliverable and every subagent brief.
TOPIC_TITLES = {
    "ai": "AI", "llm": "LLM",
    "llm/claude": "Claude", "llm/gpt": "GPT", "llm/gemini": "Gemini",
    "llm/grok": "Grok", "llm/qwen": "Qwen", "llm/kimi": "Kimi",
    "llm/other-models": "Other Models",
    "data-science": "Data Science",
    "math-sci-tech-cyber": "Math · Science · Technology · Cybersecurity",
    "math-sci-tech-cyber/math": "Math",
    "math-sci-tech-cyber/science": "Science",
    "math-sci-tech-cyber/technology": "Technology",
    "math-sci-tech-cyber/cybersecurity": "Cybersecurity",
    "misc": "Miscellaneous",
}

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# The four provenance markers of SCHEMA.md § 7.1, plus the verify flag.
LOC_RE = re.compile(r"\[(?:p\.\s*\d+[^\]]*|§\s*[\d.]+[^\]]*|Table\s+[^\]]+|"
                    r"Fig\.?\s+[^\]]+|pp\.\s*\d+[^\]]*)\]", re.I)
UNLOC_RE = re.compile(r"\[unlocated\]", re.I)
LINK_RE = re.compile(r"\[link:\s*([^\],]+?)(?:,\s*accessed\s*([\d-]+))?\]", re.I)
INFER_RE = re.compile(r"\[inference:\s*([^\]]+)\]", re.I)
VERIFY_RE = re.compile(r"\[verify:\s*([^\]]+)\]", re.I)
PAGE_NUM_RE = re.compile(r"\[p{1,2}\.\s*(\d+)", re.I)
CLAIM_LINE_RE = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")
CLAIM_TYPE_RE = re.compile(r"\[type:\s*([a-z-]+)\s*\]", re.I)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
CONTRADICTION = "**CONTRADICTION:**"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def strip_yaml_comment(value):
    """Drop a trailing ` # comment`, respecting quoted scalars and inline lists."""
    if not value:
        return value
    if value[0] in "\"'":
        end = value.find(value[0], 1)
        return value[:end + 1] if end != -1 else value
    if value[0] == "[":
        depth = 0
        for i, ch in enumerate(value):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return value[:i + 1]
        return value
    m = re.search(r"\s+#", value)
    return value[:m.start()].strip() if m else value


def split_frontmatter(text):
    """
    Split a page into (data, present_keys, raw_values, body).

    `present_keys` distinguishes an ABSENT key from one present but empty — different
    violations. `raw_values` keeps the unparsed right-hand side so the quoting rule on
    `doc_id` can be checked at all. Unterminated frontmatter returns none rather than
    raising: a linter that dies on one malformed page cannot report it.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, set(), {}, text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, set(), {}, text

    data, present, raw = {}, set(), {}
    current = None
    for line in lines[1:end]:
        s = line.strip()
        if s.startswith("- ") and current is not None:
            item = s[2:].strip().strip("'\"")
            if isinstance(data.get(current), list) and item:
                data[current].append(item)
            continue
        m = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", line)
        if not m:
            continue
        key, value = m.group(1).strip(), m.group(2).strip()
        present.add(key)
        raw[key] = value
        current = None
        value = strip_yaml_comment(value)
        if value == "":
            data[key] = []
            current = key
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            data[key] = ([p.strip().strip("'\"") for p in inner.split(",") if p.strip()]
                         if inner else [])
        else:
            data[key] = value.strip().strip("'\"")
    return data, present, raw, "\n".join(lines[end + 1:])


def iter_body_lines(body):
    """Yield (lineno, line, in_fence). Every scan goes through here so a fenced example
    inside a page can never be mistaken for the page's own grammar."""
    in_fence = False
    for lineno, line in enumerate(body.splitlines(), 1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            yield lineno, line, True
            continue
        yield lineno, line, in_fence


def split_h2(body):
    """[{text, line, lines}] per `##` section, document order."""
    out, cur = [], None
    for lineno, line, fence in iter_body_lines(body):
        m = None if fence else re.match(r"^##\s+(.*?)\s*$", line)
        if m:
            cur = {"text": m.group(1).strip(), "line": lineno, "lines": []}
            out.append(cur)
            continue
        if cur is not None:
            cur["lines"].append((lineno, line))
    return out


def section_body(sections, heading):
    for s in sections:
        if norm(s["text"]) == norm(heading):
            return s
    return None


def norm(v):
    return re.sub(r"\s+", " ", str(v or "")).strip().lower()


def is_placeholder(lines):
    text = "\n".join(l for _n, l in lines if l.strip()).strip()
    return norm(text) in PLACEHOLDERS


def as_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def rel_posix(path, root):
    return os.path.relpath(path, root).replace(os.sep, "/")


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def days_between(later, earlier):
    try:
        return (datetime.date.fromisoformat(str(later))
                - datetime.date.fromisoformat(str(earlier))).days
    except (ValueError, TypeError):
        return None


def normalize_url(u):
    """Loose canonical form, for matching a capture against a plan. Deliberately more
    forgiving than the extractor's: a trailing slash or a missing scheme must not make an
    authorized fetch look unauthorized."""
    s = str(u or "").strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    s = s.split("#", 1)[0]
    return s.rstrip("/")


# ---------------------------------------------------------------------------
# Config and taxonomy
# ---------------------------------------------------------------------------

CONFIG_KEYS = re.compile(r"^([a-z_]+)\s*:\s*(.*)$")


def load_config(root):
    cfg = {}
    text = read_text(os.path.join(root, "_config", "library-config.md"))
    if not text:
        return cfg
    for line in text.splitlines():
        if line.startswith(("|", ">", "#", "-", " ")):
            continue
        m = CONFIG_KEYS.match(line.strip())
        if m and m.group(2) and not m.group(2).startswith("{{"):
            cfg[m.group(1)] = m.group(2).strip()
    return cfg


def load_taxonomy(root):
    text = read_text(os.path.join(root, "_config", "taxonomy.md"))
    if not text:
        return {}
    m = re.search(r"```taxonomy\s*\n(.*?)```", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 2 and parts[0]:
            out[parts[0]] = {"node_type": parts[1],
                             "expected_share": parts[2] if len(parts) > 2 else "-"}
    return out


def cfg_int(cfg, key, default):
    v = as_int(cfg.get(key, default))
    return v if v is not None else default


def cfg_float(cfg, key, default):
    try:
        return float(str(cfg.get(key, default)).strip())
    except (TypeError, ValueError):
        return default


def stale_days_for(topic, cfg):
    if topic.startswith("llm"):
        return cfg_int(cfg, "stale_days_llm", 270)
    if topic == "ai":
        return cfg_int(cfg, "stale_days_ai", 540)
    if topic == "data-science":
        return cfg_int(cfg, "stale_days_data_science", 1095)
    if topic.endswith("cybersecurity"):
        return cfg_int(cfg, "stale_days_cybersecurity", 365)
    if topic.startswith("math-sci-tech-cyber"):
        return cfg_int(cfg, "stale_days_math_sci_tech", 1825)
    return cfg_int(cfg, "stale_days_misc", 1825)


def finding(rule, severity, page, message, autofix=False, derived=None, line=None,
            topic=None, doc_id=None, field=None):
    f = {"rule": rule, "severity": severity, "autofix": bool(autofix),
         "page": page, "message": message}
    if derived:
        f["derived"] = derived
    if line is not None:
        f["line"] = line
    if topic:
        f["topic"] = topic
    if doc_id:
        f["doc_id"] = doc_id
    if field:
        f["field"] = field
    return f


# ---------------------------------------------------------------------------
# Shared checks
# ---------------------------------------------------------------------------

def check_sections(rel, sections, expected, findings, **kw):
    found = [s["text"] for s in sections]
    fn, en = [norm(t) for t in found], [norm(t) for t in expected]
    missing = [expected[i] for i, e in enumerate(en) if e not in fn]
    dupes = sorted({t for t in fn if fn.count(t) > 1})
    invented = [t for t, n in zip(found, fn) if n not in en]

    seen, deduped = set(), []
    for n in [x for x in fn if x in en]:
        if n not in seen:
            seen.add(n)
            deduped.append(n)
    out_of_order = deduped != [n for n in en if n in deduped]
    capture_last = norm(OPEN_SECTION) in fn and fn[-1] != norm(OPEN_SECTION)
    only_missing = bool(missing) and not (dupes or invented or out_of_order or capture_last)

    if missing:
        findings.append(finding(
            "SEC-MISSING", "warn", rel,
            "missing fixed section(s): %s — SCHEMA.md § 3 requires all of them present, "
            "empty ones holding `%s`" % (", ".join(missing), PLACEHOLDER_TEXT),
            autofix=only_missing,
            derived={"missing": missing, "expected_order": expected}, **kw))
    if dupes:
        findings.append(finding("SEC-DUP", "error", rel,
            "duplicated section heading(s): %s — a consumer reads the first and silently "
            "drops the second" % ", ".join(dupes), **kw))
    if invented:
        findings.append(finding("SEC-INVENTED", "error", rel,
            "section heading(s) not in the contract: %s — put this content under "
            "`## Additional capture` as a `###`"
            % ", ".join("`## %s`" % t for t in invented), **kw))
    if out_of_order:
        findings.append(finding("SEC-ORDER", "warn", rel,
            "sections out of contract order — found %s, contract is %s"
            % (deduped, [n for n in en if n in deduped]), **kw))
    if capture_last:
        findings.append(finding("SEC-CAPTURE-NOT-LAST", "error", rel,
            "`## Additional capture` is not last — consumers stop reading the contract "
            "there, so everything below it is invisible", **kw))


PLACEHOLDER_TEXT = "_None recorded._"


def check_enums(rel, fm, findings, **kw):
    for key, allowed in ENUMS.items():
        if key not in fm:
            continue
        v = fm[key]
        if isinstance(v, list) or v == "":
            continue
        if v not in allowed:
            findings.append(finding("FM-ENUM", "error", rel,
                "`%s: %s` is not in the controlled vocabulary — allowed: %s "
                "(SCHEMA.md § 2.2)" % (key, v, ", ".join(allowed)),
                field=key, **kw))


def check_formats(rel, fm, raw, present, findings, **kw):
    for key in INT_FIELDS:
        if key in present and fm.get(key) != [] and as_int(fm.get(key)) is None:
            findings.append(finding("FM-INT", "error", rel,
                "`%s: %s` must be a bare integer" % (key, fm.get(key)),
                field=key, **kw))
    for key in DATE_FIELDS:
        if key in present and fm.get(key) and not isinstance(fm[key], list):
            if not DATE_RE.match(str(fm[key])):
                findings.append(finding("FM-DATE", "warn", rel,
                    "`%s: %s` is not `YYYY-MM-DD` (SCHEMA.md § 2.3)" % (key, fm[key]),
                    field=key, **kw))
    for key in BOOL_FIELDS:
        if key in present and str(fm.get(key)).lower() not in ("true", "false"):
            mapped = {"yes": "true", "no": "false", "1": "true",
                      "0": "false"}.get(norm(fm.get(key)))
            findings.append(finding("FM-BOOL", "error", rel,
                "`%s: %s` is not a YAML boolean — write `true` or `false`, unquoted"
                % (key, fm.get(key)),
                autofix=mapped is not None,
                derived={key: mapped} if mapped else None, field=key, **kw))
    for key in QUOTED_FIELDS:
        if key in raw:
            r = strip_yaml_comment(raw[key]).strip()
            if r and not r.startswith(("\"", "'")):
                findings.append(finding("FM-ID-UNQUOTED", "warn", rel,
                    "`%s` must be quoted (SCHEMA.md § 2.2)" % key,
                    autofix=True, derived={key: '"%s"' % r}, field=key, **kw))


def check_required(rel, present, findings, required, lists, ints, derived, **kw):
    missing = [k for k in required if k not in present]
    if missing:
        fixable = {k: derived[k] for k in missing if k in derived}
        findings.append(finding("FM-REQUIRED-MISSING", "error", rel,
            "required frontmatter key(s) absent: %s" % ", ".join(missing),
            autofix=bool(fixable) and set(fixable) == set(missing),
            derived={"fields": missing, "values": fixable}, **kw))
    ml = [k for k in lists if k not in present]
    if ml:
        findings.append(finding("FM-LIST-MISSING", "warn", rel,
            "list key(s) absent: %s — SCHEMA.md § 2.1 requires them to EXIST, empty as "
            "`[]`, so a reader can tell 'none' from 'never looked'" % ", ".join(ml),
            autofix=True,
            derived={"fields": ml, "values": {k: "[]" for k in ml}}, **kw))
    mi = [k for k in ints if k not in present]
    if mi:
        findings.append(finding("FM-COUNT-MISSING", "warn", rel,
            "count key(s) absent: %s — these must exist as integers, `0` being a real "
            "value (SCHEMA.md § 2.1)" % ", ".join(mi),
            autofix=True,
            derived={"fields": mi, "values": {k: "0" for k in mi}}, **kw))


def markers_in(text):
    """Every provenance marker in a blob, by kind. SCHEMA.md § 7.1."""
    return {
        "loc": LOC_RE.findall(text),
        "unloc": UNLOC_RE.findall(text),
        "link": LINK_RE.findall(text),
        "infer": INFER_RE.findall(text),
        "verify": VERIFY_RE.findall(text),
    }


def clean_body(body):
    return "\n".join(l for _n, l, f in iter_body_lines(body) if not f)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover(root):
    """One walk. Returns (topic_pages, doc_pages, capture_pages, strays, rel_index)."""
    topics, docs, caps, strays = [], [], [], []
    rel_index = set()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.lower().endswith(".md"):
                rel_index.add(rel_posix(os.path.join(dirpath, name), root))

    tdir = os.path.join(root, "topics")
    if not os.path.isdir(tdir):
        return topics, docs, caps, strays, rel_index

    for dirpath, dirnames, filenames in os.walk(tdir):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        relpath = rel_posix(dirpath, tdir)
        base = os.path.basename(dirpath)
        for name in sorted(filenames):
            if not name.lower().endswith(".md"):
                continue
            full = os.path.join(dirpath, name)
            if name == "topic.md" and base not in ("documents", "captures"):
                topics.append((relpath if relpath != "." else "", full))
            elif base == "documents":
                docs.append((os.path.dirname(relpath).replace("\\", "/"), full))
            elif base == "captures":
                caps.append((os.path.dirname(relpath).replace("\\", "/"), full))
            elif name.lower() not in NON_PAGE_FILES:
                strays.append(full)
    return topics, docs, caps, strays, rel_index


def load_link_plans(root):
    """
    Every `output/_linkplan-*.json`, keyed by doc_slug, with a normalized URL set.

    This is the authorization surface for the depth-1 audit. An absent plan directory is
    reported once rather than per capture, because "nobody has ingested yet" and "every
    capture is unauthorized" are very different situations.
    """
    plans, out = {}, os.path.join(root, "output")
    if not os.path.isdir(out):
        return plans
    for name in sorted(os.listdir(out)):
        if not (name.startswith("_linkplan-") and name.endswith(".json")):
            continue
        try:
            with open(os.path.join(out, name), "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        urls = {normalize_url(e.get("url")) for e in (data.get("authorized") or [])}
        entry = {"file": "output/" + name, "urls": urls, "authorized": len(urls),
                 "declined": len(data.get("declined") or []),
                 "max_depth": data.get("max_depth")}
        # Index under BOTH keys. `extract-pdf.py` derives `doc_slug` from the SOURCE
        # FILENAME, which is rarely the document's title slug — `cai.pdf` yields "cai"
        # while the page lands at `constitutional-ai-...`. Keying on doc_slug alone made
        # every capture look unaudited, so the filename suffix is indexed too and the
        # caller may match on either.
        for key in {data.get("doc_slug"), name[len("_linkplan-"):-len(".json")]}:
            if key:
                plans[key] = entry
    return plans


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def build_report(root, cfg, taxonomy, today):
    findings = []
    topic_pages, doc_pages, cap_pages, strays, rel_index = discover(root)
    plans = load_link_plans(root)

    for name in ("SCHEMA.md", "index.md", "log.md"):
        if not os.path.isfile(os.path.join(root, name)):
            findings.append(finding(
                "STR-ROOT-MISSING", "error" if name == "SCHEMA.md" else "warn", name,
                "`%s` absent from the library root — %s" % (name,
                    "the page contract is unavailable; run /ai-lib-setup"
                    if name == "SCHEMA.md" else
                    "run /ai-lib-lint to regenerate it" if name == "index.md" else
                    "every skill appends here; create it empty")))
    if not taxonomy:
        findings.append(finding(
            "STR-NO-TAXONOMY", "error", "_config/taxonomy.md",
            "no parseable ```taxonomy block — without it there is no way to tell a real "
            "topic from an invented one, so no placement can be validated. Run "
            "/ai-lib-setup to restore it"))
    if not plans and doc_pages:
        findings.append(finding(
            "CAP-NO-PLANS", "warn", "output/",
            "%d document(s) but no `output/_linkplan-*.json` — the depth-1 audit "
            "(SCHEMA.md § 6.2) cannot run without link plans, so every capture is "
            "unverifiable. Re-run extract-pdf.py for each document to regenerate them"
            % len(doc_pages)))

    for path in strays:
        findings.append(finding("STR-STRAY-FILE", "warn", rel_posix(path, root),
            "markdown file inside `topics/` that is neither `topic.md`, "
            "`documents/*.md` nor `captures/*.md` — consumers read those three locations "
            "and nothing else, so this file's content is invisible"))

    # ---- topics ----------------------------------------------------------
    topics_out, seen_topics = [], {}
    for tpath, path in topic_pages:
        rel = rel_posix(path, root)
        text = read_text(path) or ""
        fm, present, raw, body = split_frontmatter(text)
        secs = split_h2(body)
        declared = fm.get("topic", tpath)
        node = taxonomy.get(tpath, {}).get("node_type") or fm.get("node_type", "leaf")

        if taxonomy and tpath not in taxonomy:
            findings.append(finding("TAX-UNDEFINED-TOPIC", "error", rel,
                "topic folder `%s` is not defined in `_config/taxonomy.md`. Adding a "
                "topic is a deliberate edit to the taxonomy, never a side effect of an "
                "ingest (SCHEMA.md § 1.1)" % tpath, topic=tpath))
        if declared and declared != tpath:
            findings.append(finding("FM-TOPIC-MISMATCH", "error", rel,
                "`topic: %s` disagrees with the folder `%s` — the folder is the identity"
                % (declared, tpath), autofix=True, derived={"topic": tpath},
                topic=tpath, field="topic"))
        if fm.get("node_type") and taxonomy.get(tpath) and \
                fm["node_type"] != taxonomy[tpath]["node_type"]:
            findings.append(finding("FM-NODE-TYPE", "error", rel,
                "`node_type: %s` but the taxonomy says `%s`"
                % (fm["node_type"], taxonomy[tpath]["node_type"]),
                autofix=True, derived={"node_type": taxonomy[tpath]["node_type"]},
                topic=tpath, field="node_type"))

        check_required(rel, present, findings, REQUIRED_TOPIC, [], [],
                       {"topic": tpath, "category": "topic", "node_type": node,
                        "status": "active", "updated_by": "ai-lib-lint",
                        "title": TOPIC_TITLES.get(
                            tpath, tpath.rsplit("/", 1)[-1].replace("-", " ").title())},
                       topic=tpath)
        check_enums(rel, fm, findings, topic=tpath)
        check_formats(rel, fm, raw, present, findings, topic=tpath)
        check_sections(rel, secs, TOPIC_SECTIONS, findings, topic=tpath)

        wb = section_body(secs, "What Belongs Here")
        if wb is None or is_placeholder(wb["lines"]):
            findings.append(finding("TOP-NO-BOUNDARY", "warn", rel,
                "`## What Belongs Here` is empty. This is what a subagent reads to decide "
                "whether a borderline document is theirs; a leaf whose boundary was never "
                "stated is a leaf whose subagent cannot do its job", topic=tpath))
        seen_topics[tpath] = rel
        topics_out.append({"topic": tpath, "page": rel, "fm": fm, "node_type": node,
                           "title": fm.get("title") or TOPIC_TITLES.get(tpath, tpath)})

    for tpath, meta in (taxonomy or {}).items():
        if tpath not in seen_topics:
            findings.append(finding("TAX-MISSING-TOPIC", "warn",
                "topics/%s/topic.md" % tpath,
                "the taxonomy defines `%s` but no `topic.md` exists for it. "
                "/ai-lib-setup scaffolds every node; a missing one means a leaf nobody "
                "can be assigned" % tpath, topic=tpath))

    # ---- documents -------------------------------------------------------
    docs_out, seen_ids, docs_by_topic = [], {}, {}
    for tpath, path in doc_pages:
        rel = rel_posix(path, root)
        fn = os.path.basename(path)
        slug = fn[:-3]
        text = read_text(path)
        if text is None:
            findings.append(finding("STR-UNREADABLE", "error", rel,
                "page could not be read as UTF-8", topic=tpath))
            continue
        fm, present, raw, body = split_frontmatter(text)
        secs = split_h2(body)
        expected_id = "%s__%s" % (tpath.replace("/", "-"), slug)
        doc_id = fm.get("doc_id") or expected_id
        kw = {"topic": tpath, "doc_id": doc_id}

        if not SLUG_RE.match(slug):
            findings.append(finding("STR-BAD-SLUG", "warn", rel,
                "document filename is not kebab-case (SCHEMA.md § 1.3)", **kw))
        if taxonomy and tpath not in taxonomy:
            findings.append(finding("TAX-UNDEFINED-TOPIC", "error", rel,
                "document filed at `%s`, which the taxonomy does not define" % tpath, **kw))
        elif taxonomy.get(tpath, {}).get("node_type") == "branch":
            kids = sorted(p for p in taxonomy if p.startswith(tpath + "/"))
            findings.append(finding("TAX-DOC-ON-BRANCH", "error", rel,
                "`%s` is a BRANCH topic and may hold no documents (SCHEMA.md § 1.1). "
                "Move this into one of its leaves: %s" % (tpath, ", ".join(kids)), **kw))

        derived = {"title": fm.get("title") or slug.replace("-", " ").title(),
                   "doc_id": '"%s"' % expected_id, "topic": tpath,
                   "status": "active", "updated_by": "ai-lib-lint",
                   "extraction_confidence": "low", "source_type": "pdf",
                   "publication_type": "other", "authority": "secondary"}
        mt = os.path.getmtime(path) if os.path.exists(path) else None
        if mt:
            derived["last_updated"] = datetime.date.fromtimestamp(mt).isoformat()
            derived["created"] = derived["last_updated"]
            derived["retrieved"] = derived["last_updated"]

        check_required(rel, present, findings, REQUIRED_DOC, REQUIRED_DOC_LISTS,
                       REQUIRED_DOC_INTS, derived, **kw)
        check_enums(rel, fm, findings, **kw)
        check_formats(rel, fm, raw, present, findings, **kw)
        check_sections(rel, secs, DOC_SECTIONS, findings, **kw)

        if fm.get("doc_id") and fm["doc_id"] != expected_id:
            findings.append(finding("FM-DOC-ID-MISMATCH", "error", rel,
                "`doc_id: %s` does not match `<topic-hyphenated>__<file-slug>` = `%s`. "
                "`doc_id` is the join key for every answer and synthesis page; a mismatch "
                "silently orphans this document from anything that cites it"
                % (fm["doc_id"], expected_id),
                autofix=True, derived={"doc_id": '"%s"' % expected_id},
                field="doc_id", **kw))
        if fm.get("topic") and fm["topic"] != tpath:
            findings.append(finding("FM-TOPIC-MISMATCH", "error", rel,
                "`topic: %s` disagrees with the folder `%s`" % (fm["topic"], tpath),
                autofix=True, derived={"topic": tpath}, field="topic", **kw))
        if doc_id in seen_ids:
            findings.append(finding("FM-DUP-DOC-ID", "error", rel,
                "`doc_id: %s` is already used by `%s` — the join key must be globally "
                "unique" % (doc_id, seen_ids[doc_id]), field="doc_id", **kw))
        else:
            seen_ids[doc_id] = rel

        cbody = clean_body(body)
        pages_declared = as_int(fm.get("pages"))

        # ---- THE CLAIM AUDIT: every claim carries a marker (SCHEMA.md § 7.1) ----
        claims, unmarked, bad_type, bad_page, linked_in_claims = [], [], [], [], []
        kc = section_body(secs, "Key Claims")
        numbers = []
        if kc and not is_placeholder(kc["lines"]):
            for lineno, line in kc["lines"]:
                m = CLAIM_LINE_RE.match(line)
                if not m:
                    continue
                numbers.append(as_int(m.group(1)))
                body_txt = m.group(2)
                claims.append({"n": as_int(m.group(1)), "text": body_txt, "line": lineno})
                mk = markers_in(body_txt)
                if not (mk["loc"] or mk["unloc"] or mk["link"] or mk["infer"]):
                    unmarked.append((lineno, body_txt[:90]))
                if mk["link"]:
                    linked_in_claims.append((lineno, body_txt[:90]))
                t = CLAIM_TYPE_RE.search(body_txt)
                if not t:
                    bad_type.append((lineno, "no [type: ...]"))
                elif t.group(1).lower() not in CLAIM_TYPES:
                    bad_type.append((lineno, "[type: %s] not in vocabulary" % t.group(1)))
                for pm in PAGE_NUM_RE.finditer(body_txt):
                    pn = as_int(pm.group(1))
                    if pages_declared and pn and pn > pages_declared:
                        bad_page.append((lineno, pn))

        for lineno, snippet in unmarked:
            findings.append(finding("CLM-UNMARKED", "error", rel,
                "claim with no provenance marker: \"%s\". Every claim carries one of "
                "`[p. N]`, `[unlocated]`, `[link: ...]` or `[inference: ...]` "
                "(SCHEMA.md § 7.1). An unmarked claim is indistinguishable from a "
                "traceable one, which destroys the only property that makes this library "
                "worth having" % snippet, line=lineno, **kw))
        for lineno, snippet in linked_in_claims:
            findings.append(finding("CLM-LINKED-CLAIM", "error", rel,
                "`## Key Claims` contains a `[link: ...]` marker: \"%s\". Linked-page "
                "material belongs only in `## From Linked Pages` (SCHEMA.md § 6.3) — a "
                "linked claim sitting here reads as this document's own"
                % snippet, line=lineno, **kw))
        for lineno, why in bad_type:
            findings.append(finding("CLM-TYPE", "warn", rel,
                "claim %s — allowed: %s" % (why, ", ".join(CLAIM_TYPES)),
                line=lineno, **kw))
        for lineno, pn in bad_page:
            findings.append(finding("CLM-PAGE-RANGE", "error", rel,
                "locator cites p. %d but `pages: %s` — one of the two is wrong, and a "
                "locator nobody can follow is not a locator"
                % (pn, pages_declared), line=lineno, **kw))
        if numbers and numbers != list(range(1, len(numbers) + 1)):
            findings.append(finding("CLM-NUMBERING", "warn", rel,
                "`## Key Claims` numbering is %s, expected 1..%d. Do not write every "
                "line as `1.` and rely on markdown auto-numbering — it renders correctly "
                "and parses as %d claims all numbered 1 (SCHEMA.md § 3.1)"
                % (numbers, len(numbers), len(numbers)), **kw))

        # ---- the counts are not decorative (SCHEMA.md § 2.4) ----
        located = sum(1 for c in claims if markers_in(c["text"])["loc"])
        dc, dl = as_int(fm.get("claim_count")), as_int(fm.get("located_claim_count"))
        if dc is not None and dc != len(claims):
            findings.append(finding("CNT-CLAIMS", "error", rel,
                "`claim_count: %d` but `## Key Claims` holds %d. A page claiming more "
                "than it holds wastes a subagent's context every time it is retrieved"
                % (dc, len(claims)), autofix=True,
                derived={"claim_count": str(len(claims))}, field="claim_count", **kw))
        if dl is not None and dl != located:
            findings.append(finding("CNT-LOCATED", "warn", rel,
                "`located_claim_count: %d` but %d claim(s) carry a page locator"
                % (dl, located), autofix=True,
                derived={"located_claim_count": str(located)},
                field="located_claim_count", **kw))

        # Parse the evidence table, not merely count it. `build-compare.py` joins these
        # rows across documents on (benchmark, metric) — which is what makes a benchmark
        # comparison deterministic instead of an LLM re-reading prose. Counting alone was
        # not enough: the consumer needs the cells.
        ev = section_body(secs, "Evidence")
        evidence, bench_rows = [], 0
        if ev and not is_placeholder(ev["lines"]):
            for lineno, line in ev["lines"]:
                s = line.strip()
                if not s.startswith("|") or set(s) <= set("|-: "):
                    continue
                cells = [c.strip() for c in s.strip("|").split("|")]
                head = norm(cells[0]) if cells else ""
                if head in ("benchmark / eval", "benchmark", "benchmark/eval", ""):
                    continue
                bench_rows += 1
                row = {"benchmark": cells[0] if len(cells) > 0 else "",
                       "metric": cells[1] if len(cells) > 1 else "",
                       "reported": cells[2] if len(cells) > 2 else "",
                       "baseline": cells[3] if len(cells) > 3 else "",
                       "locator": cells[4] if len(cells) > 4 else "",
                       "line": lineno}
                evidence.append(row)
                if len(cells) < 5 or not row["locator"]:
                    findings.append(finding("EVI-NO-LOCATOR", "warn", rel,
                        "evidence row `%s / %s` has no locator. A number nobody can find "
                        "in the source is a number nobody can check"
                        % (row["benchmark"][:40], row["metric"][:24]),
                        line=lineno, **kw))
                if LINK_RE.search(s):
                    findings.append(finding("EVI-LINKED-NUMBER", "error", rel,
                        "evidence row carries a `[link: ...]` marker. `## Evidence` is "
                        "this document's OWN reported results; a linked page's number "
                        "belongs in `## From Linked Pages` (SCHEMA.md § 6.3)",
                        line=lineno, **kw))
        db = as_int(fm.get("benchmark_count"))
        if db is not None and db != bench_rows:
            findings.append(finding("CNT-BENCH", "warn", rel,
                "`benchmark_count: %d` but `## Evidence` holds %d data row(s)"
                % (db, bench_rows), autofix=True,
                derived={"benchmark_count": str(bench_rows)},
                field="benchmark_count", **kw))

        la, lf, ld = (as_int(fm.get("links_authorized")), as_int(fm.get("links_followed")),
                      as_int(fm.get("links_declined")))
        if None not in (la, lf, ld) and lf + ld != la:
            findings.append(finding("CNT-LINKS", "warn", rel,
                "`links_followed (%d) + links_declined (%d) = %d`, but "
                "`links_authorized` is %d. The plan enumerated exactly that many and each "
                "was either taken or deliberately passed over; a discrepancy means a link "
                "was neither, which is the state SCHEMA.md § 2.4 exists to prevent"
                % (lf, ld, lf + ld, la), **kw))

        # ---- the quarantine boundary, both directions (SCHEMA.md § 6.3) ----
        flp = section_body(secs, CAPTURE_QUARANTINE)
        if flp and not is_placeholder(flp["lines"]):
            blob = "\n".join(l for _n, l in flp["lines"])
            for lineno, line in flp["lines"]:
                if LOC_RE.search(line):
                    findings.append(finding("LNK-PAGE-LOCATOR", "error", rel,
                        "`## From Linked Pages` carries a page locator: \"%s\". A linked "
                        "page has page numbers too, and a `[p. N]` here makes a linked "
                        "claim indistinguishable from this document's own. Linked material "
                        "takes `[link: <url>, accessed <date>]` and only that "
                        "(SCHEMA.md § 6.3)" % line.strip()[:90], line=lineno, **kw))
            bullets = [(n, l) for n, l in flp["lines"]
                       if l.strip().startswith(("-", "*"))]
            for lineno, line in bullets:
                if not LINK_RE.search(line):
                    findings.append(finding("LNK-UNMARKED", "error", rel,
                        "item in `## From Linked Pages` with no `[link: ...]` marker: "
                        "\"%s\"" % line.strip()[:90], line=lineno, **kw))
            for m in LINK_RE.finditer(blob):
                if not m.group(2):
                    findings.append(finding("LNK-NO-DATE", "warn", rel,
                        "`[link: %s]` has no access date. A web page changes and an "
                        "undated claim from one cannot be re-verified"
                        % m.group(1).strip()[:60], **kw))
                    break

        for s in secs:
            if norm(s["text"]) in (norm(CAPTURE_QUARANTINE), norm(OPEN_SECTION)):
                continue
            for lineno, line in s["lines"]:
                if LINK_RE.search(line):
                    findings.append(finding("LNK-OUTSIDE-QUARANTINE", "error", rel,
                        "`[link: ...]` marker in `## %s`. Depth-1 linked material lives "
                        "only in `## From Linked Pages` (SCHEMA.md § 6.3) — this is the "
                        "specific failure the quarantine exists to prevent"
                        % s["text"], line=lineno, **kw))
                    break

        # ---- provenance and hygiene ----
        if not (LOC_RE.search(cbody) or UNLOC_RE.search(cbody)):
            findings.append(finding("PROV-NO-LOCATOR", "error", rel,
                "no page locator anywhere in the body. Nothing on this page can be traced "
                "to the document it came from", **kw))
        for m in VERIFY_RE.finditer(cbody):
            findings.append(finding("PROV-VERIFY", "info", rel,
                "open `[verify: %s]` — a known weakness a human must resolve; nothing "
                "auto-clears it" % m.group(1).strip()[:100], **kw))
        for m in WIKILINK_RE.finditer(cbody):
            findings.append(finding("XREF-WIKILINK", "warn", rel,
                "`[[%s]]` uses retired wikilink syntax — document titles collide "
                "constantly, so the `doc_id` is the identity (SCHEMA.md § 7.2)"
                % m.group(1)[:60], **kw))
            break
        if CONTRADICTION in cbody:
            findings.append(finding("PROV-CONTRADICTION-OPEN", "warn", rel,
                "page carries an unresolved `**CONTRADICTION:**` marker — /ai-lib-lint "
                "never picks a winner, so this stays until a human decides", **kw))

        for ref in (fm.get("builds_on") or []) + (fm.get("supersedes") or []) \
                + (fm.get("superseded_by") or []):
            if ref and ref not in ("", "[]"):
                findings.append({"_pending_xref": ref, "page": rel, "kw": dict(kw)})

        conf = fm.get("extraction_confidence")
        min_hi = cfg_int(cfg, "min_claims_for_high_confidence", 3)
        if conf == "high":
            if located < len(claims):
                findings.append(finding("CONF-HIGH-UNLOCATED", "warn", rel,
                    "`extraction_confidence: high` but %d of %d claim(s) lack a page "
                    "locator. SCHEMA.md § 2.2 reserves `high` for a read where every "
                    "claim is located" % (len(claims) - located, len(claims)),
                    field="extraction_confidence", **kw))
            elif len(claims) < min_hi:
                findings.append(finding("CONF-HIGH-THIN", "info", rel,
                    "`extraction_confidence: high` on only %d claim(s) — below the "
                    "`min_claims_for_high_confidence` of %d" % (len(claims), min_hi),
                    field="extraction_confidence", **kw))

        pub = fm.get("published")
        limit = stale_days_for(tpath, cfg)
        age = days_between(today.isoformat(), pub) if pub else None
        if age is not None and age > limit and fm.get("status") == "active":
            findings.append(finding("AGE-STALE", "info", rel,
                "`published: %s` is %d days old; the threshold for `%s` is %d. Not a "
                "defect — but /ai-lib-query must say so when it answers from this page, "
                "and it is worth checking whether something replaced it"
                % (pub, age, tpath, limit), **kw))

        thin = [s["text"] for s in secs
                if norm(s["text"]) != norm(OPEN_SECTION) and is_placeholder(s["lines"])]
        if len(thin) >= len(DOC_SECTIONS) - 2:
            findings.append(finding("SEC-STUB", "info", rel,
                "every section is still a placeholder — a scaffolded page nobody has read "
                "into yet. Distinct from stale: this page never had content", **kw))

        docs_out.append({
            "doc_id": doc_id, "topic": tpath, "slug": slug, "page": rel,
            "page_rel_topic": "documents/%s" % fn,
            "title": fm.get("title") or slug.replace("-", " ").title(),
            "fm": fm, "sections": [s["text"] for s in secs],
            "claims": claims, "claim_count_actual": len(claims),
            "located_actual": located, "benchmark_rows": bench_rows,
            "evidence": evidence,
            "unmarked_claims": len(unmarked),
            "snapshot": "\n".join(l for _n, l in (section_body(secs, "Snapshot") or
                                                  {"lines": []})["lines"]).strip(),
            "is_stub": len(thin) >= len(DOC_SECTIONS) - 2,
            "stale": bool(age is not None and age > limit),
            "age_days": age,
        })
        docs_by_topic.setdefault(tpath, []).append(docs_out[-1])

    # resolve the deferred cross-reference checks now that every doc_id is known
    pending = [f for f in findings if "_pending_xref" in f]
    findings = [f for f in findings if "_pending_xref" not in f]
    for p in pending:
        if p["_pending_xref"] not in seen_ids:
            findings.append(finding("XREF-UNKNOWN-DOC", "warn", p["page"],
                "references `%s`, which is not a doc_id in this library. Either it was "
                "retyped rather than copied, or the document was moved and this reference "
                "was not updated" % p["_pending_xref"], **p["kw"]))

    # ---- captures: THE DEPTH-1 AUDIT --------------------------------------
    caps_out, caps_by_doc = [], {}
    for tpath, path in cap_pages:
        rel = rel_posix(path, root)
        text = read_text(path) or ""
        fm, present, raw, body = split_frontmatter(text)
        secs = split_h2(body)
        parent = fm.get("parent_doc", "")
        kw = {"topic": tpath, "doc_id": parent}

        check_required(rel, present, findings, REQUIRED_CAPTURE, [], [],
                       {"category": "capture", "topic": tpath, "depth": "1",
                        "status": "active", "updated_by": "ai-lib-lint",
                        "fetch_status": "ok", "link_class": "other"}, **kw)
        check_enums(rel, fm, findings, **kw)
        check_formats(rel, fm, raw, present, findings, **kw)
        check_sections(rel, secs, CAPTURE_SECTIONS, findings, **kw)

        depth = as_int(fm.get("depth"))
        if depth != 1:
            findings.append(finding("CAP-DEPTH", "error", rel,
                "`depth: %s` — `1` is the only legal value in this contract "
                "(SCHEMA.md § 6.2). A capture at any other depth is a second hop, which "
                "this library does not take" % fm.get("depth"),
                autofix=(depth is not None), derived={"depth": "1"},
                field="depth", **kw))
        if parent and parent not in seen_ids:
            findings.append(finding("CAP-ORPHAN", "error", rel,
                "`parent_doc: %s` is not a doc_id in this library. A capture with no "
                "parent cannot be audited against a link plan, which is the whole point "
                "of it" % parent, field="parent_doc", **kw))

        url = fm.get("source_url", "")
        nurl = normalize_url(url)
        slug = parent.split("__", 1)[-1] if parent else ""
        plan = plans.get(slug)
        if not url:
            findings.append(finding("CAP-NO-URL", "error", rel,
                "no `source_url` — nothing to audit and nothing to retrace",
                field="source_url", **kw))
        elif plan is None:
            if plans:
                findings.append(finding("CAP-NO-PLAN", "warn", rel,
                    "no `output/_linkplan-%s.json` for parent `%s`, so this capture "
                    "cannot be checked against an authorization. Re-run extract-pdf.py "
                    "for that document" % (slug, parent), **kw))
        elif nurl not in plan["urls"]:
            findings.append(finding("CAP-UNAUTHORIZED", "error", rel,
                "`source_url: %s` is NOT in the parent's authorized link plan (%s, %d "
                "URLs). This is the signature of a second-hop fetch: a URL found ON a "
                "page that was itself fetched. The one-hop limit is audited here because "
                "it cannot be enforced at fetch time (SCHEMA.md § 6.2). Either this was "
                "an unauthorized fetch, or the URL was added to the plan without being "
                "recorded" % (url[:90], plan["file"], plan["authorized"]),
                field="source_url", **kw))

        nt = section_body(secs, "Not taken")
        if nt is not None and is_placeholder(nt["lines"]) and fm.get("fetch_status") == "ok":
            findings.append(finding("CAP-NO-DECLINED", "info", rel,
                "`## Not taken` is empty on a successfully fetched page. Almost every "
                "real page has outbound links; an empty list is usually a page nobody "
                "looked at, and it is the audit trail proving second-depth links were "
                "seen and declined rather than never noticed (SCHEMA.md § 6.2)", **kw))

        wt = section_body(secs, "What was taken")
        if wt and not is_placeholder(wt["lines"]):
            for lineno, line in wt["lines"]:
                if line.strip().startswith(("-", "*")) and "From Linked Pages" not in line:
                    findings.append(finding("CAP-WRONG-DESTINATION", "error", rel,
                        "`## What was taken` names a destination other than "
                        "`## From Linked Pages`: \"%s\". That is the only legal "
                        "destination for linked material, and any other means the "
                        "quarantine has been breached (SCHEMA.md § 5)"
                        % line.strip()[:90], line=lineno, **kw))
                    break

        if plan is None:
            audit = "unaudited"          # no plan exists: the audit could not run
        elif nurl in plan["urls"]:
            audit = "authorized"         # in the plan: a legitimate depth-1 fetch
        else:
            audit = "unauthorized"       # plan exists and this URL is not in it
        caps_out.append({"page": rel, "topic": tpath, "parent_doc": parent,
                         "source_url": url, "url_domain": fm.get("url_domain", ""),
                         "link_class": fm.get("link_class", ""),
                         "fetch_status": fm.get("fetch_status", ""),
                         "accessed": fm.get("accessed", ""), "depth": depth,
                         "audit": audit,
                         "authorized": audit == "authorized"})
        caps_by_doc.setdefault(parent, []).append(caps_out[-1])

    # ---- topic roster mirror + counts ------------------------------------
    for t in topics_out:
        tpath, rel = t["topic"], t["page"]
        mine = docs_by_topic.get(tpath, [])
        declared = as_int(t["fm"].get("document_count"))
        if declared is not None and declared != len(mine):
            findings.append(finding("MIR-DOC-COUNT", "error", rel,
                "`document_count: %d` but `documents/` holds %d page(s)"
                % (declared, len(mine)), autofix=True,
                derived={"document_count": str(len(mine))},
                topic=tpath, field="document_count"))
        if t["node_type"] == "branch" and mine:
            findings.append(finding("TAX-DOC-ON-BRANCH", "error", rel,
                "branch topic holds %d document(s); a branch holds `topic.md` and nothing "
                "else (SCHEMA.md § 1.1)" % len(mine), topic=tpath))
        if t["node_type"] == "leaf" and not mine:
            findings.append(finding("TOP-EMPTY-LEAF", "info", rel,
                "leaf topic holds no documents — nothing about it can be listed, queried "
                "or compared. Normal for a new library", topic=tpath))

        themes = section_body(split_h2(read_text(os.path.join(root, rel)) or ""), "Themes")
        min_docs = cfg_int(cfg, "theme_min_documents", 2)
        if themes and not is_placeholder(themes["lines"]):
            for lineno, line in themes["lines"]:
                if line.strip().startswith(("-", "*")):
                    cited = len(re.findall(r"`[a-z0-9-]+__[a-z0-9-]+`", line))
                    if cited < min_docs:
                        findings.append(finding("TOP-THIN-THEME", "warn", rel,
                            "theme bullet cites %d doc_id(s), needs %d: \"%s\". A theme "
                            "supported by one document is that document's claim, not a "
                            "theme" % (cited, min_docs, line.strip()[:80]),
                            line=lineno, topic=tpath))

    # ---- share drift ------------------------------------------------------
    total_docs = len(docs_out)
    shares = {}
    if total_docs:
        thresh = cfg_float(cfg, "drift_report_threshold", 0.15)
        for top in sorted({p.split("/")[0] for p in (taxonomy or {})}):
            n = sum(1 for d in docs_out if d["topic"].split("/")[0] == top)
            actual = n / float(total_docs)
            key = "share_" + top.replace("-", "_")
            expected = cfg_float(cfg, key, None) if key in cfg else None
            if expected is None:
                e = (taxonomy.get(top) or {}).get("expected_share", "-")
                expected = None if e in ("-", "") else cfg_float({"x": e}, "x", None)
            shares[top] = {"documents": n, "actual": round(actual, 3),
                           "expected": expected}
            if expected and abs(actual - expected) >= thresh:
                findings.append(finding("SHARE-DRIFT", "info", "index.md",
                    "`%s` holds %d of %d documents (%.0f%%), expected ~%.0f%%. Drift is "
                    "information, not an error — a topic near zero usually means its "
                    "material is being filed somewhere else"
                    % (top, n, total_docs, actual * 100, expected * 100), topic=top))

    by_sev, by_rule = {"error": 0, "warn": 0, "info": 0}, {}
    for f in findings:
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
        by_rule[f["rule"]] = by_rule.get(f["rule"], 0) + 1

    return {
        "schema": SCHEMA_VERSION,
        "generated": today.isoformat(),
        "library_root": os.path.abspath(root),
        "library_name": cfg.get("library_name") or os.path.basename(os.path.abspath(root)),
        "config": cfg,
        "taxonomy": taxonomy,
        "topics": topics_out,
        "documents": docs_out,
        "captures": caps_out,
        "link_plans": {k: {"file": v["file"], "authorized": v["authorized"],
                           "declined": v["declined"], "max_depth": v["max_depth"]}
                       for k, v in plans.items()},
        "shares": shares,
        "findings": findings,
        "counts": {
            "topics": len(topics_out),
            "leaves": sum(1 for t in topics_out if t["node_type"] == "leaf"),
            "documents": total_docs,
            "documents_active": sum(1 for d in docs_out
                                    if d["fm"].get("status", "active") == "active"),
            "documents_stub": sum(1 for d in docs_out if d["is_stub"]),
            "documents_stale": sum(1 for d in docs_out if d["stale"]),
            "captures": len(caps_out),
            "captures_authorized": sum(1 for c in caps_out
                                       if c["audit"] == "authorized"),
            "captures_unauthorized": sum(1 for c in caps_out
                                         if c["audit"] == "unauthorized"),
            "captures_unaudited": sum(1 for c in caps_out if c["audit"] == "unaudited"),
            "claims_total": sum(d["claim_count_actual"] for d in docs_out),
            "claims_located": sum(d["located_actual"] for d in docs_out),
            "claims_unmarked": sum(d["unmarked_claims"] for d in docs_out),
            "link_plans": len(plans),
            "findings": len(findings),
            "by_severity": by_sev,
            "by_rule": by_rule,
            "autofixable": sum(1 for f in findings if f["autofix"]),
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Scan an ai-lib library; emit inventory + findings as json.")
    ap.add_argument("--library", default=".", help="library root (holds SCHEMA.md)")
    ap.add_argument("--out", help="write json here; omit to print to stdout")
    ap.add_argument("--date", help="YYYY-MM-DD; pin 'today' for reproducible runs")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.library):
        sys.stderr.write("ERROR: library directory not found: %s\n"
                         "Nothing has been scaffolded here. Run /ai-lib-setup first.\n"
                         % args.library)
        return 1
    if not os.path.isfile(os.path.join(args.library, "SCHEMA.md")) \
            and not os.path.isdir(os.path.join(args.library, "topics")):
        sys.stderr.write(
            "ERROR: %s has neither SCHEMA.md nor topics/ — this is not an ai-lib library.\n"
            "Run /ai-lib-setup to scaffold one, or point --library at the right root.\n"
            % args.library)
        return 1
    try:
        today = (datetime.date.fromisoformat(args.date) if args.date
                 else datetime.date.today())
    except ValueError:
        sys.stderr.write("ERROR: --date must be YYYY-MM-DD, got %r\n" % args.date)
        return 1

    cfg = load_config(args.library)
    report = build_report(args.library, cfg, load_taxonomy(args.library), today)
    payload = json.dumps(report, indent=2, ensure_ascii=False)

    if args.out:
        try:
            d = os.path.dirname(os.path.abspath(args.out))
            if d:
                os.makedirs(d, exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(payload + "\n")
            c = report["counts"]
            sys.stderr.write(
                "wrote %s (%d topics / %d leaves, %d documents, %d captures"
                "%s, %d claims of which %d located%s; %d findings: %d error / %d warn / "
                "%d info, %d autofixable)\n"
                % (args.out, c["topics"], c["leaves"], c["documents"], c["captures"],
                   ((" — %d UNAUTHORIZED" % c["captures_unauthorized"])
                    if c["captures_unauthorized"] else "")
                   + ((" — %d unaudited" % c["captures_unaudited"])
                      if c["captures_unaudited"] else ""),
                   c["claims_total"], c["claims_located"],
                   (" — %d UNMARKED" % c["claims_unmarked"]) if c["claims_unmarked"] else "",
                   c["findings"], c["by_severity"].get("error", 0),
                   c["by_severity"].get("warn", 0), c["by_severity"].get("info", 0),
                   c["autofixable"]))
        except OSError as exc:
            sys.stderr.write("WARNING: cannot write --out %r: %s\n" % (args.out, exc))
            sys.stdout.write(payload + "\n")
    else:
        sys.stdout.write(payload + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
