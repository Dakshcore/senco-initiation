"""Senco Gold: free cash flow to the firm (FCFF) DCF and reverse DCF, adapted from titan-valuation.

`python -m senco.dcf [assumptions.csv]` (default data/assumptions/management.csv) values the operating case from
senco.model and writes outputs/dcf_<case>.xlsx.

Cash flows: FY27-FY31 come straight from the operating model. FCFF = EBIT x (1 - tax) + depreciation - capex
- increase in working capital, with EBIT = EBITDA - depreciation (other income is left out, as in Titan).
Working capital is inventory + receivables + other current assets - other liabilities, so leases and customer
advances sit in working capital, not debt. After FY31, growth fades in a straight line to terminal growth over
`fade_years`, with FY31's margins, capex, depreciation and working capital (all as % of revenue) held. A Gordon
terminal value follows the fade.

Discounting follows Titan: the price date is 1 Oct 2026, the first period is the stub to 31 Mar 2027 and only
that fraction of FY27's cash flow counts; net debt is the FY26 balance sheet. Borrowings include gold metal
loans (Q4FY26 call: GML cost 3-3.5%, target 50%+ of borrowings), and all of them are treated as debt.

All amounts are Rs crore unless stated.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import pandas as pd
from scipy.optimize import brentq

from senco import financials as fin
from senco import model as m

PRICE, PRICE_DAY = 317.4, date(2026, 10, 1)   # NSE close, same as jewellery-peer-comps
YEAR_END = date(2027, 3, 31)
TAX_SHIELD = 0.22 * 1.10 * 1.04               # Section 115BAA: 22% + 10% surcharge + 4% cess = 25.168%


@dataclass(frozen=True)
class Inputs:
    # CAPM inputs from Alpha Spread's SENCO discount-rate page (retrieved 8-Oct-2026): 7.2% + 0.78 x 4.3%.
    # Same source as Titan's cost of equity. Placeholders: the final discount rate is Daksh's call.
    risk_free: float = 0.072
    beta: float = 0.78
    erp: float = 0.043
    terminal_growth: float = 0.05   # Daksh, 10 Oct 2026 (was 6%, the titan-valuation placeholder)
    fade_years: int = 10            # FY32-FY41, growth fades to terminal growth
    wacc: float | None = 0.11       # Daksh, 9 Oct 2026: 11%, above the 9.30% CAPM build. None = use the build


def capital_structure(i: Inputs, t: dict[str, pd.DataFrame]) -> dict[str, float]:
    """Market equity at the price date, FY26 debt at its FY26 cost, and the WACC from them."""
    p, b = t["pnl"]["FY26"], t["balance"]
    debt, prior_debt = b.loc["Borrowings", "FY26"], b.loc["Borrowings", "FY25"]
    cost_of_debt = p["Interest"] / ((debt + prior_debt) / 2)
    equity = PRICE * b.loc["No. of Equity Shares", "FY26"] / 1e7
    cost_of_equity = i.risk_free + i.beta * i.erp
    wacc = (equity * cost_of_equity + debt * cost_of_debt * (1 - TAX_SHIELD)) / (equity + debt)
    return {"market_cap": equity, "debt": debt, "net_debt": debt - b.loc["Cash & Bank", "FY26"],
            "cost_of_equity": cost_of_equity, "cost_of_debt": cost_of_debt, "debt_weight": debt / (equity + debt),
            "wacc": wacc if i.wacc is None else i.wacc, "wacc_built": wacc}


def nwc(x) -> float:
    return x["inventory"] + x["receivables"] + x["other_assets"] - x["other_liabilities"]


def explicit(f: pd.DataFrame, assumptions: pd.DataFrame, base: dict[str, float]) -> list[dict]:
    """FY27-FY31 FCFF from the operating model's output."""
    rows, prior = [], nwc(base)
    for y in f.columns:
        c = f[y]
        tax = assumptions.loc["tax_rate", y] / 100
        ebit = c["ebitda"] - c["depreciation"]
        w = nwc(c)
        rows.append({"fy": y, "revenue": c["revenue"], "ebitda": c["ebitda"], "depreciation": c["depreciation"],
                     "ebit": ebit, "tax_rate": tax, "nopat": ebit * (1 - tax), "capex": c["capex"],
                     "nwc": w, "nwc_change": w - prior,
                     "fcff": ebit * (1 - tax) + c["depreciation"] - c["capex"] - (w - prior)})
        prior = w
    return rows


