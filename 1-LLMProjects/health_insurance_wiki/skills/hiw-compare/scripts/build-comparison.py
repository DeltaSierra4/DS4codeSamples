#!/usr/bin/env python3
"""
build-comparison.py — a side-by-side matrix for two or more named plans, with
deterministic annual-cost modelling.

Takes `lint-wiki.py`'s json plus a list of `plan_id`s and emits one self-contained
.html file: every comparable field as a row, every selected plan as a column, plus
three annual-cost scenarios computed here in Python rather than by a language model.

WHY THE MODEL LIVES HERE. An LLM asked to add up a premium, a deductible and four
specialist copays will usually get it right and will occasionally not, and there is no
way to tell which run you got. Arithmetic on money belongs in code that can be read
once and trusted thereafter. The model is 40 lines; read them.

THE THREE SCENARIOS, and exactly what each assumes:

  Healthy year      12 x premium
                    + <pcp_visits> primary-care copays
                    + <rx_months> tier-1 generic fills
                    Nothing touches the deductible.

  Moderate year     12 x premium
                    + the full individual deductible
                    + <specialist_visits> specialist copays
                    + one imaging study
                    + <rx_months> tier-1 generic fills
                    Assumes the deductible is met and then normal cost-sharing
                    applies. This is the softest of the three and the one to argue
                    with; the counts are tunable in `_config/wiki-config.md`.

  Bad year          12 x premium + the individual out-of-pocket maximum
                    This one is EXACT, not illustrative. In-network, the OOP max is
                    the ceiling on everything except premium, so premium + OOP max
                    is the true worst-case annual exposure. It is usually the most
                    decision-relevant number on the page and the least quoted.

TBD PROPAGATES. If any input to a scenario is TBD or absent, that scenario is
reported as UNCOMPUTABLE with the missing inputs named. It is never computed with the
missing term treated as zero. A cheapest-plan ranking built by silently dropping an
unknown deductible is not a conservative estimate — it is a wrong answer wearing the
shape of a right one.

Rankings are computed only across plans where the scenario IS computable, and the
count is always displayed, so "cheapest of 3 of 5 plans" can never read as
"cheapest of 5".

Stdlib only.

Invocation:
    python3 build-comparison.py --data output/_wiki-data.json \
        --plans "blue-shield-ca__gold-80-ppo-750-35,kaiser-permanente__gold-80-hmo-0-30" \
        --out output/comparison-2026-08-25.html

    python3 build-comparison.py --data ... --plans-file output/_selection.txt --out ...
    python3 build-comparison.py --data ... --plans "a,b" --out x.html \
        --json output/_comparison.json      # the computed totals, for /hiw-query
    python3 build-comparison.py --data ... --list          # print available plan_ids

Exit codes:
    0  comparison written
    1  hard error — data json unreadable, template missing, or fewer than two
       resolvable plan ids
"""

import argparse
import datetime
import json
import os
import sys
import tempfile

TEMPLATE_NAME = "comparison-template.html"

DEFAULTS = {"pcp_visits": 2, "specialist_visits": 4, "rx_months": 12}

