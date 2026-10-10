"""Load Senco Gold's Screener.in export into clean pandas tables.

The export's "Data Sheet" has column A labels and section header rows (PROFIT & LOSS, Quarters,
BALANCE SHEET, CASH FLOW:). Each section starts with a "Report Date" row; the rows below it are
items in rupees crore. Empty date columns (Screener pads young companies) are dropped.

Annual columns are fiscal years ending 31 March, labelled FY21, FY22, ... Quarter columns are
labelled by fiscal quarter, so the quarter ending 30 Jun 2026 is Q1FY27.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = ROOT / "data" / "raw" / "screener" / "SENCO.xlsx"

SECTIONS = {"PROFIT & LOSS": "pnl", "QUARTERS": "quarters", "BALANCE SHEET": "balance", "CASH FLOW": "cashflow"}
STOP = {"PRICE", "DERIVED"}  # sections after cash flow that hold single rows, not tables


def fiscal_year(d: dt.date) -> str:
    return f"FY{(d.year + (d.month > 3)) % 100:02d}"


def fiscal_quarter(d: dt.date) -> str:
    q = {6: 1, 9: 2, 12: 3, 3: 4}[d.month]
    return f"Q{q}{fiscal_year(d)}"


def _clean(label) -> str:
    return " ".join(str(label).split()).rstrip(":").upper()


def load(path: Path = DEFAULT_FILE) -> dict[str, pd.DataFrame]:
    """Return {'pnl', 'quarters', 'balance', 'cashflow'}: items as rows, periods as columns."""
    ws = openpyxl.load_workbook(path, data_only=True)["Data Sheet"]
    tables: dict[str, pd.DataFrame] = {}
    section, dates, rows = None, None, {}

    def close():
        if section and dates:
            keep = [i for i, d in enumerate(dates) if d is not None]
            name = fiscal_quarter if section == "quarters" else fiscal_year
            cols = [name(dates[i].date()) for i in keep]
            tables[section] = pd.DataFrame({k: [v[i] for i in keep] for k, v in rows.items()}, index=cols).T

    for label, *values in ws.iter_rows(values_only=True):
        if label is None:
            continue
        key = _clean(label)
        if key in SECTIONS or key in STOP:
            close()
            section, dates, rows = SECTIONS.get(key), None, {}
            continue
        if section is None:
            continue
        if key == "REPORT DATE":
            dates = list(values)
        elif dates is not None:
            # "Total" appears twice in the balance sheet (liabilities and assets); the export makes them equal
            rows[" ".join(str(label).split())] =[v if v is not None else float("nan") for v in values[:len(dates)]]
    close()
    return tables


def operating_costs(pnl: pd.DataFrame) -> pd.Series:
    """Raw material net of inventory change, plus every other operating expense line."""
    return (pnl.loc["Raw Material Cost"] - pnl.loc["Change in Inventory"] + pnl.loc["Power and Fuel"]
            + pnl.loc["Other Mfr. Exp"] + pnl.loc["Employee Cost"] + pnl.loc["Selling and admin"]
            + pnl.loc["Other Expenses"])


def _follows_prior_year(years: list[str]) -> list[bool]:
    """True where the previous column is the previous fiscal year (the export skips FY16-FY20)."""
    return [i > 0 and int(y[2:]) - int(years[i - 1][2:]) == 1 for i, y in enumerate(years)]


def ratios(t: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Annual ratios for the fiscal years that have a full P&L, balance sheet and cash flow."""
    pnl, bs, cf = t["pnl"], t["balance"], t["cashflow"]
    years = [y for y in pnl.columns if y in bs.columns and y in cf.columns]
    pnl, bs, cf = pnl[years], bs[years], cf[years]
    sales = pnl.loc["Sales"]
    ebitda = sales - operating_costs(pnl)
    equity = bs.loc["Equity Share Capital"] + bs.loc["Reserves"]
    out = pd.DataFrame({
        "Sales (Rs cr)": sales,
        "Sales growth": sales.pct_change(fill_method=None).where(_follows_prior_year(years)),
        "EBITDA (Rs cr)": ebitda,
        "EBITDA margin": ebitda / sales,
        "Net margin": pnl.loc["Net profit"] / sales,
        "Inventory days": bs.loc["Inventory"] / sales * 365,
        "Net debt (Rs cr)": bs.loc["Borrowings"] - bs.loc["Cash & Bank"],
        "Net debt / equity": (bs.loc["Borrowings"] - bs.loc["Cash & Bank"]) / equity,
        "ROE": pnl.loc["Net profit"] / equity,
        "CFO (Rs cr)": cf.loc["Cash from Operating Activity"],
        "CFO / net profit": cf.loc["Cash from Operating Activity"] / pnl.loc["Net profit"],
    })
    return out.T


if __name__ == "__main__":
    t = load()
    for name, df in t.items():
        print(f"{name}: {df.shape[0]} items x {df.shape[1]} periods ({', '.join(df.columns)})")
