#!/usr/bin/env python3
"""
patch-wiki.py — the only writer of page fixes, and it re-detects nothing.

Consumes the `findings` array from `lint-wiki.py`'s json and applies ONLY the entries
carrying `autofix: true`. Every value it writes comes from that finding's `derived`
map. This script derives NOTHING itself. If the value is not in `derived`, the
patcher may not write it — that boundary is the whole reason a mechanical repair here
cannot become an invention.

WHAT IT WILL DO, and nothing else:

  1. Normalize a value's FORM without changing its magnitude.
        deductible_individual: 1,000   ->  1000
        coinsurance_in_network: 20%    ->  20
        pcp_required: yes              ->  true
        plan_id: blue__gold            ->  "blue__gold"
     Every one of these is checked to be value-preserving before it is written
     (see `value_preserving`). A rewrite that would change the number is refused
     and recorded as skipped, even though the linter marked it autofixable.

  2. Fill an ABSENT required key from the linter's `derived` values, or with the
     literal `TBD`, always stamped `# [assumption: auto-filled by hiw-lint]` as a
     trailing YAML comment so the value stays machine-parseable and a human can see
     it was machine-filled and unverified.

  3. Insert an ABSENT fixed section heading with a `_TBD._` stub at its contract
     position — only on a page whose sole section fault is absence.

  4. Repoint a broken cross-reference or a retired `[[wikilink]]` when there is
     EXACTLY ONE candidate.

WHAT IT WILL NEVER DO:

  * Change a cost number's magnitude. A premium that looks wrong is a human's call.
  * Fill a value the linter did not derive. There is no fallback guess.
  * Touch a `TBD`. `TBD` is a correct value meaning "known unknown" (SCHEMA.md § 2.4);
    replacing it with a plausible number is the exact failure this wiki exists to
    prevent.
  * Resolve a contradiction, pick between two sourced values, or clear a `[verify:]`.
  * Create a page, delete a page, or move one.
  * Reformat or reorder frontmatter it is not editing. Existing lines keep their
    bytes, including their line endings.

Stdlib only. No pyyaml.

Invocation:
    python3 patch-wiki.py --data output/_wiki-data.json --dry-run
    python3 patch-wiki.py --data output/_wiki-data.json --out output/_patch.json

Exit codes:
    0  ran to completion, however many fixes it applied or skipped
    1  hard error — data json missing or unparseable, wiki root absent
"""

import argparse
import json
import os
import re
import sys
import tempfile

ASSUMPTION_MARKER = "[assumption: auto-filled by hiw-lint]"

# Only these rules are honoured. A rule absent from this map is never applied, even
# if a future linter marks it autofixable — the writer's input contract is closed
# on purpose, so extending the detector cannot silently extend the writer.
SCALAR_RULES = {
    "FM-MONEY-FORMAT", "FM-MONEY-QUOTED", "FM-PCT-FORMAT", "FM-BOOL-FORMAT",
    "FM-ID-UNQUOTED", "FM-PLAN-ID-MISMATCH", "FM-COMPANY-MISMATCH",
    "MIR-PLAN-COUNT",
}
FIELD_FILL_RULES = {"FM-REQUIRED-MISSING", "FM-LIST-MISSING"}
SECTION_RULES = {"SEC-MISSING"}
XREF_RULES = {"XREF-BROKEN", "XREF-WIKILINK"}

HONOURED = SCALAR_RULES | FIELD_FILL_RULES | SECTION_RULES | XREF_RULES

BOOL_WORDS = {"true", "false"}


# ---------------------------------------------------------------------------
# Frontmatter mutation — deliberately dumber than the linter's reader
# ---------------------------------------------------------------------------

