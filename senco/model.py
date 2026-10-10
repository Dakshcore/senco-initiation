"""Senco Gold operating model: FY26 actuals rolled forward with a set of annual drivers.

`python -m senco.model [assumptions.csv]` (default data/assumptions/management.csv) prints the forecast and
writes outputs/model_<case>.xlsx with the history, the drivers and the forecast side by side.

Revenue follows management's own framework (Q2FY26 call): growth = same-store sales growth (value, so it
includes the gold price) + the contribution from new stores. EBITDA margin is a direct input, because that is
what management guides. Working capital is driven by days of revenue; inventory days use management's
definition, average inventory / revenue x 365 (it reproduces their 166 days for FY25 and 186 for FY26).
Borrowings are the balancing item: whatever the balance sheet needs after equity and other liabilities.
Interest is charged on average borrowings, so the year is solved by iteration.

All amounts are Rs crore, consolidated, March year-end.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pandas as pd

from senco import financials as fin

ROOT = Path(__file__).resolve().parent.parent
ASSUMPTIONS = ROOT / "data" / "assumptions"
OUTPUTS = ROOT / "outputs"
BASE = "FY26"

DRIVERS = {  # key: (unit, description)
    "sssg": ("%", "Same-store sales growth, value (includes gold price)"),
    "new_store_contribution": ("pp", "Revenue growth added by stores opened in the last two years"),
    "store_additions": ("count", "Stores opened (memo: not used in the arithmetic)"),
    "gold_price_change": ("%", "Average gold price change (memo: splits SSSG into price and volume)"),
    "ebitda_margin": ("%", "EBITDA / revenue"),
    "other_income_pct": ("%", "Other income / revenue"),
    "dep_rate": ("%", "Depreciation / opening net block"),
    "capex_pct": ("%", "Capex / revenue"),
    "interest_rate": ("%", "Interest / average borrowings"),
    "tax_rate": ("%", "Tax / profit before tax"),
    "inventory_days": ("days", "Average inventory / revenue x 365 (management's definition)"),
    "receivable_days": ("days", "Closing receivables / revenue x 365"),
    "other_assets_pct": ("%", "Other current assets / revenue"),
    "other_liab_days": ("days", "Other liabilities (trade payables, customer advances, scheme deposits, tax) / revenue x 365"),
    "payout": ("%", "Dividend / net profit"),
}


def base_state(t: dict[str, pd.DataFrame], year: str = BASE) -> dict[str, float]:
    p, b = t["pnl"][year], t["balance"][year]
    other_assets = b["Other Assets"] - b["Inventory"] - b["Receivables"] - b["Cash & Bank"]
    return {
        "revenue": p["Sales"], "net_block": b["Net Block"], "cwip": b["Capital Work in Progress"],
        "investments": b["Investments"], "inventory": b["Inventory"], "receivables": b["Receivables"],
        "cash": b["Cash & Bank"], "other_assets": other_assets, "share_capital": b["Equity Share Capital"],
        "reserves": b["Reserves"], "borrowings": b["Borrowings"], "other_liabilities": b["Other Liabilities"],
        "shares": b["No. of Equity Shares"],
    }


def history(t: dict[str, pd.DataFrame], years=("FY22", "FY23", "FY24", "FY25", "FY26")) -> pd.DataFrame:
    """The same drivers measured on reported years, so every assumption can be read against its history."""
    p, b, r = t["pnl"], t["balance"], fin.ratios(t)
    cols = list(p.columns)
    out = {}
    for y in years:
        prev = cols[cols.index(y) - 1]
        s = p.loc["Sales", y]
        capex = (b.loc["Net Block", y] - b.loc["Net Block", prev] + b.loc["Capital Work in Progress", y]
                 - b.loc["Capital Work in Progress", prev] + p.loc["Depreciation", y])
        oa = b.loc["Other Assets", y] - b.loc["Inventory", y] - b.loc["Receivables", y] - b.loc["Cash & Bank", y]
        out[y] = {
            "revenue_growth": (s / p.loc["Sales", prev] - 1) * 100 if prev == f"FY{int(y[2:]) - 1}" else float("nan"),
            "ebitda_margin": r.loc["EBITDA margin", y] * 100,
            "other_income_pct": p.loc["Other Income", y] / s * 100,
            "dep_rate": p.loc["Depreciation", y] / b.loc["Net Block", prev] * 100,
            "capex_pct": capex / s * 100,
            "interest_rate": p.loc["Interest", y] / ((b.loc["Borrowings", y] + b.loc["Borrowings", prev]) / 2) * 100,
            "tax_rate": p.loc["Tax", y] / p.loc["Profit before tax", y] * 100,
            "inventory_days": (b.loc["Inventory", y] + b.loc["Inventory", prev]) / 2 / s * 365,
            "receivable_days": b.loc["Receivables", y] / s * 365,
            "other_assets_pct": oa / s * 100,
            "other_liab_days": b.loc["Other Liabilities", y] / s * 365,
            "payout": p.loc["Dividend Amount", y] / p.loc["Net profit", y] * 100,
        }
    return pd.DataFrame(out)


def read_assumptions(path: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    """Rows are drivers, columns are forecast years; blanks are allowed only for memo drivers."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    years = [c for c in rows[0] if c.startswith("FY")]
    unknown = {r["driver"] for r in rows} - set(DRIVERS)
    if unknown:
        raise ValueError(f"unknown drivers: {unknown}")
    values = {r["driver"]: [float(r[y]) if r[y] != "" else float("nan") for y in years] for r in rows}
    return pd.DataFrame(values, index=years).T, {r["driver"]: r["source"] for r in rows}


