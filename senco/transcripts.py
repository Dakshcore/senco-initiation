"""Turn the earnings-call PDFs into page-tagged text, so every guidance quote can cite a page.

`python -m senco.transcripts` writes data/transcripts/text/<quarter>.txt with a "=== page N ===" line before
each PDF page. Page numbers are PDF pages (page 1 is the stock-exchange cover letter).
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import pypdf

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data" / "transcripts"
TEXT_DIR = PDF_DIR / "text"


def quarters() -> list[str]:
    with open(PDF_DIR / "sources.csv", newline="") as fh:
        return [row["quarter"] for row in csv.DictReader(fh)]


def pages(quarter: str) -> list[str]:
    reader = pypdf.PdfReader(PDF_DIR / f"{quarter}.pdf")
    return [" ".join((p.extract_text() or "").split()) for p in reader.pages]


def normalise(s: str) -> str:
    """Lower-case, straight quotes, single spaces: for checking that a quote appears in the text."""
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def write_text() -> None:
    TEXT_DIR.mkdir(exist_ok=True)
    for q in quarters():
        body = "\n".join(f"=== page {i} ===\n{t}" for i, t in enumerate(pages(q), start=1))
        (TEXT_DIR / f"{q}.txt").write_text(body, encoding="utf-8")


if __name__ == "__main__":
    write_text()
    print(f"wrote {len(quarters())} files to {TEXT_DIR}")