def split_frontmatter(text):
    """
    Split a page into (fm_lines, body_text, had_frontmatter).

    `fm_lines` is the list of lines BETWEEN the `---` delimiters, with their line
    endings intact. We never parse values and never reformat: parsing implies
    reformatting, and reformatting a page we were asked to touch in one place is
    how a "safe" repair destroys authored content.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return [], text, False
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], "".join(lines[i + 1:]), True
    return [], text, False


def frontmatter_end(lines):
    """Index of the closing `---`, or -1 when there is no frontmatter block."""
    if not lines or lines[0].strip() != "---":
        return -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return i
    return -1


def frontmatter_has_key(fm_lines, key):
    pat = re.compile(r"^\s*" + re.escape(key) + r"\s*:", re.IGNORECASE)
    return any(pat.match(ln) for ln in fm_lines)


def get_fm_raw(text, key):
    """The unparsed right-hand side of `key`, or None."""
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
    Set or replace one scalar frontmatter key, preserving every other line.

    An absent key is inserted just above the closing fence; a present key has only
    its value replaced. Nothing else in the block moves. A page with no frontmatter
    is returned unchanged rather than gaining one — that is a structure fault for
    the linter to report, not for the patcher to invent a fix for.
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
    """
    Append absent keys just above the closing fence. Append-only; never duplicates.

    Each value is stamped with the assumption marker as a trailing YAML comment.
    """
    fm_lines, body, had_fm = split_frontmatter(text)
    if not had_fm:
        return text, []
    added, new_lines = [], []
    for field in sorted(values):
        if frontmatter_has_key(fm_lines, field):
            continue
        new_lines.append("%s: %s  # %s\n"
                         % (field, values[field], ASSUMPTION_MARKER))
        added.append(field)
    if not added:
        return text, []
    block = list(fm_lines)
    if block and not block[-1].endswith("\n"):
        block[-1] = block[-1] + "\n"
    return "---\n" + "".join(block) + "".join(new_lines) + "---\n" + body, added


# ---------------------------------------------------------------------------
# Section insertion
# ---------------------------------------------------------------------------

def iter_body_lines(body):
    in_fence = False
    for lineno, line in enumerate(body.splitlines(), 1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            yield lineno, line, True
            continue
        yield lineno, line, in_fence


def normalize(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def insert_missing_sections(text, missing, expected_order):
    """
    Insert each absent `##` heading with a `_TBD._` stub at its contract position.

    Position is derived from the contract order, not appended at the end: a section
    appended below `## Additional capture` would be invisible to every consumer,
    which is the bug this function exists to avoid rather than create.
    """
    lines = text.splitlines(keepends=True)
    fm_end = frontmatter_end(lines)
    start = fm_end + 1 if fm_end != -1 else 0

    present = {}
    in_fence = False
    for i in range(start, len(lines)):
        s = lines[i].strip()
        if s.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^##\s+(.*?)\s*$", lines[i])
        if m:
            present.setdefault(normalize(m.group(1)), i)

    inserted = []
    for heading in missing:
        n = normalize(heading)
        if n in present:
            continue
        try:
            idx = [normalize(h) for h in expected_order].index(n)
        except ValueError:
            continue

        # Insert before the first LATER contract section that exists; if none does,
        # append at the end of the document.
        anchor = None
        for later in expected_order[idx + 1:]:
            ln = present.get(normalize(later))
            if ln is not None:
                anchor = ln if anchor is None else min(anchor, ln)
        if anchor is None:
            anchor = len(lines)

        block = ["## %s\n" % heading, "_TBD._\n", "\n"]
        lines[anchor:anchor] = block
        present = {k: (v + len(block) if v >= anchor else v)
                   for k, v in present.items()}
        present[n] = anchor
        inserted.append(heading)

    return "".join(lines), inserted


# ---------------------------------------------------------------------------
# The value-preservation guard
# ---------------------------------------------------------------------------

def value_preserving(rule, old_raw, new_value):
    """
    True when applying `new_value` cannot change what the field MEANS.

    This is the guard that separates a format normalization from an edit. The linter
    marked the finding autofixable; this function is the second, independent check,
    and it runs on the bytes actually on disk rather than on what the linter saw.
    A disagreement between the two means the page changed since the scan, and the
    correct response is to refuse.
    """
    if old_raw is None:
        return False
    old = old_raw.strip()
    new = str(new_value).strip()

    if rule in ("FM-ID-UNQUOTED",):
        return new.strip("\"'") == old.strip("\"'")

    if rule in ("FM-PLAN-ID-MISMATCH", "FM-COMPANY-MISMATCH", "MIR-PLAN-COUNT"):
        # These deliberately DO change the value — they realign an identifier or a
        # count with the tree, which is the only truth for either. Guarded instead
        # by being derived purely from the path or from a file count.
        return True

    if rule == "FM-BOOL-FORMAT":
        mapped = {"yes": "true", "y": "true", "true": "true",
                  "no": "false", "n": "false", "false": "false",
                  "1": "true", "0": "false"}.get(old.strip("\"'").lower())
        return new.lower() in BOOL_WORDS and mapped == new.lower()

    # Money and percentage: the digits must survive untouched.
    old_digits = re.sub(r"[^\d.]", "", old)
    new_digits = re.sub(r"[^\d.]", "", new)
    if not old_digits or not new_digits:
        return False
    try:
        return abs(float(old_digits) - float(new_digits)) < 1e-9
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------

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


def to_os_path(wiki_root, rel):
    return os.path.join(wiki_root, rel.replace("/", os.sep))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Apply lint-wiki.py's autofixable findings. Writes nothing else.")
    ap.add_argument("--data", default="output/_wiki-data.json", required=False,
                    help="the json emitted by lint-wiki.py")
    ap.add_argument("--wiki", help="wiki root; default is taken from the json")
    ap.add_argument("--out", help="write the run summary json here")
    ap.add_argument("--dry-run", action="store_true",
                    help="report exactly what would change; write nothing")
    args = ap.parse_args(argv)

    try:
        with open(args.data, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("ERROR: cannot read wiki data %r: %s\n"
                         "Run lint-wiki.py first.\n" % (args.data, exc))
        return 1
    if not isinstance(data, dict):
        sys.stderr.write("ERROR: %r is not a wiki-data object\n" % args.data)
        return 1

    wiki = args.wiki or data.get("wiki_root")
    if not wiki or not os.path.isdir(wiki):
        sys.stderr.write("ERROR: wiki root not found: %s\n" % wiki)
        return 1

    findings = [f for f in (data.get("findings") or [])
                if f.get("autofix") and f.get("rule") in HONOURED]

    # Group by page so each page is read once and written once. A page written
    # twice in one run is a page whose second write was based on a stale read.
    by_page = {}
    for f in findings:
        by_page.setdefault(f.get("page"), []).append(f)

    applied, skipped = [], []

    for rel in sorted(by_page):
        path = to_os_path(wiki, rel)
        if not os.path.isfile(path):
            skipped.append({"page": rel, "rule": "-",
                            "reason": "page not found on disk; the tree changed "
                                      "since the scan — re-run lint-wiki.py"})
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                original = fh.read()
        except (OSError, UnicodeDecodeError) as exc:
            skipped.append({"page": rel, "rule": "-",
                            "reason": "unreadable: %s" % exc})
            continue

        text = original
        page_applied = []

        # Order matters: scalars, then field fills, then sections, then references.
        # Frontmatter edits first so a section insertion cannot shift the fence.
        for f in sorted(by_page[rel], key=lambda x: (
                0 if x["rule"] in SCALAR_RULES else
                1 if x["rule"] in FIELD_FILL_RULES else
                2 if x["rule"] in SECTION_RULES else 3)):
            rule = f["rule"]
            derived = f.get("derived") or {}

            if rule in SCALAR_RULES:
                pairs = {k: v for k, v in derived.items()
                         if k not in ("fields", "values", "missing",
                                      "expected_order", "from", "to", "candidates")}
                if not pairs:
                    skipped.append({"page": rel, "rule": rule,
                                    "reason": "no derived value; the patcher never "
                                              "derives one itself"})
                    continue
                for key, value in pairs.items():
                    old_raw = get_fm_raw(text, key)
                    if not value_preserving(rule, old_raw, value):
                        skipped.append({
                            "page": rel, "rule": rule, "field": key,
                            "reason": "refused — rewriting %r as %r would not "
                                      "preserve the value. A change of magnitude is "
                                      "a human's call." % (old_raw, value)})
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
                        "reason": "%d required key(s) absent with no derivable "
                                  "value — a human must supply them"
                                  % len(derived.get("fields") or [])})
                    continue
                text, added = add_frontmatter_fields(text, values)
                for k in added:
                    page_applied.append({"rule": rule, "field": k,
                                         "from": None, "to": values[k],
                                         "marked": ASSUMPTION_MARKER})
                unfilled = [k for k in (derived.get("fields") or [])
                            if k not in values]
                if unfilled:
                    skipped.append({
                        "page": rel, "rule": rule,
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
                                         "to": "## %s + _TBD._" % h})
                not_inserted = [h for h in missing if h not in inserted]
                if not_inserted:
                    skipped.append({"page": rel, "rule": rule,
                                    "reason": "could not place: %s"
                                              % ", ".join(not_inserted)})

            elif rule in XREF_RULES:
                src, dst = derived.get("from"), derived.get("to")
                if not src or not dst:
                    skipped.append({
                        "page": rel, "rule": rule,
                        "reason": "%d candidate(s) — an ambiguous reference is "
                                  "repointed by a human, never guessed"
                                  % len(derived.get("candidates") or [])})
                    continue
                if src not in text:
                    skipped.append({"page": rel, "rule": rule,
                                    "reason": "reference %r no longer on the page"
                                              % src})
                    continue
                text = text.replace(src, dst)
                page_applied.append({"rule": rule, "from": src, "to": dst})

        if text != original and page_applied:
            if not args.dry_run:
                try:
                    atomic_write(path, text)
                except OSError as exc:
                    skipped.append({"page": rel, "rule": "-",
                                    "reason": "write failed: %s" % exc})
                    continue
            for entry in page_applied:
                entry["page"] = rel
                applied.append(entry)

    summary = {
        "schema": 1,
        "dry_run": bool(args.dry_run),
        "wiki_root": os.path.abspath(wiki),
        "data": os.path.abspath(args.data),
        "applied": applied,
        "skipped": skipped,
        "counts": {
            "candidates": len(findings),
            "applied": len(applied),
            "skipped": len(skipped),
            "pages_touched": len({a["page"] for a in applied}),
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

    sys.stderr.write("%s %d fix(es) across %d page(s); %d skipped\n"
                     % ("would apply" if args.dry_run else "applied",
                        len(applied), summary["counts"]["pages_touched"],
                        len(skipped)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
