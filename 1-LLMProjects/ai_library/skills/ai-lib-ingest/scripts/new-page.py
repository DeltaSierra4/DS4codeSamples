#!/usr/bin/env python3
"""
new-page.py — emit a schema-conformant skeleton for a document, topic or capture page.

`/ai-lib-ingest` uses this so the SHAPE of a page is never retyped from memory. The agent
supplies the facts; this script guarantees every required key exists, the ten sections are
present in contract order, `doc_id` agrees with the path, and the taxonomy path is real.

THREE THINGS IT REFUSES TO DO, each for a reason:

  * It will not write a document into a path the taxonomy does not define, or into a
    BRANCH topic. `_config/taxonomy.md` is the authority (SCHEMA.md § 1.1) and a document
    filed at an invented path is invisible to the subagent that should own it.

  * It will not overwrite an existing page. Exit 3, with the path. An existing page is
    updated under the resolution policy (SCHEMA.md § 8.2), by reading it first — never by
    regenerating it from a partial fact set, which is how a page loses every field the
    current source happens not to mention.

  * It will not invent a `[p. N]`. Sections come out holding `_None recorded._`, and the
    counts come out at 0. A skeleton that guessed at claims would be indistinguishable
    from a page someone actually read.

There is deliberately NO `TBD` sentinel in this contract. A document either has a DOI or
it does not; an absent optional key is a fact about the document, not a knowledge gap.
Knowledge gaps go in `## Open Questions` with a `[verify: ...]` marker.

Stdlib only.

Invocation:
    python3 new-page.py document --library . --topic ai \
        --title "Constitutional AI — Harmlessness from AI Feedback" \
        --set publication_type=paper --set authority=preprint \
        --set publisher=Anthropic --set published=2022-12-15 \
        --source-file constitutional-ai.pdf --source-type pdf \
        --set 'tags=[rlhf, alignment]' --links-authorized 11

    python3 new-page.py topic --library . --topic llm/claude --title Claude
    python3 new-page.py capture --library . --topic ai \
        --parent-doc "ai__constitutional-ai-harmlessness-from-ai-feedback" \
        --title "Training a Helpful and Harmless Assistant" \
        --set source_url=https://arxiv.org/abs/2204.05862 --set link_class=preprint

    python3 new-page.py document ... --print      # to stdout, write nothing

Exit codes:
    0  page written (or printed)
    1  hard error — bad arguments, unknown key, undefined or non-leaf topic, unwritable
    3  the page already exists; read it and update it instead
"""

import argparse
import datetime
import json
import os
import re
import sys
import tempfile

DOC_SECTIONS = [
    "Snapshot", "Problem & Context", "Method", "Key Claims", "Evidence",
    "Limitations", "Connections", "Open Questions", "From Linked Pages",
    "Additional capture",
]
TOPIC_SECTIONS = [
    "Snapshot", "What Belongs Here", "Key Documents", "Themes", "Gaps",
    "Additional capture",
]
CAPTURE_SECTIONS = ["Metadata", "What was taken", "Not taken"]

PLACEHOLDER = "_None recorded._"

DOC_KEY_ORDER = [
    "title", "doc_id", "aka", "topic", "publication_type", "authority", "publisher",
    "authors", "published", "year", "venue", "doi", "arxiv_id", "url", "version",
    "pages", "models", "tags",
    "contribution_type", "maturity", "reproducibility", "supersedes", "superseded_by",
    "claim_count", "located_claim_count", "benchmark_count", "has_limitations",
    "links_authorized", "links_followed", "links_declined",
    "builds_on", "related",
    "source_file", "source_type", "retrieved", "created", "last_updated",
    "updated_by", "extraction_confidence", "status",
]
TOPIC_KEY_ORDER = [
    "title", "topic", "category", "node_type", "parent", "document_count",
    "expected_share", "created", "last_updated", "updated_by", "status",
]
CAPTURE_KEY_ORDER = [
    "title", "category", "topic", "parent_doc", "source_url", "url_domain",
    "link_class", "depth", "accessed", "fetch_status", "authority",
    "created", "last_updated", "updated_by", "status",
]
ALL_KNOWN = set(DOC_KEY_ORDER) | set(TOPIC_KEY_ORDER) | set(CAPTURE_KEY_ORDER)

