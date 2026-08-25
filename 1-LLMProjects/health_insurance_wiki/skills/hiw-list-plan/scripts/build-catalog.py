#!/usr/bin/env python3
"""
build-catalog.py — every plan in the wiki as one self-contained HTML page.

Reads `lint-wiki.py`'s json (the numbers) plus an optional notes json (the narrative
written by the per-company subagents in /hiw-list-plan), joins them on `plan_id`, and
emits a single .html file with no server, no CDN and no build step. Double-click to
open; email it as an attachment.

The division of labour is deliberate and it is the point of this script:

    Python does DATA. Every number in the output came off a plan page's frontmatter
    and was not re-read, re-typed or re-derived by a language model.

    JavaScript does RENDERING. Filtering, sorting and search happen in the browser,
    so the same file answers "cheapest Gold PPO in California" without regenerating.

    The subagents do NARRATIVE, and only narrative. Their prose is merged in by
    plan_id and clearly attributed. If a note disagrees with a number, the number
    wins — and the note is displayed beside it rather than replacing it.

TBD NEVER BECOMES ZERO. A field that is `TBD` renders as `TBD` and sorts LAST in
every ascending sort, in every column. A field that is absent renders as an em dash.
A reader hunting the cheapest plan must not be able to mistake either for free, and a
sort must not silently promote an unknown to the top of the list.

Stdlib only. No pyyaml, no jinja, no requests.

Invocation:
    python3 build-catalog.py --data output/_wiki-data.json \
                             --notes output/_catalog-notes.json \
                             --out output/plan-catalog.html

Exit codes:
    0  catalog written
    1  hard error — data json missing/unparseable, or the template is not beside this script
"""

import argparse
import datetime
import json
import os
import sys
import tempfile

TEMPLATE_NAME = "catalog-template.html"

# The columns the table offers, in order. `key` is a frontmatter key; `kind` drives
# both the cell renderer and the sort comparator on the client.
COLUMNS = [
    {"key": "title",                       "label": "Plan",       "kind": "text"},
    {"key": "company_name",                "label": "Carrier",    "kind": "text"},
    {"key": "metal_tier",                  "label": "Tier",       "kind": "tier"},
    {"key": "network_type",                "label": "Network",    "kind": "text"},
    {"key": "market",                      "label": "Market",     "kind": "text"},
    {"key": "premium_monthly_individual",  "label": "Premium/mo", "kind": "money"},
    {"key": "deductible_individual",       "label": "Deductible", "kind": "money"},
    {"key": "oop_max_individual",          "label": "OOP max",    "kind": "money"},
    {"key": "coinsurance_in_network",      "label": "Coins.",     "kind": "pct"},
    {"key": "copay_primary_care",          "label": "PCP",        "kind": "money"},
    {"key": "copay_specialist",            "label": "Spec.",      "kind": "money"},
    {"key": "confidence",                  "label": "Conf.",      "kind": "conf"},
]

# Surfaced in the per-plan detail drawer, grouped the way a reader compares them.
DETAIL_GROUPS = [
    ("Cost structure", [
        ("premium_monthly_individual", "Premium / mo (individual)", "money"),
        ("premium_monthly_family", "Premium / mo (family)", "money"),
        ("premium_basis", "Premium basis", "text"),
        ("deductible_individual", "Deductible (individual)", "money"),
        ("deductible_family", "Deductible (family)", "money"),
        ("deductible_type", "Deductible type", "text"),
        ("oop_max_individual", "OOP max (individual)", "money"),
        ("oop_max_family", "OOP max (family)", "money"),
        ("coinsurance_in_network", "Coinsurance in-network", "pct"),
        ("coinsurance_out_of_network", "Coinsurance out-of-network", "pct"),
    ]),
    ("Visit cost shares", [
        ("copay_primary_care", "Primary care", "money"),
        ("copay_specialist", "Specialist", "money"),
        ("copay_urgent_care", "Urgent care", "money"),
        ("copay_emergency_room", "Emergency room", "money"),
        ("copay_telehealth", "Telehealth", "money"),
        ("copay_lab", "Lab", "money"),
        ("copay_imaging", "Imaging", "money"),
        ("inpatient_cost_share", "Inpatient", "text"),
    ]),
    ("Pharmacy", [
        ("rx_deductible", "Rx deductible", "money"),
        ("rx_tier1_generic", "Tier 1 generic", "money"),
        ("rx_tier2_preferred_brand", "Tier 2 preferred brand", "money"),
        ("rx_tier3_nonpreferred_brand", "Tier 3 non-preferred", "money"),
        ("rx_tier4_specialty", "Tier 4 specialty", "money"),
    ]),
    ("Network & access", [
        ("network_name", "Network", "text"),
        ("pcp_required", "PCP required", "bool"),
        ("referral_required", "Referral required", "bool"),
        ("out_of_network_covered", "Out-of-network covered", "bool"),
        ("service_area", "Service area", "text"),
        ("states", "States", "list"),
    ]),
    ("Extras & identity", [
        ("hsa_eligible", "HSA eligible", "bool"),
        ("dental_included", "Dental included", "bool"),
        ("vision_included", "Vision included", "bool"),
        ("carrier_plan_code", "Carrier plan code", "text"),
        ("effective_date", "Effective date", "text"),
        ("plan_year", "Plan year", "text"),
        ("aka", "Also known as", "list"),
    ]),
]


