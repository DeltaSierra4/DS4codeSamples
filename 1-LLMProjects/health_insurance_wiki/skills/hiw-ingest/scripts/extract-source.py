#!/usr/bin/env python3
"""
extract-source.py — pull plain text out of a source document, stdlib only.

`/hiw-ingest` uses this so that a .docx, .xlsx or .pptx becomes readable text without
installing python-docx, openpyxl or python-pptx. All three formats are zip archives
of XML, so `zipfile` plus a careful tag strip is genuinely enough — and an ingest
skill that needs a pip install is an ingest skill that fails on a locked-down laptop.

WHAT IT HANDLES
    .txt .md .csv .tsv .json  read directly
    .html .htm                script/style stripped, tags stripped, entities decoded
    .docx .dotx               word/document.xml, paragraph breaks preserved
    .xlsx .xlsm .xltx         every sheet, tab-separated, shared strings resolved
    .pptx .potx               every slide plus its speaker notes, in slide order

WHAT IT DOES NOT HANDLE, and says so plainly
    .pdf     Extracting PDF text correctly needs a real PDF library. This script
             tries `pdftotext` if it is on PATH and otherwise EXITS 2 with the
             instruction to read the file with the agent's own Read tool, which
             reads PDFs natively. It does NOT return partial or garbled text —
             a plausible-looking mis-extraction of a benefits table is worse than
             no extraction, because the numbers land in the wiki either way.
    .doc     The pre-2007 binary format. Exits 2 with the same instruction.
    images   Exits 2; the agent reads images natively.

The exit code is the contract: 0 means the text on stdout is the document's text.
2 means "I cannot do this one, use your own reader" — which is a normal outcome,
not a failure of the run.

Invocation:
    python3 extract-source.py <path> [--max-chars N] [--out FILE]

Exit codes:
    0  text extracted, on stdout (or written to --out)
    1  hard error — file missing, unreadable, or a corrupt archive
    2  unsupported format; read it with the agent's native reader instead
"""

import argparse
import html as htmllib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"

NATIVE_READ = (
    "Unsupported format: %s\n"
    "Read this file with the agent's own Read tool, which handles it natively, then "
    "extract the plan facts from what you see. Do not guess at the contents.\n"
)