LIST_KEYS = {"aka", "authors", "models", "tags", "contribution_type", "supersedes",
             "superseded_by", "builds_on", "related"}
QUOTED_KEYS = {"doc_id", "parent_doc", "doi", "arxiv_id", "url", "source_url",
               "carrier_plan_code"}
INT_KEYS = {"pages", "claim_count", "located_claim_count", "benchmark_count",
            "links_authorized", "links_followed", "links_declined",
            "document_count", "depth", "year"}

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
}


# Display names for topic slugs whose title-cased form reads badly. `ai` -> "Ai" and
# `llm/gpt` -> "Gpt" appear in index.md, every HTML deliverable and every subagent brief,
# so the acronyms are worth spelling out once here.
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


def topic_title(topic):
    """A readable name for a topic path, falling back to a title-cased slug."""
    return TOPIC_TITLES.get(topic, topic.rsplit("/", 1)[-1].replace("-", " ").title())


def slugify(text, limit=60):
    """Kebab-case, truncated at a word boundary. SCHEMA.md § 1.3."""
    s = str(text or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if len(s) <= limit:
        return s
    cut = s[:limit]
    return (cut.rsplit("-", 1)[0] if "-" in cut else cut).strip("-")


def load_taxonomy(library):
    """
    Parse the fenced ```taxonomy block in _config/taxonomy.md.

    Returns {path: node_type}. An unreadable or absent taxonomy returns {} and the caller
    must then REFUSE to place a document — guessing a path here would defeat the one
    check that keeps documents findable by the subagent that owns them.
    """
    path = os.path.join(library, "_config", "taxonomy.md")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return {}
    m = re.search(r"```taxonomy\s*\n(.*?)```", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2 or not parts[0]:
            continue
        out[parts[0]] = parts[1]
    return out


def topic_to_id_prefix(topic):
    """`llm/claude` -> `llm-claude`. The doc_id prefix (SCHEMA.md § 2.2)."""
    return topic.replace("/", "-")


def quote_list_item(item):
    s = str(item).strip()
    if s.startswith(('"', "'")):
        return s
    if re.search(r"^\w+://|[:#,\[\]{}]|^\s|\s$", s):
        return '"%s"' % s.replace('"', '\\"')
    return s


def fmt_value(key, value):
    if isinstance(value, list):
        return "[%s]" % ", ".join(quote_list_item(v) for v in value)
    s = str(value)
    if key in LIST_KEYS:
        inner = [p.strip() for p in s.strip("[]").split(",") if p.strip()]
        return "[%s]" % ", ".join(quote_list_item(x) for x in inner)
    if key in INT_KEYS:
        return s
    if key in QUOTED_KEYS and not (s.startswith('"') or s.startswith("'")):
        return '"%s"' % s
    return s


def frontmatter(order, values):
    lines = ["---"]
    for key in order:
        if key in values:
            lines.append("%s: %s" % (key, fmt_value(key, values[key])))
    for key in sorted(k for k in values if k not in order):
        lines.append("%s: %s" % (key, fmt_value(key, values[key])))
    lines.append("---")
    return "\n".join(lines)


def sections(names, seeded=None):
    seeded = seeded or {}
    out = []
    for name in names:
        out.append("## %s" % name)
        body = seeded.get(name)
        if body:
            out.append(body.rstrip())
        elif name == "Additional capture":
            pass
        else:
            out.append(PLACEHOLDER)
        out.append("")
    return "\n".join(out)


def atomic_write(path, text):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def parse_sets(pairs, json_path):
    values = {}
    if json_path:
        try:
            with open(json_path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            sys.stderr.write("ERROR: cannot read --json %r: %s\n" % (json_path, exc))
            return None
        if not isinstance(loaded, dict):
            sys.stderr.write("ERROR: --json must hold a flat object of key: value\n")
            return None
        values.update(loaded)
    for pair in pairs or []:
        if "=" not in pair:
            sys.stderr.write("ERROR: --set expects KEY=VALUE, got %r\n" % pair)
            return None
        k, v = pair.split("=", 1)
        values[k.strip()] = v.strip()

    unknown = [k for k in values if k not in ALL_KNOWN]
    if unknown:
        sys.stderr.write(
            "ERROR: unknown frontmatter key(s): %s\n"
            "SCHEMA.md § 2 defines the key set. A key it does not define belongs in the "
            "page body under `## Additional capture`, not in the frontmatter — an unknown "
            "key is invisible to every skill that reads this library.\n"
            % ", ".join(sorted(unknown)))
        return None

    bad = []
    for k, allowed in ENUMS.items():
        if k in values and str(values[k]) not in allowed:
            bad.append("%s=%s (allowed: %s)" % (k, values[k], ", ".join(allowed)))
    if bad:
        sys.stderr.write("ERROR: value(s) outside the controlled vocabulary:\n  %s\n"
                         % "\n  ".join(bad))
        return None
    return values


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_document(args, values, today, taxonomy):
    topic = args.topic
    slug = args.slug or slugify(args.title, args.max_slug)
    doc_id = "%s__%s" % (topic_to_id_prefix(topic), slug)

    fm = {
        "title": args.title,
        "doc_id": doc_id,
        "aka": values.get("aka", []),
        "topic": topic,
        "publication_type": values.get("publication_type", "other"),
        "authority": values.get("authority", "secondary"),
        "authors": values.get("authors", []),
        "models": values.get("models", []),
        "tags": values.get("tags", []),
        "contribution_type": values.get("contribution_type", []),
        "supersedes": values.get("supersedes", []),
        "superseded_by": values.get("superseded_by", []),
        "claim_count": values.get("claim_count", 0),
        "located_claim_count": values.get("located_claim_count", 0),
        "benchmark_count": values.get("benchmark_count", 0),
        "links_authorized": values.get("links_authorized",
                                       args.links_authorized if args.links_authorized
                                       is not None else 0),
        "links_followed": values.get("links_followed", 0),
        "links_declined": values.get("links_declined", 0),
        "builds_on": values.get("builds_on", []),
        "related": values.get("related", []),
        "source_file": values.get("source_file", args.source_file or ""),
        "source_type": values.get("source_type", args.source_type or "pdf"),
        "retrieved": values.get("retrieved", today.isoformat()),
        "created": values.get("created", today.isoformat()),
        "last_updated": values.get("last_updated", today.isoformat()),
        "updated_by": values.get("updated_by", "ai-lib-ingest"),
        "extraction_confidence": values.get("extraction_confidence", "low"),
        "status": values.get("status", "active"),
    }
    for k, v in values.items():
        if k in DOC_KEY_ORDER:
            fm[k] = v
    if "published" in fm and "year" not in fm:
        m = re.match(r"^(\d{4})", str(fm["published"]))
        if m:
            fm["year"] = m.group(1)

    byline = " · ".join(x for x in [
        fm.get("publication_type"),
        fm.get("publisher") or (", ".join(fm["authors"][:3]) if fm.get("authors") else ""),
        str(fm.get("published", "")),
        fm.get("authority"),
    ] if x)

    seeded = {}
    if fm["source_file"]:
        seeded["Snapshot"] = (
            "_Skeleton created by `/ai-lib-ingest` from %s. Awaiting the read._"
            % fm["source_file"])
    if fm["links_authorized"]:
        seeded["From Linked Pages"] = (
            "_%d link(s) authorized at depth 1 for this document; none followed yet. "
            "Every item added here carries a `[link: <url>, accessed <date>]` marker and "
            "nothing else (SCHEMA.md § 6.3)._" % fm["links_authorized"])

    doc = "\n".join([
        frontmatter(DOC_KEY_ORDER, fm), "",
        "# %s" % args.title, "",
        "_%s_" % byline if byline else "", "",
        sections(DOC_SECTIONS, seeded),
    ])
    rel = "topics/%s/documents/%s.md" % (topic, slug)
    return rel, re.sub(r"\n{3,}", "\n\n", doc).rstrip() + "\n"


def build_topic(args, values, today, taxonomy):
    topic = args.topic
    node_type = taxonomy.get(topic, values.get("node_type", "leaf"))
    parent = topic.rsplit("/", 1)[0] if "/" in topic else ""
    name = args.title or topic_title(topic)

    fm = {
        "title": name,
        "topic": topic,
        "category": "topic",
        "node_type": node_type,
        "document_count": values.get("document_count", 0),
        "created": values.get("created", today.isoformat()),
        "last_updated": values.get("last_updated", today.isoformat()),
        "updated_by": values.get("updated_by", "ai-lib-setup"),
        "status": values.get("status", "active"),
    }
    if parent:
        fm["parent"] = parent
    for k, v in values.items():
        if k in TOPIC_KEY_ORDER:
            fm[k] = v

    children = sorted(p for p in taxonomy
                      if p.startswith(topic + "/") and p.count("/") == topic.count("/") + 1)
    seeded = {}
    if node_type == "branch":
        seeded["What Belongs Here"] = "\n".join(
            ["_A branch topic: it holds no documents of its own. Its leaves are:_", ""] +
            ["- `topics/%s/`" % c for c in children])
        seeded["Key Documents"] = PLACEHOLDER
        seeded["Themes"] = PLACEHOLDER
    else:
        seeded["Key Documents"] = (
            "| Document | Type | Authority | Published | Claims | Page |\n"
            "|---|---|---|---|---|---|")
    doc = "\n".join([frontmatter(TOPIC_KEY_ORDER, fm), "", "# %s" % name, "",
                     sections(TOPIC_SECTIONS, seeded)])
    return "topics/%s/topic.md" % topic, doc.rstrip() + "\n"


def build_capture(args, values, today, taxonomy):
    url = values.get("source_url", "")
    if not url:
        sys.stderr.write("ERROR: a capture needs --set source_url=<the url fetched>\n")
        return None, None
    domain = re.sub(r"^www\.", "", re.sub(r"^\w+://([^/]+).*$", r"\1", url).lower())
    link_slug = args.slug or slugify(re.sub(r"^\w+://", "", url), 48)
    parent_slug = args.parent_doc.split("__", 1)[-1] if args.parent_doc else "unknown"

    fm = {
        "title": args.title,
        "category": "capture",
        "topic": args.topic,
        "parent_doc": args.parent_doc or "",
        "source_url": url,
        "url_domain": domain,
        "link_class": values.get("link_class", "other"),
        "depth": 1,
        "accessed": values.get("accessed", today.isoformat()),
        "fetch_status": values.get("fetch_status", "ok"),
        "authority": values.get("authority", "secondary"),
        "created": values.get("created", today.isoformat()),
        "last_updated": values.get("last_updated", today.isoformat()),
        "updated_by": values.get("updated_by", "ai-lib-ingest"),
        "status": values.get("status", "active"),
    }
    for k, v in values.items():
        if k in CAPTURE_KEY_ORDER and k != "depth":
            fm[k] = v
    fm["depth"] = 1        # contract term; not overridable (SCHEMA.md § 6.2)

    seeded = {
        "Metadata": "\n".join([
            "- URL: %s" % url,
            "- Domain: %s" % domain,
            "- Class: %s" % fm["link_class"],
            "- Accessed: %s" % fm["accessed"],
            "- Fetch status: %s" % fm["fetch_status"],
            "- Authority: %s" % fm["authority"],
            "- Title as given: %s" % args.title,
            "- What this page is: _None recorded._",
        ]),
        "What was taken": (
            "_None recorded. Every line here names its destination, which is always "
            "`## From Linked Pages` on the parent document (SCHEMA.md § 5)._"),
        "Not taken": (
            "_Every link found ON this page goes here, unfetched. An empty list on a page "
            "that plainly had links is a page nobody looked at (SCHEMA.md § 6.2)._"),
    }
    doc = "\n".join([frontmatter(CAPTURE_KEY_ORDER, fm), "", "# %s" % args.title, "",
                     sections(CAPTURE_SECTIONS, seeded)])
    rel = "topics/%s/captures/%s__%s.md" % (args.topic, parent_slug, link_slug)
    return rel, doc.rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Emit a schema-conformant document, topic or capture page skeleton.")
    ap.add_argument("kind", choices=["document", "topic", "capture"])
    ap.add_argument("--library", default=".", help="library root")
    ap.add_argument("--topic", required=True, help="topic path from _config/taxonomy.md")
    ap.add_argument("--title", help="page title (required for document and capture)")
    ap.add_argument("--slug", help="override the derived file slug")
    ap.add_argument("--parent-doc", help="doc_id of the parent document (capture only)")
    ap.add_argument("--source-file", help="the file in raw/ this came from")
    ap.add_argument("--source-type", choices=["pdf", "txt"])
    ap.add_argument("--links-authorized", type=int,
                    help="count from the document's link plan")
    ap.add_argument("--max-slug", type=int, default=60)
    ap.add_argument("--set", action="append", dest="sets",
                    help="KEY=VALUE frontmatter value; repeatable")
    ap.add_argument("--json", help="a flat json object of frontmatter values")
    ap.add_argument("--print", action="store_true", dest="to_stdout",
                    help="print the page instead of writing it")
    ap.add_argument("--allow-unknown-topic", action="store_true",
                    help="write even when the taxonomy does not define the topic. "
                         "Use only while editing the taxonomy itself.")
    args = ap.parse_args(argv)

    if args.kind in ("document", "capture") and not args.title:
        sys.stderr.write("ERROR: --title is required for a %s page\n" % args.kind)
        return 1
    if args.kind == "capture" and not args.parent_doc:
        sys.stderr.write(
            "ERROR: --parent-doc is required for a capture. A capture with no parent "
            "cannot be audited against a link plan, which is the whole point of it "
            "(SCHEMA.md § 6.2).\n")
        return 1

    taxonomy = load_taxonomy(args.library)
    if not taxonomy and not args.allow_unknown_topic:
        sys.stderr.write(
            "ERROR: cannot read a taxonomy from %s/_config/taxonomy.md.\n"
            "Without it there is no way to tell a real topic from an invented one. Run "
            "/ai-lib-setup, or pass --allow-unknown-topic if you are editing the taxonomy "
            "itself.\n" % args.library)
        return 1
    if taxonomy and args.topic not in taxonomy and not args.allow_unknown_topic:
        close = [p for p in taxonomy if args.topic.split("/")[-1] in p]
        sys.stderr.write(
            "ERROR: topic %r is not defined in _config/taxonomy.md.\n"
            "Defined paths: %s\n%s"
            "A document filed at an invented path is invisible to the subagent that "
            "should own it. Add the topic to the taxonomy deliberately, then re-run.\n"
            % (args.topic, ", ".join(sorted(taxonomy)),
               ("Did you mean: %s\n" % ", ".join(close)) if close else ""))
        return 1
    if (args.kind in ("document", "capture")
            and taxonomy.get(args.topic) == "branch" and not args.allow_unknown_topic):
        kids = sorted(p for p in taxonomy if p.startswith(args.topic + "/"))
        sys.stderr.write(
            "ERROR: %r is a BRANCH topic and holds no documents (SCHEMA.md § 1.1).\n"
            "File this in one of its leaves: %s\n" % (args.topic, ", ".join(kids)))
        return 1

    values = parse_sets(args.sets, args.json)
    if values is None:
        return 1

    today = datetime.date.today()
    builder = {"document": build_document, "topic": build_topic,
               "capture": build_capture}[args.kind]
    rel, doc = builder(args, values, today, taxonomy)
    if rel is None:
        return 1

    if args.to_stdout:
        sys.stdout.write(doc)
        sys.stderr.write("would write %s\n" % rel)
        return 0

    path = os.path.join(args.library, rel.replace("/", os.sep))
    if os.path.exists(path):
        sys.stderr.write(
            "%s already exists.\n"
            "Read it and update it under the resolution policy (SCHEMA.md § 8.2). Do NOT "
            "regenerate it from this run's facts — a skeleton rebuilt from a partial fact "
            "set silently drops every field the current source happens not to mention.\n"
            % rel)
        return 3

    try:
        atomic_write(path, doc)
    except OSError as exc:
        sys.stderr.write("ERROR: cannot write %s: %s\n" % (path, exc))
        return 1

    sys.stderr.write("wrote %s\n" % rel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