def is_tbd(v):
    return isinstance(v, str) and v.strip().upper() == "TBD"


def as_number(value):
    """Bare numbers only. A quoted cost-share string and TBD both return None."""
    if value is None or isinstance(value, (list, dict, bool)):
        return None
    s = str(value).strip()
    if not s or is_tbd(s):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def cell_value(fm, key):
    """
    Normalize one frontmatter value into the shape the client renderer expects.

    Returns {"v": <display string>, "n": <number or None>, "state": ok|tbd|absent}.
    The three states are kept distinct all the way to the DOM because they mean
    three different things (SCHEMA.md § 2.4) and collapsing them is how a catalog
    starts lying.
    """
    if key not in fm:
        return {"v": "", "n": None, "state": "absent"}
    raw = fm[key]
    if is_tbd(raw):
        return {"v": "TBD", "n": None, "state": "tbd"}
    if isinstance(raw, list):
        return {"v": ", ".join(str(x) for x in raw), "n": None,
                "state": "ok" if raw else "absent"}
    s = "" if raw is None else str(raw)
    return {"v": s, "n": as_number(raw), "state": "ok" if s else "absent"}


def load_notes(path):
    """
    Load the per-company narrative notes, if the caller produced any.

    Absent is a normal state: the catalog is complete without them, just drier. A
    malformed notes file is a warning, never a failure — the numbers do not depend
    on it.
    """
    if not path:
        return {}
    if not os.path.isfile(path):
        sys.stderr.write("note: no notes file at %s; building numbers only\n" % path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("WARNING: cannot parse notes %r: %s — building numbers "
                         "only\n" % (path, exc))
        return {}

    out = {"companies": {}, "plans": {}}
    if isinstance(raw, dict):
        for c in raw.get("companies") or []:
            if isinstance(c, dict) and c.get("company"):
                out["companies"][c["company"]] = {
                    "positioning": str(c.get("positioning") or ""),
                    "networks": str(c.get("networks") or ""),
                    "watch_outs": str(c.get("watch_outs") or ""),
                }
        for p in raw.get("plans") or []:
            if isinstance(p, dict) and p.get("plan_id"):
                out["plans"][p["plan_id"]] = {
                    "one_liner": str(p.get("one_liner") or ""),
                    "suits": str(p.get("suits") or ""),
                    "look_elsewhere": str(p.get("look_elsewhere") or ""),
                    "notable_limits": str(p.get("notable_limits") or ""),
                }
    return out


def build_payload(data, notes, include_superseded):
    plans_in = data.get("plans") or []
    companies_in = data.get("companies") or []
    findings = data.get("findings") or []

    fcount = {}
    for f in findings:
        pid = f.get("plan_id")
        if pid:
            d = fcount.setdefault(pid, {"error": 0, "warn": 0, "info": 0})
            d[f.get("severity", "info")] = d.get(f.get("severity", "info"), 0) + 1

    company_names = {c.get("slug"): (c.get("name") or c.get("slug"))
                     for c in companies_in}

    plans_out = []
    for p in plans_in:
        fm = p.get("fm") or {}
        status = fm.get("status", "active")
        if status == "superseded" and not include_superseded:
            continue
        pid = p.get("plan_id")
        row = {c["key"]: cell_value(fm, c["key"]) for c in COLUMNS}
        row["title"] = {"v": p.get("title") or "", "n": None, "state": "ok"}
        row["company_name"] = {
            "v": p.get("company_name") or company_names.get(p.get("company")) or "",
            "n": None, "state": "ok"}

        detail = []
        for group, fields in DETAIL_GROUPS:
            rows = []
            for key, label, kind in fields:
                cv = cell_value(fm, key)
                if cv["state"] == "absent" and not cv["v"]:
                    continue
                rows.append({"label": label, "kind": kind, **cv})
            if rows:
                detail.append({"group": group, "rows": rows})

        note = (notes.get("plans") or {}).get(pid) or {}
        plans_out.append({
            "plan_id": pid,
            "company": p.get("company"),
            "page": p.get("page"),
            "status": status,
            "is_stub": bool(p.get("is_stub")),
            "tbd_core": p.get("tbd_core") or [],
            "tbd_count": len(p.get("tbd_fields") or []),
            "has_source": bool(p.get("has_source_tag")),
            "row": row,
            "detail": detail,
            "note": note,
            "findings": fcount.get(pid, {"error": 0, "warn": 0, "info": 0}),
            "snapshot": p.get("snapshot") or "",
        })

    counted = {}
    for p in plans_out:
        counted[p["company"]] = counted.get(p["company"], 0) + 1

    companies_out = []
    for c in companies_in:
        slug = c.get("slug")
        cfm = c.get("fm") or {}
        note = (notes.get("companies") or {}).get(slug) or {}
        companies_out.append({
            "company": slug,
            "name": c.get("name") or slug,
            "page": c.get("page"),
            "website": cfm.get("website", ""),
            "networks": cfm.get("networks") or [],
            "markets": cfm.get("markets") or [],
            "states": cfm.get("states") or [],
            "plan_count": counted.get(slug, 0),
            "note": note,
        })
    companies_out.sort(key=lambda c: (c["name"] or "").lower())

    return {
        "generated": data.get("generated") or datetime.date.today().isoformat(),
        "wiki_name": data.get("wiki_name") or "health-insurance-wiki",
        "currency": data.get("currency", "USD"),
        "plan_year": data.get("plan_year", ""),
        "geography": data.get("geography", ""),
        "include_superseded": bool(include_superseded),
        "columns": COLUMNS,
        "companies": companies_out,
        "plans": plans_out,
        "totals": {
            "companies": len(companies_out),
            "plans": len(plans_out),
            "plans_with_tbd_core": sum(1 for p in plans_out if p["tbd_core"]),
            "plans_without_source": sum(1 for p in plans_out if not p["has_source"]),
            "stubs": sum(1 for p in plans_out if p["is_stub"]),
            "errors": sum(p["findings"].get("error", 0) for p in plans_out),
        },
    }


def json_island(payload):
    """
    Serialize for embedding in a <script type="application/json"> block.

    `</` is escaped because a plan page can legitimately contain the characters
    `</script>` inside a quoted cost-share note, and an unescaped one terminates the
    block and silently breaks the whole page. This is not hypothetical — it is the
    single most common way a self-contained HTML build goes wrong.
    """
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
        description="Build a self-contained HTML plan catalog from lint-wiki.py json.")
    ap.add_argument("--data", default="output/_wiki-data.json")
    ap.add_argument("--notes", help="optional per-company narrative json")
    ap.add_argument("--out", default="output/plan-catalog.html")
    ap.add_argument("--title", help="override the page title")
    ap.add_argument("--include-superseded", action="store_true",
                    help="include plans with status: superseded")
    args = ap.parse_args(argv)

    try:
        with open(args.data, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("ERROR: cannot read wiki data %r: %s\n"
                         "Run lint-wiki.py --wiki <root> --out %s first.\n"
                         % (args.data, exc, args.data))
        return 1

    tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), TEMPLATE_NAME)
    try:
        with open(tpl_path, "r", encoding="utf-8") as fh:
            template = fh.read()
    except OSError as exc:
        sys.stderr.write("ERROR: template not found beside this script: %s (%s)\n"
                         % (tpl_path, exc))
        return 1

    payload = build_payload(data, load_notes(args.notes), args.include_superseded)
    title = args.title or ("%s — Plan Catalog" % payload["wiki_name"])

    # Substitution order matters: the data island goes LAST so that page content
    # containing a literal {{TITLE}} cannot be substituted into.
    html = template.replace("{{TITLE}}", title)
    html = html.replace("{{CATALOG_DATA}}", json_island(payload))

    atomic_write(args.out, html)
    t = payload["totals"]
    sys.stderr.write(
        "wrote %s (%d compan%s, %d plan%s; %d with a TBD core field, %d with no "
        "source, %d stub%s)\n"
        % (args.out, t["companies"], "y" if t["companies"] == 1 else "ies",
           t["plans"], "" if t["plans"] == 1 else "s",
           t["plans_with_tbd_core"], t["plans_without_source"],
           t["stubs"], "" if t["stubs"] == 1 else "s"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