def fade(last: dict, prior_revenue: float, i: Inputs) -> list[dict]:
    """Years after FY31: growth falls in a straight line to terminal growth; FY31 ratios to revenue held."""
    g0 = last["revenue"] / prior_revenue - 1
    r = {k: last[k] / last["revenue"] for k in ("ebitda", "depreciation", "capex", "nwc")}
    rows, rev, w = [], last["revenue"], last["nwc"]
    end = int(last["fy"][2:])
    for n in range(1, i.fade_years + 1):
        g = g0 + (i.terminal_growth - g0) * n / i.fade_years
        rev *= 1 + g
        ebit = rev * (r["ebitda"] - r["depreciation"])
        new_w = rev * r["nwc"]
        rows.append({"fy": f"FY{end + n}", "revenue": rev, "ebitda": rev * r["ebitda"],
                     "depreciation": rev * r["depreciation"], "ebit": ebit, "tax_rate": last["tax_rate"],
                     "nopat": ebit * (1 - last["tax_rate"]), "capex": rev * r["capex"], "nwc": new_w,
                     "nwc_change": new_w - w,
                     "fcff": ebit * (1 - last["tax_rate"]) + rev * (r["depreciation"] - r["capex"]) - (new_w - w)})
        w = new_w
    return rows


def value(assumptions: pd.DataFrame, i: Inputs = Inputs(), t: dict[str, pd.DataFrame] | None = None) -> dict:
    """Value per share in Rs, with the workings."""
    t = t or fin.load()
    base = m.base_state(t)
    f = m.project(assumptions, t)
    cs = capital_structure(i, t)
    wacc, g = cs["wacc"], i.terminal_growth
    if wacc <= g:
        raise ValueError("WACC must exceed terminal growth")
    rows = explicit(f, assumptions, base)
    prior_revenue = rows[-2]["revenue"] if len(rows) > 1 else base["revenue"]
    rows += fade(rows[-1], prior_revenue, i)

    stub = (YEAR_END - PRICE_DAY).days / 365
    pv_explicit = 0.0
    for n, r in enumerate(rows):
        r["factor"] = 1 / (1 + wacc) ** (stub + n)
        r["pv"] = r["fcff"] * (stub if n == 0 else 1) * r["factor"]
        pv_explicit += r["pv"]

    last = rows[-1]
    next_rev = last["revenue"] * (1 + g)
    ebit_pct, dep_pct = last["ebit"] / last["revenue"], last["depreciation"] / last["revenue"]
    capex_pct, nwc_pct = last["capex"] / last["revenue"], last["nwc"] / last["revenue"]
    fcff_next = (next_rev * ebit_pct * (1 - last["tax_rate"]) + next_rev * (dep_pct - capex_pct)
                 - (next_rev - last["revenue"]) * nwc_pct)
    terminal = fcff_next / (wacc - g)
    pv_terminal = terminal * last["factor"]
    ev = pv_explicit + pv_terminal
    equity = ev - cs["net_debt"]
    shares = base["shares"]
    return {"per_share": equity * 1e7 / shares, "ev": ev, "equity": equity, "pv_explicit": pv_explicit,
            "pv_terminal": pv_terminal, "tv_share": pv_terminal / ev, "terminal": terminal,
            "fcff_next": fcff_next, "terminal_ev_ebitda": terminal / last["ebitda"], "stub": stub,
            "nwc_pct_terminal": nwc_pct, "rows": rows, **cs}


def flat(assumptions: pd.DataFrame, driver: str, x: float) -> pd.DataFrame:
    a = assumptions.copy()
    a.loc[driver] = x
    return a


def implied(field: str, assumptions: pd.DataFrame, i: Inputs = Inputs(), lo: float = 0.0, hi: float = 0.5,
            t: dict[str, pd.DataFrame] | None = None) -> float | None:
    """The value of one assumption that makes the DCF equal today's price, all else as in the case.

    `field` is an Inputs field (terminal_growth, wacc) or a model driver, which is then held flat in every year.
    Returns None when the price is not reached anywhere between `lo` and `hi`."""
    t = t or fin.load()
    if field in m.DRIVERS:
        f = lambda x: value(flat(assumptions, field, x), i, t)["per_share"] - PRICE
    else:
        f = lambda x: value(assumptions, replace(i, **{field: x}), t)["per_share"] - PRICE
    if f(lo) * f(hi) > 0:
        return None
    return brentq(f, lo, hi)


