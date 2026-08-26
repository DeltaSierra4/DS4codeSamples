#!/usr/bin/env python3
"""
build-library.py — the whole library as one self-contained HTML page.

Reads `lint-library.py`'s json (the inventory) plus an optional notes json (the narrative
written by the per-leaf subagents in `/ai-lib-list`), joins them on `doc_id`, and emits a
single .html file with no server, no CDN and no build step.

The division of labour:

    Python does DATA. Every count, date and flag came off a document page's frontmatter or
    was counted out of its sections. No language model retyped a number.

    JavaScript does RENDERING. Filtering by topic, type, authority and staleness, plus
    full-text search across titles, snapshots and CLAIMS, happens in the browser.

    The subagents do NARRATIVE. Their prose is merged in by doc_id and attributed. If a
    note contradicts a count, the count wins and the note is shown beside it.

PROVENANCE IS VISIBLE, ALWAYS. Every claim renders with its marker, and the four markers
render differently: a page locator, an `[unlocated]`, a `[link: ...]` and an
`[inference: ...]` are four different epistemic states (SCHEMA.md § 7.1) and this page
never collapses them. A claim with NO marker renders as a loud red warning rather than as
plain text, because that is the one thing the library may not contain.

Stdlib only.

Invocation:
    python3 build-library.py --data output/_library-data.json \
                             --notes output/_library-notes.json \
                             --out output/library.html

Exit codes:
    0  page written
    1  hard error — data json missing/unparseable, or the template is not beside this script
"""

import argparse
import datetime
import json
import os
import re
import sys
import tempfile

TEMPLATE_NAME = "library-template.html"

LOC_RE = re.compile(r"\[(?:p{1,2}\.\s*\d+[^\]]*|§\s*[\d.]+[^\]]*|Table\s+[^\]]+|"
                    r"Fig\.?\s+[^\]]+)\]", re.I)
UNLOC_RE = re.compile(r"\[unlocated\]", re.I)
LINK_RE = re.compile(r"\[link:\s*([^\]]+)\]", re.I)
INFER_RE = re.compile(r"\[inference:\s*([^\]]+)\]", re.I)
TYPE_RE = re.compile(r"\[type:\s*([a-z-]+)\s*\]", re.I)


def split_claim(text):
    """
    Break a claim line into (prose, marker_kind, marker_text, claim_type).

    Four marker kinds, never collapsed: `loc` (this document, located), `unloc` (this
    document, page unknown), `link` (a depth-1 linked page), `infer` (the reader's own
    conclusion). `none` is the failure state and renders as a warning.
    """
    ctype = None
    m = TYPE_RE.search(text)
    if m:
        ctype = m.group(1).lower()
        text = TYPE_RE.sub("", text)

    kind, marker = "none", ""
    for k, rx in (("loc", LOC_RE), ("unloc", UNLOC_RE),
                  ("link", LINK_RE), ("infer", INFER_RE)):
        mm = rx.search(text)
        if mm:
            kind, marker = k, mm.group(0)
            text = rx.sub("", text)
            break
    return re.sub(r"\s{2,}", " ", text).strip(" .;,"), kind, marker.strip("[]"), ctype