# Every row of the matrix, in the order a person actually compares them.
# kind drives the renderer; `better` drives the highlight: lo = lower is better,
# hi = higher is better, None = no ordering (a fact, not a score).
ROWS = [
    ("Identity", [
        ("company_name", "Carrier", "text", None),
        ("plan_year", "Plan year", "text", None),
        ("market", "Market", "text", None),
        ("metal_tier", "Metal tier", "tier", None),
        ("network_type", "Network type", "text", None),
        ("carrier_plan_code", "Carrier plan code", "text", None),
    ]),
    ("Premium", [
        ("premium_monthly_individual", "Premium / mo — individual", "money", "lo"),
        ("premium_monthly_family", "Premium / mo — family", "money", "lo"),
        ("premium_basis", "Premium basis", "text", None),
    ]),
    ("Deductible & ceiling", [
        ("deductible_individual", "Deductible — individual", "money", "lo"),
        ("deductible_family", "Deductible — family", "money", "lo"),
        ("deductible_type", "Deductible type", "text", None),
        ("oop_max_individual", "Out-of-pocket max — individual", "money", "lo"),
        ("oop_max_family", "Out-of-pocket max — family", "money", "lo"),
        ("coinsurance_in_network", "Coinsurance in-network (member pays)", "pct", "lo"),
        ("coinsurance_out_of_network", "Coinsurance out-of-network", "pct", "lo"),
    ]),
    ("Visit cost shares", [
        ("copay_primary_care", "Primary care", "money", "lo"),
        ("copay_specialist", "Specialist", "money", "lo"),
        ("copay_urgent_care", "Urgent care", "money", "lo"),
        ("copay_emergency_room", "Emergency room", "money", "lo"),
        ("copay_telehealth", "Telehealth", "money", "lo"),
        ("copay_lab", "Lab", "money", "lo"),
        ("copay_imaging", "Imaging", "money", "lo"),
        ("inpatient_cost_share", "Inpatient", "text", None),
    ]),
    ("Pharmacy", [
        ("rx_deductible", "Rx deductible", "money", "lo"),
        ("rx_tier1_generic", "Tier 1 — generic", "money", "lo"),
        ("rx_tier2_preferred_brand", "Tier 2 — preferred brand", "money", "lo"),
        ("rx_tier3_nonpreferred_brand", "Tier 3 — non-preferred brand", "money", "lo"),
        ("rx_tier4_specialty", "Tier 4 — specialty", "money", "lo"),
    ]),
    ("Network & access", [
        ("network_name", "Network", "text", None),
        ("pcp_required", "PCP required", "bool", None),
        ("referral_required", "Referral required", "bool", None),
        ("out_of_network_covered", "Out-of-network covered", "bool", None),
        ("service_area", "Service area", "text", None),
        ("states", "States", "list", None),
    ]),
    ("Extras", [
        ("hsa_eligible", "HSA eligible", "bool", None),
        ("dental_included", "Dental included", "bool", None),
        ("vision_included", "Vision included", "bool", None),
    ]),
    ("Provenance", [
        ("confidence", "Confidence", "conf", None),
        ("status", "Status", "text", None),
        ("effective_date", "Effective date", "text", None),
        ("last_updated", "Page last updated", "text", None),
        ("sources", "Sources", "list", None),
    ]),
]


def is_tbd(v):
    return isinstance(v, str) and v.strip().upper() == "TBD"


def as_number(value):
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


# ---------------------------------------------------------------------------
# The cost model. Read it; it is the whole reason this script exists.
# ---------------------------------------------------------------------------

def term(fm, key, multiplier, missing, label):
    """
    One addend. Returns its value, or records the key as missing and returns None.

    A term whose input is TBD or absent does not become zero. It disqualifies the
    whole scenario, and the reason is named so the reader knows what to go find.
    """
    n = as_number(fm.get(key))
    if n is None:
        if is_tbd(fm.get(key)):
            why = "TBD"
        elif key not in fm:
            # An absent key means "this dimension does not apply to this plan"
            # (SCHEMA.md § 2.4) — but a scenario cannot tell that from an ingest that
            # simply never wrote the key. Refusing is the honest response either way,
            # and naming the remedy is what turns the refusal into a task.
            why = "key absent — write the value or TBD on the plan page"
        else:
            why = "not a bare number: %r" % str(fm.get(key))[:40]
        missing.append("%s (%s)" % (label, why))
        return None
    return n * multiplier


def scenario(fm, spec, opts):
    """
    Compute one scenario. Returns
        {"total": float|None, "missing": [str], "breakdown": [{label, amount}]}

    `total` is None whenever `missing` is non-empty. There is no partial total, on
    purpose: a partial total is a number a reader will use.
    """
    missing, breakdown, total = [], [], 0.0
    for key, mult, label in spec:
        m = mult(opts) if callable(mult) else mult
        v = term(fm, key, m, missing, label)
        if v is not None:
            breakdown.append({"label": label, "mult": m, "amount": round(v, 2)})
            total += v
    if missing:
        return {"total": None, "missing": missing, "breakdown": breakdown}
    return {"total": round(total, 2), "missing": [], "breakdown": breakdown}