def grid(assumptions: pd.DataFrame, i: Inputs, t, waccs, growths) -> pd.DataFrame:
    return pd.DataFrame({f"{g:.1%}": [value(assumptions, replace(i, wacc=w, terminal_growth=g), t)["per_share"]
                                      for w in waccs] for g in growths}, index=[f"{w:.2%}" for w in waccs])


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else m.ASSUMPTIONS / "management.csv"
    t = fin.load()
    a, _ = m.read_assumptions(path)
    i = Inputs()
    v = value(a, i, t)
    pd.set_option("display.width", 200)
    print(f"Case: {path.stem}. Price Rs {PRICE:,.2f} (NSE close, {PRICE_DAY:%d-%b-%Y})\n")
    print(f"Cost of equity {v['cost_of_equity']:.2%} = {i.risk_free:.1%} + {i.beta} x {i.erp:.1%}; "
          f"cost of debt {v['cost_of_debt']:.2%} pre-tax (FY26 interest / average borrowings)")
    print(f"WACC {v['wacc']:.2%} (debt {v['debt_weight']:.1%} of Rs {v['market_cap'] + v['debt']:,.2f} cr), "
          f"terminal growth {i.terminal_growth:.1%}, fade {i.fade_years} years\n")
    rows = pd.DataFrame(v["rows"]).set_index("fy")
    cols = ["revenue", "ebitda", "ebit", "nopat", "capex", "depreciation", "nwc_change", "fcff", "factor", "pv"]
    print(rows[cols].T.round(2).to_string())
    print(f"\nFCFF DCF value per share: Rs {v['per_share']:,.2f} ({v['per_share'] / PRICE - 1:+.1%} vs price)")
    print(f"  EV Rs {v['ev']:,.2f} cr = explicit + fade Rs {v['pv_explicit']:,.2f} cr + terminal "
          f"Rs {v['pv_terminal']:,.2f} cr ({v['tv_share']:.1%}); net debt Rs {v['net_debt']:,.2f} cr")
    print(f"  Terminal value = {v['terminal_ev_ebitda']:.2f}x {rows.index[-1]} EBITDA; "
          f"working capital {v['nwc_pct_terminal']:.1%} of revenue")

    print("\nWhat the price implies (one assumption at a time, drivers held flat FY27-FY31):")
    imp = {
        "EBITDA margin %": implied("ebitda_margin", a, i, 1.0, 30.0, t),
        "SSSG %": implied("sssg", a, i, -30.0, 60.0, t),
        "Inventory days (avg)": implied("inventory_days", a, i, 30.0, 400.0, t),
        "Terminal growth": implied("terminal_growth", a, i, -0.05, v["wacc"] - 1e-4, t),
        "WACC": implied("wacc", a, i, i.terminal_growth + 1e-3, 0.40, t),
    }
    for k, x in imp.items():
        if x is None:
            print(f"  {k:<22} not reached in the search range (value stays above the price)")
        else:
            print(f"  {k:<22} {x:.2%}" if k in ("Terminal growth", "WACC") else f"  {k:<22} {x:.2f}")

    waccs = [v["wacc"] + d for d in (-0.01, -0.005, 0, 0.005, 0.01)]
    g = grid(a, i, t, waccs, [0.04, 0.05, 0.06, 0.07])
    print("\nValue per share (Rs): WACC (rows) x terminal growth (columns)")
    print(g.round(2).to_string())

    summary = pd.Series({"Price (Rs)": PRICE, "Value per share (Rs)": v["per_share"], "EV": v["ev"],
                         "PV explicit + fade": v["pv_explicit"], "PV terminal": v["pv_terminal"],
                         "Net debt": v["net_debt"], "Cost of equity": v["cost_of_equity"],
                         "Cost of debt (pre-tax)": v["cost_of_debt"], "WACC": v["wacc"],
                         "Terminal growth": i.terminal_growth, "Terminal EV/EBITDA": v["terminal_ev_ebitda"],
                         **{f"Implied {k}": x for k, x in imp.items()}})
    out = m.OUTPUTS / f"dcf_{path.stem}.xlsx"
    out.parent.mkdir(exist_ok=True)
    with pd.ExcelWriter(out) as xl:
        summary.to_frame("value").to_excel(xl, sheet_name="Summary")
        rows.T.to_excel(xl, sheet_name="FCFF")
        g.to_excel(xl, sheet_name="WACC x g")
    print(f"\nwrote {out}")
