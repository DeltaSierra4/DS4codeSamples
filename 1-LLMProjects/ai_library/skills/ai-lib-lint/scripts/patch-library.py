#!/usr/bin/env python3
"""
patch-library.py — the only writer of page fixes, and it re-detects nothing.

Consumes the `findings` array from `lint-library.py`'s json and applies ONLY the entries
carrying `autofix: true`. Every value it writes comes from that finding's `derived` map.
This script derives NOTHING itself. If the value is not in `derived`, the patcher may not
write it — that boundary is the whole reason a mechanical repair here cannot become an
invention.

WHAT IT WILL DO:

  1. Realign an identifier or a count with the tree, where the tree is the only truth:
        doc_id, topic, node_type, document_count, claim_count, located_claim_count,
        benchmark_count, depth
     These deliberately DO change a value — they correct a field that disagrees with what
     is on disk or in the section it summarizes.

  2. Normalize a value's FORM without changing its meaning:
        has_limitations: yes  ->  true
        doc_id: ai__x         ->  "ai__x"

  3. Fill an ABSENT required key from the linter's derived values, stamped
     `# [assumption: auto-filled by ai-lib-lint]` as a trailing YAML comment so the value
     stays machine-parseable and a human can see it was machine-filled.

  4. Insert an ABSENT fixed section heading with a `_None recorded._` placeholder at its
     contract position — only on a page whose sole section fault is absence.

WHAT IT WILL NEVER DO:

  * Write, edit, move or invent a CLAIM. Not a locator, not a `[link: ...]`, not a
    `[type: ...]`. `CLM-UNMARKED` is the highest-severity finding this library produces
    and it is deliberately not autofixable: the only correct fix is to reopen the source
    and find the page, and a marker invented to satisfy a linter is worse than the
    unmarked claim it replaced.
  * Move linked-page material out of a section it should not be in. That is content
    relocation, and which sentence belongs where is a judgement.
  * Delete or relocate a capture, however unauthorized. `CAP-UNAUTHORIZED` means a fetch
    happened that should not have; erasing the evidence is the opposite of the right
    response.
  * Resolve a contradiction, clear a `[verify:]`, or change a `published` date.
  * Create or delete a page.
  * Reformat frontmatter it is not editing. Existing lines keep their bytes, including
    their line endings.

Stdlib only.

Invocation:
    python3 patch-library.py --data output/_library-data.json --dry-run
    python3 patch-library.py --data output/_library-data.json --out output/_patch.json

Exit codes:
    0  ran to completion, however many fixes it applied or skipped
    1  hard error — data json missing or unparseable, library root absent
"""

import argparse
import json
import os
import re
import sys
import tempfile

ASSUMPTION_MARKER = "[assumption: auto-filled by ai-lib-lint]"

# A rule absent from these sets is never applied, even if a future linter marks it
# autofixable. The writer's input contract is closed on purpose, so extending the detector
# cannot silently extend the writer.
SCALAR_RULES = {"FM-DOC-ID-MISMATCH", "FM-TOPIC-MISMATCH", "FM-NODE-TYPE",
                "FM-ID-UNQUOTED", "FM-BOOL", "MIR-DOC-COUNT",
                "CNT-CLAIMS", "CNT-LOCATED", "CNT-BENCH", "CAP-DEPTH"}
FIELD_FILL_RULES = {"FM-REQUIRED-MISSING", "FM-LIST-MISSING", "FM-COUNT-MISSING"}
SECTION_RULES = {"SEC-MISSING"}
HONOURED = SCALAR_RULES | FIELD_FILL_RULES | SECTION_RULES

PLACEHOLDER = "_None recorded._"

# Fields whose value the patcher may legitimately CHANGE (rather than only normalize),
# because the tree or the section it summarizes is the authority for it.
REALIGNABLE = {"doc_id", "topic", "node_type", "document_count", "claim_count",
               "located_claim_count", "benchmark_count", "depth"}


