#!/usr/bin/env python3
"""
build-compare.py — two or more documents side by side, benchmarks joined.

Takes `lint-library.py`'s json plus a list of `doc_id`s and emits one self-contained
.html: a metadata matrix, a BENCHMARK JOIN, and every claim laid out by type with its
provenance marker intact.

THE BENCHMARK JOIN IS THE POINT. Documents are joined on the normalized pair
(benchmark, metric) from their `## Evidence` tables. Where two documents report the same
benchmark and metric with different numbers, that is flagged as a DISAGREEMENT — with both
numbers, both locators and both authorities shown. Two vendors reporting different MMLU
scores for the same model is exactly the finding a library like this exists to surface, and
it is a string join plus a numeric compare, so it belongs in code rather than in a prompt.

The join is deliberately EXACT on the normalized name. "MMLU" and "Massive Multitask
Language Understanding" do not join, and that is correct: fuzzy-matching benchmark names
would silently equate a 5-shot result with a 0-shot one. SCHEMA.md § 11 requires the
document's own names verbatim precisely so this join works.

A DISAGREEMENT IS NOT AN ERROR. Different harnesses, prompts, dates and checkpoints all
produce different numbers legitimately. The page says "these differ" and shows the
evidence; it never picks a winner.

Stdlib only.

Invocation:
    python3 build-compare.py --data output/_library-data.json \
        --docs "ai__constitutional-ai,llm-claude__claude-4-5-system-card" \
        --out output/compare-2026-08-26.html --json output/_compare.json
    python3 build-compare.py --data output/_library-data.json --list

Exit codes:
    0  page written
    1  hard error — data unreadable, template missing, or fewer than two docs resolved
"""

import argparse
import datetime
import json
import os
import re
import sys
import tempfile

TEMPLATE_NAME = "compare-template.html"

META_ROWS = [
    ("publication_type", "Type"), ("authority", "Authority"),
    ("publisher", "Publisher"), ("published", "Published"),
    ("venue", "Venue"), ("pages", "Pages"),
    ("maturity", "Maturity"), ("reproducibility", "Reproducibility"),
    ("extraction_confidence", "Extraction confidence"), ("status", "Status"),
]
CLAIM_TYPES = ["empirical", "methodological", "architectural", "capability",
               "limitation", "normative", "forecast", None]

LOC_RE = re.compile(r"\[(?:p{1,2}\.\s*\d+[^\]]*|§\s*[\d.]+[^\]]*|Table\s+[^\]]+|"
                    r"Fig\.?\s+[^\]]+)\]", re.I)
UNLOC_RE = re.compile(r"\[unlocated\]", re.I)
LINK_RE = re.compile(r"\[link:\s*([^\]]+)\]", re.I)
INFER_RE = re.compile(r"\[inference:\s*([^\]]+)\]", re.I)
TYPE_RE = re.compile(r"\[type:\s*([a-z-]+)\s*\]", re.I)


def split_claim(text):
    ctype = None
    m = TYPE_RE.search(text)
    if m:
        ctype = m.group(1).lower()
        text = TYPE_RE.sub("", text)
    kind, marker = "none", ""
    for k, rx in (("loc", LOC_RE), ("unloc", UNLOC_RE), ("link", LINK_RE),
                  ("infer", INFER_RE)):
        mm = rx.search(text)
        if mm:
            kind, marker = k, mm.group(0)
            text = rx.sub("", text)
            break
    return re.sub(r"\s{2,}", " ", text).strip(" .;,"), kind, marker.strip("[]"), ctype


def norm_key(s):
    """Normalize a benchmark or metric name for joining: case and spacing only.

    Deliberately conservative. Stripping punctuation or expanding abbreviations would join
    a 5-shot MMLU to a 0-shot one and report a disagreement that does not exist."""
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def as_num(v):
    s = str(v or "").strip().replace(",", "")
    m = re.match(r"^[~<>=]*\s*(-?\d+(?:\.\d+)?)\s*%?$", s)
    return float(m.group(1)) if m else None


