import os        # (only used indirectly if you keep it; safe to remove if not used elsewhere)
import sys
from pathlib import Path
import re

import fitz           # PyMuPDF
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import mammoth


def extract_pdf_text(pdf_path: str) -> str:
    """
    Extracts all text from a PDF.
    If a page has no embedded text, OCR is used instead.
    Returns a single combined text string.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    text_output = []
    print(f"Processing: {pdf_path}\n")

    # --------------------------
    # 1. Extract text via PyMuPDF
    # --------------------------
    print("Extracting embedded text...")
    doc = fitz.open(pdf_path)

    for i, page in enumerate(doc, 1):
        extracted = page.get_text().strip()
        if extracted:
            print(f"  Page {i}: Found embedded text")
            text_output.append(f"--- Page {i} ---\n{extracted}\n")
        else:
            print(f"  Page {i}: No text found — running OCR...")
            # --------------------------------
            # 2. Convert page to image for OCR
            # --------------------------------
            image = convert_from_path(str(pdf_path), dpi=300, first_page=i, last_page=i)[0]
            text = pytesseract.image_to_string(image)
            text_output.append(f"--- Page {i} (OCR) ---\n{text}\n")

    doc.close()
    print("\nDone.")
    return "\n".join(text_output)


def parse_doc(file_path):
    """
    Parse all non-pdf files.
    File extensions handled: doc, docx, txt
    """
    file_ext = file_path.split(".")[-1].lower()
    return_txt = ""

    if file_path.lower().endswith(".docx"):
        with open(file_path_full, "rb") as doc_file:
            result = mammoth.extract_raw_text(doc_file)
            return_txt = result.value
    elif file_path.lower().endswith(".doc"):
        rawb = ""
        with open(file_path_full, "rb") as doc_file:
            rawb = doc_file.read()

        # Extract all sequences of 3+ printable ASCII characters
        printable = re.findall(b"[ -~]{3,}", rawb)
        for match in printable:
            return_txt += (match.decode("utf-8", errors="ignore"))
    elif file_path.lower().endswith(".txt"):
        with open(file_path_full, "r") as doc_file:
            for line in doc_file:
                return_txt += line
    else:
        return None
    return return_txt


def main():
    if len(sys.argv) < 2:
        print("Usage: python scanner.py <file>")
        return 1

    file_path = sys.argv[1]

    try:
        if not file_path.lower().endswith(".pdf"):
            text = parse_doc(file_path)
        else:
            text = extract_pdf_text(file_path)
    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
