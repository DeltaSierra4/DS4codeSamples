#!/usr/bin/env python3
"""
lint-wiki.py — the only detector in health-insurance-wiki, and the only thing that
walks the tree.

Reads a health-insurance-wiki and emits ONE json document that is simultaneously:

  * the plan INVENTORY  — every company, every plan, every frontmatter key, verbatim
  * the FINDINGS list   — every place the tree disagrees with SCHEMA.md

Both live in the same file on purpose. `index-wiki.py`, `build-catalog.py` and
`build-comparison.py` all read this json and NEVER walk the tree themselves, so the
four scripts can never disagree about what the wiki contains. One walker, many
consumers. If you add a consumer, add it here as a reader — do not add a second walk.

This script is READ-ONLY. It never writes into `companies/`. `patch-wiki.py` is the
only writer of page fixes and it re-detects nothing; it consumes the `findings` entries
that carry `autofix: true`.

Findings carry a stable `rule` id, a `severity`, an `autofix` flag and, where the
detector can compute the sanctioned fix, a `derived` map. The patcher is FORBIDDEN
from deriving anything itself — if the value is not in `derived`, the patcher may not
write it. That is what keeps a mechanical repair from becoming an invention.

Severity vocabulary, and it is about consequence, not about tidiness:
    error  a comparison built on this page would be wrong
    warn   a comparison built on this page would be incomplete or misleading
    info   worth a human's attention; nothing downstream breaks

TBD is a first-class non-value. `TBD` means "this plan has this dimension and we do
not know it"; an ABSENT key means "this dimension does not apply to this plan"
(SCHEMA.md § 2.4). The two are counted separately everywhere below, and neither is
ever reported as zero.

Stdlib only (argparse, datetime, json, os, re, sys). No pyyaml, no install step.

Invocation:
    python3 lint-wiki.py --wiki <wiki-root> --out output/_wiki-data.json
    python3 lint-wiki.py --wiki <wiki-root>            # json to stdout

Exit codes:
    0  successful scan, however many findings it produced
    1  hard error — the wiki root is absent or holds no SCHEMA.md
"""

import argparse
import datetime
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# The contract, as data. SCHEMA.md is the prose; these constants are the
# machine-readable restatement. A change to one is a change to both.
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

PLAN_SECTIONS = [
    "Snapshot", "Cost Structure", "Covered Services", "Pharmacy",
    "Network & Access", "Exclusions & Limits", "Extras & Riders",
    "Fit Notes", "Additional capture",
]
COMPANY_SECTIONS = [
    "Snapshot", "Plans Offered", "Networks", "Service Area",
    "Enrollment & Service", "Additional capture",
]
SOURCE_SECTIONS = ["Metadata", "Key extractions", "Coverage"]

CAPTURE_SECTION = "Additional capture"

# SCHEMA.md § 2.1
REQUIRED_PLAN_FIELDS = [
    "title", "plan_id", "company", "company_name", "plan_year", "market",
    "network_type", "sources", "created", "last_updated", "updated_by",
    "confidence", "status",
]
REQUIRED_PLAN_LISTS = ["aka", "states", "source_urls", "sources"]

REQUIRED_COMPANY_FIELDS = [
    "title", "company", "category", "created", "last_updated", "updated_by", "status",
]
REQUIRED_SOURCE_FIELDS = [
    "title", "category", "company", "source_type", "source_ref", "retrieved",
    "authority", "created", "last_updated", "updated_by", "status",
]

# SCHEMA.md § 2.2
ENUMS = {
    "market": ["individual", "family", "small-group", "large-group",
               "medicare-advantage", "medicare-supplement", "medicare-part-d",
               "medicaid", "student", "short-term", "dental", "vision"],
    "network_type": ["HMO", "PPO", "EPO", "POS", "HDHP", "Indemnity", "Other"],
    "metal_tier": ["Bronze", "Expanded Bronze", "Silver", "Gold", "Platinum",
                   "Catastrophic", "n/a"],
    "premium_basis": ["unsubsidized", "post-subsidy", "employer-contribution-net",
                      "employee-share", "TBD"],
    "deductible_type": ["aggregate", "embedded", "none", "TBD"],
    "updated_by": ["hiw-setup", "hiw-ingest", "hiw-refresh", "hiw-list-plan",
                   "hiw-query", "hiw-compare", "hiw-lint", "practitioner"],
    "confidence": ["high", "medium", "low"],
    "status": ["active", "superseded", "draft"],
    "source_type": ["pdf", "docx", "txt", "xlsx", "pptx", "html", "url",
                    "image", "verbal"],
    "authority": ["official", "secondary", "unofficial"],
    "category": ["company", "sources", "synthesis"],
}

MONEY_FIELDS = [
    "premium_monthly_individual", "premium_monthly_family",
    "deductible_individual", "deductible_family",
    "oop_max_individual", "oop_max_family",
    "copay_primary_care", "copay_specialist", "copay_urgent_care",
    "copay_emergency_room", "copay_telehealth", "copay_lab", "copay_imaging",
    "rx_deductible", "rx_tier1_generic", "rx_tier2_preferred_brand",
    "rx_tier3_nonpreferred_brand", "rx_tier4_specialty",
]
PCT_FIELDS = ["coinsurance_in_network", "coinsurance_out_of_network"]
BOOL_FIELDS = ["hsa_eligible", "pcp_required", "referral_required",
               "out_of_network_covered", "dental_included", "vision_included"]
DATE_FIELDS = ["effective_date", "created", "last_updated", "retrieved"]
QUOTED_FIELDS = ["plan_id"]

# The fields a comparison actually ranks on. A TBD here is the thing /hiw-refresh
# should go after first, which is why they are named as a set rather than inferred.
CORE_COMPARE_FIELDS = [
    "premium_monthly_individual", "deductible_individual", "oop_max_individual",
    "copay_primary_care", "copay_specialist", "coinsurance_in_network",
]

# The exact inputs /hiw-compare's three annual-cost scenarios need. A field absent
# here is why a scenario comes back "not computable", and that is a much less obvious
# failure than a TBD in a column — so it gets its own rule rather than being folded
# into TBD-CORE.
COST_MODEL_FIELDS = {
    "healthy": ["premium_monthly_individual", "copay_primary_care",
                "rx_tier1_generic"],
    "moderate": ["premium_monthly_individual", "deductible_individual",
                 "copay_specialist", "copay_imaging", "rx_tier1_generic"],
    "bad": ["premium_monthly_individual", "oop_max_individual"],
}

NON_PAGE_FILES = {"schema.md", "index.md", "log.md", "readme.md", "agents.md",
                  "claude.md", "wiki-config.md"}

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SOURCE_TAG_RE = re.compile(r"\[source:\s*([^\]]+)\]")
VERIFY_TAG_RE = re.compile(r"\[verify:\s*([^\]]+)\]")
ASSUMPTION_TAG_RE = re.compile(r"\[assumption:\s*([^\]]+)\]")
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
PATH_REF_RE = re.compile(r"`((?:companies|synthesis|raw)/[^`\s]+\.md)`")
CONTRADICTION_MARKER = "**CONTRADICTION:**"
ASSUMPTION_MARKER = "[assumption: auto-filled by hiw-lint]"

DEFAULT_STALE_DAYS = 120


