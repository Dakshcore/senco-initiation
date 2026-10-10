"""Senco Gold against its listed jewellery peers, on reported and on margin-normalised FY26 earnings.

The peer multiples come from jewellery-peer-comps, run with Senco as the target:

    python -m comps --target SENCO --peers KALYANKJIL,THANGAMAYL,PNGJL --reference TITAN,TRENT
        --ref-price 317.4 --ref-date 1-Oct-2026 --out-dir <this repo>/data/comps/fy   (add --basis ltm and data/comps/ltm for LTM)

`python -m senco.comps` reads that workbook and applies the peer range to Senco twice: to FY26 as reported, and
to FY26 sales at other EBITDA margins. FY26's 11.7% margin includes gold-price gains on inventory (Day 5), so
peer multiples on reported EBITDA treat a one-off as recurring. Which margin is "normal" is Daksh's call; the
levels shown are Senco's own FY24 and FY25 margins and management's FY27 guide.

Normalised net profit = reported net profit - (reported EBITDA - normalised EBITDA) x (1 - FY26 tax rate).
Money is Rs crore unless stated.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from senco import financials as fin
from senco import model as m

COMPS = m.ROOT / "data" / "comps" / "fy" / "comps.xlsx"
PRICE = 317.4
STATS = ("Peer minimum", "Peer 25th percentile", "Peer median", "Peer 75th percentile", "Peer maximum")
MULTIPLES = {"EV/EBITDA": "ebitda", "P/E": "net_profit", "EV/Sales": "sales"}


def load(path: Path = COMPS) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """Peer rows, peer statistics (rows = statistic, columns = multiple) and Senco's own row."""
    c = pd.read_excel(path, sheet_name="Comps table")
    peers = c[c["Group"] == "Core peer"].set_index("Symbol")
    stats = c[c["Symbol"].isin(STATS)].set_index("Symbol")[list(MULTIPLES)]
    target = c[c["Group"] == "Target"].iloc[0]
    if target["Symbol"] != "SENCO":
        raise ValueError(f"{path} was run for {target['Symbol']}, not SENCO")
    return peers, stats.loc[list(STATS)], target


def senco(t: dict[str, pd.DataFrame], margin: float | None = None) -> dict[str, float]:
    """FY26 sales, EBITDA and net profit, with EBITDA reset to `margin` (a fraction) when one is given."""
    p, b = t["pnl"]["FY26"], t["balance"]["FY26"]
    ebitda = p["Profit before tax"] + p["Interest"] + p["Depreciation"] - p["Other Income"]
    out = {"sales": p["Sales"], "ebitda": ebitda, "net_profit": p["Net profit"],
           "net_debt": b["Borrowings"] - b["Cash & Bank"], "shares": b["No. of Equity Shares"]}
    if margin is not None:
        tax = p["Tax"] / p["Profit before tax"]
        out["ebitda"] = p["Sales"] * margin
        out["net_profit"] = p["Net profit"] - (ebitda - out["ebitda"]) * (1 - tax)
    return out


def implied(multiple: str, x: float, s: dict[str, float]) -> float:
    """Value per share in Rs from one multiple applied to Senco's metric."""
    metric = s[MULTIPLES[multiple]]
    equity = x * metric if multiple == "P/E" else x * metric - s["net_debt"]
    return equity * 1e7 / s["shares"]


def implied_table(stats: pd.DataFrame, s: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame({k: [implied(k, stats.loc[r, k], s) for r in stats.index] for k in MULTIPLES},
                        index=[r.replace("Peer ", "") for r in stats.index]).T


def margin_for_price(multiple: str, x: float, t: dict[str, pd.DataFrame], price: float = PRICE) -> float:
    """The FY26 EBITDA margin at which the peer multiple gives today's price (EV/EBITDA and P/E only)."""
    s = senco(t)
    equity = price * s["shares"] / 1e7
    if multiple == "EV/EBITDA":
        return (equity + s["net_debt"]) / x / s["sales"]
    p = t["pnl"]["FY26"]
    tax = p["Tax"] / p["Profit before tax"]
    # net profit at margin m = reported net profit - (reported EBITDA - sales x m)(1 - tax); solve for m.
    return (equity / x - s["net_profit"] + s["ebitda"] * (1 - tax)) / (s["sales"] * (1 - tax))


def margins(t: dict[str, pd.DataFrame]) -> dict[str, float]:
    h = m.history(t).loc["ebitda_margin"] / 100
    a, _ = m.read_assumptions(m.ASSUMPTIONS / "management.csv")
    return {"FY26 reported": None, "FY24 (7.41%)": h["FY24"], "FY25 (6.02%)": h["FY25"],
            f"Mgmt FY27 guide ({a.loc['ebitda_margin', 'FY27']:.2f}%)": a.loc["ebitda_margin", "FY27"] / 100}


if __name__ == "__main__":
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else COMPS
    t = fin.load()
    peers, stats, target = load(path)
    pd.set_option("display.width", 200)
    cols = ["Price (₹)", "EV/Sales", "EV/EBITDA", "P/E", "EBITDA margin", "ROCE", "Inventory days",
            "Revenue growth 1y"]
    print(f"Peer workbook: {path}\n")
    print(pd.concat([target.to_frame().T.set_index("Symbol"), peers])[cols].round(3).to_string())
    print("\nPeer multiples (n = %d):" % len(peers))
    print(stats.round(2).to_string())

    rows = []
    for label, mg in margins(t).items():
        s = senco(t, mg)
        tab = implied_table(stats, s)
        print(f"\nImplied value per share (Rs), Senco FY26 at {label}: EBITDA {s['ebitda']:,.2f}, "
              f"net profit {s['net_profit']:,.2f}")
        print(tab.round(2).to_string())
        for k in MULTIPLES:
            rows.append({"basis": label, "multiple": k, **tab.loc[k].to_dict()})
    print(f"\nReference price Rs {PRICE} (1-Oct-2026)")

    print("\nFY26 EBITDA margin at which the peer multiple gives today's price:")
    for k in ("EV/EBITDA", "P/E"):
        for r in ("Peer minimum", "Peer median"):
            print(f"  {k:<10} {r:<14} {stats.loc[r, k]:5.2f}x -> {margin_for_price(k, stats.loc[r, k], t):.2%}")

    out = m.OUTPUTS / "comps_senco.xlsx"
    with pd.ExcelWriter(out) as xl:
        stats.to_excel(xl, sheet_name="Peer multiples")
        pd.DataFrame(rows).to_excel(xl, sheet_name="Implied values", index=False)
    print(f"\nwrote {out}")