def resolve(data, wanted):
    """
    Match each requested id against the library, tolerantly, reporting every miss.

    Exact `doc_id` first, always: a tolerant matcher that silently prefers a title over an
    id is how the wrong document ends up in a comparison.
    """
    docs = data.get("documents") or []
    by_id = {d.get("doc_id"): d for d in docs}
    by_slug, by_title = {}, {}
    for d in docs:
        by_slug.setdefault(d.get("slug"), []).append(d)
        by_title.setdefault(norm_key(d.get("title")), []).append(d)

    picked, misses, ambiguous = [], [], []
    for w in wanted:
        w = w.strip()
        if not w:
            continue
        if w in by_id:
            picked.append(by_id[w]); continue
        hit = False
        for table, key in ((by_slug, w), (by_title, norm_key(w))):
            found = table.get(key) or []
            if len(found) == 1:
                picked.append(found[0]); hit = True; break
            if len(found) > 1:
                ambiguous.append((w, [x.get("doc_id") for x in found])); hit = True; break
        if not hit:
            misses.append(w)

    seen, out = set(), []
    for d in picked:
        if d.get("doc_id") not in seen:
            seen.add(d.get("doc_id")); out.append(d)
    return out, misses, ambiguous


def build_payload(data, chosen):
    docs = []
    for d in chosen:
        fm = d.get("fm") or {}
        claims = []
        for c in d.get("claims") or []:
            prose, kind, marker, ctype = split_claim(c.get("text", ""))
            claims.append({"n": c.get("n"), "text": prose, "kind": kind,
                           "marker": marker, "type": ctype})
        docs.append({
            "doc_id": d.get("doc_id"), "title": d.get("title"),
            "topic": d.get("topic"), "page": d.get("page"),
            "fm": {k: fm.get(k, "") for k, _ in META_ROWS},
            "authority": fm.get("authority", ""),
            "published": fm.get("published", ""),
            "url": fm.get("url", ""),
            "tags": fm.get("tags") or [], "models": fm.get("models") or [],
            "claims": claims,
            "claim_count": d.get("claim_count_actual", 0),
            "located": d.get("located_actual", 0),
            "unmarked": d.get("unmarked_claims", 0),
            "evidence": d.get("evidence") or [],
            "stale": bool(d.get("stale")), "age_days": d.get("age_days"),
        })

    # ---- the benchmark join --------------------------------------------------
    rows = {}
    for d in docs:
        for e in d["evidence"]:
            key = (norm_key(e.get("benchmark")), norm_key(e.get("metric")))
            if not key[0]:
                continue
            r = rows.setdefault(key, {"benchmark": e.get("benchmark"),
                                      "metric": e.get("metric"), "cells": {}})
            r["cells"][d["doc_id"]] = {
                "reported": e.get("reported", ""), "baseline": e.get("baseline", ""),
                "locator": e.get("locator", ""), "n": as_num(e.get("reported")),
                "authority": d["authority"]}

    join, disagreements = [], []
    for key, r in sorted(rows.items()):
        present = [i for i in r["cells"]]
        nums = [(i, r["cells"][i]["n"]) for i in present
                if r["cells"][i]["n"] is not None]
        best = None
        if len(nums) >= 2:
            vals = {round(v, 6) for _i, v in nums}
            if len(vals) > 1:
                disagreements.append({
                    "benchmark": r["benchmark"], "metric": r["metric"],
                    "values": [{"doc_id": i, "reported": r["cells"][i]["reported"],
                                "locator": r["cells"][i]["locator"],
                                "authority": r["cells"][i]["authority"]}
                               for i, _v in nums],
                    "spread": round(max(v for _i, v in nums) - min(v for _i, v in nums), 4),
                })
            best = max(nums, key=lambda x: x[1])[0]
        join.append({"benchmark": r["benchmark"], "metric": r["metric"],
                     "cells": r["cells"], "shared": len(present) > 1,
                     "comparable": len(nums), "of": len(docs), "highest": best})

    shared_tags = None
    for d in docs:
        s = set(d["tags"])
        shared_tags = s if shared_tags is None else (shared_tags & s)

    ids = {d["doc_id"] for d in docs}
    relevant = [{"rule": f["rule"], "severity": f["severity"], "page": f["page"],
                 "doc_id": f.get("doc_id"), "message": f["message"]}
                for f in (data.get("findings") or [])
                if f.get("doc_id") in ids and f["severity"] in ("error", "warn")]

    return {
        "generated": data.get("generated") or datetime.date.today().isoformat(),
        "library_name": data.get("library_name") or "ai-lib",
        "meta_rows": [{"key": k, "label": l} for k, l in META_ROWS],
        "claim_types": [t for t in CLAIM_TYPES],
        "documents": docs,
        "join": join,
        "disagreements": disagreements,
        "shared_tags": sorted(shared_tags or []),
        "findings": relevant,
        "totals": {
            "documents": len(docs),
            "topics": len({d["topic"] for d in docs}),
            "benchmark_rows": len(join),
            "shared_rows": sum(1 for r in join if r["shared"]),
            "disagreements": len(disagreements),
            "claims": sum(d["claim_count"] for d in docs),
            "unmarked": sum(d["unmarked"] for d in docs),
            "stale": sum(1 for d in docs if d["stale"]),
            "errors": sum(1 for f in relevant if f["severity"] == "error"),
            "all_first_party": bool(docs) and all(d["authority"] == "first-party"
                                                  for d in docs),
        },
    }


