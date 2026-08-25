#!/usr/bin/env python3
"""
index-wiki.py — regenerate `index.md` from the wiki data json.

`index.md` is a DERIVED CATALOG. It holds no knowledge of its own, so it is
rebuildable from `companies/` at any moment and needs no approval to rewrite — which
is exactly why it is safe to regenerate on every run rather than letting it drift
until nobody trusts it. A stale index is a normal condition, not an error.

This script NEVER walks the tree. Every value comes off `lint-wiki.py`'s json, so the
two can never disagree about what the wiki contains. If a plan is missing from the
index, the fix is to run the linter again, not to walk the tree from here.

THE ONE RULE: never record anything in `index.md` that is not on a page. The moment
the index holds a fact of its own, regenerating it destroys that fact and this script
stops being safe to run unattended.

Stdlib only. No pyyaml.

Invocation:
    python3 index-wiki.py --data output/_wiki-data.json --wiki <wiki-root>
    python3 index-wiki.py --data output/_wiki-data.json --out -      # to stdout

Exit codes:
    0  index written
    1  hard error — data json missing or unparseable, or the wiki root is absent
"""

import argparse
import datetime
import json
import os
import sys
import tempfile

COLUMNS = ["Plan", "Tier", "Network", "Market", "Premium/mo", "Deductible",
           "OOP max", "Conf.", "Page"]


def cell(value):
    """Make a value safe inside a markdown table cell."""
    text = "" if value is None else str(value)
    text = text.replace("|", "\\|").replace("\n", " ").strip()
    return text or "—"


def money(value):
    """
    Render a money field. TBD stays TBD; absent becomes an em dash.

    A missing number is NEVER rendered as 0. A reader scanning this table for the
    cheapest plan must not be able to mistake 'unknown' for 'free'.
    """
    if value is None or value == "":
        return "—"
    s = str(value).strip()
    if s.upper() == "TBD":
        return "TBD"
    return cell(s)


def atomic_write(path, text):
    """
    Write via a temp file in the same directory, then replace.

    A half-written index is worse than a stale one: a truncated table looks like a
    wiki that lost plans.
    """
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


def plan_row(p):
    fm = p.get("fm") or {}
    return "| %s |" % " | ".join([
        cell(p.get("title")),
        cell(fm.get("metal_tier")),
        cell(fm.get("network_type")),
        cell(fm.get("market")),
        money(fm.get("premium_monthly_individual")),
        money(fm.get("deductible_individual")),
        money(fm.get("oop_max_individual")),
        cell(fm.get("confidence")),
        "`%s`" % cell(p.get("page_rel_company") or p.get("page")),
    ])


