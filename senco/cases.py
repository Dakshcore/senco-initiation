"""Draft bear, base and bull cases from Senco's own FY22-FY26 history, then run the model and DCF on each.

`python -m senco.cases draft` writes data/assumptions/{bear,base,bull}.csv. `python -m senco.cases` runs every
case in data/assumptions/ through senco.model and senco.dcf and prints them side by side
(outputs/cases.xlsx).

The rule for the draft, one value held flat FY27-FY31:
- Value drivers (growth, margin, interest, working capital): base = the FY22-FY26 median; bear and bull = the
  25th and 75th percentiles, whichever is worse or better for Senco. With five years these are the 2nd-worst and
  2nd-best years, so no case assumes the single best or worst year.
- Other drivers (other income, depreciation, capex, tax, payout): the median in all three cases.
- Revenue growth is split as 7 points from new stores (G133) and the rest same-store growth.
- Store additions and the gold price are memo lines with no history in the Screener export; left blank.
- Override (Daksh, 9 Oct 2026): base other_liab_days is the FY26 level excluding current tax and acceptances
  (data/fy26_liabilities.csv), not the median, because the FY26 rise in customer advances and supplier credit
  looks durable while the tax liability and acceptances do not. Bull other_liab_days is the FY26 reported level
  (all of the FY26 rise persists).

These are a starting point for Daksh's own cases, not his view. The DCF uses the placeholder discount rate.
"""
from __future__ import annotations

import csv
import sys

import numpy as np
import pandas as pd

from senco import dcf
from senco import financials as fin
from senco import model as m

YEARS = ("FY27", "FY28", "FY29", "FY30", "FY31")
BETTER = {"revenue_growth": "higher", "ebitda_margin": "higher", "interest_rate": "lower",
          "inventory_days": "lower", "receivable_days": "lower", "other_assets_pct": "lower",
          "other_liab_days": "higher"}
NEUTRAL = ("other_income_pct", "dep_rate", "capex_pct", "tax_rate", "payout")
NEW_STORES = 7.0  # G133 (Q2FY26): new stores add 6-8% to growth; midpoint
CASES = ("bear", "base", "bull")
LIABILITIES = m.ROOT / "data" / "fy26_liabilities.csv"


def liabilities() -> pd.DataFrame:
    """FY26 annual-report line items behind Screener's "Other Liabilities", Rs million, with a one_off flag."""
    return pd.read_csv(LIABILITIES, index_col="item")


def other_liab_days_ex_one_offs(t: dict[str, pd.DataFrame]) -> float:
    """FY26 other liabilities less the one-off lines (current tax, acceptances), in days of FY26 revenue."""
    li = liabilities()
    return li.loc[li["one_off"] == "no", "FY26"].sum() / 10 / fin.ratios(t).loc["Sales (Rs cr)", "FY26"] * 365


def overrides(t: dict[str, pd.DataFrame]) -> dict[tuple[str, str], tuple[float, str]]:
    """Hand choices that replace the rule: (case, driver) -> (value, source)."""
    return {("base", "other_liab_days"): (
        round(other_liab_days_ex_one_offs(t), 2),
        "Daksh: FY26 level excl. current tax and acceptances (data/fy26_liabilities.csv, AR FY26 p.324-326)"),
            ("bull", "other_liab_days"): (
        round(float(m.history(t).loc["other_liab_days", "FY26"]), 2),
        "Daksh: FY26 reported level (Screener balance sheet); the whole FY26 rise persists")}


def pick(values: pd.Series, case: str, better: str) -> tuple[float, str]:
    """The FY22-FY26 percentile for a case, rounded to 2 dp, with a description of where it came from."""
    q = {"bear": 25, "base": 50, "bull": 75}[case]
    if better == "lower" and case != "base":
        q = 100 - q
    x = round(float(np.percentile(values, q)), 2)
    label = "median" if q == 50 else f"{q}th percentile"
    return x, f"FY22-FY26 {label} ({better} is better); range {values.min():.2f}-{values.max():.2f}"