def build_scenarios(fm, opts):
    healthy = [
        ("premium_monthly_individual", 12, "Premium x 12"),
        ("copay_primary_care", lambda o: o["pcp_visits"],
         "Primary care x %d" % opts["pcp_visits"]),
        ("rx_tier1_generic", lambda o: o["rx_months"],
         "Tier-1 generic x %d" % opts["rx_months"]),
    ]
    moderate = [
        ("premium_monthly_individual", 12, "Premium x 12"),
        ("deductible_individual", 1, "Deductible, met in full"),
        ("copay_specialist", lambda o: o["specialist_visits"],
         "Specialist x %d" % opts["specialist_visits"]),
        ("copay_imaging", 1, "Imaging x 1"),
        ("rx_tier1_generic", lambda o: o["rx_months"],
         "Tier-1 generic x %d" % opts["rx_months"]),
    ]
    bad = [
        ("premium_monthly_individual", 12, "Premium x 12"),
        ("oop_max_individual", 1, "Out-of-pocket maximum"),
    ]
    return {
        "healthy": scenario(fm, healthy, opts),
        "moderate": scenario(fm, moderate, opts),
        "bad": scenario(fm, bad, opts),
    }


SCENARIO_META = [
    ("healthy", "Healthy year",
     "Premium for the year plus routine primary care and a generic prescription. "
     "Nothing touches the deductible. Illustrative."),
    ("moderate", "Moderate year",
     "Premium plus the full individual deductible, some specialist care, one "
     "imaging study and a generic prescription. Illustrative, and the softest of "
     "the three — the visit counts are assumptions, not facts about you."),
    ("bad", "Bad year (worst case)",
     "Premium plus the individual out-of-pocket maximum. In-network this is EXACT: "
     "the OOP max is the ceiling on everything except premium. It is the number "
     "that decides how much a bad year can actually cost."),
]


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def resolve_ids(data, requested):
    """
    Match each requested id against the wiki, tolerantly, and report every miss.

    Accepts a full `plan_id`, a bare plan slug, or a case-insensitive title. Exact
    plan_id first, always — a tolerant matcher that silently prefers a title over an
    id is how the wrong plan ends up in a comparison.
    """
    plans = data.get("plans") or []
    by_id = {p.get("plan_id"): p for p in plans}
    by_slug, by_title = {}, {}
    for p in plans:
        by_slug.setdefault(p.get("slug"), []).append(p)
        by_title.setdefault(str(p.get("title", "")).strip().lower(), []).append(p)

    picked, misses, ambiguous = [], [], []
    for want in requested:
        w = want.strip()
        if not w:
            continue
        if w in by_id:
            picked.append(by_id[w])
            continue
        for table in (by_slug, by_title):
            key = w.lower() if table is by_title else w
            hits = table.get(key) or []
            if len(hits) == 1:
                picked.append(hits[0])
                break
            if len(hits) > 1:
                ambiguous.append((w, [h.get("plan_id") for h in hits]))
                break
        else:
            misses.append(w)

    seen, unique = set(), []
    for p in picked:
        if p.get("plan_id") not in seen:
            seen.add(p.get("plan_id"))
            unique.append(p)
    return unique, misses, ambiguous