# ---------------------------------------------------------------------------
# Frontmatter / body parsing — hand-rolled, deliberately
# ---------------------------------------------------------------------------

def strip_yaml_comment(value):
    """
    Drop a trailing ` # comment` from a frontmatter value.

    `patch-wiki.py` writes its `[assumption: auto-filled by hiw-lint]` marker as a
    YAML comment precisely so the value stays machine-parseable. Without this the
    marker would be read as part of the value and every auto-filled `status` or
    `confidence` would fail its own enum check on the very next run — the linter
    would be reporting a violation it created itself. Quoted scalars and inline
    lists are respected, so a `#` inside them survives.
    """
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
    Split a markdown page into (data, present_keys, raw_values, body).

    Supports the three forms the contract uses and nothing else:
        key: value
        key: [a, b, c]
        key:
          - item

    `present_keys` is the set of keys that physically appeared, so a list key that
    is entirely ABSENT stays distinguishable from one present but empty — those are
    different violations (SCHEMA.md § 2.4). `raw_values` keeps the unparsed
    right-hand side so the quoting rule on `plan_id` can be checked at all.

    Unterminated frontmatter returns no frontmatter rather than raising: a linter
    that dies on one malformed page cannot report the malformed page.
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

    fm_lines = lines[1:end]
    body = "\n".join(lines[end + 1:])

    data, present, raw = {}, set(), {}
    current_key = None

    for line in fm_lines:
        stripped = line.strip()
        if stripped.startswith("- ") and current_key is not None:
            item = stripped[2:].strip().strip("'\"")
            if isinstance(data.get(current_key), list) and item:
                data[current_key].append(item)
            continue

        m = re.match(r"^([A-Za-z0-9_\-]+)\s*:\s*(.*)$", line)
        if not m:
            continue

        key = m.group(1).strip()
        value = m.group(2).strip()
        present.add(key)
        raw[key] = value
        current_key = None
        value = strip_yaml_comment(value)

        if value == "":
            data[key] = []
            current_key = key
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            data[key] = ([p.strip().strip("'\"") for p in inner.split(",") if p.strip()]
                         if inner else [])
        else:
            data[key] = value.strip().strip("'\"")

    return data, present, raw, body


