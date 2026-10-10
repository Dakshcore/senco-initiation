"""Monte Carlo on the DCF: draw the drivers from Senco's own FY22-FY26 range and value each draw.

`python -m senco.montecarlo [n]` (default 5,000 draws, fixed seed) prints the distribution of value per share and
writes outputs/montecarlo.xlsx and outputs/montecarlo.png.

Each draw takes every value driver from a triangular distribution with the FY22-FY26 minimum, median and maximum
as low, mode and high (for a driver Daksh set by hand in the base case, that value is the mode instead),
held flat FY27-FY31 (the same drivers and history as senco.cases; revenue growth again
splits into 7 points from new stores and the rest same-store growth). Other drivers sit at the base case. The
discount rate and terminal growth are drawn within one point of Daksh's inputs (WACC 11%, terminal growth 5%). Draws are independent: in reality a bad margin year and a
bad working-capital year tend to come together, so the true spread is probably wider than this.
"""
from __future__ import annotations

import sys
from dataclasses import replace

import numpy as np
import pandas as pd

from senco import cases as cs
from senco import dcf
from senco import financials as fin
from senco import model as m

SEED = 20261001
WACC_SPREAD = 0.01
GROWTH_SPREAD = 0.01  # terminal growth drawn within one point of the base


def ranges(h: pd.DataFrame, t: dict[str, pd.DataFrame] | None = None) -> dict[str, tuple[float, float, float]]:
    """Low, mode, high per driver: the FY22-FY26 min, median and max, with base-case overrides as the mode."""
    mode = {k: x for (c, k), (x, _) in (cs.overrides(t) if t is not None else {}).items() if c == "base"}
    return {k: (h.loc[k].min(), mode.get(k, h.loc[k].median()), h.loc[k].max()) for k in cs.BETTER}


def simulate(n: int = 5000, seed: int = SEED, t: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    t = t or fin.load()
    h = m.history(t)
    base, _ = m.read_assumptions(m.ASSUMPTIONS / "base.csv")
    i = dcf.Inputs()
    wacc0 = dcf.capital_structure(i, t)["wacc"]
    rng = np.random.default_rng(seed)
    draws = {k: rng.triangular(*r, n) for k, r in ranges(h, t).items()}
    draws["wacc"] = rng.triangular(wacc0 - WACC_SPREAD, wacc0, wacc0 + WACC_SPREAD, n)
    g0 = i.terminal_growth
    draws["terminal_growth"] = rng.triangular(g0 - GROWTH_SPREAD, g0, g0 + GROWTH_SPREAD, n)
    out = pd.DataFrame(draws)
    values = []
    for _, d in out.iterrows():
        a = base.copy()
        a.loc["sssg"] = d["revenue_growth"] - cs.NEW_STORES
        for k in cs.BETTER:
            if k != "revenue_growth":
                a.loc[k] = d[k]
        values.append(dcf.value(a, replace(i, wacc=d["wacc"], terminal_growth=d["terminal_growth"]), t)["per_share"])
    out["value"] = values
    return out


def summary(sim: pd.DataFrame, price: float = dcf.PRICE) -> dict[str, float]:
    v = sim["value"]
    return {"draws": len(v), "mean": v.mean(), "p5": v.quantile(0.05), "p25": v.quantile(0.25),
            "median": v.median(), "p75": v.quantile(0.75), "p95": v.quantile(0.95),
            "share above price %": (v > price).mean() * 100, "share below zero %": (v < 0).mean() * 100}


def drivers(sim: pd.DataFrame) -> pd.Series:
    """Rank correlation of each draw with value per share: which driver moves the answer most."""
    return sim.drop(columns="value").corrwith(sim["value"], method="spearman").sort_values(key=abs, ascending=False)


def chart(sim: pd.DataFrame, s: dict[str, float], path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    v = sim["value"].clip(sim["value"].quantile(0.01), sim["value"].quantile(0.99))
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.hist(v, bins=60, color="#4C72B0", alpha=0.85)
    ax.axvline(dcf.PRICE, color="black", linestyle="--", label=f"Price Rs {dcf.PRICE} (1 Oct 2026)")
    ax.axvline(s["median"], color="#C44E52", label=f"Median Rs {s['median']:,.0f}")
    ax.set_xlabel("DCF value per share (Rs); 1st-99th percentile shown")
    ax.set_ylabel("Draws")
    ax.set_title(f"Senco: {s['draws']:,} draws of the drivers across their FY22-FY26 range\n"
                 f"{s['share above price %']:.0f}% of draws are above the price")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    sim = simulate(n)
    s = summary(sim)
    print(f"{n:,} draws, seed {SEED}. Price Rs {dcf.PRICE} (1-Oct-2026)\n")
    for k, x in s.items():
        print(f"  {k:<22} {x:,.2f}")
    print("\nRank correlation with value per share:")
    print(drivers(sim).round(3).to_string())
    m.OUTPUTS.mkdir(exist_ok=True)
    with pd.ExcelWriter(m.OUTPUTS / "montecarlo.xlsx") as xl:
        pd.Series(s).to_frame("value").to_excel(xl, sheet_name="Summary")
        drivers(sim).to_frame("spearman").to_excel(xl, sheet_name="Drivers")
        sim.to_excel(xl, sheet_name="Draws", index=False)
    chart(sim, s, m.OUTPUTS / "montecarlo.png")
    print(f"\nwrote {m.OUTPUTS / 'montecarlo.xlsx'} and montecarlo.png")