def build_payload(data, chosen, opts, notes):
    plans = []
    for p in chosen:
        fm = p.get("fm") or {}
        plans.append({
            "plan_id": p.get("plan_id"),
            "title": p.get("title"),
            "company": p.get("company"),
            "company_name": p.get("company_name"),
            "page": p.get("page"),
            "status": fm.get("status", "active"),
            "tbd_core": p.get("tbd_core") or [],
            "has_source": bool(p.get("has_source_tag")),
            "cells": {},
            "scenarios": build_scenarios(fm, opts),
            "snapshot": p.get("snapshot") or "",
            "fit_notes": p.get("fit_notes") or "",
            "note": (notes.get(p.get("plan_id")) or {}),
        })

    for grp, fields in ROWS:
        for key, _label, _kind, _better in fields:
            for out, src in zip(plans, chosen):
                out["cells"][key] = cell_value(src.get("fm") or {}, key)

    # Rankings, computed only over the plans where the value exists at all.
    rank = {}
    for grp, fields in ROWS:
        for key, _label, kind, better in fields:
            if not better or kind not in ("money", "pct"):
                continue
            vals = [(p["plan_id"], p["cells"][key]["n"]) for p in plans
                    if p["cells"][key]["state"] == "ok"
                    and p["cells"][key]["n"] is not None]
            if len(vals) < 2:
                continue
            best = (min if better == "lo" else max)(v for _i, v in vals)
            rank[key] = {"best": best, "comparable": len(vals), "total": len(plans),
                         "winners": [i for i, v in vals if v == best]}

    scen_rank = {}
    for skey, _label, _desc in SCENARIO_META:
        vals = [(p["plan_id"], p["scenarios"][skey]["total"]) for p in plans
                if p["scenarios"][skey]["total"] is not None]
        if len(vals) >= 2:
            best = min(v for _i, v in vals)
            scen_rank[skey] = {"best": best, "comparable": len(vals),
                               "total": len(plans),
                               "winners": [i for i, v in vals if v == best]}

    findings = data.get("findings") or []
    ids = {p["plan_id"] for p in plans}
    relevant = [{"rule": f["rule"], "severity": f["severity"], "page": f["page"],
                 "plan_id": f.get("plan_id"), "message": f["message"]}
                for f in findings
                if f.get("plan_id") in ids and f["severity"] in ("error", "warn")]

    return {
        "generated": data.get("generated") or datetime.date.today().isoformat(),
        "wiki_name": data.get("wiki_name") or "health-insurance-wiki",
        "currency": data.get("currency", "USD"),
        "plan_year": data.get("plan_year", ""),
        "rows": [{"group": g, "fields": [
            {"key": k, "label": l, "kind": kd, "better": b} for k, l, kd, b in fs]}
            for g, fs in ROWS],
        "scenario_meta": [{"key": k, "label": l, "desc": d}
                          for k, l, d in SCENARIO_META],
        "assumptions": opts,
        "plans": plans,
        "rank": rank,
        "scenario_rank": scen_rank,
        "findings": relevant,
        "totals": {
            "plans": len(plans),
            "errors": sum(1 for f in relevant if f["severity"] == "error"),
            "warns": sum(1 for f in relevant if f["severity"] == "warn"),
            "uncomputable": sum(
                1 for p in plans for s in p["scenarios"].values()
                if s["total"] is None),
        },
    }


def json_island(payload):
    """Escape `</` so a quoted cost-share note can never terminate the script block."""
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


