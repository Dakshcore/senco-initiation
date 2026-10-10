"""Guidance vs delivery: score each due guidance statement against what Senco reported.

Inputs
- data/guidance.csv: the statements (from senco.guidance).
- data/delivery_parts/actuals_*.csv: the actual management reported on a later call, with a verbatim quote.
- data/delivery_rules.csv: for each due statement, the guided range as numbers and which way is better, plus
  which actual to score against (the call, or an audited figure from the Screener export).

`python -m senco.delivery` checks every actual quote against its page, scores each due statement, writes the
actual and the verdict back into data/guidance.csv, writes data/delivery.csv with the detail, and prints the
delivery rate.

Verdicts, given a guided range [lo, hi] (either end may be open):
- better = higher (sales, margins, stores): above hi is "beat", inside is "met", below lo is "missed".
- better = lower (debt, costs, inventory days): below lo is "beat", inside is "met", above hi is "missed".
A point guide such as "~20%" is scored as the range within 5% of the point (19-21%). Delivered means met or
beat. Rows whose period has not ended are "not due"; rows with no reported actual are "no actual".
"""
from __future__ import annotations

import csv
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from senco import financials as fin
from senco.guidance import GUIDANCE, COLUMNS, read, text_pages
from senco.transcripts import normalise

ROOT = Path(__file__).resolve().parent.parent
PARTS = ROOT / "data" / "delivery_parts"
RULES = ROOT / "data" / "delivery_rules.csv"
DETAIL = ROOT / "data" / "delivery.csv"
POINT_BAND = 0.05  # "~x" is scored as x +/- 5%


def screener_actuals() -> dict[str, float]:
    """Audited consolidated figures from the Screener export, keyed like 'rev_growth:FY25'."""
    t = fin.load()
    pnl, q, bs = t["pnl"], t["quarters"], t["balance"]
    out: dict[str, float] = {}
    ebitda_margin = fin.ratios(t).loc["EBITDA margin"] * 100
    gross_margin = (pnl.loc["Sales"] - pnl.loc["Raw Material Cost"] + pnl.loc["Change in Inventory"]) / pnl.loc["Sales"] * 100
    for fy in ("FY23", "FY24", "FY25", "FY26"):
        out[f"gross_margin:{fy}"] = gross_margin[fy]
        out[f"ebitda_margin:{fy}"] = ebitda_margin[fy]
    for fy, prev in (("FY24", "FY23"), ("FY25", "FY24"), ("FY26", "FY25")):
        out[f"gm_change_bps:{fy}"] = (gross_margin[fy] - gross_margin[prev]) * 100
        out[f"ebitda_change_bps:{fy}"] = (ebitda_margin[fy] - ebitda_margin[prev]) * 100
        out[f"revenue:{fy}"] = pnl.loc["Sales", fy]
        out[f"rev_growth:{fy}"] = (pnl.loc["Sales", fy] / pnl.loc["Sales", prev] - 1) * 100
        out[f"pat:{fy}"] = pnl.loc["Net profit", fy]
        out[f"pat_growth:{fy}"] = (pnl.loc["Net profit", fy] / pnl.loc["Net profit", prev] - 1) * 100
        out[f"pat_margin:{fy}"] = pnl.loc["Net profit", fy] / pnl.loc["Sales", fy] * 100
        equity = bs.loc["Equity Share Capital", fy] + bs.loc["Reserves", fy]
        out[f"de:{fy}"] = bs.loc["Borrowings", fy] / equity
        out[f"borrowing_change:{fy}"] = bs.loc["Borrowings", fy] - bs.loc["Borrowings", prev]
        out[f"share_capital_change:{fy}"] = bs.loc["Equity Share Capital", fy] - bs.loc["Equity Share Capital", prev]
    for qtr in q.columns:
        prior = f"{qtr[:2]}FY{int(qtr[4:]) - 1:02d}"
        out[f"q_ebitda_margin:{qtr}"] = q.loc["Operating Profit", qtr] / q.loc["Sales", qtr] * 100
        if prior in q.columns:
            out[f"q_rev_growth:{qtr}"] = (q.loc["Sales", qtr] / q.loc["Sales", prior] - 1) * 100
    h2 = lambda fy: q.loc["Sales", [f"Q3{fy}", f"Q4{fy}"]].sum()
    out["h2_rev_growth:FY26"] = (h2("FY26") / h2("FY25") - 1) * 100
    return out


def first_number(s: str) -> float | None:
    m = re.search(r"-?\d[\d,]*\.?\d*", s or "")
    return float(m.group().replace(",", "")) if m else None


def verdict(actual: float, lo: float | None, hi: float | None, better: str) -> str:
    lo = -math.inf if lo is None else lo
    hi = math.inf if hi is None else hi
    if lo <= actual <= hi:
        return "met"
    above = actual > hi
    return "beat" if above == (better == "higher") else "missed"


def _num(s: str) -> float | None:
    return float(s) if s not in ("", None) else None


def load_actuals() -> dict[str, dict]:
    return {r["id"]: r for p in sorted(PARTS.glob("actuals_*.csv")) for r in read(p)}


