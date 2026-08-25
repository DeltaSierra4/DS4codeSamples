#!/usr/bin/env python3
"""
new-page.py — emit a schema-conformant skeleton for a plan, company or source page.

`/hiw-ingest` uses this so the SHAPE of a page is never retyped from memory. The
agent supplies the facts; this script guarantees that every required key exists, the
nine sections are present in contract order, the slug and `plan_id` agree with the
path, and an unstated field lands as `TBD` rather than as a plausible number.

Every cost field the caller does not supply is written as `TBD`. That is the whole
point: `TBD` means "this plan has this dimension and we do not know it", the linter
counts it, and `/hiw-refresh` goes after it. A skeleton that omitted the key instead
would claim the dimension does not apply — a quieter and more permanent kind of wrong.

REFUSES TO OVERWRITE. If the target page exists, the script exits 3 and prints the
path. An existing page is updated under the resolution policy in `SCHEMA.md` § 7.2,
by reading it first — never by regenerating it from a partial fact set, which is how
a page loses every field the current source happens not to mention.

Field values come from --set KEY=VALUE (repeatable) or a --json file. Nothing is
inferred from anything: no metal tier guessed from a premium, no deductible copied
from a sibling plan.

Invocation:
    python3 new-page.py plan --wiki WIKI --company blue-shield-ca \
        --company-name "Blue Shield of California" --title "Gold 80 PPO 750/35" \
        --set market=individual --set network_type=PPO \
        --set premium_monthly_individual=612.40 --source blue-2026-sbc.pdf

    python3 new-page.py company --wiki WIKI --company blue-shield-ca \
        --company-name "Blue Shield of California" --set website=https://...

    python3 new-page.py source --wiki WIKI --company blue-shield-ca \
        --title "Blue Shield 2026 SBC" --set source_type=pdf \
        --set source_ref=blue-2026-sbc.pdf --set authority=official

    python3 new-page.py plan ... --print      # to stdout, write nothing

Exit codes:
    0  page written (or printed)
    1  hard error — bad arguments, unwritable path, unknown key
    3  the page already exists; read and update it instead
"""

import argparse
import datetime
import json
import os
import re
import sys
import tempfile

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

# Frontmatter key order on a plan page. Grouped the way SCHEMA.md § 2 shows it,
# because a consistent order is what makes two plan pages diffable by eye.
PLAN_KEY_ORDER = [
    "title", "plan_id", "aka", "company", "company_name", "plan_year", "market",
    "network_type", "metal_tier", "hsa_eligible", "carrier_plan_code", "states",
    "service_area",
    "premium_monthly_individual", "premium_monthly_family", "premium_basis",
    "deductible_individual", "deductible_family", "deductible_type",
    "oop_max_individual", "oop_max_family",
    "coinsurance_in_network", "coinsurance_out_of_network",
    "copay_primary_care", "copay_specialist", "copay_urgent_care",
    "copay_emergency_room", "copay_telehealth", "copay_lab", "copay_imaging",
    "inpatient_cost_share",
    "rx_deductible", "rx_tier1_generic", "rx_tier2_preferred_brand",
    "rx_tier3_nonpreferred_brand", "rx_tier4_specialty",
    "network_name", "pcp_required", "referral_required", "out_of_network_covered",
    "dental_included", "vision_included",
    "sources", "source_urls", "effective_date", "created", "last_updated",
    "updated_by", "confidence", "status",
]