def load_notes(path):
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("WARNING: cannot parse notes %r: %s\n" % (path, exc))
        return {}
    out = {}
    for p in (raw.get("plans") if isinstance(raw, dict) else None) or []:
        if isinstance(p, dict) and p.get("plan_id"):
            out[p["plan_id"]] = {
                "one_liner": str(p.get("one_liner") or ""),
                "suits": str(p.get("suits") or ""),
                "look_elsewhere": str(p.get("look_elsewhere") or ""),
                "notable_limits": str(p.get("notable_limits") or ""),
                "exclusions": str(p.get("exclusions") or ""),
            }
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Build a side-by-side plan comparison with annual cost modelling.")
    ap.add_argument("--data", default="output/_wiki-data.json")
    ap.add_argument("--plans", help="comma-separated plan_ids (or slugs, or titles)")
    ap.add_argument("--plans-file", help="file with one plan_id per line")
    ap.add_argument("--notes", help="optional per-plan narrative json")
    ap.add_argument("--out", help="output html path")
    ap.add_argument("--json", dest="json_out",
                    help="also write the computed payload here as json, or - for "
                         "stdout. This is how /hiw-query reads the scenario totals: "
                         "scraping them back out of the HTML island would mean two "
                         "readers of one number, and the second one drifting.")
    ap.add_argument("--title", help="override the page title")
    ap.add_argument("--list", action="store_true",
                    help="print every plan_id in the wiki and exit")
    ap.add_argument("--pcp-visits", type=int)
    ap.add_argument("--specialist-visits", type=int)
    ap.add_argument("--rx-months", type=int)
    args = ap.parse_args(argv)

    try:
        with open(args.data, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write("ERROR: cannot read wiki data %r: %s\n"
                         "Run lint-wiki.py --wiki <root> --out %s first.\n"
                         % (args.data, exc, args.data))
        return 1

    if args.list:
        for p in sorted(data.get("plans") or [],
                        key=lambda x: (x.get("company") or "", x.get("title") or "")):
            sys.stdout.write("%s\t%s\t%s\n" % (p.get("plan_id"),
                                               p.get("company_name"),
                                               p.get("title")))
        return 0

    requested = []
    if args.plans:
        requested += [s for s in args.plans.split(",")]
    if args.plans_file:
        try:
            with open(args.plans_file, "r", encoding="utf-8") as fh:
                requested += [l.strip() for l in fh if l.strip()
                              and not l.startswith("#")]
        except OSError as exc:
            sys.stderr.write("ERROR: cannot read --plans-file %r: %s\n"
                             % (args.plans_file, exc))
            return 1
    if not requested:
        sys.stderr.write(
            "ERROR: no plans given. Pass --plans with two or more comma-separated "
            "ids, or --list to see what is available.\n")
        return 1

    chosen, misses, ambiguous = resolve_ids(data, requested)
    for w in misses:
        sys.stderr.write("WARNING: no plan matches %r — skipped\n" % w)
    for w, hits in ambiguous:
        sys.stderr.write("WARNING: %r matches %d plans (%s) — skipped; name it by "
                         "plan_id\n" % (w, len(hits), ", ".join(hits)))
    if len(chosen) < 2:
        sys.stderr.write(
            "ERROR: resolved %d plan(s); a comparison needs at least two.\n"
            "Run with --list to see every plan_id in this wiki.\n" % len(chosen))
        return 1

    cfg = data.get("config") or {}
    def pick(flag, cfg_key, default):
        if flag is not None:
            return flag
        try:
            return int(str(cfg.get(cfg_key, default)).strip())
        except (ValueError, TypeError):
            return default
    opts = {
        "pcp_visits": pick(args.pcp_visits, "cost_model_pcp_visits",
                           DEFAULTS["pcp_visits"]),
        "specialist_visits": pick(args.specialist_visits,
                                  "cost_model_specialist_visits",
                                  DEFAULTS["specialist_visits"]),
        "rx_months": pick(args.rx_months, "cost_model_rx_months",
                          DEFAULTS["rx_months"]),
    }

    tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), TEMPLATE_NAME)
    try:
        with open(tpl_path, "r", encoding="utf-8") as fh:
            template = fh.read()
    except OSError as exc:
        sys.stderr.write("ERROR: template not found beside this script: %s (%s)\n"
                         % (tpl_path, exc))
        return 1

    payload = build_payload(data, chosen, opts, load_notes(args.notes))
    title = args.title or ("Plan comparison — %d plans" % len(chosen))
    out = args.out or ("output/comparison-%s.html" % payload["generated"])

    # Substitution order matters: the data island goes LAST so that page content
    # carrying a literal {{TITLE}} cannot be substituted into.
    html = template.replace("{{TITLE}}", title)
    html = html.replace("{{COMPARISON_DATA}}", json_island(payload))

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
        "wrote %s (%d plans; %d scenario(s) uncomputable for want of a TBD input; "
        "%d error / %d warn on the pages compared)\n"
        % (out, t["plans"], t["uncomputable"], t["errors"], t["warns"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