def step(prev: dict[str, float], d: dict[str, float], iterations: int = 50,
         overrides: dict[str, float] | None = None) -> dict[str, float]:
    """Roll one year forward from the previous year's closing balances.

    `overrides` sets closing balances directly (used by the tests to replay a reported year)."""
    pct = lambda k: d[k] / 100
    s = {}
    growth = pct("sssg") + pct("new_store_contribution")
    s["revenue"] = rev = prev["revenue"] * (1 + growth)
    s["ebitda"] = rev * pct("ebitda_margin")
    s["other_income"] = rev * pct("other_income_pct")
    s["depreciation"] = prev["net_block"] * pct("dep_rate")
    s["capex"] = rev * pct("capex_pct")
    s["net_block"] = prev["net_block"] + s["capex"] - s["depreciation"]
    for k in ("cwip", "investments", "cash", "share_capital", "shares"):
        s[k] = prev[k]
    # Average inventory = days x revenue / 365. Solving that exactly for closing inventory makes it swing year
    # to year, so closing inventory is set to what it would be if inventory grew in line with revenue.
    s["inventory"] = d["inventory_days"] * rev / 365 * 2 * (1 + growth) / (2 + growth)
    s["receivables"] = d["receivable_days"] * rev / 365
    s["other_assets"] = rev * pct("other_assets_pct")
    s["other_liabilities"] = d["other_liab_days"] * rev / 365
    s.update(overrides or {})
    assets =(s["net_block"] + s["cwip"] + s["investments"] + s["inventory"] + s["receivables"] + s["cash"]
              + s["other_assets"])
    borrowings = prev["borrowings"]
    for _ in range(iterations):
        s["interest"] = (borrowings + prev["borrowings"]) / 2 * pct("interest_rate")
        s["pbt"] = s["ebitda"] + s["other_income"] - s["depreciation"] - s["interest"]
        s["tax"] = s["pbt"] * pct("tax_rate")
        s["net_profit"] = s["pbt"] - s["tax"]
        s["dividend"] = s["net_profit"] * pct("payout")
        s["reserves"] = prev["reserves"] + s["net_profit"] - s["dividend"]
        new = assets - s["share_capital"] - s["reserves"] - s["other_liabilities"]
        if abs(new - borrowings) < 1e-9:
            break
        borrowings = new
    s["borrowings"] = borrowings
    nwc = lambda x: x["inventory"] + x["receivables"] + x["other_assets"] - x["other_liabilities"]
    s["cfo"] = s["net_profit"] + s["depreciation"] - (nwc(s) - nwc(prev))
    s["cfi"] = -(s["capex"] + s["cwip"] - prev["cwip"] + s["investments"] - prev["investments"])
    s["cff"] = s["borrowings"] - prev["borrowings"] - s["dividend"] + s["share_capital"] - prev["share_capital"]
    s["cash_change"] = s["cash"] - prev["cash"]
    return s