# Written as TBD when the caller does not supply them: a plan has these dimensions
# whether or not the source stated them.
# Written as TBD when the caller does not supply them. Two groups:
#   - the fields /hiw-compare's cost model needs (premium, deductible, oop max,
#     primary care, specialist, imaging, tier-1 generic). A key absent here makes a
#     whole cost scenario refuse to compute, which is a far less visible failure than
#     a TBD in a column — so the skeleton always writes them.
#   - the fields every plan has by definition (tier, basis, network name).
PLAN_TBD_DEFAULT = [
    "metal_tier", "premium_monthly_individual", "premium_monthly_family",
    "premium_basis", "deductible_individual", "deductible_family",
    "deductible_type", "oop_max_individual", "oop_max_family",
    "coinsurance_in_network", "copay_primary_care", "copay_specialist",
    "copay_emergency_room", "copay_imaging", "rx_tier1_generic", "network_name",
]
# Left ABSENT when not supplied: these genuinely do not apply to every plan, and
# writing TBD would assert that they do.
PLAN_OPTIONAL = [
    "carrier_plan_code", "service_area", "hsa_eligible",
    "coinsurance_out_of_network", "copay_urgent_care", "copay_telehealth",
    "copay_lab", "inpatient_cost_share", "rx_deductible",
    "rx_tier2_preferred_brand", "rx_tier3_nonpreferred_brand",
    "rx_tier4_specialty", "pcp_required", "referral_required",
    "out_of_network_covered", "dental_included", "vision_included",
    "effective_date",
]
LIST_KEYS = {"aka", "states", "sources", "source_urls", "markets", "networks"}
QUOTED_KEYS = {"plan_id", "carrier_plan_code", "website", "source_url",
               "network_name", "inpatient_cost_share", "rx_tier4_specialty",
               "service_area"}

COMPANY_KEY_ORDER = [
    "title", "company", "category", "plan_year", "markets", "states", "networks",
    "plan_count", "website", "sources", "created", "last_updated", "updated_by",
    "status",
]
SOURCE_KEY_ORDER = [
    "title", "category", "company", "source_type", "source_ref", "source_url",
    "retrieved", "publisher", "plan_year", "authority", "created", "last_updated",
    "updated_by", "status",
]

ALL_KNOWN = set(PLAN_KEY_ORDER) | set(COMPANY_KEY_ORDER) | set(SOURCE_KEY_ORDER)


def slugify(text):
    """Kebab-case per SCHEMA.md § 1.1: `&` -> `and`, everything else non-alnum out."""
    s = str(text or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def quote_list_item(item):
    """
    Quote a flow-sequence item that would be ambiguous unquoted.

    A URL is the case that matters: `[https://x.com/a]` parses today but any item
    carrying a `: ` or a `#` does not, and the schema's own examples quote URLs. A
    list is read by every consumer, so an item that parses on one reader and not
    another is a silent data loss.
    """
    s = item.strip()
    if s.startswith(('"', "'")):
        return s
    if re.search(r"^\w+://|[:#,\[\]{}]|^\s|\s$", s):
        return '"%s"' % s.replace('"', '\\"')
    return s


def fmt_value(key, value):
    """
    Render one frontmatter value.

    Money and percentages go out bare; ids and free-text cost shares go out quoted;
    lists go out in inline flow style. `TBD` is never quoted — a quoted "TBD" would
    read as a string value rather than as the sentinel.
    """
    if isinstance(value, list):
        return "[%s]" % ", ".join(quote_list_item(str(v)) for v in value)
    s = str(value)
    if s.upper() == "TBD":
        return "TBD"
    if key in LIST_KEYS:
        inner = [p.strip() for p in s.strip("[]").split(",") if p.strip()]
        return "[%s]" % ", ".join(quote_list_item(x) for x in inner)
    if key in QUOTED_KEYS and not (s.startswith('"') or s.startswith("'")):
        return '"%s"' % s
    return s


def frontmatter(order, values):
    lines = ["---"]
    for key in order:
        if key not in values:
            continue
        lines.append("%s: %s" % (key, fmt_value(key, values[key])))
    # Anything the caller set that is not in the canonical order still gets written,
    # at the end, rather than silently dropped.
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
            out.append("_TBD._")
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
            "SCHEMA.md § 2 defines the key set. A key it does not define belongs in "
            "the page body under `## Additional capture`, not in the frontmatter — "
            "an unknown key is invisible to every comparison.\n" % ", ".join(unknown))
        return None
    return values