def frontmatter_end(lines):
    if not lines or lines[0].strip() != "---":
        return -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return i
    return -1


def split_frontmatter(text):
    """
    (fm_lines, body, had_frontmatter). `fm_lines` keeps its line endings.

    We never parse values and never reformat: parsing implies reformatting, and
    reformatting a page we were asked to touch in one place is how a "safe" repair
    destroys authored content.
    """
    lines = text.splitlines(keepends=True)
    end = frontmatter_end(lines)
    if end == -1:
        return [], text, False
    return lines[1:end], "".join(lines[end + 1:]), True


def frontmatter_has_key(fm_lines, key):
    pat = re.compile(r"^\s*" + re.escape(key) + r"\s*:", re.IGNORECASE)
    return any(pat.match(ln) for ln in fm_lines)


def get_fm_raw(text, key):
    lines = text.splitlines()
    end = frontmatter_end(lines)
    if end == -1:
        return None
    pat = re.compile(r"^\s*" + re.escape(key) + r"\s*:\s*(.*)$")
    for j in range(1, end):
        m = pat.match(lines[j])
        if m:
            return m.group(1).strip()
    return None


def set_fm_scalar(text, key, value):
    """
    Set or replace one scalar key, preserving every other line.

    An absent key is inserted just above the closing fence; a present key has only its
    value replaced. A page with no frontmatter is returned unchanged rather than gaining
    one — that is a structure fault for the linter to report, not for the patcher to
    invent a fix for.
    """
    lines = text.splitlines(keepends=True)
    end = frontmatter_end(lines)
    if end == -1:
        return text, False
    pat = re.compile(r"^\s*" + re.escape(key) + r"\s*:")
    for j in range(1, end):
        if pat.match(lines[j]):
            lines[j] = "%s: %s\n" % (key, value)
            return "".join(lines), True
    lines.insert(end, "%s: %s\n" % (key, value))
    return "".join(lines), True


def add_frontmatter_fields(text, values):
    """Append absent keys above the closing fence, stamped. Append-only; never duplicates."""
    fm_lines, body, had = split_frontmatter(text)
    if not had:
        return text, []
    added, new_lines = [], []
    for field in sorted(values):
        if frontmatter_has_key(fm_lines, field):
            continue
        new_lines.append("%s: %s  # %s\n" % (field, values[field], ASSUMPTION_MARKER))
        added.append(field)
    if not added:
        return text, []
    block = list(fm_lines)
    if block and not block[-1].endswith("\n"):
        block[-1] = block[-1] + "\n"
    return "---\n" + "".join(block) + "".join(new_lines) + "---\n" + body, added


def norm(v):
    return re.sub(r"\s+", " ", str(v or "")).strip().lower()


def insert_missing_sections(text, missing, expected_order):
    """
    Insert each absent `##` heading with a placeholder at its contract position.

    Position comes from the contract order, not the end of the file: a section appended
    below `## Additional capture` would be invisible to every consumer, which is the bug
    this function exists to avoid rather than create.
    """
    lines = text.splitlines(keepends=True)
    fm_end = frontmatter_end(lines)
    start = fm_end + 1 if fm_end != -1 else 0

    present, in_fence = {}, False
    for i in range(start, len(lines)):
        s = lines[i].strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^##\s+(.*?)\s*$", lines[i])
        if m:
            present.setdefault(norm(m.group(1)), i)

    order_n = [norm(h) for h in expected_order]
    inserted = []
    for heading in missing:
        n = norm(heading)
        if n in present:
            continue
        try:
            idx = order_n.index(n)
        except ValueError:
            continue
        anchor = None
        for later in expected_order[idx + 1:]:
            ln = present.get(norm(later))
            if ln is not None:
                anchor = ln if anchor is None else min(anchor, ln)
        if anchor is None:
            anchor = len(lines)
        block = ["## %s\n" % heading, "%s\n" % PLACEHOLDER, "\n"]
        lines[anchor:anchor] = block
        present = {k: (v + len(block) if v >= anchor else v) for k, v in present.items()}
        present[n] = anchor
        inserted.append(heading)
    return "".join(lines), inserted


