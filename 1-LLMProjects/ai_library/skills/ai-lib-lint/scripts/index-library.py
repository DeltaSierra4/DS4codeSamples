#!/usr/bin/env python3
"""
index-library.py — regenerate `index.md` from the library data json.

`index.md` is a DERIVED CATALOG. It holds no knowledge of its own, so it is rebuildable
from `topics/` at any moment and needs no approval to rewrite — which is exactly why it is
safe to regenerate on every run rather than letting it drift until nobody trusts it. A
stale index is a normal condition, not an error.

This script NEVER walks the tree. Every value comes off `lint-library.py`'s json, so the
two can never disagree about what the library contains. If a document is missing from the
index, the fix is to run the linter again, not to walk the tree from here.

THE ONE RULE: never record anything in `index.md` that is not on a page. The moment the
index holds a fact of its own, regenerating it destroys that fact and this script stops
being safe to run unattended.

Ordering is TAXONOMY ORDER, not alphabetical. A reader scanning for `llm/claude` expects
it beside `llm/gpt`, and the taxonomy order is the only order that is meaningful.

Stdlib only.

Invocation:
    python3 index-library.py --data output/_library-data.json --library <root>
    python3 index-library.py --data output/_library-data.json --out -      # to stdout

Exit codes:
    0  index written
    1  hard error — data json missing or unparseable, or the library root is absent
"""

import argparse
import datetime
import json
import os
import sys
import tempfile

COLUMNS = ["Document", "Type", "Authority", "Published", "Claims", "Bench", "Page"]


def cell(value):
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ").strip() or "—"


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


def doc_row(d):
    fm = d.get("fm") or {}
    claims = "%s" % d.get("claim_count_actual", 0)
    if d.get("located_actual", 0) != d.get("claim_count_actual", 0):
        # A reader must be able to see at a glance that some claims are unlocated.
        claims = "%d (%d loc.)" % (d.get("claim_count_actual", 0),
                                   d.get("located_actual", 0))
    flags = []
    if d.get("stale"):
        flags.append("stale")
    if d.get("is_stub"):
        flags.append("stub")
    if d.get("unmarked_claims"):
        flags.append("**%d unmarked**" % d["unmarked_claims"])
    title = cell(d.get("title"))
    if flags:
        title += " _(%s)_" % ", ".join(flags)
    return "| %s |" % " | ".join([
        title, cell(fm.get("publication_type")), cell(fm.get("authority")),
        cell(fm.get("published")), claims, "%s" % d.get("benchmark_rows", 0),
        "`%s`" % cell(d.get("page_rel_topic") or d.get("page")),
    ])


def share_line(top, shares):
    s = (shares or {}).get(top)
    if not s:
        return None
    if s.get("expected") is None:
        return "_%d document(s)_" % s["documents"]
    return "_%d document(s) — %.0f%% of the library, expected ~%.0f%%_" % (
        s["documents"], s["actual"] * 100, s["expected"] * 100)