def iter_body_lines(body):
    """
    Yield (lineno, line, in_fence) for every body line, tracking fenced blocks.

    Every structural scan goes through here so a markdown example inside a page —
    and `## Additional capture` is full of them — can never be mistaken for the
    page's own grammar.
    """
    in_fence = False
    for lineno, line in enumerate(body.splitlines(), 1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            yield lineno, line, True
            continue
        yield lineno, line, in_fence


def split_h2_sections(body):
    """Return [{text, line, lines}] — one record per `##` section, document order."""
    sections, current = [], None
    for lineno, line, in_fence in iter_body_lines(body):
        m = None if in_fence else re.match(r"^##\s+(.*?)\s*$", line)
        if m:
            current = {"text": m.group(1).strip(), "line": lineno, "lines": []}
            sections.append(current)
            continue
        if current is not None:
            current["lines"].append(line)
    return sections


def scan_h3_outside_capture(body):
    """Line numbers of `###` headings that sit above `## Additional capture`."""
    out, in_capture = [], False
    for lineno, line, in_fence in iter_body_lines(body):
        if in_fence:
            continue
        m2 = re.match(r"^##\s+(.*?)\s*$", line)
        if m2:
            in_capture = normalize(m2.group(1)) == normalize(CAPTURE_SECTION)
            continue
        if not in_capture and re.match(r"^###\s+\S", line):
            out.append(lineno)
    return out


def body_outside_fences(body):
    """The body with fenced blocks removed, for tag and reference scanning."""
    return "\n".join(l for _n, l, f in iter_body_lines(body) if not f)


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def normalize(value):
    """Normalize a string for identity comparison (case- and space-insensitive)."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def slugify(text):
    """
    Kebab-case a name per SCHEMA.md § 1.1: `&` becomes `and`, every other
    non-alphanumeric goes, hyphens collapse.
    """
    s = str(text or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def strip_md(name):
    """
    Drop a trailing `.md`. NEVER use os.path.splitext here — plan slugs carry
    dotted fragments like `750-35`, and a future id form may be dotted outright.
    """
    v = str(name or "")
    return v[:-3] if v.lower().endswith(".md") else v


def is_tbd(value):
    """True when the value is the literal TBD sentinel, in any casing."""
    return isinstance(value, str) and value.strip().upper() == "TBD"


def as_number(value):
    """
    Return a float for a bare numeric value, else None.

    A quoted cost-share string like `"20% after deductible"` returns None BY
    DESIGN: SCHEMA.md § 2.3 warns that a string is invisible to the comparison
    math, and this is the function that makes that true. `TBD` returns None too,
    and `build-comparison.py` renders both as unknown, never as zero.
    """
    if value is None or isinstance(value, list):
        return None
    s = str(value).strip()
    if not s or is_tbd(s):
        return None
    if not re.match(r"^-?\d+(\.\d+)?$", s):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def as_bool(value):
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return None


def rel_posix(path, root):
    """Identity for every finding and every cross-reference: a posix relative path."""
    return os.path.relpath(path, root).replace(os.sep, "/")


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError):
        return None


def days_between(later, earlier):
    try:
        a = datetime.date.fromisoformat(str(later))
        b = datetime.date.fromisoformat(str(earlier))
    except (ValueError, TypeError):
        return None
    return (a - b).days


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_KEYS = ["wiki_name", "wiki_root", "plan_year", "currency", "geography",
               "markets", "created", "created_by", "schema_version",
               "stale_days", "lint_keep", "cost_model_pcp_visits",
               "cost_model_specialist_visits", "cost_model_rx_months"]


def load_config(wiki_root):
    """
    Read `_config/wiki-config.md` as flat `key: value` lines.

    Absent file is a normal state, not an error: a hand-assembled wiki has no
    config and every value below has a documented default.
    """
    cfg = {}
    path = os.path.join(wiki_root, "_config", "wiki-config.md")
    text = read_text(path)
    if not text:
        return cfg
    for line in text.splitlines():
        if line.startswith(("|", ">", "#", "-", " ")):
            continue
        m = re.match(r"^([a-z_]+)\s*:\s*(.*)$", line.strip())
        if m and m.group(1) in CONFIG_KEYS:
            v = m.group(2).strip()
            if v and not v.startswith("{{"):
                cfg[m.group(1)] = v
    return cfg


def cfg_int(cfg, key, default):
    try:
        return int(str(cfg.get(key, default)).strip())
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

def finding(rule, severity, page, message, autofix=False, derived=None,
            line=None, company=None, plan_id=None, field=None):
    f = {
        "rule": rule,
        "severity": severity,
        "autofix": bool(autofix),
        "page": page,
        "message": message,
    }
    if derived:
        f["derived"] = derived
    if line is not None:
        f["line"] = line
    if company:
        f["company"] = company
    if plan_id:
        f["plan_id"] = plan_id
    if field:
        f["field"] = field
    return f


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover(wiki_root):
    """
    One walk. Returns (companies, plans, sources, strays, rel_index).

    `rel_index` is every .md path in the wiki, including the non-page files, so a
    plan page may legitimately cite `SCHEMA.md` without producing a broken
    reference. Indexing happens before the exclusion check for exactly that reason.
    """
    companies, plans, sources, strays = [], [], [], []
    rel_index = set()

    companies_dir = os.path.join(wiki_root, "companies")

    for dirpath, dirnames, filenames in os.walk(wiki_root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if not name.lower().endswith(".md"):
                continue
            full = os.path.join(dirpath, name)
            rel_index.add(rel_posix(full, wiki_root))

    if not os.path.isdir(companies_dir):
        return companies, plans, sources, strays, rel_index

    for slug in sorted(os.listdir(companies_dir)):
        cdir = os.path.join(companies_dir, slug)
        if not os.path.isdir(cdir) or slug.startswith("."):
            continue

        rec = {"slug": slug, "dir": cdir, "company_page": None,
               "plan_pages": [], "source_pages": []}

        cpage = os.path.join(cdir, "company.md")
        if os.path.isfile(cpage):
            rec["company_page"] = cpage

        pdir = os.path.join(cdir, "plans")
        if os.path.isdir(pdir):
            for fn in sorted(os.listdir(pdir)):
                if fn.lower().endswith(".md") and not fn.startswith("."):
                    rec["plan_pages"].append(os.path.join(pdir, fn))

        sdir = os.path.join(cdir, "sources")
        if os.path.isdir(sdir):
            for fn in sorted(os.listdir(sdir)):
                if fn.lower().endswith(".md") and not fn.startswith("."):
                    rec["source_pages"].append(os.path.join(sdir, fn))

        # Anything else under a company folder is a stray. A plan page filed one
        # level too high is invisible to every consumer while looking perfectly
        # fine in a file browser, so it is reported rather than absorbed.
        known = set(rec["plan_pages"]) | set(rec["source_pages"])
        if rec["company_page"]:
            known.add(rec["company_page"])
        for dirpath, dirnames, filenames in os.walk(cdir):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
            for fn in sorted(filenames):
                if not fn.lower().endswith(".md"):
                    continue
                full = os.path.join(dirpath, fn)
                if full not in known and fn.lower() not in NON_PAGE_FILES:
                    strays.append(full)

        companies.append(rec)
        plans.extend((slug, p) for p in rec["plan_pages"])
        sources.extend((slug, p) for p in rec["source_pages"])

    return companies, plans, sources, strays, rel_index


# ---------------------------------------------------------------------------
# Section checking
# ---------------------------------------------------------------------------

def check_sections(rel, body, expected, findings, company=None, plan_id=None):
    """
    Report missing / duplicated / misordered / invented `##` sections.

    `autofix` is granted ONLY when absence is the sole fault. A page whose sections
    are out of order or duplicated needs a human, because fixing it moves authored
    content and a script cannot know which copy the author meant.
    """
    found = [s["text"] for s in split_h2_sections(body)]
    found_n = [normalize(t) for t in found]
    exp_n = [normalize(t) for t in expected]

    missing = [expected[i] for i, e in enumerate(exp_n) if e not in found_n]
    dupes = sorted({t for t in found_n if found_n.count(t) > 1})
    invented = [t for t, n in zip(found, found_n) if n not in exp_n]

    present_in_order = [n for n in found_n if n in exp_n]
    seen, deduped = set(), []
    for n in present_in_order:
        if n not in seen:
            seen.add(n)
            deduped.append(n)
    expected_order = [n for n in exp_n if n in deduped]
    out_of_order = deduped != expected_order

    capture_not_last = (normalize(CAPTURE_SECTION) in found_n
                        and found_n[-1] != normalize(CAPTURE_SECTION))

    only_missing = bool(missing) and not (dupes or invented or out_of_order
                                         or capture_not_last)

    if missing:
        findings.append(finding(
            "SEC-MISSING", "warn", rel,
            "missing fixed section(s): %s — SCHEMA.md § 3 requires all of them "
            "present, empty ones holding `_TBD._`" % ", ".join(missing),
            autofix=only_missing,
            derived={"missing": missing, "expected_order": expected},
            company=company, plan_id=plan_id))
    if dupes:
        findings.append(finding(
            "SEC-DUP", "error", rel,
            "duplicated section heading(s): %s — a consumer reads the first and "
            "silently drops the second" % ", ".join(dupes),
            company=company, plan_id=plan_id))
    if invented:
        findings.append(finding(
            "SEC-INVENTED", "error", rel,
            "section heading(s) not in the contract: %s — put this content under "
            "`## Additional capture` as a `###`, which is the sanctioned place for it"
            % ", ".join("`## %s`" % t for t in invented),
            company=company, plan_id=plan_id))
    if out_of_order:
        findings.append(finding(
            "SEC-ORDER", "warn", rel,
            "sections out of contract order — found %s, contract is %s"
            % (deduped, expected_order),
            company=company, plan_id=plan_id))
    if capture_not_last:
        findings.append(finding(
            "SEC-CAPTURE-NOT-LAST", "error", rel,
            "`## Additional capture` is not the last section — consumers stop "
            "reading the contract there, so everything below it is invisible",
            company=company, plan_id=plan_id))

    for lineno in scan_h3_outside_capture(body):
        findings.append(finding(
            "SEC-H3-OUTSIDE-CAPTURE", "info", rel,
            "free-form `###` heading above `## Additional capture`; `###` headings "
            "are only sanctioned inside the capture section",
            line=lineno, company=company, plan_id=plan_id))

    return found


def section_text(body, heading):
    for s in split_h2_sections(body):
        if normalize(s["text"]) == normalize(heading):
            return "\n".join(s["lines"])
    return None


def section_is_stub(text):
    if text is None:
        return False
    stripped = "\n".join(l for l in text.splitlines() if l.strip())
    return stripped.strip() in ("_TBD._", "_TBD_", "TBD")


# ---------------------------------------------------------------------------
# Frontmatter checking
# ---------------------------------------------------------------------------

def check_enums(rel, fm, findings, company=None, plan_id=None):
    for key, allowed in ENUMS.items():
        if key not in fm:
            continue
        val = fm[key]
        if isinstance(val, list) or val == "" or is_tbd(val):
            continue
        if val not in allowed:
            findings.append(finding(
                "FM-ENUM", "error", rel,
                "`%s: %s` is not in the controlled vocabulary — allowed: %s "
                "(SCHEMA.md § 2.2)" % (key, val, ", ".join(allowed)),
                company=company, plan_id=plan_id, field=key))


def check_value_formats(rel, fm, raw, findings, company=None, plan_id=None):
    for key in MONEY_FIELDS:
        if key not in fm:
            continue
        r = strip_yaml_comment(raw.get(key, ""))
        if is_tbd(fm[key]):
            continue
        if r.startswith(('"', "'")):
            # A quoted string is legal for a genuinely non-numeric cost share
            # ("20% after deductible"), but not for something that is plainly a
            # number wearing quotes or a currency symbol. Both are invisible to the
            # comparison math, and invisible is indistinguishable from absent.
            inner = r.strip("\"'").strip()
            cleaned = re.sub(r"[^\d.\-]", "", inner)
            if re.match(r"^-?\d+(\.\d+)?$", inner):
                findings.append(finding(
                    "FM-MONEY-QUOTED", "error", rel,
                    "`%s: %s` is a number in quotes — quoted values are invisible "
                    "to the comparison math (SCHEMA.md § 2.3). Write it bare: %s"
                    % (key, r, inner),
                    autofix=True, derived={key: inner},
                    company=company, plan_id=plan_id, field=key))
            elif (re.search(r"[$£€,]", inner)
                  and re.match(r"^-?\d+(\.\d+)?$", cleaned)
                  and not re.search(r"[A-Za-z%]", inner)):
                # The letter/percent guard is load-bearing. A genuinely non-numeric
                # cost share like "25% coinsurance, maximum $300 per fill" is
                # SANCTIONED by § 2.3, and stripping it to digits yields "25300",
                # which looks like a number carrying separators. Without this guard
                # the rule fires at ERROR severity on the most common cost-share
                # shape in a real SBC, and tells the author to replace a correct
                # value with a meaningless one. Found by a live model test: all
                # three models produced this shape and all three were wrongly
                # flagged.
                findings.append(finding(
                    "FM-MONEY-QUOTED", "error", rel,
                    "`%s: %s` is a quoted number carrying a currency symbol or "
                    "separator — money is a bare number in the wiki currency "
                    "(SCHEMA.md § 2.3). Write it as %s" % (key, r, cleaned),
                    autofix=True, derived={key: cleaned},
                    company=company, plan_id=plan_id, field=key))
            continue
        if re.search(r"[$£€,]", r):
            cleaned = re.sub(r"[^\d.\-]", "", r)
            findings.append(finding(
                "FM-MONEY-FORMAT", "error", rel,
                "`%s: %s` carries a currency symbol or separator — money is a bare "
                "number in the wiki currency (SCHEMA.md § 2.3)" % (key, r),
                autofix=bool(re.match(r"^-?\d+(\.\d+)?$", cleaned)),
                derived={key: cleaned} if re.match(r"^-?\d+(\.\d+)?$", cleaned) else None,
                company=company, plan_id=plan_id, field=key))

    for key in PCT_FIELDS:
        if key not in fm or is_tbd(fm[key]):
            continue
        r = strip_yaml_comment(raw.get(key, "")).strip("\"'")
        if r.endswith("%"):
            cleaned = r[:-1].strip()
            findings.append(finding(
                "FM-PCT-FORMAT", "error", rel,
                "`%s: %s` — coinsurance is a bare number meaning the share the "
                "MEMBER pays (SCHEMA.md § 2.3). Write `%s`, and check it is not "
                "the plan's share inverted" % (key, r, cleaned),
                autofix=bool(re.match(r"^\d+(\.\d+)?$", cleaned)),
                derived={key: cleaned} if re.match(r"^\d+(\.\d+)?$", cleaned) else None,
                company=company, plan_id=plan_id, field=key))
        else:
            n = as_number(r)
            if n is not None and n > 100:
                findings.append(finding(
                    "FM-PCT-RANGE", "error", rel,
                    "`%s: %s` exceeds 100 — a coinsurance share cannot" % (key, r),
                    company=company, plan_id=plan_id, field=key))

    for key in BOOL_FIELDS:
        if key not in fm or is_tbd(fm[key]):
            continue
        if as_bool(fm[key]) is None:
            low = normalize(fm[key])
            mapped = {"yes": "true", "y": "true", "no": "false", "n": "false",
                      "1": "true", "0": "false"}.get(low)
            findings.append(finding(
                "FM-BOOL-FORMAT", "error", rel,
                "`%s: %s` is not a YAML boolean — write `true` or `false`, "
                "unquoted (SCHEMA.md § 2.3)" % (key, fm[key]),
                autofix=mapped is not None,
                derived={key: mapped} if mapped else None,
                company=company, plan_id=plan_id, field=key))

    for key in DATE_FIELDS:
        if key not in fm or is_tbd(fm[key]) or isinstance(fm[key], list):
            continue
        if fm[key] and not DATE_RE.match(str(fm[key])):
            findings.append(finding(
                "FM-DATE-FORMAT", "warn", rel,
                "`%s: %s` is not `YYYY-MM-DD`" % (key, fm[key]),
                company=company, plan_id=plan_id, field=key))

    for key in QUOTED_FIELDS:
        if key not in raw:
            continue
        r = strip_yaml_comment(raw[key]).strip()
        if r and not (r.startswith('"') or r.startswith("'")):
            findings.append(finding(
                "FM-ID-UNQUOTED", "warn", rel,
                "`%s` must be quoted (SCHEMA.md § 2.2) — an unquoted id can be "
                "coerced by a downstream YAML reader" % key,
                autofix=True, derived={key: '"%s"' % r},
                company=company, plan_id=plan_id, field=key))


def check_required(rel, fm, present, findings, required, lists, derived,
                   company=None, plan_id=None):
    missing = [k for k in required if k not in present]
    missing_lists = [k for k in lists if k not in present]
    if missing:
        fixable = {k: derived[k] for k in missing if k in derived}
        findings.append(finding(
            "FM-REQUIRED-MISSING", "error", rel,
            "required frontmatter key(s) absent: %s" % ", ".join(missing),
            autofix=bool(fixable) and set(fixable) == set(missing),
            derived={"fields": missing, "values": fixable},
            company=company, plan_id=plan_id))
    if missing_lists:
        findings.append(finding(
            "FM-LIST-MISSING", "warn", rel,
            "list key(s) absent: %s — SCHEMA.md § 2.1 requires them to EXIST, "
            "empty as `[]`, so a reader can tell 'none' from 'never looked'"
            % ", ".join(missing_lists),
            autofix=True,
            derived={"fields": missing_lists,
                     "values": {k: "[]" for k in missing_lists}},
            company=company, plan_id=plan_id))


# ---------------------------------------------------------------------------
# Cross-reference checking
# ---------------------------------------------------------------------------

def check_references(rel, body, rel_index, findings, company=None, plan_id=None):
    clean = body_outside_fences(body)

    for m in PATH_REF_RE.finditer(clean):
        target = m.group(1)
        if target in rel_index:
            continue
        base = os.path.basename(target).lower()
        candidates = sorted(p for p in rel_index if os.path.basename(p).lower() == base)
        findings.append(finding(
            "XREF-BROKEN", "warn" if candidates else "error", rel,
            "cross-reference `%s` does not resolve%s" % (
                target,
                (" — one candidate: `%s`" % candidates[0]) if len(candidates) == 1
                else (" — %d candidates, ambiguous" % len(candidates)) if candidates
                else " — no page of that name exists anywhere in the wiki"),
            autofix=len(candidates) == 1,
            derived={"from": target, "to": candidates[0]} if len(candidates) == 1 else
                    {"from": target, "candidates": candidates},
            company=company, plan_id=plan_id))

    for m in WIKILINK_RE.finditer(clean):
        name = m.group(1).strip()
        slug = slugify(name)
        candidates = sorted(p for p in rel_index
                            if strip_md(os.path.basename(p)).lower() == slug)
        findings.append(finding(
            "XREF-WIKILINK", "warn", rel,
            "`[[%s]]` uses retired wikilink syntax — plan names collide across "
            "carriers, so the path is the identity (SCHEMA.md § 6.2)%s" % (
                name,
                (". Resolves to `%s`" % candidates[0]) if len(candidates) == 1 else ""),
            autofix=len(candidates) == 1,
            derived={"from": "[[%s]]" % name,
                     "to": "`%s`" % candidates[0]} if len(candidates) == 1 else None,
            company=company, plan_id=plan_id))


# ---------------------------------------------------------------------------
# Company roster mirror
# ---------------------------------------------------------------------------

def parse_roster(body):
    """
    Rows of the `## Plans Offered` table, keyed by normalized plan title.

    The company page is a MIRROR, not a second source of truth (SCHEMA.md § 4). It
    is checked against the plan folder because a company page that disagrees with
    its own plans is exactly how a comparison quietly drops a plan.
    """
    text = section_text(body, "Plans Offered")
    if text is None:
        return None          # the section is absent entirely
    rows = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        if not cells or normalize(cells[0]) in ("plan", ""):
            continue
        rows[normalize(cells[0])] = cells
    return rows


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def build_report(wiki_root, cfg, stale_days, today):
    findings = []
    companies_rec, plan_refs, source_refs, strays, rel_index = discover(wiki_root)

    for name in ("SCHEMA.md", "index.md", "log.md"):
        if not os.path.isfile(os.path.join(wiki_root, name)):
            findings.append(finding(
                "STR-ROOT-MISSING", "warn" if name != "SCHEMA.md" else "error",
                name,
                "`%s` absent from the wiki root — %s" % (
                    name,
                    "the page contract is unavailable; run /hiw-setup"
                    if name == "SCHEMA.md" else
                    "run /hiw-lint to regenerate it" if name == "index.md" else
                    "every skill appends here; create it empty")))

    if not os.path.isdir(os.path.join(wiki_root, "_config")):
        findings.append(finding(
            "STR-ROOT-MISSING", "info", "_config/",
            "`_config/` absent — this wiki was assembled by hand rather than "
            "scaffolded by /hiw-setup; every setting falls back to its default"))

    for path in strays:
        findings.append(finding(
            "STR-STRAY-FILE", "warn", rel_posix(path, wiki_root),
            "markdown file inside a company folder that is neither `company.md`, "
            "`plans/*.md` nor `sources/*.md` — every consumer reads those three "
            "locations and nothing else, so this file's content is invisible"))

    # ---- companies -------------------------------------------------------
    companies_out = []
    plan_index = {}

    for rec in companies_rec:
        slug = rec["slug"]
        if not SLUG_RE.match(slug):
            findings.append(finding(
                "STR-BAD-SLUG", "warn", "companies/%s/" % slug,
                "company folder name is not kebab-case (SCHEMA.md § 1.1); "
                "`%s` would be `%s`" % (slug, slugify(slug)),
                company=slug))

        entry = {
            "slug": slug,
            "name": slug.replace("-", " ").title(),
            "page": None,
            "fm": {},
            "plan_count_declared": None,
            "plan_count_actual": len(rec["plan_pages"]),
            "source_count": len(rec["source_pages"]),
            "roster": {},
        }

        if not rec["company_page"]:
            findings.append(finding(
                "STR-NO-COMPANY-PAGE", "error", "companies/%s/company.md" % slug,
                "company folder has no `company.md` — /hiw-list-plan and /hiw-query "
                "read it for carrier positioning and will skip this carrier's "
                "narrative entirely", company=slug))
        else:
            rel = rel_posix(rec["company_page"], wiki_root)
            entry["page"] = rel
            text = read_text(rec["company_page"]) or ""
            fm, present, raw, body = split_frontmatter(text)
            entry["fm"] = fm
            entry["name"] = fm.get("title") or entry["name"]
            entry["roster"] = parse_roster(body)

            derived = {
                "title": entry["name"],
                "company": slug,
                "category": "company",
                "status": "active",
                "updated_by": "hiw-lint",
            }
            check_required(rel, fm, present, findings, REQUIRED_COMPANY_FIELDS,
                           [], derived, company=slug)
            check_enums(rel, fm, findings, company=slug)
            check_value_formats(rel, fm, raw, findings, company=slug)
            check_sections(rel, body, COMPANY_SECTIONS, findings, company=slug)
            check_references(rel, body, rel_index, findings, company=slug)

            if fm.get("company") and fm["company"] != slug:
                findings.append(finding(
                    "FM-COMPANY-MISMATCH", "error", rel,
                    "`company: %s` disagrees with the folder `%s` — the folder is "
                    "the identity" % (fm["company"], slug),
                    company=slug, field="company"))

            declared = as_number(fm.get("plan_count"))
            entry["plan_count_declared"] = int(declared) if declared is not None else None
            if declared is not None and int(declared) != entry["plan_count_actual"]:
                findings.append(finding(
                    "MIR-PLAN-COUNT", "error", rel,
                    "`plan_count: %d` but `plans/` holds %d page(s) — SCHEMA.md § 4 "
                    "requires them equal" % (int(declared), entry["plan_count_actual"]),
                    autofix=True,
                    derived={"plan_count": str(entry["plan_count_actual"])},
                    company=slug, field="plan_count"))

        if entry["plan_count_actual"] == 0:
            findings.append(finding(
                "STR-EMPTY-COMPANY", "info", "companies/%s/plans/" % slug,
                "company folder holds no plan pages — nothing about this carrier "
                "can be listed, queried or compared. Run /hiw-ingest for it, or "
                "leave it if ingest is still in progress", company=slug))

        companies_out.append(entry)

    companies_by_slug = {c["slug"]: c for c in companies_out}

    # ---- plans -----------------------------------------------------------
    plans_out = []
    seen_plan_ids = {}

    for slug, path in plan_refs:
        rel = rel_posix(path, wiki_root)
        fn = os.path.basename(path)
        plan_slug = strip_md(fn)
        text = read_text(path)
        if text is None:
            findings.append(finding("STR-UNREADABLE", "error", rel,
                                    "page could not be read as UTF-8", company=slug))
            continue

        fm, present, raw, body = split_frontmatter(text)
        expected_id = "%s__%s" % (slug, plan_slug)
        plan_id = fm.get("plan_id") or expected_id

        if not SLUG_RE.match(plan_slug):
            findings.append(finding(
                "STR-BAD-SLUG", "warn", rel,
                "plan filename is not kebab-case (SCHEMA.md § 1.1); `%s` would be "
                "`%s`" % (plan_slug, slugify(plan_slug)),
                company=slug, plan_id=plan_id))

        derived = {
            "title": fm.get("title") or plan_slug.replace("-", " ").title(),
            "plan_id": '"%s"' % expected_id,
            "company": slug,
            "company_name": companies_by_slug.get(slug, {}).get("name", ""),
            "status": "active",
            "updated_by": "hiw-lint",
            "confidence": "low",
            "aka": "[]", "states": "[]", "source_urls": "[]", "sources": "[]",
        }
        mt = os.path.getmtime(path) if os.path.exists(path) else None
        if mt:
            derived["last_updated"] = datetime.date.fromtimestamp(mt).isoformat()
            derived["created"] = derived["last_updated"]

        check_required(rel, fm, present, findings, REQUIRED_PLAN_FIELDS,
                       REQUIRED_PLAN_LISTS, derived, company=slug, plan_id=plan_id)
        check_enums(rel, fm, findings, company=slug, plan_id=plan_id)
        check_value_formats(rel, fm, raw, findings, company=slug, plan_id=plan_id)
        sections_found = check_sections(rel, body, PLAN_SECTIONS, findings,
                                        company=slug, plan_id=plan_id)
        check_references(rel, body, rel_index, findings, company=slug, plan_id=plan_id)

        if fm.get("plan_id") and fm["plan_id"] != expected_id:
            findings.append(finding(
                "FM-PLAN-ID-MISMATCH", "error", rel,
                "`plan_id: %s` does not match `<company>__<file-slug>` = `%s`. "
                "`plan_id` is the join key for every comparison and synthesis page; "
                "a mismatch silently orphans this plan from anything that cites it"
                % (fm["plan_id"], expected_id),
                autofix=True, derived={"plan_id": '"%s"' % expected_id},
                company=slug, plan_id=plan_id, field="plan_id"))

        if fm.get("company") and fm["company"] != slug:
            findings.append(finding(
                "FM-COMPANY-MISMATCH", "error", rel,
                "`company: %s` disagrees with the folder `%s`" % (fm["company"], slug),
                autofix=True, derived={"company": slug},
                company=slug, plan_id=plan_id, field="company"))

        if plan_id in seen_plan_ids:
            findings.append(finding(
                "FM-DUP-PLAN-ID", "error", rel,
                "`plan_id: %s` is already used by `%s` — the join key must be "
                "globally unique" % (plan_id, seen_plan_ids[plan_id]),
                company=slug, plan_id=plan_id, field="plan_id"))
        else:
            seen_plan_ids[plan_id] = rel

        # ---- numeric sanity: impossible combinations, not merely unusual ones
        ded_i = as_number(fm.get("deductible_individual"))
        oop_i = as_number(fm.get("oop_max_individual"))
        ded_f = as_number(fm.get("deductible_family"))
        oop_f = as_number(fm.get("oop_max_family"))

        if ded_i is not None and oop_i is not None and oop_i < ded_i:
            findings.append(finding(
                "CON-OOP-LT-DEDUCTIBLE", "error", rel,
                "`oop_max_individual: %g` is below `deductible_individual: %g`, "
                "which cannot happen — the OOP max includes the deductible unless "
                "the source says otherwise (SCHEMA.md § 2.5). One of the two was "
                "read wrong, or an exclusive OOP max was recorded without adding "
                "the deductible" % (oop_i, ded_i),
                company=slug, plan_id=plan_id))
        if ded_i is not None and ded_f is not None and ded_f < ded_i:
            findings.append(finding(
                "CON-FAMILY-LT-INDIVIDUAL", "error", rel,
                "`deductible_family: %g` is below `deductible_individual: %g`"
                % (ded_f, ded_i), company=slug, plan_id=plan_id))
        if oop_i is not None and oop_f is not None and oop_f < oop_i:
            findings.append(finding(
                "CON-FAMILY-LT-INDIVIDUAL", "error", rel,
                "`oop_max_family: %g` is below `oop_max_individual: %g`"
                % (oop_f, oop_i), company=slug, plan_id=plan_id))

        nt = fm.get("network_type")
        oon = as_bool(fm.get("out_of_network_covered"))
        if nt in ("HMO", "EPO") and oon is True:
            findings.append(finding(
                "CON-NETWORK-OON", "info", rel,
                "`network_type: %s` with `out_of_network_covered: true` — usually "
                "an HMO or EPO covers out-of-network care for emergencies only. "
                "Check what the source actually said and state it in "
                "`## Network & Access`" % nt,
                company=slug, plan_id=plan_id))

        if nt == "HDHP" and as_bool(fm.get("hsa_eligible")) is False:
            findings.append(finding(
                "CON-HDHP-HSA", "info", rel,
                "`network_type: HDHP` with `hsa_eligible: false` — possible, but "
                "uncommon enough to be worth re-reading the source",
                company=slug, plan_id=plan_id))

        # ---- TBD accounting: known unknowns, counted, never guessed at
        tbd_core = [k for k in CORE_COMPARE_FIELDS if is_tbd(fm.get(k))]
        absent_core = [k for k in CORE_COMPARE_FIELDS if k not in present]
        tbd_all = sorted(k for k, v in fm.items() if is_tbd(v))
        cost_keys = [k for k in MONEY_FIELDS + PCT_FIELDS if k in present]
        tbd_cost = [k for k in cost_keys if is_tbd(fm.get(k))]

        if tbd_core:
            findings.append(finding(
                "TBD-CORE", "warn", rel,
                "core comparison field(s) are TBD: %s — /hiw-compare shows these as "
                "unknown and /hiw-query cannot rank on them. This is the correct "
                "state for an unstated value; run /hiw-refresh to go get them"
                % ", ".join(tbd_core),
                derived={"fields": tbd_core}, company=slug, plan_id=plan_id))
        if absent_core:
            findings.append(finding(
                "TBD-CORE-ABSENT", "info", rel,
                "core comparison field(s) entirely absent: %s. An absent key means "
                "'this dimension does not apply to this plan' (SCHEMA.md § 2.4). If "
                "it does apply and you simply do not know it, write `TBD` so the "
                "linter counts it and /hiw-refresh targets it"
                % ", ".join(absent_core),
                derived={"fields": absent_core}, company=slug, plan_id=plan_id))

        blocked = {}
        for scen, needed in COST_MODEL_FIELDS.items():
            gaps = [k for k in needed
                    if as_number(fm.get(k)) is None]
            if gaps:
                blocked[scen] = gaps
        if blocked:
            worst = "; ".join(
                "%s needs %s" % (s, ", ".join(g)) for s, g in sorted(blocked.items()))
            findings.append(finding(
                "COST-MODEL-BLOCKED", "info", rel,
                "/hiw-compare cannot compute %d of its 3 annual-cost scenarios for "
                "this plan: %s. A scenario is refused rather than estimated with a "
                "missing term treated as zero, so filling these is what makes this "
                "plan comparable on cost" % (len(blocked), worst),
                derived={"blocked": blocked}, company=slug, plan_id=plan_id))

        conf = fm.get("confidence")
        if cost_keys and len(tbd_cost) * 2 > len(cost_keys) and conf != "low":
            findings.append(finding(
                "TBD-HEAVY", "warn", rel,
                "%d of %d cost fields are TBD but `confidence: %s` — SCHEMA.md § 2.2 "
                "puts a partial extraction at `low`"
                % (len(tbd_cost), len(cost_keys), conf),
                autofix=False, company=slug, plan_id=plan_id, field="confidence"))

        # ---- provenance
        clean = body_outside_fences(body)
        if not SOURCE_TAG_RE.search(clean) and not fm.get("sources"):
            findings.append(finding(
                "PROV-NO-SOURCE", "error", rel,
                "no `[source: ...]` marker anywhere in the body and `sources:` is "
                "empty — nothing on this page can be traced to an origin, so no "
                "number on it can be trusted or re-verified",
                company=slug, plan_id=plan_id))
        for m in VERIFY_TAG_RE.finditer(clean):
            findings.append(finding(
                "PROV-VERIFY", "info", rel,
                "open `[verify: %s]` — a known weakness a human must resolve; "
                "nothing auto-clears it" % m.group(1).strip(),
                company=slug, plan_id=plan_id))
        if CONTRADICTION_MARKER in clean:
            findings.append(finding(
                "PROV-CONTRADICTION-OPEN", "warn", rel,
                "page carries an unresolved `**CONTRADICTION:**` marker — /hiw-lint "
                "never picks a winner, so this stays until a human decides",
                company=slug, plan_id=plan_id))

        urls = fm.get("source_urls") or []
        if isinstance(urls, list) and urls:
            for m in SOURCE_TAG_RE.finditer(clean):
                tag = m.group(1)
                if tag.startswith("http") and "accessed" not in tag:
                    findings.append(finding(
                        "PROV-URL-NO-DATE", "warn", rel,
                        "`[source: %s]` cites a URL with no access date — a web page "
                        "changes and an undated web claim cannot be re-verified "
                        "(SCHEMA.md § 6.1)" % tag[:60],
                        company=slug, plan_id=plan_id))
                    break

        # ---- staleness and plan year
        lu = fm.get("last_updated")
        age = days_between(today.isoformat(), lu) if lu else None
        if age is not None and age > stale_days:
            findings.append(finding(
                "AGE-STALE", "info", rel,
                "`last_updated: %s` is %d days old (threshold %d). Health plans "
                "re-rate annually, so this is a nudge, not a defect — but a premium "
                "this old should not be presented as current" % (lu, age, stale_days),
                company=slug, plan_id=plan_id))

        py = as_number(fm.get("plan_year"))
        cfg_py = as_number(cfg.get("plan_year"))
        if py is not None and cfg_py is not None and py < cfg_py \
                and fm.get("status") == "active":
            findings.append(finding(
                "AGE-PLAN-YEAR-PAST", "warn", rel,
                "`plan_year: %d` is behind the wiki's `plan_year: %d` but `status` "
                "is still `active`. A new plan year is a new page; last year's page "
                "becomes `status: superseded` (SCHEMA.md § 7.1) — that is what keeps "
                "rate history intact" % (int(py), int(cfg_py)),
                company=slug, plan_id=plan_id, field="status"))

        if fm.get("status") == "superseded":
            cap = section_text(body, CAPTURE_SECTION) or ""
            if not cap.strip() or section_is_stub(cap):
                findings.append(finding(
                    "CON-SUPERSEDED-SILENT", "warn", rel,
                    "`status: superseded` but `## Additional capture` does not name "
                    "what replaced it (SCHEMA.md § 7.1). A superseded page with no "
                    "successor is a dead end for anyone tracing rate history",
                    company=slug, plan_id=plan_id))

        stub = all(section_is_stub(section_text(body, s))
                   for s in PLAN_SECTIONS[:-1]
                   if section_text(body, s) is not None) and len(sections_found) > 1
        if stub:
            findings.append(finding(
                "SEC-STUB", "info", rel,
                "every fixed section is still `_TBD._` — a scaffolded page nobody "
                "has ingested into yet. Distinct from stale: this page never had "
                "content, rather than having gone quiet", company=slug, plan_id=plan_id))

        rec = {
            "plan_id": plan_id,
            "company": slug,
            "company_name": (fm.get("company_name")
                             or companies_by_slug.get(slug, {}).get("name", "")),
            "title": fm.get("title") or plan_slug.replace("-", " ").title(),
            "slug": plan_slug,
            "page": rel,
            "page_rel_company": "plans/%s" % fn,
            "fm": fm,
            "sections": sections_found,
            "tbd_fields": tbd_all,
            "tbd_core": tbd_core,
            "absent_core": absent_core,
            "has_source_tag": bool(SOURCE_TAG_RE.search(clean)),
            "is_stub": stub,
            "snapshot": (section_text(body, "Snapshot") or "").strip(),
            "fit_notes": (section_text(body, "Fit Notes") or "").strip(),
        }
        plans_out.append(rec)
        plan_index.setdefault(slug, []).append(rec)

    # ---- roster mirror ---------------------------------------------------
    for entry in companies_out:
        if not entry["page"]:
            continue
        roster = entry["roster"]
        n_active = sum(1 for p in plan_index.get(entry["slug"], [])
                       if (p["fm"].get("status", "active") != "superseded"))
        if roster is not None and not roster and n_active:
            # A header-only table is the default state of a freshly scaffolded
            # company page, and it is exactly as harmful as a wrong row: a reader
            # scanning `## Plans Offered` concludes the carrier has no plans.
            findings.append(finding(
                "MIR-ROSTER-EMPTY", "warn", entry["page"],
                "`## Plans Offered` has no rows, but `plans/` holds %d active plan "
                "page(s). SCHEMA.md § 4 wants one row per plan — an empty roster "
                "reads to a human as a carrier with nothing on offer"
                % n_active, company=entry["slug"]))
            continue
        if not roster:
            continue
        # Only ACTIVE plans belong in `## Plans Offered`. A superseded page is
        # deliberately not in the roster (SCHEMA.md § 7.1 keeps it for rate history,
        # § 8 files it under `### Superseded`), so requiring a row would train the
        # practitioner to add rows for plans nobody can buy. And keying by title
        # alone would collide: a 2025 and a 2026 page for one plan share a title,
        # which is exactly why plan_id exists.
        active = [p for p in plan_index.get(entry["slug"], [])
                  if p["fm"].get("status", "active") != "superseded"]
        titles = {}
        for p in active:
            titles.setdefault(normalize(p["title"]), []).append(p)
        for t, group in titles.items():
            if t not in entry["roster"]:
                for plan in group:
                    findings.append(finding(
                        "MIR-ROSTER-MISSING", "warn", entry["page"],
                        "plan `%s` has an active page but no row in "
                        "`## Plans Offered` — a carrier page that disagrees with its "
                        "own plan folder is how a comparison quietly drops a plan"
                        % plan["title"],
                        company=entry["slug"], plan_id=plan["plan_id"]))
        for t, cells in entry["roster"].items():
            if t not in titles:
                findings.append(finding(
                    "MIR-ROSTER-EXTRA", "warn", entry["page"],
                    "`## Plans Offered` lists `%s`, which has no page in `plans/`"
                    % cells[0], company=entry["slug"]))
                continue
            group = titles[t]
            if len(group) > 1:
                # Ambiguous: two active pages claim this title, which CON-DUP-TITLE
                # already reports. Comparing values against an arbitrary one of them
                # would produce a finding that changes with directory order.
                continue
            plan = group[0]
            fm = plan["fm"]
            # Columns per SCHEMA.md § 4: Plan | Tier | Network | Premium/mo |
            # Deductible | OOP max | Page
            for idx, key, label in ((1, "metal_tier", "Tier"),
                                    (2, "network_type", "Network"),
                                    (3, "premium_monthly_individual", "Premium/mo"),
                                    (4, "deductible_individual", "Deductible"),
                                    (5, "oop_max_individual", "OOP max")):
                if idx >= len(cells):
                    continue
                shown, actual = cells[idx].strip(), str(fm.get(key, "")).strip()
                if not shown or not actual:
                    continue
                sn, an = as_number(shown), as_number(actual)
                same = (sn == an) if (sn is not None and an is not None) \
                    else normalize(shown) == normalize(actual)
                if not same:
                    findings.append(finding(
                        "MIR-ROSTER-VALUE", "error", entry["page"],
                        "`## Plans Offered` shows %s = `%s` for `%s`, but the plan "
                        "page frontmatter says `%s: %s`. The frontmatter is the "
                        "machine truth (SCHEMA.md § 4); the roster is a mirror"
                        % (label, shown, cells[0], key, actual),
                        company=entry["slug"], plan_id=plan["plan_id"], field=key))

    # ---- duplicate titles within a carrier -------------------------------
    for slug, recs in plan_index.items():
        seen = {}
        for r in recs:
            key = (normalize(r["title"]), str(r["fm"].get("plan_year", "")))
            if key in seen:
                findings.append(finding(
                    "CON-DUP-TITLE", "warn", r["page"],
                    "same `title` and `plan_year` as `%s`. Two pages for one plan "
                    "drift apart on the next ingest and then read as a "
                    "contradiction" % seen[key],
                    company=slug, plan_id=r["plan_id"]))
            else:
                seen[key] = r["page"]

    # ---- sources ---------------------------------------------------------
    sources_out = []
    source_refs_by_company = {}
    for slug, path in source_refs:
        rel = rel_posix(path, wiki_root)
        text = read_text(path) or ""
        fm, present, raw, body = split_frontmatter(text)
        derived = {"category": "sources", "company": slug, "status": "active",
                   "updated_by": "hiw-lint"}
        check_required(rel, fm, present, findings, REQUIRED_SOURCE_FIELDS, [],
                       derived, company=slug)
        check_enums(rel, fm, findings, company=slug)
        check_sections(rel, body, SOURCE_SECTIONS, findings, company=slug)

        for plan_key in ("premium_monthly_individual", "deductible_individual",
                         "network_type", "metal_tier"):
            if plan_key in present:
                findings.append(finding(
                    "FM-SOURCE-PLAN-KEY", "error", rel,
                    "source record carries the plan key `%s` — a source record is a "
                    "receipt, not a plan (SCHEMA.md § 5). A linter must not have to "
                    "guess which kind of page it is reading" % plan_key,
                    company=slug, field=plan_key))

        rec = {"company": slug, "page": rel,
               "title": fm.get("title") or strip_md(os.path.basename(path)),
               "source_ref": fm.get("source_ref", ""),
               "source_type": fm.get("source_type", ""),
               "source_url": fm.get("source_url", ""),
               "authority": fm.get("authority", ""),
               "retrieved": fm.get("retrieved", ""),
               "plan_year": fm.get("plan_year", ""),
               "status": fm.get("status", "")}
        sources_out.append(rec)
        source_refs_by_company.setdefault(slug, set()).add(
            normalize(fm.get("source_ref", "")))
        source_refs_by_company[slug].add(normalize(strip_md(os.path.basename(path))))

    # ---- every cited source has a receipt --------------------------------
    for p in plans_out:
        cited = p["fm"].get("sources") or []
        if not isinstance(cited, list):
            continue
        known = source_refs_by_company.get(p["company"], set())
        raw_dir = os.path.join(wiki_root, "raw", p["company"])
        raw_files = set()
        if os.path.isdir(raw_dir):
            raw_files = {normalize(f) for f in os.listdir(raw_dir)}
        for ref in cited:
            n = normalize(ref)
            if n and n not in known and n not in raw_files \
                    and normalize(slugify(strip_md(ref))) not in known:
                findings.append(finding(
                    "PROV-NO-RECEIPT", "warn", p["page"],
                    "`sources:` cites `%s`, but there is no source record in "
                    "`companies/%s/sources/` and no file in `raw/%s/`. The number on "
                    "this page cannot be retraced to its origin"
                    % (ref, p["company"], p["company"]),
                    company=p["company"], plan_id=p["plan_id"]))

    # ---- assemble --------------------------------------------------------
    by_sev = {"error": 0, "warn": 0, "info": 0}
    for f in findings:
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1

    by_rule = {}
    for f in findings:
        by_rule[f["rule"]] = by_rule.get(f["rule"], 0) + 1

    for c in companies_out:
        c.pop("roster", None)

    return {
        "schema": SCHEMA_VERSION,
        "generated": today.isoformat(),
        "wiki_root": os.path.abspath(wiki_root),
        "wiki_name": cfg.get("wiki_name") or os.path.basename(
            os.path.abspath(wiki_root)),
        "currency": cfg.get("currency", "USD"),
        "plan_year": cfg.get("plan_year", ""),
        "geography": cfg.get("geography", ""),
        "stale_days": stale_days,
        "config": cfg,
        "companies": companies_out,
        "plans": plans_out,
        "sources": sources_out,
        "findings": findings,
        "counts": {
            "companies": len(companies_out),
            "plans": len(plans_out),
            "plans_active": sum(1 for p in plans_out
                                if p["fm"].get("status", "active") == "active"),
            "plans_superseded": sum(1 for p in plans_out
                                    if p["fm"].get("status") == "superseded"),
            "plans_stub": sum(1 for p in plans_out if p["is_stub"]),
            "source_records": len(sources_out),
            "findings": len(findings),
            "by_severity": by_sev,
            "by_rule": by_rule,
            "autofixable": sum(1 for f in findings if f["autofix"]),
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Scan a health-insurance-wiki; emit inventory + findings as json.")
    ap.add_argument("--wiki", default=".", help="wiki root (holds SCHEMA.md)")
    ap.add_argument("--out", help="write json here; omit to print to stdout")
    ap.add_argument("--stale-days", type=int,
                    help="override stale_days from _config/wiki-config.md")
    ap.add_argument("--date", help="YYYY-MM-DD; pin 'today' for reproducible runs")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.wiki):
        sys.stderr.write(
            "ERROR: wiki directory not found: %s\n"
            "Nothing has been scaffolded here. Run /hiw-setup first.\n" % args.wiki)
        return 1

    if not os.path.isfile(os.path.join(args.wiki, "SCHEMA.md")) \
            and not os.path.isdir(os.path.join(args.wiki, "companies")):
        sys.stderr.write(
            "ERROR: %s has neither SCHEMA.md nor companies/ — this is not a "
            "health-insurance-wiki.\nRun /hiw-setup to scaffold one, or point "
            "--wiki at the right root.\n" % args.wiki)
        return 1

    try:
        today = (datetime.date.fromisoformat(args.date) if args.date
                 else datetime.date.today())
    except ValueError:
        sys.stderr.write("ERROR: --date must be YYYY-MM-DD, got %r\n" % args.date)
        return 1

    cfg = load_config(args.wiki)
    stale_days = (args.stale_days if args.stale_days is not None
                  else cfg_int(cfg, "stale_days", DEFAULT_STALE_DAYS))

    report = build_report(args.wiki, cfg, stale_days, today)
    payload = json.dumps(report, indent=2, ensure_ascii=False)

    if args.out:
        out_dir = os.path.dirname(os.path.abspath(args.out))
        try:
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(payload + "\n")
            c = report["counts"]
            sys.stderr.write(
                "wrote %s (%d compan%s, %d plan%s, %d finding%s: %d error / %d warn "
                "/ %d info, %d autofixable)\n"
                % (args.out, c["companies"], "y" if c["companies"] == 1 else "ies",
                   c["plans"], "" if c["plans"] == 1 else "s",
                   c["findings"], "" if c["findings"] == 1 else "s",
                   c["by_severity"].get("error", 0), c["by_severity"].get("warn", 0),
                   c["by_severity"].get("info", 0), c["autofixable"]))
        except OSError as exc:
            sys.stderr.write("WARNING: cannot write --out %r: %s\n" % (args.out, exc))
            sys.stdout.write(payload + "\n")
    else:
        sys.stdout.write(payload + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