def build_plan(args, values, today):
    company = args.company
    company_name = args.company_name or company.replace("-", " ").title()
    title = args.title
    plan_slug = args.slug or slugify(title)
    plan_id = "%s__%s" % (company, plan_slug)

    fm = {
        "title": title,
        "plan_id": plan_id,
        "aka": values.get("aka", []),
        "company": company,
        "company_name": company_name,
        "plan_year": values.get("plan_year", args.plan_year or today.year),
        "market": values.get("market", "TBD"),
        "network_type": values.get("network_type", "TBD"),
        "states": values.get("states", []),
        "sources": values.get("sources", args.source or []),
        "source_urls": values.get("source_urls", args.source_url or []),
        "created": values.get("created", today.isoformat()),
        "last_updated": values.get("last_updated", today.isoformat()),
        "updated_by": values.get("updated_by", "hiw-ingest"),
        "confidence": values.get("confidence", "low"),
        "status": values.get("status", "active"),
    }
    for key in PLAN_TBD_DEFAULT:
        fm[key] = values.get(key, "TBD")
    for key in PLAN_OPTIONAL:
        if key in values:
            fm[key] = values[key]
    for key, val in values.items():
        if key in PLAN_KEY_ORDER:
            fm[key] = val

    heading = "# %s — %s (%s)" % (title, company_name, fm["plan_year"])
    seeded = {}
    if args.source:
        seeded["Snapshot"] = (
            "_Skeleton created by `/hiw-ingest`. Awaiting the facts from "
            "%s._\n[source: %s]" % (", ".join(args.source), ", ".join(args.source)))
    doc = "\n".join([frontmatter(PLAN_KEY_ORDER, fm), "", heading, "",
                     sections(PLAN_SECTIONS, seeded)])
    rel = "companies/%s/plans/%s.md" % (company, plan_slug)
    return rel, doc.rstrip() + "\n"


def build_company(args, values, today):
    company = args.company
    name = args.company_name or args.title or company.replace("-", " ").title()
    fm = {
        "title": name,
        "company": company,
        "category": "company",
        "plan_year": values.get("plan_year", args.plan_year or today.year),
        "markets": values.get("markets", []),
        "states": values.get("states", []),
        "networks": values.get("networks", []),
        "plan_count": values.get("plan_count", 0),
        "sources": values.get("sources", args.source or []),
        "created": values.get("created", today.isoformat()),
        "last_updated": values.get("last_updated", today.isoformat()),
        "updated_by": values.get("updated_by", "hiw-ingest"),
        "status": values.get("status", "active"),
    }
    if "website" in values:
        fm["website"] = values["website"]
    seeded = {"Plans Offered":
              "| Plan | Tier | Network | Premium/mo | Deductible | OOP max | Page |\n"
              "|---|---|---|---|---|---|---|"}
    doc = "\n".join([frontmatter(COMPANY_KEY_ORDER, fm), "", "# %s" % name, "",
                     sections(COMPANY_SECTIONS, seeded)])
    return "companies/%s/company.md" % company, doc.rstrip() + "\n"