def draft(h: pd.DataFrame, t: dict[str, pd.DataFrame] | None = None) -> dict[str, list[dict]]:
    over = overrides(t) if t is not None else {}
    out = {}
    for case in CASES:
        rows = []
        growth, src = pick(h.loc["revenue_growth"], case, "higher")
        rows.append(("sssg", round(growth - NEW_STORES, 2), f"Revenue growth {growth:.2f}: {src}; less new stores"))
        rows.append(("new_store_contribution", NEW_STORES, "G133 (Q2FY26): new stores add 6-8%; midpoint"))
        rows.append(("store_additions", "", "Memo; no store history in the Screener export"))
        rows.append(("gold_price_change", "", "Memo; not in the history"))
        for k in m.DRIVERS:
            if k in BETTER:
                x, src = pick(h.loc[k], case, BETTER[k])
            elif k in NEUTRAL:
                x = round(float(h.loc[k].median()), 2)
                src = f"FY22-FY26 median, same in all cases; range {h.loc[k].min():.2f}-{h.loc[k].max():.2f}"
            else:
                continue
            x, src = over.get((case, k), (x, src))
            rows.append((k, x, src))
        order = list(m.DRIVERS)
        rows.sort(key=lambda r: order.index(r[0]))
        out[case] = [{"driver": k, **{y: x for y in YEARS}, "source": s} for k, x, s in rows]
    return out


def write(cases: dict[str, list[dict]]) -> None:
    for case, rows in cases.items():
        with open(m.ASSUMPTIONS / f"{case}.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["driver", *YEARS, "source"])
            w.writeheader()
            w.writerows(rows)


def run(name: str, t: dict[str, pd.DataFrame]) -> dict[str, float]:
    a, _ = m.read_assumptions(m.ASSUMPTIONS / f"{name}.csv")
    f = m.project(a, t)
    k = m.metrics(f, m.base_state(t))
    v = dcf.value(a, dcf.Inputs(), t)
    return {
        "Revenue growth FY27 %": k.loc["Revenue growth %", "FY27"],
        "EBITDA margin FY27 %": a.loc["ebitda_margin", "FY27"],
        "Inventory days FY27": a.loc["inventory_days", "FY27"],
        "Revenue FY31": k.loc["Revenue (Rs cr)", "FY31"],
        "Net profit FY27": k.loc["Net profit (Rs cr)", "FY27"],
        "Net profit FY31": k.loc["Net profit (Rs cr)", "FY31"],
        "EPS FY27 (Rs)": k.loc["EPS (Rs)", "FY27"],
        "Debt/equity FY31 (x)": k.loc["Debt / equity (x)", "FY31"],
        "ROE FY31 %": k.loc["ROE % (avg equity)", "FY31"],
        "FCF FY27-FY31 (Rs cr)": k.loc["Free cash flow (Rs cr)"].sum(),
        "DCF value (Rs/share)": v["per_share"],
        "vs price %": (v["per_share"] / dcf.PRICE - 1) * 100,
        "Terminal share of EV %": v["tv_share"] * 100,
    }


if __name__ == "__main__":
    t = fin.load()
    if sys.argv[1:] == ["draft"]:
        write(draft(m.history(t), t))
        print("wrote " + ", ".join(f"data/assumptions/{c}.csv" for c in CASES))
    else:
        names = [c for c in (*CASES, "management") if (m.ASSUMPTIONS / f"{c}.csv").exists()]
        names += sorted(p.stem for p in m.ASSUMPTIONS.glob("*.csv") if p.stem not in names)
        table = pd.DataFrame({n: run(n, t) for n in names})
        pd.set_option("display.width", 200)
        print(f"Price Rs {dcf.PRICE} (1-Oct-2026). DCF at the placeholder discount rate, terminal growth "
              f"{dcf.Inputs().terminal_growth:.0%}.\n")
        print(table.round(2).to_string())
        out = m.OUTPUTS / "cases.xlsx"
        table.round(4).to_excel(out, sheet_name="Cases")
        print(f"\nwrote {out}")