def project(assumptions: pd.DataFrame, t: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    t = t or fin.load()
    state = base_state(t)
    out = {}
    for year in assumptions.columns:
        state = step(state, assumptions[year].to_dict())
        out[year] = state
    return pd.DataFrame(out)


def metrics(f: pd.DataFrame, base: dict[str, float]) -> pd.DataFrame:
    """Ratios on the forecast, in the units management uses, for checking against their guidance."""
    equity = f.loc["share_capital"] + f.loc["reserves"]
    prev_inventory = pd.concat([pd.Series({BASE: base["inventory"]}), f.loc["inventory"]]).shift(1)[f.columns]
    prev_revenue = pd.concat([pd.Series({BASE: base["revenue"]}), f.loc["revenue"]]).shift(1)[f.columns]
    prev_equity = pd.concat([pd.Series({BASE: base["share_capital"] + base["reserves"]}), equity]).shift(1)[f.columns]
    return pd.DataFrame({
        "Revenue (Rs cr)": f.loc["revenue"],
        "Revenue growth %": (f.loc["revenue"] / prev_revenue - 1) * 100,
        "EBITDA (Rs cr)": f.loc["ebitda"],
        "Net profit (Rs cr)": f.loc["net_profit"],
        "PAT margin %": f.loc["net_profit"] / f.loc["revenue"] * 100,
        "EPS (Rs)": f.loc["net_profit"] * 1e7 / f.loc["shares"],
        "Inventory days (avg, mgmt def.)": (f.loc["inventory"] + prev_inventory) / 2 / f.loc["revenue"] * 365,
        "Borrowings (Rs cr)": f.loc["borrowings"],
        "Debt / equity (x)": f.loc["borrowings"] / equity,
        "ROE % (avg equity)": f.loc["net_profit"] / ((equity + prev_equity) / 2) * 100,
        "CFO (Rs cr)": f.loc["cfo"],
        "Free cash flow (Rs cr)": f.loc["cfo"] + f.loc["cfi"],
    }).T


def write_excel(path: Path, hist: pd.DataFrame, assumptions: pd.DataFrame, sources: dict[str, str],
                forecast: pd.DataFrame, m: pd.DataFrame) -> None:
    path.parent.mkdir(exist_ok=True)
    a = assumptions.copy()
    a.insert(0, "unit", [DRIVERS[k][0] for k in a.index])
    a["source"] = [sources[k] for k in a.index]
    with pd.ExcelWriter(path) as xl:
        m.round(2).to_excel(xl, sheet_name="Summary")
        a.to_excel(xl, sheet_name="Assumptions")
        hist.round(2).to_excel(xl, sheet_name="Driver history")
        forecast.round(2).to_excel(xl, sheet_name="Forecast detail")


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ASSUMPTIONS / "management.csv"
    t = fin.load()
    assumptions, sources = read_assumptions(path)
    forecast = project(assumptions, t)
    m = metrics(forecast, base_state(t))
    pd.set_option("display.width", 200)
    print(f"Case: {path.stem}\n")
    print(m.round(2).to_string())
    out = OUTPUTS / f"model_{path.stem}.xlsx"
    write_excel(out, history(t), assumptions, sources, forecast, m)
    print(f"\nwrote {out}")