def build_index(data):
    gen = data.get("generated") or datetime.date.today().isoformat()
    counts = data.get("counts") or {}
    taxonomy = data.get("taxonomy") or {}
    docs = data.get("documents") or []
    caps = data.get("captures") or []
    topics = {t["topic"]: t for t in (data.get("topics") or [])}
    shares = data.get("shares") or {}

    by_topic = {}
    for d in docs:
        by_topic.setdefault(d.get("topic"), []).append(d)
    caps_by_topic = {}
    for c in caps:
        caps_by_topic.setdefault(c.get("topic"), []).append(c)

    out = ["# Index", ""]
    out.append("_Generated %s by `ai-lib-lint` · %d leaf topic(s) · %d document(s) "
               "(%d active) · %d capture(s) · %d claim(s), %d located_"
               % (gen, counts.get("leaves", 0), counts.get("documents", 0),
                  counts.get("documents_active", 0), counts.get("captures", 0),
                  counts.get("claims_total", 0), counts.get("claims_located", 0)))
    out.append("")
    out.append("_Derived from the document pages themselves and rewritten on every "
               "`/ai-lib-lint` run. Do not hand-edit, and do not record anything here "
               "that is not on a page._")
    out.append("")

    warn = []
    if counts.get("claims_unmarked"):
        warn.append("**%d claim(s) carry no provenance marker** — an unmarked claim is "
                    "indistinguishable from a traceable one" % counts["claims_unmarked"])
    if counts.get("captures_unauthorized"):
        warn.append("**%d capture(s) are not in any authorized link plan** — the "
                    "signature of a second-hop fetch"
                    % counts["captures_unauthorized"])
    if counts.get("documents_stale"):
        warn.append("%d document(s) are past their topic's staleness threshold"
                    % counts["documents_stale"])
    if warn:
        out.append("> " + "  \n> ".join(warn))
        out.append("")

    # Taxonomy order, parents before children.
    ordered = list(taxonomy.keys())
    if not ordered:
        ordered = sorted(by_topic)

    for tpath in ordered:
        meta = taxonomy.get(tpath) or {}
        node = meta.get("node_type") or (topics.get(tpath) or {}).get("node_type", "leaf")
        depth = tpath.count("/")
        heading = "##" if depth == 0 else "###"
        title = (topics.get(tpath) or {}).get("title") or tpath.rsplit("/", 1)[-1]
        out.append("%s %s — `topics/%s/`" % (heading, title, tpath))
        out.append("")

        if node == "branch":
            kids = [p for p in ordered if p.startswith(tpath + "/")
                    and p.count("/") == depth + 1]
            sl = share_line(tpath, shares)
            if sl:
                out.append(sl)
                out.append("")
            out.append("_Branch topic — holds no documents. Leaves: %s_"
                       % ", ".join("`%s`" % k for k in kids))
            out.append("")
            continue

        if depth == 0:
            sl = share_line(tpath, shares)
            if sl:
                out.append(sl)
                out.append("")

        group = by_topic.get(tpath, [])
        active = [d for d in group
                  if (d.get("fm") or {}).get("status", "active") != "superseded"]
        superseded = [d for d in group
                      if (d.get("fm") or {}).get("status") == "superseded"]

        if not group:
            out.append("_No documents yet — run `/ai-lib-ingest` with a PDF for this "
                       "topic._")
            out.append("")
            continue

        if active:
            out.append("| %s |" % " | ".join(COLUMNS))
            out.append("|%s|" % "|".join(["---"] * len(COLUMNS)))
            for d in sorted(active, key=lambda x: (
                    str((x.get("fm") or {}).get("published") or "0000"),
                    (x.get("title") or "").lower()), reverse=True):
                out.append(doc_row(d))
            out.append("")
        else:
            out.append("_Every document in this topic is superseded._")
            out.append("")

        if superseded:
            # Never mixed into the main table: a superseded document read as current is
            # the specific harm this separation prevents.
            out.append("#### Superseded" if depth else "### Superseded")
            out.append("")
            out.append("| %s |" % " | ".join(COLUMNS))
            out.append("|%s|" % "|".join(["---"] * len(COLUMNS)))
            for d in sorted(superseded,
                            key=lambda x: str((x.get("fm") or {}).get("published") or "")):
                out.append(doc_row(d))
            out.append("")

        nc = len(caps_by_topic.get(tpath, []))
        if nc:
            bad = sum(1 for c in caps_by_topic[tpath] if c.get("audit") != "authorized")
            out.append("_%d depth-1 capture(s) in this topic%s._"
                       % (nc, (", **%d not authorized by a link plan**" % bad)
                          if bad else ", all authorized"))
            out.append("")

    known = set(ordered)
    orphans = [d for d in docs if d.get("topic") not in known]
    if orphans:
        # Silently dropping one would make the index disagree with the tree, which is the
        # one thing this file may never do.
        out.append("## Unplaced")
        out.append("")
        out.append("_Documents filed at a path the taxonomy does not define. Run "
                   "`/ai-lib-lint` and read the findings._")
        out.append("")
        out.append("| Document | Topic path on disk | Page |")
        out.append("|---|---|---|")
        for d in orphans:
            out.append("| %s | %s | `%s` |" % (cell(d.get("title")),
                                               cell(d.get("topic")), cell(d.get("page"))))
        out.append("")

    if not docs:
        out.append("_No documents yet. This is a library nobody has ingested into — run "
                   "`/ai-lib-ingest` with a PDF._")
        out.append("")

    out.append("---")
    out.append("")
    out.append("_This library records what a collection of documents says. A document "
               "being here implies nothing about whether it is correct. Every claim on "
               "every page carries a marker naming where it came from; an answer built "
               "from this library names the kind of source it rests on._")
    return "\n".join(out).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Regenerate index.md from lint-library.py's json. Never walks the tree.")
    ap.add_argument("--data", default="output/_library-data.json")
    ap.add_argument("--library", help="library root; default from the json")
    ap.add_argument("--out", help="output path, or - for stdout; default <library>/index.md")
    args = ap.parse_args(argv)

    try:
        with open(args.data, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("ERROR: cannot read library data %r: %s\n"
                         "Run lint-library.py --library <root> --out %s first.\n"
                         % (args.data, exc, args.data))
        return 1
    if not isinstance(data, dict):
        sys.stderr.write("ERROR: %r is not a library-data object\n" % args.data)
        return 1

    library = args.library or data.get("library_root")
    text = build_index(data)

    if args.out == "-":
        sys.stdout.write(text)
        return 0
    out = args.out
    if not out:
        if not library:
            sys.stderr.write("ERROR: no --out and no library_root in the data json\n")
            return 1
        if not os.path.isdir(library):
            sys.stderr.write("ERROR: library root not found: %s\n" % library)
            return 1
        out = os.path.join(library, "index.md")

    atomic_write(out, text)
    c = data.get("counts") or {}
    sys.stderr.write("wrote %s (%d leaf topics, %d documents, %d captures)\n"
                     % (out, c.get("leaves", 0), c.get("documents", 0),
                        c.get("captures", 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