def load_notes(path):
    """Absent is normal: the page is complete without narrative, just drier."""
    if not path:
        return {}
    if not os.path.isfile(path):
        sys.stderr.write("note: no notes file at %s; building from data only\n" % path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("WARNING: cannot parse notes %r: %s — building from data only\n"
                         % (path, exc))
        return {}
    out = {"topics": {}, "documents": {}}
    if isinstance(raw, dict):
        for t in raw.get("topics") or []:
            if isinstance(t, dict) and t.get("topic"):
                out["topics"][t["topic"]] = {
                    "positioning": str(t.get("positioning") or ""),
                    "themes": str(t.get("themes") or ""),
                    "gaps": str(t.get("gaps") or "")}
        for d in raw.get("documents") or []:
            if isinstance(d, dict) and d.get("doc_id"):
                out["documents"][d["doc_id"]] = {
                    "one_liner": str(d.get("one_liner") or ""),
                    "why_read": str(d.get("why_read") or ""),
                    "caveat": str(d.get("caveat") or "")}
    return out


def build_payload(data, notes, include_superseded):
    taxonomy = data.get("taxonomy") or {}
    topics = {t["topic"]: t for t in (data.get("topics") or [])}
    caps_by_doc = {}
    for c in data.get("captures") or []:
        caps_by_doc.setdefault(c.get("parent_doc"), []).append({
            "url": c.get("source_url"), "domain": c.get("url_domain"),
            "link_class": c.get("link_class"), "status": c.get("fetch_status"),
            "accessed": c.get("accessed"), "audit": c.get("audit"),
            "page": c.get("page")})

    fcount = {}
    for f in data.get("findings") or []:
        did = f.get("doc_id")
        if did:
            d = fcount.setdefault(did, {"error": 0, "warn": 0, "info": 0})
            d[f.get("severity", "info")] = d.get(f.get("severity", "info"), 0) + 1

    docs = []
    for d in data.get("documents") or []:
        fm = d.get("fm") or {}
        if fm.get("status") == "superseded" and not include_superseded:
            continue
        claims = []
        for c in d.get("claims") or []:
            prose, kind, marker, ctype = split_claim(c.get("text", ""))
            claims.append({"n": c.get("n"), "text": prose, "kind": kind,
                           "marker": marker, "type": ctype})
        note = (notes.get("documents") or {}).get(d.get("doc_id")) or {}
        docs.append({
            "doc_id": d.get("doc_id"), "title": d.get("title"),
            "topic": d.get("topic"), "page": d.get("page"),
            "publication_type": fm.get("publication_type", ""),
            "authority": fm.get("authority", ""),
            "publisher": fm.get("publisher", ""),
            "authors": fm.get("authors") or [],
            "published": fm.get("published", ""),
            "year": fm.get("year", ""),
            "url": fm.get("url", ""),
            "pages": fm.get("pages", ""),
            "tags": fm.get("tags") or [],
            "models": fm.get("models") or [],
            "maturity": fm.get("maturity", ""),
            "status": fm.get("status", "active"),
            "confidence": fm.get("extraction_confidence", ""),
            "claims": claims,
            "claim_count": d.get("claim_count_actual", 0),
            "located": d.get("located_actual", 0),
            "unmarked": d.get("unmarked_claims", 0),
            "benchmarks": d.get("benchmark_rows", 0),
            "links_followed": fm.get("links_followed", 0),
            "links_declined": fm.get("links_declined", 0),
            "captures": caps_by_doc.get(d.get("doc_id")) or [],
            "stale": bool(d.get("stale")), "age_days": d.get("age_days"),
            "is_stub": bool(d.get("is_stub")),
            "snapshot": d.get("snapshot") or "",
            "note": note,
            "findings": fcount.get(d.get("doc_id"), {"error": 0, "warn": 0, "info": 0}),
        })

    counted = {}
    for d in docs:
        counted[d["topic"]] = counted.get(d["topic"], 0) + 1

    tree = []
    for tpath in taxonomy.keys():
        meta = taxonomy[tpath]
        t = topics.get(tpath) or {}
        note = (notes.get("topics") or {}).get(tpath) or {}
        tree.append({
            "topic": tpath,
            "title": t.get("title") or tpath.rsplit("/", 1)[-1],
            "node_type": meta.get("node_type", "leaf"),
            "depth": tpath.count("/"),
            "parent": tpath.rsplit("/", 1)[0] if "/" in tpath else "",
            "documents": counted.get(tpath, 0),
            "page": t.get("page", ""),
            "note": note,
        })

    return {
        "generated": data.get("generated") or datetime.date.today().isoformat(),
        "library_name": data.get("library_name") or "ai-lib",
        "include_superseded": bool(include_superseded),
        "tree": tree,
        "documents": docs,
        "shares": data.get("shares") or {},
        "totals": {
            "topics": len(tree),
            "leaves": sum(1 for t in tree if t["node_type"] == "leaf"),
            "documents": len(docs),
            "claims": sum(d["claim_count"] for d in docs),
            "located": sum(d["located"] for d in docs),
            "unmarked": sum(d["unmarked"] for d in docs),
            "captures": sum(len(d["captures"]) for d in docs),
            "captures_bad": sum(1 for d in docs for c in d["captures"]
                                if c.get("audit") != "authorized"),
            "stale": sum(1 for d in docs if d["stale"]),
            "stubs": sum(1 for d in docs if d["is_stub"]),
            "errors": sum(d["findings"].get("error", 0) for d in docs),
        },
    }


def json_island(payload):
    """Escape `</` so a quoted claim can never terminate the script block."""
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


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


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Build a self-contained HTML library browser from lint-library.py json.")
    ap.add_argument("--data", default="output/_library-data.json")
    ap.add_argument("--notes", help="optional per-leaf narrative json")
    ap.add_argument("--out", default="output/library.html")
    ap.add_argument("--title", help="override the page title")
    ap.add_argument("--include-superseded", action="store_true")
    args = ap.parse_args(argv)

    try:
        with open(args.data, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("ERROR: cannot read library data %r: %s\n"
                         "Run lint-library.py --library <root> --out %s first.\n"
                         % (args.data, exc, args.data))
        return 1

    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), TEMPLATE_NAME)
    try:
        with open(tpl, "r", encoding="utf-8") as fh:
            template = fh.read()
    except OSError as exc:
        sys.stderr.write("ERROR: template not found beside this script: %s (%s)\n"
                         % (tpl, exc))
        return 1

    payload = build_payload(data, load_notes(args.notes), args.include_superseded)
    title = args.title or ("%s — Library" % payload["library_name"])

    # The data island goes LAST so page content carrying a literal {{TITLE}} cannot be
    # substituted into.
    html = template.replace("{{TITLE}}", title)
    html = html.replace("{{LIBRARY_DATA}}", json_island(payload))

    atomic_write(args.out, html)
    t = payload["totals"]
    sys.stderr.write(
        "wrote %s (%d leaf topics, %d documents, %d claims of which %d located%s; "
        "%d captures%s; %d stale)\n"
        % (args.out, t["leaves"], t["documents"], t["claims"], t["located"],
           (", %d UNMARKED" % t["unmarked"]) if t["unmarked"] else "",
           t["captures"],
           (" — %d not authorized" % t["captures_bad"]) if t["captures_bad"] else "",
           t["stale"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