def build_source(args, values, today):
    company = args.company
    title = args.title
    slug = args.slug or slugify(values.get("source_ref") or title)
    fm = {
        "title": title,
        "category": "sources",
        "company": company,
        "source_type": values.get("source_type", "TBD"),
        "source_ref": values.get("source_ref", slug),
        "retrieved": values.get("retrieved", today.isoformat()),
        "authority": values.get("authority", "TBD"),
        "created": values.get("created", today.isoformat()),
        "last_updated": values.get("last_updated", today.isoformat()),
        "updated_by": values.get("updated_by", "hiw-ingest"),
        "status": values.get("status", "active"),
    }
    for key in ("source_url", "publisher", "plan_year"):
        if key in values:
            fm[key] = values[key]

    seeded = {
        "Metadata": "\n".join([
            "- Source ref: %s" % fm["source_ref"],
            "- Type: %s" % fm["source_type"],
            "- URL: %s" % values.get("source_url", "n/a"),
            "- Retrieved: %s" % fm["retrieved"],
            "- Publisher: %s" % values.get("publisher", "TBD"),
            "- Plan year: %s" % values.get("plan_year", "TBD"),
            "- Authority: %s" % fm["authority"],
            "- Pages or sections read: TBD",
        ]),
        "Key extractions": "_TBD — one line per fact set, each naming its "
                           "destination page and section by wiki-relative path._",
        "Coverage": "| Plan page | Sections touched |\n|---|---|",
    }
    doc = "\n".join([frontmatter(SOURCE_KEY_ORDER, fm), "", "# %s" % title, "",
                     sections(SOURCE_SECTIONS, seeded)])
    return "companies/%s/sources/%s.md" % (company, slug), doc.rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Emit a schema-conformant plan, company or source page skeleton.")
    ap.add_argument("kind", choices=["plan", "company", "source"])
    ap.add_argument("--wiki", default=".", help="wiki root")
    ap.add_argument("--company", required=True, help="company slug (kebab-case)")
    ap.add_argument("--company-name", help="the carrier's display name")
    ap.add_argument("--title", help="plan or source title (required for those kinds)")
    ap.add_argument("--slug", help="override the derived file slug")
    ap.add_argument("--plan-year", type=int)
    ap.add_argument("--source", action="append",
                    help="a source_ref to cite; repeatable")
    ap.add_argument("--source-url", action="append", help="a source URL; repeatable")
    ap.add_argument("--set", action="append", dest="sets",
                    help="KEY=VALUE frontmatter override; repeatable")
    ap.add_argument("--json", help="a flat json object of frontmatter values")
    ap.add_argument("--print", action="store_true", dest="to_stdout",
                    help="print the page instead of writing it")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing page. Read SCHEMA.md § 7.2 first.")
    args = ap.parse_args(argv)

    if args.kind in ("plan", "source") and not args.title:
        sys.stderr.write("ERROR: --title is required for a %s page\n" % args.kind)
        return 1
    if args.company != slugify(args.company):
        sys.stderr.write(
            "ERROR: --company %r is not kebab-case; use %r. The folder name is the "
            "carrier's durable identity (SCHEMA.md § 1.1) and renaming it later "
            "breaks every plan_id under it.\n" % (args.company, slugify(args.company)))
        return 1

    values = parse_sets(args.sets, args.json)
    if values is None:
        return 1

    today = datetime.date.today()
    builder = {"plan": build_plan, "company": build_company,
               "source": build_source}[args.kind]
    rel, doc = builder(args, values, today)

    if args.to_stdout:
        sys.stdout.write(doc)
        sys.stderr.write("would write %s\n" % rel)
        return 0

    path = os.path.join(args.wiki, rel.replace("/", os.sep))
    if os.path.exists(path) and not args.force:
        sys.stderr.write(
            "%s already exists.\n"
            "Read it and update it under the resolution policy (SCHEMA.md § 7.2). Do "
            "NOT regenerate it from this run's facts — a skeleton rebuilt from a "
            "partial fact set silently drops every field the current source happens "
            "not to mention.\n" % rel)
        return 3

    try:
        atomic_write(path, doc)
    except OSError as exc:
        sys.stderr.write("ERROR: cannot write %s: %s\n" % (path, exc))
        return 1

    tbd = len(re.findall(r":\s*TBD\s*$", doc, re.M))
    sys.stderr.write("wrote %s (%d field(s) as TBD — run /hiw-refresh or re-read the "
                     "source to fill them)\n" % (rel, tbd))
    return 0


if __name__ == "__main__":
    sys.exit(main())