def quote_problems(actuals: dict[str, dict]) -> list[str]:
    cache: dict[str, dict[int, str]] = {}
    out = []
    for gid, a in actuals.items():
        for call, page, quote in ((a["src_call"], a["src_page"], a["src_quote"]),
                                  (a["src2_call"], a["src2_page"], a["src2_quote"])):
            if not quote:
                continue
            pages = cache.setdefault(call, text_pages(call))
            if normalise(quote) not in pages.get(int(page), ""):
                out.append(f"{gid}: actual quote not on {call} page {page}")
    return out


def unquoted_numbers(detail: list[dict], actuals: dict[str, dict]) -> list[str]:
    """Call-scored rows whose number is not in the quotes (derived by arithmetic; the rule note says how)."""
    out = []
    for d in detail:
        if d["scored_on"] != "call":
            continue
        a = actuals[d["id"]]
        text = normalise(a["src_quote"] + " " + a["src2_quote"])
        n = d["actual"]
        if f"{n:g}" not in text:
            out.append(f"{d['id']}: {n:g} derived, not quoted ({d['reason']})")
    return out


def score() -> tuple[list[dict], list[str]]:
    guidance = read()
    actuals = load_actuals()
    rules = {r["id"]: r for r in read(RULES)}
    sa = screener_actuals()
    problems = quote_problems(actuals)
    detail = []
    for g in guidance:
        rule, act = rules.get(g["id"]), actuals.get(g["id"], {})
        row = {"id": g["id"], "call_quarter": g["call_quarter"], "metric": g["metric"],
               "guided_value": g["guided_value"], "target_period": g["target_period"],
               "lo": "", "hi": "", "better": "", "call_actual": act.get("actual_value", ""),
               "screener_key": "", "screener_actual": "", "scored_on": "", "actual": "", "verdict": "not due",
               "reason": ""}
        if rule is None:
            detail.append(row)
            continue
        row.update(lo=rule["lo"], hi=rule["hi"], better=rule["better"], screener_key=rule["screener_key"],
                   reason=rule["note"])
        if rule["screener_key"]:
            row["screener_actual"] = round(sa[rule["screener_key"]], 2)
        if rule["manual_verdict"]:
            row.update(verdict=rule["manual_verdict"], scored_on="manual", actual=act.get("actual_value", ""))
        elif rule["basis"] == "screener":
            row.update(scored_on="screener", actual=row["screener_actual"])
        elif rule["basis"] == "call" and act.get("actual_value"):
            row.update(scored_on="call", actual=_num(rule["actual_num"]) if rule["actual_num"]
                       else first_number(act["actual_value"]))
        else:
            row.update(verdict="no actual")
        if row["scored_on"] in ("screener", "call"):
            row["verdict"] = verdict(float(row["actual"]), _num(rule["lo"]), _num(rule["hi"]), rule["better"])
        detail.append(row)
    return detail, problems


def write(detail: list[dict]) -> None:
    with open(DETAIL, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(detail[0]))
        w.writeheader()
        w.writerows(detail)
    by_id = {d["id"]: d for d in detail}
    actuals = load_actuals()
    rows = read()
    for r in rows:
        d, a = by_id[r["id"]], actuals.get(r["id"], {})
        if d["verdict"] == "not due":
            continue
        if d["scored_on"] == "screener":
            r["actual_value"] = f"{d['actual']}"
            r["actual_source"] = f"Screener consolidated export ({d['screener_key']})"
        elif a.get("src_call"):
            r["actual_value"] = a["actual_value"]
            r["actual_source"] = f"{a['src_call']} call p{a['src_page']}" + (
                f"; {a['src2_call']} call p{a['src2_page']}" if a.get("src2_call") else "")
        r["delivered"] = d["verdict"]
    with open(GUIDANCE, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def summary(detail: list[dict]) -> str:
    scored = [d for d in detail if d["verdict"] in ("met", "beat", "missed")]
    hit = [d for d in scored if d["verdict"] != "missed"]
    lines = [f"verdicts: {dict(Counter(d['verdict'] for d in detail))}",
             f"delivery rate: {len(hit)} of {len(scored)} scored = {len(hit) / len(scored):.1%}" if scored else ""]
    target_year = lambda d: re.search(r"FY\d\d", d["target_period"]).group()
    for label, key in (("by metric", lambda d: d["metric"]), ("by call", lambda d: d["call_quarter"]),
                       ("by target year", target_year)):
        groups = defaultdict(list)
        for d in scored:
            groups[key(d)].append(d["verdict"] != "missed")
        lines.append(label + ": " + "; ".join(f"{k} {sum(v)}/{len(v)}" for k, v in groups.items()))
    # The same target is often repeated on several calls; count each (metric, period) once, on its latest guide.
    latest = {(d["metric"], d["target_period"]): d for d in scored if d["metric"] != "other"}
    hit = [d for d in latest.values() if d["verdict"] != "missed"]
    lines.append(f"distinct targets (latest guide per metric and period, excluding 'other'): "
                 f"{len(hit)} of {len(latest)} = {len(hit) / len(latest):.1%}")
    return "\n".join(lines)


if __name__ == "__main__":
    detail, problems = score()
    if problems:
        print("\n".join(problems))
        sys.exit(1)
    write(detail)
    print(summary(detail))
    print("\n".join(unquoted_numbers(detail, load_actuals())))
