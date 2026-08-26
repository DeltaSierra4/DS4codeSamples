#!/usr/bin/env python3
"""
extract-pdf.py — text and an AUTHORIZED LINK PLAN out of one PDF or text file.

Two jobs, and the second is the important one.

TEXT. Tries `pdftotext -layout` for a PDF, reads a .txt directly. `-layout` is not
optional: without it a two-column paper interleaves its columns and a claim ends up
attributed to the wrong section. Where pdftotext is absent or fails, this script EXITS 2
and tells the caller to read the file with the agent's own native reader. It does not
return partial or garbled text — a plausible mis-extraction of a benchmark table is worse
than no extraction, because either way the number lands in the library.

THE LINK PLAN. Extracts every URL in the document, filters the junk, classifies what is
left, caps it, and writes `output/_linkplan-<slug>.json` with every entry stamped
`depth: 1`.

    That file is the COMPLETE AND ONLY set of URLs authorized for fetching from this
    document. Not a starting point, not a suggestion. `/ai-lib-lint` checks every capture
    page's `source_url` against these plans, and a capture whose URL is in no plan is an
    error — that is the signature of a second-hop fetch.

A script cannot do the fetching (web access belongs to the agent's fetch tool), so the
one-hop limit cannot be physically enforced here. It is made AUDITABLE instead: the plan
is the authorization surface, and the audit is the linter. Which is why this script writes
the plan even when it finds zero links — an absent plan and an empty plan are different
facts, and only one of them means "nothing was authorized".

WHAT IT CANNOT SEE. A URL that exists only as a PDF link annotation, with anchor text and
no visible address, is invisible to a text-layer extractor. Those are reported as
`annotation_links_possible` so the caller knows to look. Where the agent finds one, the
correct move is to ADD IT TO THE PLAN FILE and record that it did — never to fetch it
unrecorded, which defeats the audit.

Stdlib only (argparse, hashlib, json, os, re, shutil, subprocess, sys, urllib.parse).
No network calls of any kind.

Invocation:
    python3 extract-pdf.py <path> --out-text output/_extract-<slug>.txt \
                                  --out-plan output/_linkplan-<slug>.json
    python3 extract-pdf.py <path> --links-only          # plan to stdout, no text
    python3 extract-pdf.py <path> --max-links 25 --deny twitter.com,x.com

Exit codes:
    0  text extracted and plan written
    1  hard error — file missing, unreadable, or a corrupt PDF
    2  unsupported or un-extractable; read it with the agent's native reader instead
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit, urlunsplit

MAX_LINKS_DEFAULT = 25

# Social and aggregator domains are excluded by default: a link to a post is almost never
# the substance, and those pages are JS-only in practice anyway.
DENY_DEFAULT = ["twitter.com", "x.com", "facebook.com", "instagram.com",
                "linkedin.com", "reddit.com", "t.co", "bit.ly", "lnkd.in"]

# Ranked first when the cap bites. Not fetched preferentially in any other sense.
PREFER_DEFAULT = ["arxiv.org", "github.com", "openreview.net", "aclanthology.org",
                  "nature.com", "science.org", "acm.org", "ieee.org", "doi.org",
                  "pubmed.ncbi.nlm.nih.gov", "huggingface.co"]

# Extensions that are assets rather than readable pages.
ASSET_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".svg",
             ".ico", ".mp4", ".mov", ".avi", ".webm", ".mp3", ".wav", ".m4a",
             ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
             ".woff", ".woff2", ".ttf", ".eot", ".css", ".js", ".map",
             ".exe", ".dmg", ".pkg", ".deb", ".rpm"}

# Path fragments that mean "not content".
JUNK_PATH = re.compile(
    r"/(login|signin|sign-in|signup|sign-up|register|logout|account|cart|checkout|"
    r"subscribe|unsubscribe|newsletter|privacy|terms|cookie|legal|imprint|"
    r"share|intent|sitemap|rss|feed|search|tag|tags|category|categories|author|"
    r"page/\d+)(/|$)", re.I)

# Query keys that are pure tracking. Note the prefix alternatives carry `.*` — anchoring
# the whole key with `^(utm_)$` would only ever match a literal "utm_", leaving
# "utm_source" in place, and a tracking param that survives normalization breaks dedup:
# the same page arriving with two different utm_source values becomes two plan entries.
TRACKING_KEYS = re.compile(r"^(utm_.*|ref|referrer|source|fbclid|gclid|msclkid|"
                           r"mc_cid|mc_eid|_hsenc|_hsmi|igshid|si|at_.*|ck_subscriber_id|"
                           r"__s|spm|scid|trk|trkCampaign)$", re.I)

URL_RE = re.compile(
    r"""(?xi)
    \b
    (?:https?://|www\.)
    [^\s<>"'\)\]\}]+
    """)

# arXiv and DOI often appear without a scheme in a references list.
BARE_ARXIV_RE = re.compile(r"\barXiv[:\s]+(\d{4}\.\d{4,5})(v\d+)?\b", re.I)
BARE_DOI_RE = re.compile(r"\b(?:doi[:\s]+|https?://doi\.org/)(10\.\d{4,9}/[^\s<>\"']+)", re.I)

CLASS_RULES = [
    ("preprint",      [r"arxiv\.org", r"biorxiv\.org", r"medrxiv\.org", r"ssrn\.com"]),
    ("paper",         [r"doi\.org", r"aclanthology\.org", r"openreview\.net",
                       r"nature\.com", r"science\.org", r"acm\.org", r"ieee\.org",
                       r"springer", r"sciencedirect", r"pubmed", r"jmlr\.org",
                       r"proceedings\.", r"neurips\.cc", r"mlr\.press"]),
    ("code",          [r"github\.com", r"gitlab\.com", r"bitbucket\.org",
                       r"huggingface\.co/(?!datasets)", r"pypi\.org", r"npmjs\.com"]),
    ("dataset",       [r"huggingface\.co/datasets", r"kaggle\.com", r"zenodo\.org",
                       r"data\.gov", r"figshare\.com"]),
    ("benchmark",     [r"paperswithcode", r"lmarena", r"leaderboard", r"eval"]),
    ("documentation", [r"docs\.", r"/docs/", r"readthedocs", r"developer\.",
                       r"platform\.", r"/reference/", r"/api/"]),
    ("announcement",  [r"/news/", r"/blog/announcing", r"/announcement", r"/press/",
                       r"/newsroom/"]),
    ("video",         [r"youtube\.com", r"youtu\.be", r"vimeo\.com"]),
    ("blog-post",     [r"/blog/", r"medium\.com", r"substack\.com", r"\.blog/",
                       r"/posts?/", r"/article"]),
]


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def slugify(text, limit=60):
    """Kebab-case, truncated at a word boundary. Mirrors SCHEMA.md § 1.3."""
    s = str(text or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if len(s) <= limit:
        return s
    cut = s[:limit]
    return (cut.rsplit("-", 1)[0] if "-" in cut else cut).strip("-")


def read_txt(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def pdf_to_text(path):
    """
    Try `pdftotext -layout`. Return the text, or None to signal "read it natively".

    Returning None rather than a best effort is deliberate: see the module docstring.
    """
    exe = shutil.which("pdftotext")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "-layout", "-enc", "UTF-8", path, "-"],
                           capture_output=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    text = r.stdout.decode("utf-8", errors="replace")
    # A scanned PDF yields page breaks and almost no characters. Better to hand it to a
    # native reader than to record three words as the document.
    stripped = re.sub(r"[\s\f]", "", text)
    return text if len(stripped) >= 200 else None


def pdf_page_count(path):
    exe = shutil.which("pdfinfo")
    if exe:
        try:
            r = subprocess.run([exe, path], capture_output=True, timeout=60)
            if r.returncode == 0:
                m = re.search(rb"^Pages:\s+(\d+)", r.stdout, re.M)
                if m:
                    return int(m.group(1))
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    # Fall back to counting form feeds in the extracted text, done by the caller.
    return None


ANNOT_URI_RE = re.compile(rb"/URI\s*\(((?:[^()\\]|\\.)*)\)")


def annotation_uris(path):
    """
    Recover the targets of /URI link annotations by scanning the raw PDF bytes.

    A byte scan, not a parse. It exists because the most common blind spot in text-layer
    extraction is a hyperlink whose anchor text reads "our earlier work" and whose target
    appears nowhere in the visible text. Those are real depth-1 links from this document
    and belong in the plan, so this recovers them and MERGES them in rather than merely
    counting them — an earlier version reported a count and compared it against the
    text-derived total, which is comparing two different sets and reported 0 unaccounted
    while two targets were in fact missing.

    Returns (uris, annot_count). Best effort by construction: an annotation living inside
    a compressed object stream is invisible to a byte scan, so `annot_count` can undercount
    and the caller must keep saying so. Never treated as authoritative — only additive.
    """
    try:
        with open(path, "rb") as fh:
            blob = fh.read(24 * 1024 * 1024)
    except OSError:
        return [], 0
    out = []
    for m in ANNOT_URI_RE.finditer(blob):
        raw = m.group(1)
        # Undo the PDF string escapes that matter for a URL.
        raw = raw.replace(rb"\)", b")").replace(rb"\(", b"(").replace(rb"\\", b"\\")
        try:
            out.append(raw.decode("utf-8", errors="strict"))
        except UnicodeDecodeError:
            try:
                out.append(raw.decode("latin-1"))
            except UnicodeDecodeError:
                continue
    return out, len(out)


# ---------------------------------------------------------------------------
# URL handling
# ---------------------------------------------------------------------------

def repair_wrapped(text):
    """
    Undo the line-wrapping a PDF does to long URLs.

    A URL broken across a line arrives as "https://arxiv.org/abs/\n2212.08073". Only breaks
    after a slash, dot, equals, question mark or ampersand are rejoined — the places a PDF
    renderer actually breaks a URL. Rejoining on a hyphen would corrupt a legitimately
    hyphenated path.

    The lookahead requiring a LOWERCASE letter, digit or URL punctuation on the next line is
    load-bearing, and it is there because of a real failure: the text

        assistant work at https://arxiv.org/abs/2204.05862.
        Code: https://github.com/...

    rejoined into "https://arxiv.org/abs/2204.05862.Code", one bogus URL where there were a
    sentence end and a new line. A wrapped URL continues with path characters; a new
    sentence begins with a capital. That single distinction separates the two.
    """
    return re.sub(r"(?<=[/.=?&])[ \t]*\n[ \t]*(?=[a-z0-9\-_~%/?&=#+])", "", text)


def normalize_url(raw):
    """
    Canonical form for dedup: scheme lowered, host lowered, tracking params dropped,
    fragment dropped, trailing punctuation and trailing slash removed.

    Returns None for anything that is not a fetchable http(s) page.
    """
    u = raw.strip().rstrip(".,;:!?)]}>\"'")
    if u.lower().startswith("www."):
        u = "https://" + u
    try:
        parts = urlsplit(u)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https"):
        return None
    host = (parts.hostname or "").lower()
    if not host or "." not in host:
        return None

    path = parts.path or "/"
    ext = os.path.splitext(path)[1].lower()
    if ext in ASSET_EXT:
        return None

    kept = []
    for pair in (parts.query or "").split("&"):
        if not pair:
            continue
        k = pair.split("=", 1)[0]
        if not TRACKING_KEYS.match(k):
            kept.append(pair)
    query = "&".join(kept)

    if path != "/" and path.endswith("/"):
        path = path[:-1]
    port = "" if parts.port in (None, 80, 443) else ":%d" % parts.port
    return urlunsplit((parts.scheme.lower(), host + port, path, query, ""))


def classify(url):
    low = url.lower()
    for name, pats in CLASS_RULES:
        for p in pats:
            if re.search(p, low):
                return name
    return "other"


def domain_of(url):
    try:
        return (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def host_matches(host, needle):
    """True when `host` is `needle` or a subdomain of it. Never a bare substring match —
    'notx.com' must not match a deny entry of 'x.com'."""
    needle = needle.lower().strip()
    return bool(needle) and (host == needle or host.endswith("." + needle))


def find_urls(text, self_url=None, deny=None, prefer=None, max_links=MAX_LINKS_DEFAULT,
              annot_uris=None):
    """
    Build the authorized link plan.

    Returns (authorized, declined, stats). Every authorized entry carries depth 1, a
    class, and the reason it survived; every declined entry carries the reason it did not,
    because a link silently dropped is indistinguishable from a link never present.
    """
    deny = list(deny if deny is not None else DENY_DEFAULT)
    prefer = list(prefer if prefer is not None else PREFER_DEFAULT)
    text = repair_wrapped(text)

    # (raw, how it was found). Provenance is kept because "this URL was only ever a
    # hyperlink annotation" is exactly what a reader needs to know when the plan and the
    # visible text disagree.
    candidates = []
    for m in URL_RE.finditer(text):
        candidates.append((m.group(0), "text"))
    for m in BARE_ARXIV_RE.finditer(text):
        candidates.append(("https://arxiv.org/abs/%s" % m.group(1), "text"))
    for m in BARE_DOI_RE.finditer(text):
        candidates.append(("https://doi.org/%s" % m.group(1), "text"))
    for u in (annot_uris or []):
        candidates.append((u, "annotation"))

    self_norm = normalize_url(self_url) if self_url else None
    self_host = domain_of(self_norm) if self_norm else None

    seen, declined, kept = {}, [], []
    for raw, found_via in candidates:
        norm = normalize_url(raw)
        if norm is None:
            declined.append({"url": str(raw).strip()[:300],
                             "reason": "not a fetchable page", "found_via": found_via})
            continue
        if norm in seen:
            # Seen in the text AND as an annotation is the good case: note both.
            if found_via not in seen[norm]:
                seen[norm].append(found_via)
            continue
        seen[norm] = [found_via]

        host = domain_of(norm)
        if self_norm and norm == self_norm:
            declined.append({"url": norm, "reason": "self-link"}); continue
        if any(host_matches(host, d) for d in deny):
            declined.append({"url": norm, "reason": "denied domain"}); continue
        if JUNK_PATH.search(urlsplit(norm).path or ""):
            declined.append({"url": norm, "reason": "navigation or account path"}); continue

        kept.append({"url": norm, "domain": host, "link_class": classify(norm),
                     "depth": 1, "found_via": found_via,
                     "self_host": bool(self_host and host == self_host)})

    # Rank: preferred domains first, then document order. Only matters when the cap bites.
    def rank(entry):
        pref = 0 if any(host_matches(entry["domain"], p) for p in prefer) else 1
        return (pref,)
    ordered = sorted(kept, key=rank)

    authorized = ordered[:max_links]
    for e in ordered[max_links:]:
        declined.append({"url": e["url"], "reason": "over max_links cap (%d)" % max_links})

    for e in kept:
        e["found_via"] = "+".join(seen.get(e["url"], [e["found_via"]]))

    stats = {
        "candidates_seen": len(candidates),
        "unique_urls": len(seen),
        "authorized": len(authorized),
        "declined": len(declined),
        "cap": max_links,
        "from_text_only": sum(1 for e in authorized if e["found_via"] == "text"),
        "from_annotation_only": sum(1 for e in authorized
                                    if e["found_via"] == "annotation"),
        "by_class": {},
    }
    for e in authorized:
        stats["by_class"][e["link_class"]] = stats["by_class"].get(e["link_class"], 0) + 1
    return authorized, declined, stats


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


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Extract text and an authorized depth-1 link plan from a PDF or txt.")
    ap.add_argument("path")
    ap.add_argument("--out-text", help="write the extracted text here")
    ap.add_argument("--out-plan", help="write the link plan json here")
    ap.add_argument("--links-only", action="store_true",
                    help="emit the plan to stdout and skip the text")
    ap.add_argument("--max-links", type=int, default=MAX_LINKS_DEFAULT)
    ap.add_argument("--deny", help="comma-separated domains to add to the deny list")
    ap.add_argument("--prefer", help="comma-separated domains to rank first")
    ap.add_argument("--self-url", help="the document's own canonical URL, to drop self-links")
    ap.add_argument("--doc-slug", help="override the slug used in default output names")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.path):
        sys.stderr.write("ERROR: file not found: %s\n" % args.path)
        return 1

    ext = os.path.splitext(args.path)[1].lower()
    slug = args.doc_slug or slugify(os.path.splitext(os.path.basename(args.path))[0])

    if ext == ".txt":
        try:
            text = read_txt(args.path)
        except OSError as exc:
            sys.stderr.write("ERROR: cannot read %s: %s\n" % (args.path, exc))
            return 1
        pages = None
    elif ext == ".pdf":
        text = pdf_to_text(args.path)
        if text is None:
            sys.stderr.write(
                "Cannot extract this PDF here: `pdftotext` is unavailable, failed, or the "
                "file is a scan with no text layer.\n"
                "Read it with the agent's own Read tool — it reads PDFs natively, page by "
                "page — and build the link plan by hand from the URLs you see, recording "
                "every one you add. Do NOT approximate the text: a plausible mis-read of a "
                "benchmark table is worse than no read, because either way the number "
                "lands in the library.\n")
            return 2
        pages = pdf_page_count(args.path) or (text.count("\f") + 1)
    else:
        sys.stderr.write(
            "Unsupported format: %s. This library ingests .pdf and .txt only "
            "(SCHEMA.md § 2.2). Convert it, or read it with the agent's native reader and "
            "record the source_type honestly.\n" % (ext or "(no extension)"))
        return 2

    deny = DENY_DEFAULT + ([d.strip() for d in args.deny.split(",")] if args.deny else [])
    prefer = ([p.strip() for p in args.prefer.split(",")] if args.prefer
              else PREFER_DEFAULT)

    annot_uris, annot_count = (annotation_uris(args.path) if ext == ".pdf"
                               else ([], 0))
    authorized, declined, stats = find_urls(
        text, self_url=args.self_url, deny=deny, prefer=prefer,
        max_links=args.max_links, annot_uris=annot_uris)

    hidden = stats["from_annotation_only"]

    plan = {
        "schema": 1,
        "doc_slug": slug,
        "source_file": os.path.basename(args.path),
        "source_type": "pdf" if ext == ".pdf" else "txt",
        "source_sha256": hashlib.sha256(
            open(args.path, "rb").read()).hexdigest()[:16],
        "pages": pages,
        "max_depth": 1,
        "_max_depth_note": (
            "Contract term, not a setting. Every entry below is authorized at depth 1 and "
            "no deeper. A URL found ON one of these pages is NOT authorized: record it in "
            "that capture's `## Not taken` and stop (SCHEMA.md § 6.2)."),
        "authorized": authorized,
        "declined": declined,
        "stats": stats,
        "annotation_links_seen": annot_count,
        "annotation_only_authorized": hidden,
        "_annotation_note": (
            "`annotation_links_seen` counts /URI hyperlink annotations recovered by a byte "
            "scan; their targets are merged into `authorized` above and tagged "
            "found_via=annotation. This is BEST EFFORT: an annotation inside a compressed "
            "object stream is invisible to a byte scan. Where you read the PDF natively "
            "and find a hyperlink this plan does not list, ADD it to `authorized` and "
            "record that you added it. Never fetch an unrecorded URL — the plan is the "
            "audit surface."),
    }

    payload = json.dumps(plan, indent=2, ensure_ascii=False)

    if args.links_only:
        sys.stdout.write(payload + "\n")
        return 0

    if args.out_plan:
        atomic_write(args.out_plan, payload + "\n")
    if args.out_text:
        header = "<!-- extracted from %s (%s, %s pages) -->\n" % (
            os.path.basename(args.path), plan["source_type"],
            pages if pages else "?")
        atomic_write(args.out_text, header + text.rstrip() + "\n")

    if not args.out_plan and not args.out_text:
        sys.stdout.write(text)
        sys.stderr.write("note: no --out-text/--out-plan given; text to stdout, plan "
                         "discarded\n")
        return 0

    sys.stderr.write(
        "extracted %s (%s pages, %d chars); plan: %d authorized of %d unique, %d declined%s\n"
        % (os.path.basename(args.path), pages if pages else "?", len(text),
           stats["authorized"], stats["unique_urls"], stats["declined"],
           ("; %d recovered from link annotations only (invisible in the text)" % hidden)
           if hidden else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
