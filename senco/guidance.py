"""Merge the per-batch guidance extracts into data/guidance.csv and check every quote against its page.

`python -m senco.guidance merge` combines data/guidance_parts/part*.csv in call order and numbers the rows.
`python -m senco.guidance check` confirms each quote appears, after normalising, on the PDF page it cites.
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

from senco.transcripts import TEXT_DIR, normalise, quarters

ROOT = Path(__file__).resolve().parent.parent
GUIDANCE = ROOT / "data" / "guidance.csv"
PARTS = ROOT / "data" / "guidance_parts"
COLUMNS = ["id", "call_quarter", "page", "speaker", "quote", "metric", "guided_value", "target_period",
           "actual_value", "actual_source", "delivered", "notes"]
METRICS = {"revenue_growth", "sssg", "ebitda_margin", "gross_margin", "pat_margin", "pat_growth",
           "showroom_additions", "showroom_count", "franchise_mix", "diamond_share", "inventory", "debt",
           "capex", "working_capital", "tax_rate", "other"}


def read(path: Path = GUIDANCE) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def text_pages(quarter: str) -> dict[int, str]:
    """{page number: normalised text} from the page-tagged transcript."""
    out, page = {}, None
    for line in (TEXT_DIR / f"{quarter}.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("=== page ") and line.endswith(" ==="):
            page = int(line.split()[2])
            out[page] = ""
        elif page is not None:
            out[page] += " " + line
    return {p: normalise(t) for p, t in out.items()}


def merge() -> list[dict]:
    order = {q: i for i, q in enumerate(quarters())}
    rows = [r for part in sorted(PARTS.glob("part*.csv")) for r in read(part)]
    rows.sort(key=lambda r: (order[r["call_quarter"]], int(r["page"])))
    for i, r in enumerate(rows, start=1):
        r["id"] = f"G{i:03d}"
    with open(GUIDANCE, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in COLUMNS} for r in rows)
    return rows


def problems(rows: list[dict]) -> list[str]:
    """Every reason a row fails: unknown call or metric, quote not on the cited page, or wrong length."""
    cache: dict[str, dict[int, str]] = {}
    out = []
    for r in rows:
        q = r["call_quarter"]
        if q not in quarters():
            out.append(f"{r['id']}: unknown call {q}")
            continue
        pages = cache.setdefault(q, text_pages(q))
        if normalise(r["quote"]) not in pages.get(int(r["page"]), ""):
            out.append(f"{r['id']}: quote not on {q} page {r['page']}")
        if r["metric"] not in METRICS:
            out.append(f"{r['id']}: unknown metric {r['metric']}")
        if not 10 <= len(r["quote"].split()) <= 45:
            out.append(f"{r['id']}: quote is {len(r['quote'].split())} words")
    return out


if __name__ == "__main__":
    rows = merge() if sys.argv[1:] == ["merge"] else read()
    bad = problems(rows)
    per_call = Counter(r["call_quarter"] for r in rows)
    for q in quarters():
        print(f"{q}: {per_call.get(q, 0)}")
    print(f"total rows: {len(rows)}; passed: {len(rows) - len({b.split(':')[0] for b in bad})} of {len(rows)}")
    print("\n".join(bad))