def value_preserving(rule, field, old_raw, new_value):
    """
    True when writing `new_value` is legitimate.

    An independent second check, run on the bytes actually on disk rather than on what the
    linter saw. A disagreement between the two means the page changed since the scan, and
    the correct response is to refuse.
    """
    if old_raw is None:
        return True                       # inserting an absent key
    old, new = old_raw.strip(), str(new_value).strip()

    if field in REALIGNABLE:
        # These are meant to change: the tree or the summarized section is the authority.
        return True
    if rule == "FM-ID-UNQUOTED":
        return new.strip("\"'") == old.strip("\"'")
    if rule == "FM-BOOL":
        mapped = {"yes": "true", "y": "true", "true": "true", "1": "true",
                  "no": "false", "n": "false", "false": "false",
                  "0": "false"}.get(old.strip("\"'").lower())
        return new.lower() in ("true", "false") and mapped == new.lower()
    return False


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


def to_os_path(root, rel):
    return os.path.join(root, rel.replace("/", os.sep))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Apply lint-library.py's autofixable findings. Writes nothing else.")
    ap.add_argument("--data", default="output/_library-data.json")
    ap.add_argument("--library", help="library root; default from the json")
    ap.add_argument("--out", help="write the run summary json here")
    ap.add_argument("--dry-run", action="store_true",
                    help="report exactly what would change; write nothing")
    args = ap.parse_args(argv)

    try:
        with open(args.data, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("ERROR: cannot read library data %r: %s\nRun lint-library.py "
                         "first.\n" % (args.data, exc))
        return 1
    if not isinstance(data, dict):
        sys.stderr.write("ERROR: %r is not a library-data object\n" % args.data)
        return 1

    root = args.library or data.get("library_root")
    if not root or not os.path.isdir(root):
        sys.stderr.write("ERROR: library root not found: %s\n" % root)
        return 1

    findings = [f for f in (data.get("findings") or [])
                if f.get("autofix") and f.get("rule") in HONOURED]

    by_page = {}
    for f in findings:
        by_page.setdefault(f.get("page"), []).append(f)

    applied, skipped = [], []

    for rel in sorted(by_page):
        path = to_os_path(root, rel)
        if not os.path.isfile(path):
            skipped.append({"page": rel, "rule": "-",
                            "reason": "page not found on disk; the tree changed since "
                                      "the scan — re-run lint-library.py"})
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                original = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            skipped.append({"page": rel, "rule": "-", "reason": "unreadable: %s" % exc})
            continue

        text, page_applied = original, []
        # Frontmatter first, so a section insertion cannot shift the closing fence.
        for f in sorted(by_page[rel], key=lambda x: (
                0 if x["rule"] in SCALAR_RULES else
                1 if x["rule"] in FIELD_FILL_RULES else 2)):
            rule, derived = f["rule"], (f.get("derived") or {})

            if rule in SCALAR_RULES:
                pairs = {k: v for k, v in derived.items()
                         if k not in ("fields", "values", "missing", "expected_order")}
                if not pairs:
                    skipped.append({"page": rel, "rule": rule,
                                    "reason": "no derived value; the patcher never "
                                              "derives one itself"})
                    continue
                for key, value in pairs.items():
                    old_raw = get_fm_raw(text, key)
                    if not value_preserving(rule, key, old_raw, value):
                        skipped.append({
                            "page": rel, "rule": rule, "field": key,
                            "reason": "refused — rewriting %r as %r is not a form "
                                      "normalization and %s is not a field the tree is "
                                      "authoritative for" % (old_raw, value, key)})
                        continue
                    text, ok = set_fm_scalar(text, key, value)
                    if ok:
                        page_applied.append({"rule": rule, "field": key,
                                             "from": old_raw, "to": value})
                    else:
                        skipped.append({"page": rel, "rule": rule, "field": key,
                                        "reason": "page has no frontmatter block"})

            elif rule in FIELD_FILL_RULES:
                values = derived.get("values") or {}
                if not values:
                    skipped.append({
                        "page": rel, "rule": rule,
                        "reason": "%d required key(s) absent with no derivable value — a "
                                  "human must supply them"
                                  % len(derived.get("fields") or [])})
                    continue
                text, added = add_frontmatter_fields(text, values)
                for k in added:
                    page_applied.append({"rule": rule, "field": k, "from": None,
                                         "to": values[k], "marked": ASSUMPTION_MARKER})
                unfilled = [k for k in (derived.get("fields") or []) if k not in values]
                if unfilled:
                    skipped.append({"page": rel, "rule": rule,
                                    "reason": "not derivable, left absent: %s"
                                              % ", ".join(unfilled)})

            elif rule in SECTION_RULES:
                missing = derived.get("missing") or []
                order = derived.get("expected_order") or []
                if not missing or not order:
                    skipped.append({"page": rel, "rule": rule,
                                    "reason": "no section list in the finding"})
                    continue
                text, inserted = insert_missing_sections(text, missing, order)
                for h in inserted:
                    page_applied.append({"rule": rule, "section": h,
                                         "to": "## %s + placeholder" % h})
                not_in = [h for h in missing if h not in inserted]
                if not_in:
                    skipped.append({"page": rel, "rule": rule,
                                    "reason": "could not place: %s" % ", ".join(not_in)})

        if text != original and page_applied:
            if not args.dry_run:
                try:
                    atomic_write(path, text)
                except OSError as exc:
                    skipped.append({"page": rel, "rule": "-",
                                    "reason": "write failed: %s" % exc})
                    continue
            for e in page_applied:
                e["page"] = rel
                applied.append(e)

    # Findings the patcher deliberately declines, surfaced so the report can say why
    # rather than leaving them looking overlooked.
    never = {}
    for f in (data.get("findings") or []):
        if f.get("rule") in ("CLM-UNMARKED", "CLM-LINKED-CLAIM",
                             "LNK-OUTSIDE-QUARANTINE", "LNK-PAGE-LOCATOR",
                             "CAP-UNAUTHORIZED", "SEC-INVENTED", "TAX-DOC-ON-BRANCH"):
            never[f["rule"]] = never.get(f["rule"], 0) + 1

    summary = {
        "schema": 1,
        "dry_run": bool(args.dry_run),
        "library_root": os.path.abspath(root),
        "data": os.path.abspath(args.data),
        "applied": applied,
        "skipped": skipped,
        "never_autofixed": never,
        "_never_note": (
            "These need a human by design. A claim's marker cannot be invented to satisfy "
            "a linter; misplaced linked-page material is a content move, not a format "
            "fix; and an unauthorized capture is evidence of a fetch that should not have "
            "happened — erasing it is the opposite of the right response."),
        "counts": {
            "candidates": len(findings),
            "applied": len(applied),
            "skipped": len(skipped),
            "pages_touched": len({a["page"] for a in applied}),
            "needs_a_human": sum(never.values()),
            "by_rule": {},
        },
    }
    for a in applied:
        summary["counts"]["by_rule"][a["rule"]] = \
            summary["counts"]["by_rule"].get(a["rule"], 0) + 1

    payload = json.dumps(summary, indent=2, ensure_ascii=False)
    if args.out:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(payload + "\n")
        except OSError as exc:
            sys.stderr.write("WARNING: cannot write --out %r: %s\n" % (args.out, exc))
            sys.stdout.write(payload + "\n")
    else:
        sys.stdout.write(payload + "\n")

    sys.stderr.write("%s %d fix(es) across %d page(s); %d skipped; %d finding(s) need a "
                     "human and were not touched\n"
                     % ("would apply" if args.dry_run else "applied", len(applied),
                        summary["counts"]["pages_touched"], len(skipped),
                        summary["counts"]["needs_a_human"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