def squeeze(text):
    """Collapse runs of blank lines and trailing whitespace; keep paragraph breaks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def from_plain(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def from_json(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        try:
            return json.dumps(json.load(fh), indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            fh.seek(0)
            return fh.read()


def from_html(text):
    """
    Strip an HTML document to readable text.

    Tables are the reason this is not a one-line regex: a benefits grid loses all its
    meaning if the cell boundaries vanish, so cells become tab-separated and rows
    become lines BEFORE tags are removed.
    """
    text = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1\s*>", " ", text)
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = re.sub(r"(?i)</t[dh]\s*>\s*<t[dh][^>]*>", "\t", text)
    text = re.sub(r"(?i)</tr\s*>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|h[1-6]|table|section|article)\s*>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = htmllib.unescape(text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def from_docx(path):
    with zipfile.ZipFile(path) as z:
        names = [n for n in ("word/document.xml",) if n in z.namelist()]
        if not names:
            raise ValueError("no word/document.xml — not a Word document")
        root = ET.fromstring(z.read(names[0]))

    out = []
    for para in root.iter(W + "p"):
        parts = []
        for node in para.iter():
            if node.tag == W + "t" and node.text:
                parts.append(node.text)
            elif node.tag == W + "tab":
                parts.append("\t")
            elif node.tag in (W + "br", W + "cr"):
                parts.append("\n")
        line = "".join(parts).strip()
        # A table cell ends up as its own paragraph; keeping empties would double
        # every blank row in a benefits grid.
        out.append(line)
    return "\n".join(out)


def _shared_strings(z):
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    out = []
    for si in root.findall(S + "si"):
        out.append("".join(t.text or "" for t in si.iter(S + "t")))
    return out


def from_xlsx(path):
    with zipfile.ZipFile(path) as z:
        shared = _shared_strings(z)
        sheet_names = {}
        if "xl/workbook.xml" in z.namelist():
            wb = ET.fromstring(z.read("xl/workbook.xml"))
            for i, sh in enumerate(wb.iter(S + "sheet"), 1):
                sheet_names[i] = sh.get("name") or ("Sheet%d" % i)

        paths = sorted(n for n in z.namelist()
                       if re.match(r"^xl/worksheets/sheet\d+\.xml$", n))
        if not paths:
            raise ValueError("no worksheets — not a spreadsheet")

        out = []
        for p in paths:
            idx = int(re.search(r"sheet(\d+)\.xml$", p).group(1))
            out.append("### Sheet: %s" % sheet_names.get(idx, "Sheet%d" % idx))
            root = ET.fromstring(z.read(p))
            for row in root.iter(S + "row"):
                cells = []
                for c in row.findall(S + "c"):
                    v = c.find(S + "v")
                    raw = v.text if v is not None else None
                    if c.get("t") == "s" and raw is not None:
                        try:
                            raw = shared[int(raw)]
                        except (ValueError, IndexError):
                            pass
                    elif c.get("t") == "inlineStr":
                        istr = c.find(S + "is")
                        raw = ("".join(t.text or "" for t in istr.iter(S + "t"))
                               if istr is not None else raw)
                    cells.append("" if raw is None else str(raw))
                if any(x.strip() for x in cells):
                    out.append("\t".join(cells))
            out.append("")
        return "\n".join(out)


def from_pptx(path):
    with zipfile.ZipFile(path) as z:
        slides = sorted(
            (n for n in z.namelist()
             if re.match(r"^ppt/slides/slide\d+\.xml$", n)),
            key=lambda n: int(re.search(r"slide(\d+)\.xml$", n).group(1)))
        if not slides:
            raise ValueError("no slides — not a presentation")

        out = []
        for p in slides:
            num = int(re.search(r"slide(\d+)\.xml$", p).group(1))
            out.append("### Slide %d" % num)
            root = ET.fromstring(z.read(p))
            for para in root.iter(A + "p"):
                line = "".join(t.text or "" for t in para.iter(A + "t")).strip()
                if line:
                    out.append(line)
            notes = "ppt/notesSlides/notesSlide%d.xml" % num
            if notes in z.namelist():
                nroot = ET.fromstring(z.read(notes))
                lines = []
                for para in nroot.iter(A + "p"):
                    line = "".join(t.text or "" for t in para.iter(A + "t")).strip()
                    if line:
                        lines.append(line)
                if lines:
                    out.append("_Speaker notes:_ " + " ".join(lines))
            out.append("")
        return "\n".join(out)


def from_pdf(path):
    """
    Try `pdftotext`, and refuse rather than guess if it is absent.

    `-layout` is not optional: without it a two-column SBC interleaves its columns
    and a copay lands next to the wrong service. That failure is silent and the
    output looks fine.
    """
    exe = shutil.which("pdftotext")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "-layout", "-enc", "UTF-8", path, "-"],
                           capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    text = r.stdout.decode("utf-8", errors="replace")
    return text if text.strip() else None


HANDLERS = {
    ".txt": lambda p: from_plain(p), ".md": lambda p: from_plain(p),
    ".markdown": lambda p: from_plain(p),
    ".csv": lambda p: from_plain(p), ".tsv": lambda p: from_plain(p),
    ".json": from_json,
    ".html": lambda p: from_html(from_plain(p)),
    ".htm": lambda p: from_html(from_plain(p)),
    ".xml": lambda p: from_html(from_plain(p)),
    ".docx": from_docx, ".dotx": from_docx, ".docm": from_docx,
    ".xlsx": from_xlsx, ".xlsm": from_xlsx, ".xltx": from_xlsx,
    ".pptx": from_pptx, ".potx": from_pptx, ".pptm": from_pptx,
}

NATIVE_ONLY = {".doc", ".xls", ".ppt", ".rtf", ".pages", ".numbers", ".key",
               ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff",
               ".heic", ".eml", ".msg"}


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Extract plain text from a source document. Stdlib only.")
    ap.add_argument("path")
    ap.add_argument("--out", help="write here instead of stdout")
    ap.add_argument("--max-chars", type=int, default=0,
                    help="truncate after N characters, noting the truncation")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.path):
        sys.stderr.write("ERROR: file not found: %s\n" % args.path)
        return 1

    ext = os.path.splitext(args.path)[1].lower()

    if ext == ".pdf":
        text = from_pdf(args.path)
        if text is None:
            sys.stderr.write(
                "Unsupported here: .pdf, and `pdftotext` is not on PATH.\n"
                "Read this PDF with the agent's own Read tool — it reads PDFs "
                "natively, page by page — then extract the plan facts from what you "
                "see. Do NOT approximate the numbers: a plausible mis-read of a "
                "benefits table is worse than no read at all, because either way "
                "the number lands in the wiki.\n")
            return 2
    elif ext in NATIVE_ONLY:
        sys.stderr.write(NATIVE_READ % ext)
        return 2
    elif ext in HANDLERS:
        try:
            text = HANDLERS[ext](args.path)
        except (zipfile.BadZipFile, ET.ParseError, ValueError, KeyError) as exc:
            sys.stderr.write(
                "ERROR: could not parse %s as %s: %s\n"
                "If the file opens correctly in its own application, read it with "
                "the agent's Read tool instead.\n" % (args.path, ext, exc))
            return 1
        except OSError as exc:
            sys.stderr.write("ERROR: cannot read %s: %s\n" % (args.path, exc))
            return 1
    else:
        # Unknown extension: try it as text, but only if it decodes cleanly and
        # actually looks like text. Guessing at a binary file produces mojibake
        # that reads like a corrupted document rather than like an error.
        try:
            with open(args.path, "rb") as fh:
                blob = fh.read(65536)
            if b"\x00" in blob:
                raise ValueError("binary content")
            blob.decode("utf-8")
            text = from_plain(args.path)
            sys.stderr.write("note: unknown extension %r, read as plain text\n" % ext)
        except (OSError, UnicodeDecodeError, ValueError):
            sys.stderr.write(NATIVE_READ % (ext or "(no extension)"))
            return 2

    text = squeeze(text)
    truncated = False
    if args.max_chars and len(text) > args.max_chars:
        text = text[:args.max_chars]
        truncated = True

    header = "<!-- extracted from %s (%s, %d bytes) -->\n" % (
        os.path.basename(args.path), ext or "no extension",
        os.path.getsize(args.path))
    payload = header + text + (
        "\n\n<!-- TRUNCATED at %d characters. Re-run without --max-chars, or with a "
        "larger value, before concluding a field is absent from this source. -->\n"
        % args.max_chars if truncated else "\n")

    if args.out:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(payload)
            sys.stderr.write("wrote %s (%d chars%s)\n"
                             % (args.out, len(text),
                                ", truncated" if truncated else ""))
        except OSError as exc:
            sys.stderr.write("WARNING: cannot write --out %r: %s\n" % (args.out, exc))
            sys.stdout.write(payload)
    else:
        sys.stdout.write(payload)

    if not text.strip():
        sys.stderr.write(
            "WARNING: extraction produced no text. The document may be a scan or "
            "image-only. Read it with the agent's native reader instead of treating "
            "this as an empty source.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