def build_index(data):
    gen = data.get("generated") or datetime.date.today().isoformat()
    counts = data.get("counts") or {}
    companies = data.get("companies") or []
    plans = data.get("plans") or []

    by_company = {}
    for p in plans:
        by_company.setdefault(p.get("company"), []).append(p)

    out = ["# Index", ""]
    out.append("_Generated %s by `hiw-lint` · %d compan%s · %d plan%s (%d active, "
               "%d superseded) · currency %s_"
               % (gen, counts.get("companies", 0),
                  "y" if counts.get("companies") == 1 else "ies",
                  counts.get("plans", 0), "" if counts.get("plans") == 1 else "s",
                  counts.get("plans_active", 0), counts.get("plans_superseded", 0),
                  data.get("currency", "USD")))
    out.append("")
    out.append("_Derived from the plan pages themselves and rewritten on every "
               "`/hiw-lint` run. Do not hand-edit, and do not record anything here "
               "that is not on a page._")
    out.append("")

    known = {c.get("slug") for c in companies}
    ordered = sorted(companies, key=lambda c: (c.get("name") or c.get("slug") or "").lower())

    for c in ordered:
        slug = c.get("slug")
        name = c.get("name") or slug
        out.append("## %s — `companies/%s/`" % (name, slug))
        out.append("")

        group = by_company.get(slug, [])
        active = [p for p in group
                  if (p.get("fm") or {}).get("status", "active") != "superseded"]
        superseded = [p for p in group
                      if (p.get("fm") or {}).get("status") == "superseded"]

        if not group:
            out.append("_No plan pages yet — run `/hiw-ingest` for this carrier._")
            out.append("")
            continue

        if active:
            out.append("| %s |" % " | ".join(COLUMNS))
            out.append("|%s|" % "|".join(["---"] * len(COLUMNS)))
            for p in sorted(active, key=lambda x: (
                    str((x.get("fm") or {}).get("metal_tier") or "zz"),
                    (x.get("title") or "").lower())):
                out.append(plan_row(p))
            out.append("")
        else:
            out.append("_Every plan page for this carrier is superseded._")
            out.append("")

        if superseded:
            # Superseded plans are listed separately, never mixed into the main
            # table (SCHEMA.md § 8). Mixing them is how a comparison ends up
            # ranking a plan nobody can buy.
            out.append("### Superseded")
            out.append("")
            out.append("| %s |" % " | ".join(COLUMNS))
            out.append("|%s|" % "|".join(["---"] * len(COLUMNS)))
            for p in sorted(superseded, key=lambda x: (
                    str((x.get("fm") or {}).get("plan_year") or ""),
                    (x.get("title") or "").lower())):
                out.append(plan_row(p))
            out.append("")

    # A plan whose company folder produced no company record still gets listed.
    # Silently dropping it would make the index disagree with the tree, which is
    # the one thing this file may never do.
    orphans = [p for p in plans if p.get("company") not in known]
    if orphans:
        out.append("## Unplaced")
        out.append("")
        out.append("_Plan pages whose company folder produced no record. Run "
                   "`/hiw-lint` and read the findings._")
        out.append("")
        out.append("| Plan | Company folder | Page |")
        out.append("|---|---|---|")
        for p in orphans:
            out.append("| %s | %s | `%s` |" % (cell(p.get("title")),
                                               cell(p.get("company")),
                                               cell(p.get("page"))))
        out.append("")

    if not ordered:
        out.append("_No companies yet. This is a wiki nobody has ingested into — "
                   "run `/hiw-ingest` with a plan document or a carrier URL._")
        out.append("")

    src = data.get("sources") or []
    if src:
        out.append("## Source records")
        out.append("")
        out.append("| Company | Source | Type | Authority | Retrieved | Page |")
        out.append("|---|---|---|---|---|---|")
        for s in sorted(src, key=lambda x: (x.get("company") or "",
                                            x.get("title") or "")):
            out.append("| %s | %s | %s | %s | %s | `%s` |" % (
                cell(s.get("company")), cell(s.get("title")),
                cell(s.get("source_type")), cell(s.get("authority")),
                cell(s.get("retrieved")), cell(s.get("page"))))
        out.append("")

    out.append("---")
    out.append("")
    out.append("_This index records what published sources say. It is not advice, "
               "not a quote, and not an eligibility determination. Premiums are "
               "list values for the basis stated on each plan page and will differ "
               "from what a specific person is offered._")

    return "\n".join(out).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Regenerate index.md from lint-wiki.py's json. Never walks the tree.")
    ap.add_argument("--data", default="output/_wiki-data.json",
                    help="the json emitted by lint-wiki.py")
    ap.add_argument("--wiki", help="wiki root; default is taken from the json")
    ap.add_argument("--out", help="output path, or - for stdout; "
                                 "default <wiki>/index.md")
    args = ap.parse_args(argv)

    try:
        with open(args.data, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(
            "ERROR: cannot read wiki data %r: %s\n"
            "Run lint-wiki.py --wiki <root> --out %s first.\n"
            % (args.data, exc, args.data))
        return 1
    if not isinstance(data, dict):
        sys.stderr.write("ERROR: %r is not a wiki-data object\n" % args.data)
        return 1

    wiki = args.wiki or data.get("wiki_root")
    text = build_index(data)

    if args.out == "-":
        sys.stdout.write(text)
        return 0

    out = args.out
    if not out:
        if not wiki:
            sys.stderr.write("ERROR: no --out and no wiki_root in the data json\n")
            return 1
        if not os.path.isdir(wiki):
            sys.stderr.write("ERROR: wiki root not found: %s\n" % wiki)
            return 1
        out = os.path.join(wiki, "index.md")

    atomic_write(out, text)
    c = data.get("counts") or {}
    sys.stderr.write("wrote %s (%d compan%s, %d plan%s, %d source record%s)\n"
                     % (out, c.get("companies", 0),
                        "y" if c.get("companies") == 1 else "ies",
                        c.get("plans", 0), "" if c.get("plans") == 1 else "s",
                        c.get("source_records", 0),
                        "" if c.get("source_records") == 1 else "s"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