def json_island(payload):
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
        description="Build a side-by-side document comparison with a benchmark join.")
    ap.add_argument("--data", default="output/_library-data.json")
    ap.add_argument("--docs", help="comma-separated doc_ids (or slugs, or titles)")
    ap.add_argument("--docs-file", help="file with one doc_id per line")
    ap.add_argument("--out", help="output html path")
    ap.add_argument("--json", dest="json_out",
                    help="also write the computed payload here, or - for stdout. This is "
                         "how /ai-lib-query reads the join rather than scraping the HTML.")
    ap.add_argument("--title")
    ap.add_argument("--list", action="store_true",
                    help="print every doc_id in the library and exit")
    args = ap.parse_args(argv)

    try:
        with open(args.data, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("ERROR: cannot read library data %r: %s\n"
                         "Run lint-library.py --library <root> --out %s first.\n"
                         % (args.data, exc, args.data))
        return 1

    if args.list:
        for d in sorted(data.get("documents") or [],
                        key=lambda x: (x.get("topic") or "", x.get("title") or "")):
            sys.stdout.write("%s\t%s\t%s\n" % (d.get("doc_id"), d.get("topic"),
                                               d.get("title")))
        return 0

    wanted = []
    if args.docs:
        wanted += args.docs.split(",")
    if args.docs_file:
        try:
            with open(args.docs_file, "r", encoding="utf-8") as fh:
                wanted += [l.strip() for l in fh
                           if l.strip() and not l.startswith("#")]
        except OSError as exc:
            sys.stderr.write("ERROR: cannot read --docs-file %r: %s\n"
                             % (args.docs_file, exc))
            return 1
    if not wanted:
        sys.stderr.write("ERROR: no documents given. Pass --docs with two or more "
                         "comma-separated ids, or --list to see what is available.\n")
        return 1

    chosen, misses, ambiguous = resolve(data, wanted)
    for w in misses:
        sys.stderr.write("WARNING: no document matches %r — skipped\n" % w)
    for w, hits in ambiguous:
        sys.stderr.write("WARNING: %r matches %d documents (%s) — skipped; name it by "
                         "doc_id\n" % (w, len(hits), ", ".join(hits)))
    if len(chosen) < 2:
        sys.stderr.write("ERROR: resolved %d document(s); a comparison needs at least "
                         "two.\nRun with --list to see every doc_id.\n" % len(chosen))
        return 1

    tpl = os.path.join(os.path.dirname(os.path.abspath(__file__)), TEMPLATE_NAME)
    try:
        with open(tpl, "r", encoding="utf-8") as fh:
            template = fh.read()
    except OSError as exc:
        sys.stderr.write("ERROR: template not found beside this script: %s (%s)\n"
                         % (tpl, exc))
        return 1

    payload = build_payload(data, chosen)
    title = args.title or ("Compare — %d documents" % len(chosen))
    out = args.out or ("output/compare-%s.html" % payload["generated"])

    html = template.replace("{{TITLE}}", title)
    html = html.replace("{{COMPARE_DATA}}", json_island(payload))
    atomic_write(out, html)

    if args.json_out:
        blob = json.dumps(payload, indent=2, ensure_ascii=False)
        if args.json_out == "-":
            sys.stdout.write(blob + "\n")
        else:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(args.json_out)),
                            exist_ok=True)
                with open(args.json_out, "w", encoding="utf-8") as fh:
                    fh.write(blob + "\n")
            except OSError as exc:
                sys.stderr.write("WARNING: cannot write --json %r: %s\n"
                                 % (args.json_out, exc))
                sys.stdout.write(blob + "\n")

    t = payload["totals"]
    sys.stderr.write(
        "wrote %s (%d documents, %d benchmark row(s), %d shared, %d DISAGREEMENT(S)"
        "%s%s; %d error / %d claim(s) unmarked)\n"
        % (out, t["documents"], t["benchmark_rows"], t["shared_rows"],
           t["disagreements"],
           "; all sources first-party" if t["all_first_party"] else "",
           "; %d stale" % t["stale"] if t["stale"] else "",
           t["errors"], t["unmarked"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
