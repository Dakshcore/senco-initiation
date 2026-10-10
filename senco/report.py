"""Build the initiation report from the model: numbers, charts, HTML and PDF, plus the Day 13 number check.

    python -m senco.report            # numbers + charts + report/build/senco_initiation.{md,html,pdf}
    python -m senco.report check      # Day 13: every number in the report comes from a run or a cited source

The report text is report/senco_initiation.md. Every model number in it is a {placeholder} filled from
`numbers()`, so the text cannot drift from the model. A number typed into the text by hand is allowed only on a
line that carries a citation ([^n]) or in a period label (FY26, Q4FY26, G123); `check` fails on anything else.
Until REVIEWED is set to True, every page carries a "Draft, not reviewed" banner.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

from senco import cases as cs
from senco import comps
from senco import dcf
from senco import financials as fin
from senco import model as m
from senco import montecarlo as mc

REVIEWED = True   # Daksh, 10 Oct 2026
RATING = "Buy"   # Daksh, 10 Oct 2026. None = rule on upside to the target (Buy above 15%, Sell below -10%)
REPORT = m.ROOT / "report"
TEMPLATE = REPORT / "senco_initiation.md"
BUILD = REPORT / "build"
FIG = REPORT / "fig"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
MC_DRAWS = 5000
# Published targets after Q4FY26, Rs per share (docs/research/coverage.md, read 9 Oct 2026).
BROKER_TARGETS = {"Emkay, 13 Aug 2026": 575, "Motilal Oswal, 12 Aug 2026": 385,
                  "BOB Capital Markets, 12 Aug 2026": 422, "SBI Securities, 29 May 2026": 400}


def f0(x): return f"{x:,.0f}"
def f1(x): return f"{x:,.1f}"
def f2(x): return f"{x:,.2f}"
def pct(x, dp=1): return f"{x * 100:.{dp}f}%"   # fraction -> "12.3%"
def pp(x, dp=1): return f"{x:.{dp}f}%"          # already in percent -> "12.3%"


def delivery() -> dict[str, str]:
    d = pd.read_csv(m.ROOT / "data" / "delivery.csv")
    scored = d[d["verdict"].isin(["met", "beat", "missed"])].copy()
    scored["ok"] = scored["verdict"] != "missed"
    scored["year"] = scored["target_period"].str.extract(r"(FY\d\d)")[0]
    out = {"del_hit": str(scored["ok"].sum()), "del_n": str(len(scored)),
           "del_rate": pct(scored["ok"].mean()), "del_not_due": str((d["verdict"] == "not due").sum()),
           "del_rows": str(len(d)), "del_no_actual": str((d["verdict"] == "no actual").sum())}
    for y, g in scored.groupby("year"):
        out[f"del_{y}_hit"], out[f"del_{y}_n"] = str(g["ok"].sum()), str(len(g))
    for k, g in scored.groupby("metric"):
        out[f"del_m_{k}_hit"], out[f"del_m_{k}_n"] = str(g["ok"].sum()), str(len(g))
    latest = scored[scored["metric"] != "other"].drop_duplicates(["metric", "target_period"], keep="last")
    out["del_distinct_hit"], out["del_distinct_n"] = str(latest["ok"].sum()), str(len(latest))
    out["del_distinct_rate"] = pct(latest["ok"].mean())
    return out


def numbers(t: dict[str, pd.DataFrame] | None = None) -> tuple[dict[str, str], dict]:
    """Every model figure the report quotes, formatted, plus the raw objects the charts need."""
    t = t or fin.load()
    n: dict[str, str] = {}
    r, p, b = fin.ratios(t), t["pnl"], t["balance"]
    base = m.base_state(t)
    n.update(price=f2(dcf.PRICE), price_date="1 October 2026", shares_mn=f2(base["shares"] / 1e6))

    # History
    for y in ("FY21", "FY22", "FY23", "FY24", "FY25", "FY26"):
        n[f"sales_{y}"] = f2(r.loc["Sales (Rs cr)", y])
        n[f"ebitda_m_{y}"] = pct(r.loc["EBITDA margin", y])
        n[f"inv_days_{y}"] = f0(r.loc["Inventory days", y])
        n[f"cfo_{y}"] = f2(r.loc["CFO (Rs cr)", y])
        n[f"roe_{y}"] = pct(r.loc["ROE", y])
        n[f"net_margin_{y}"] = pct(r.loc["Net margin", y])
    for y in ("FY22", "FY23", "FY24", "FY25", "FY26"):
        n[f"growth_{y}"] = pct(r.loc["Sales growth", y])
    n["sales_cagr_21_26"] = pct((r.loc["Sales (Rs cr)", "FY26"] / r.loc["Sales (Rs cr)", "FY21"]) ** (1 / 5) - 1)
    n["cfo_sum_22_26"] = f2(r.loc["CFO (Rs cr)", ["FY22", "FY23", "FY24", "FY25", "FY26"]].sum())
    n["pat_FY26"], n["ebitda_FY26"] = f2(p.loc["Net profit", "FY26"]), f2(r.loc["EBITDA (Rs cr)", "FY26"])
    n["net_debt_FY26"], n["nde_FY26"] = f2(r.loc["Net debt (Rs cr)", "FY26"]), f2(r.loc["Net debt / equity", "FY26"])
    n["borrowings_FY26"], n["cash_FY26"] = f2(b.loc["Borrowings", "FY26"]), f2(b.loc["Cash & Bank", "FY26"])
    h = m.history(t)
    n["oliab_days_FY25"], n["oliab_days_FY26"] = f2(h.loc["other_liab_days", "FY25"]), f2(h.loc["other_liab_days", "FY26"])
    n["oliab_days_min"], n["oliab_days_max_pre26"] = f2(h.loc["other_liab_days"].min()), f2(h.loc["other_liab_days", ["FY22", "FY23", "FY24", "FY25"]].max())
    n["inv_days_avg_FY25"], n["inv_days_avg_FY26"] = f0(h.loc["inventory_days", "FY25"]), f0(h.loc["inventory_days", "FY26"])
    n["oliab_FY25"], n["oliab_FY26"] = f2(b.loc["Other Liabilities", "FY25"]), f2(b.loc["Other Liabilities", "FY26"])
    li = cs.liabilities()
    for y in ("FY25", "FY26"):
        for item, key in (("Revenue received in advance", "adv"), ("Scheme deposits (current)", "scheme"),
                          ("Acceptances (deferred payment to suppliers)", "accept"), ("Current tax liabilities (net)", "tax")):
            n[f"li_{key}_{y}"] = f2(li.loc[item, y] / 10)
        n[f"li_total_{y}"] = f2(li[y].sum() / 10)
    n["li_trade_FY25"] = f2(li.loc[li.index.str.startswith(("Trade", "Accept")), "FY25"].sum() / 10)
    n["li_trade_FY26"] = f2(li.loc[li.index.str.startswith(("Trade", "Accept")), "FY26"].sum() / 10)
    oliab_adj = cs.other_liab_days_ex_one_offs(t)
    n["oliab_days_adj"] = f2(oliab_adj)

    n.update(delivery())

    # Management case: model and DCF
    a_mgmt, _ = m.read_assumptions(m.ASSUMPTIONS / "management.csv")
    f_mgmt = m.project(a_mgmt, t)
    k = m.metrics(f_mgmt, base)
    for y in ("FY27", "FY28", "FY31"):
        n[f"mg_rev_{y}"] = f2(k.loc["Revenue (Rs cr)", y])
        n[f"mg_pat_{y}"] = f2(k.loc["Net profit (Rs cr)", y])
        n[f"mg_eps_{y}"] = f2(k.loc["EPS (Rs)", y])
        n[f"mg_de_{y}"] = f2(k.loc["Debt / equity (x)", y])
        n[f"mg_roe_{y}"] = pp(k.loc["ROE % (avg equity)", y])
        n[f"mg_fcf_{y}"] = f2(k.loc["Free cash flow (Rs cr)", y])
    n["mg_fcf_sum"] = f2(k.loc["Free cash flow (Rs cr)"].sum())
    n["mg_pe_FY27"] = f1(dcf.PRICE / k.loc["EPS (Rs)", "FY27"])
    k_flat = m.metrics(m.project(dcf.flat(a_mgmt, "inventory_days", h.loc["inventory_days", "FY26"]), t), base)
    n["mg_fcf_sum_invflat"] = f2(k_flat.loc["Free cash flow (Rs cr)"].sum())
    i = dcf.Inputs()
    v = dcf.value(a_mgmt, i, t)
    n.update(rf=pct(i.risk_free), beta=f2(i.beta), erp=pct(i.erp), ke=pct(v["cost_of_equity"], 2),
             kd=pct(v["cost_of_debt"], 2), wacc=pct(v["wacc"], 2), wacc_built=pct(v["wacc_built"], 2), debt_w=pct(v["debt_weight"]),
             tg=pct(i.terminal_growth), fade=str(i.fade_years), mktcap=f2(v["market_cap"]),
             ev_mkt=f2(v["market_cap"] + v["net_debt"]))
    n.update(dcf_mg=f2(v["per_share"]), dcf_mg_up=pct(v["per_share"] / dcf.PRICE - 1, 0),
             dcf_mg_tv=pct(v["tv_share"]), dcf_mg_tvx=f2(v["terminal_ev_ebitda"]), dcf_mg_ev=f2(v["ev"]),
             dcf_mg_nwc=pct(v["nwc_pct_terminal"]))
    imp = {"margin": dcf.implied("ebitda_margin", a_mgmt, i, 1.0, 30.0, t),
           "sssg": dcf.implied("sssg", a_mgmt, i, -30.0, 60.0, t),
           "inv": dcf.implied("inventory_days", a_mgmt, i, 30.0, 400.0, t),
           "wacc": dcf.implied("wacc", a_mgmt, i, i.terminal_growth + 1e-3, 0.40, t)}
    n.update(imp_margin=pp(imp["margin"], 2), imp_sssg=pp(imp["sssg"], 2), imp_inv=f0(imp["inv"]),
             imp_wacc=pct(imp["wacc"], 2))
    grid = dcf.grid(a_mgmt, i, t, [v["wacc"] - 0.01, v["wacc"], v["wacc"] + 0.01],
                    [i.terminal_growth - 0.01, i.terminal_growth + 0.01])
    n["grid_lo"], n["grid_hi"] = f0(grid.values.min()), f0(grid.values.max())
    n["grid_hi_wacc_lo_g"] = f0(grid.iloc[-1, 0])

    # Bear / base / bull
    case_runs = {c: cs.run(c, t) for c in cs.CASES}
    for c, x in case_runs.items():
        n[f"{c}_growth"] = pp(x["Revenue growth FY27 %"], 2)
        n[f"{c}_margin"] = pp(x["EBITDA margin FY27 %"], 2)
        n[f"{c}_inv"] = f0(x["Inventory days FY27"])
        n[f"{c}_eps27"] = f2(x["EPS FY27 (Rs)"])
        n[f"{c}_pat31"] = f2(x["Net profit FY31"])
        n[f"{c}_de31"] = f2(x["Debt/equity FY31 (x)"])
        n[f"{c}_fcf"] = f2(x["FCF FY27-FY31 (Rs cr)"])
        n[f"{c}_dcf"] = f2(x["DCF value (Rs/share)"])
        n[f"{c}_tv"] = pp(x["Terminal share of EV %"], 0)
        a, _ = m.read_assumptions(m.ASSUMPTIONS / f"{c}.csv")
        n[f"{c}_oliab"] = f2(a.loc["other_liab_days", "FY27"])
        n[f"{c}_dcf_oliab80"] = f2(dcf.value(dcf.flat(a, "other_liab_days", h.loc["other_liab_days", "FY26"]), i, t)["per_share"])
        n[f"{c}_dcf_oliabadj"] = f2(dcf.value(dcf.flat(a, "other_liab_days", oliab_adj), i, t)["per_share"])
        n[f"{c}_dcf_oliabmed"] = f2(dcf.value(dcf.flat(a, "other_liab_days", h.loc["other_liab_days"].median()), i, t)["per_share"])
    n["oliab_days_median"] = f2(h.loc["other_liab_days"].median())

    # Comps
    peers, stats, target = comps.load()
    n.update(sen_ev_ebitda=f1(target["EV/EBITDA"]), sen_pe=f1(target["P/E"]), sen_ev_sales=f2(target["EV/Sales"]),
             peer_n=str(len(peers)))
    for s_, lab in (("Peer minimum", "min"), ("Peer median", "med"), ("Peer maximum", "max")):
        for k_, lab2 in (("EV/EBITDA", "eve"), ("P/E", "pe"), ("EV/Sales", "evs")):
            n[f"peer_{lab}_{lab2}"] = f1(stats.loc[s_, k_]) if lab2 != "evs" else f2(stats.loc[s_, k_])
    for sym in peers.index:
        n[f"{sym}_eve"], n[f"{sym}_pe"] = f1(peers.loc[sym, "EV/EBITDA"]), f1(peers.loc[sym, "P/E"])
        n[f"{sym}_inv"], n[f"{sym}_margin"] = f0(peers.loc[sym, "Inventory days"]), pct(peers.loc[sym, "EBITDA margin"])
    n["sen_inv_closing"], n["sen_margin"] = f0(target["Inventory days"]), pct(target["EBITDA margin"])
    comp_vals = {}
    for label, mg in comps.margins(t).items():
        key = {"FY26 reported": "rep", "FY24 (7.41%)": "fy24", "FY25 (6.02%)": "fy25"}.get(label, "guide")
        tab = comps.implied_table(stats, comps.senco(t, mg))
        comp_vals[key] = tab
        for k_, lab2 in (("EV/EBITDA", "eve"), ("P/E", "pe")):
            n[f"cmp_{key}_{lab2}_med"] = f0(tab.loc[k_, "median"])
            n[f"cmp_{key}_{lab2}_min"] = f0(tab.loc[k_, "minimum"])
    n["cmp_evs_med"] = f0(comp_vals["rep"].loc["EV/Sales", "median"])
    # Target price: the lowest peer EV/EBITDA and P/E, on FY26 sales at management's FY27 margin guide.
    tp = (comp_vals["guide"].loc["EV/EBITDA", "minimum"] + comp_vals["guide"].loc["P/E", "minimum"]) / 2
    up = tp / dcf.PRICE - 1
    n.update(tp=f0(tp), tp_up=pct(up, 0), rating=RATING if RATING else ("Buy" if up > 0.15 else "Hold" if up > -0.10 else "Sell"))
    n["broker_lo"], n["broker_hi"] = f0(min(BROKER_TARGETS.values())), f0(max(BROKER_TARGETS.values()))
    n["broker_n"] = str(len(BROKER_TARGETS))
    for y in ("FY27", "FY28", "FY31"):
        n[f"mg_sssg_{y}"] = pp(a_mgmt.loc["sssg", y], 1)
        n[f"mg_margin_{y}"] = pp(a_mgmt.loc["ebitda_margin", y], 2)
        n[f"mg_inv_{y}"] = f0(a_mgmt.loc["inventory_days", y])
        n[f"mg_growth_{y}"] = pp(k.loc["Revenue growth %", y], 1)
    for k_, lab2 in (("EV/EBITDA", "eve"), ("P/E", "pe")):
        n[f"mfp_{lab2}_med"] = pct(comps.margin_for_price(k_, stats.loc["Peer median", k_], t), 2)
        n[f"mfp_{lab2}_min"] = pct(comps.margin_for_price(k_, stats.loc["Peer minimum", k_], t), 2)

    # Monte Carlo
    sim = mc.simulate(MC_DRAWS, t=t)
    s = mc.summary(sim)
    n.update(mc_n=f0(s["draws"]), mc_p5=f0(s["p5"]), mc_p25=f0(s["p25"]), mc_med=f0(s["median"]),
             mc_p75=f0(s["p75"]), mc_p95=f0(s["p95"]), mc_above=pp(s["share above price %"], 0),
             mc_neg=pp(s["share below zero %"], 1))
    drv = mc.drivers(sim)
    n["mc_rho_margin"], n["mc_rho_inv"] = f2(drv["ebitda_margin"]), f2(drv["inventory_days"])
    n["mc_rho_wacc"], n["mc_rho_oliab"] = f2(drv["wacc"]), f2(drv["other_liab_days"])

    raw = {"ratios": r, "history": h, "f_mgmt": f_mgmt, "cases": case_runs, "comp_vals": comp_vals, "sim": sim,
           "mc": s, "dcf_mg": v["per_share"], "stats": stats, "tp": tp}
    return n, raw


def charts(raw: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    r = raw["ratios"]
    years = ["FY21", "FY22", "FY23", "FY24", "FY25", "FY26"]

    fig, ax = plt.subplots(figsize=(6.5, 3))
    ax.bar(years, r.loc["Sales (Rs cr)", years], color="#9DB4D3")
    ax.set_ylabel("Revenue (Rs cr)")
    ax2 = ax.twinx()
    ax2.plot(years, r.loc["EBITDA margin", years] * 100, color="#C44E52", marker="o")
    ax2.set_ylabel("EBITDA margin (%)", color="#C44E52")
    ax2.spines["top"].set_visible(False)
    ax.set_title("Revenue tripled in five years; the FY26 margin is an outlier")
    fig.tight_layout(); fig.savefig(FIG / "history.png", dpi=200); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.5, 3))
    ax.bar(years, r.loc["CFO (Rs cr)", years], color=["#55A868" if x > 0 else "#C44E52" for x in r.loc["CFO (Rs cr)", years]])
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_ylabel("Cash from operations (Rs cr)")
    ax2 = ax.twinx()
    ax2.plot(years, r.loc["Inventory days", years], color="#4C72B0", marker="o")
    ax2.set_ylabel("Inventory days (closing)", color="#4C72B0")
    ax2.spines["top"].set_visible(False)
    ax.set_title("Inventory days keep rising and operating cash flow stays negative")
    fig.tight_layout(); fig.savefig(FIG / "cash.png", dpi=200); plt.close(fig)

    d = pd.read_csv(m.ROOT / "data" / "delivery.csv")
    sc = d[d["verdict"].isin(["met", "beat", "missed"])].copy()
    sc["year"] = sc["target_period"].str.extract(r"(FY\d\d)")[0]
    tab = sc.groupby(["year", "verdict"]).size().unstack(fill_value=0).reindex(columns=["beat", "met", "missed"], fill_value=0)
    fig, ax = plt.subplots(figsize=(6.5, 2.8))
    left = pd.Series(0, index=tab.index)
    for col, colour in (("beat", "#55A868"), ("met", "#9DB4D3"), ("missed", "#C44E52")):
        ax.barh(tab.index, tab[col], left=left, color=colour, label=col)
        left += tab[col]
    ax.invert_yaxis(); ax.set_xlabel("Guidance statements scored"); ax.legend(frameon=False, ncol=3)
    ax.set_title("Guidance vs delivery by target year")
    fig.tight_layout(); fig.savefig(FIG / "delivery.png", dpi=200); plt.close(fig)

    # Football field
    rows = []
    cv = raw["comp_vals"]
    for key, lab in (("rep", "reported FY26 margin"), ("guide", "mgmt FY27 margin guide"), ("fy25", "FY25 margin")):
        rows.append((f"Peer EV/EBITDA, {lab}", cv[key].loc["EV/EBITDA", "25th percentile"],
                     cv[key].loc["EV/EBITDA", "75th percentile"], cv[key].loc["EV/EBITDA", "minimum"], cv[key].loc["EV/EBITDA", "maximum"]))
    rows.append(("Peer EV/Sales", cv["rep"].loc["EV/Sales", "25th percentile"], cv["rep"].loc["EV/Sales", "75th percentile"],
                 cv["rep"].loc["EV/Sales", "minimum"], cv["rep"].loc["EV/Sales", "maximum"]))
    c = raw["cases"]
    vals = [c[k]["DCF value (Rs/share)"] for k in cs.CASES]
    rows.append(("DCF bear / base / bull", min(vals), max(vals), min(vals), max(vals)))
    s = raw["mc"]
    rows.append(("Monte Carlo (p25-p75; p5-p95)", s["p25"], s["p75"], s["p5"], s["p95"]))
    lo, hi = min(BROKER_TARGETS.values()), max(BROKER_TARGETS.values())
    rows.append((f"Sell-side targets ({len(BROKER_TARGETS)} brokers)", lo, hi, lo, hi))
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    for y, (lab, lo, hi, mn, mx) in enumerate(rows):
        ax.barh(y, mx - mn, left=mn, color="#D9E2EF", height=0.6)
        ax.barh(y, hi - lo, left=lo, color="#4C72B0", height=0.6)
    ax.plot(c["base"]["DCF value (Rs/share)"], [x[0] for x in rows].index("DCF bear / base / bull"), "D", color="black", markersize=5)
    ax.set_yticks(range(len(rows)), [x[0] for x in rows]); ax.invert_yaxis()
    ax.axvline(dcf.PRICE, color="#C44E52", linestyle="--", label=f"Price Rs {dcf.PRICE}")
    ax.set_xlabel("Value per share (Rs)")
    ax.axvline(raw["tp"], color="black", linestyle=":", label=f"Target Rs {raw['tp']:,.0f}")
    ax.legend(frameon=False, loc="lower right")
    ax.set_title("Most ranges sit above the price\n(dark: central range; light: full range)", loc="left")
    fig.tight_layout(); fig.savefig(FIG / "football.png", dpi=200); plt.close(fig)

    mc.chart(raw["sim"], raw["mc"], FIG / "montecarlo.png")


def fill(n: dict[str, str]) -> str:
    text = re.sub(r"<!--.*?-->\n?", "", TEMPLATE.read_text(encoding="utf-8"), flags=re.S)
    missing = sorted(set(re.findall(r"\{([a-zA-Z0-9_]+)\}", text)) - set(n))
    if missing:
        raise KeyError(f"placeholders with no value: {missing}")
    return re.sub(r"\{([a-zA-Z0-9_]+)\}", lambda mt: n[mt.group(1)], text)


CSS = """
@page { size: A4; margin: 18mm 16mm 22mm 16mm; }
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 10pt; line-height: 1.45; color: #1a1a1a; }
h1 { font-size: 18pt; margin: 0 0 4pt; } h2 { font-size: 13pt; border-bottom: 1px solid #999; margin-top: 16pt; }
h3 { font-size: 11pt; margin-bottom: 2pt; }
table { border-collapse: collapse; margin: 6pt 0; font-size: 9pt; } th, td { border-bottom: 1px solid #ddd; padding: 2pt 6pt; text-align: right; }
th:first-child, td:first-child { text-align: left; } img { width: 100%; } .footnote { font-size: 8pt; }
.banner { color: #C44E52; font-weight: bold; margin-bottom: 6pt; }
blockquote { margin: 6pt 0; padding: 4pt 10pt; background: #f3f5f9; border-left: 3px solid #4C72B0; }
"""


def render(n: dict[str, str]) -> Path:
    import markdown

    BUILD.mkdir(parents=True, exist_ok=True)
    text = fill(n)
    (BUILD / "senco_initiation.md").write_text(text, encoding="utf-8")
    body = markdown.markdown(text, extensions=["tables", "footnotes"])
    body = body.replace('src="fig/', f'src="{(FIG).as_uri()}/')
    banner = "" if REVIEWED else f'<div class="banner">{BANNER}</div>'
    html = (f"<!doctype html><html><head><meta charset='utf-8'><title>Senco Gold initiation</title>"
            f"<style>{CSS}</style></head><body>{banner}{body}</body></html>")
    out = BUILD / "senco_initiation.html"
    out.write_text(html, encoding="utf-8")
    pdf = BUILD / "senco_initiation.pdf"
    if EDGE.exists():
        subprocess.run([str(EDGE), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf}", out.as_uri()], check=True, capture_output=True, timeout=120)
        if not REVIEWED:
            stamp(pdf)
    return pdf


BANNER = "Draft, not reviewed by the author"


def stamp(pdf: Path) -> None:
    """Write the draft banner into the bottom margin of every page (Edge drops fixed elements on some pages)."""
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(pdf)
    box = reader.pages[0].mediabox
    w, h = float(box.width) / 72, float(box.height) / 72
    fig = plt.figure(figsize=(w, h))
    fig.text(0.5, 0.025, BANNER, ha="center", va="center", color="#C44E52", fontsize=8)
    buf = io.BytesIO()
    fig.savefig(buf, format="pdf", transparent=True)
    plt.close(fig)
    overlay = PdfReader(buf).pages[0]
    writer = PdfWriter()
    for page in reader.pages:
        page.merge_page(overlay)
        writer.add_page(page)
    with open(pdf, "wb") as fh:
        writer.write(fh)


PERIOD = re.compile(r"\b(?:FY|Q[1-4]FY|H[12]FY|9MFY)\d{2}\b|\bG\d{3}\b|\b(?:19|20)\d{2}\b")


def check(text: str | None = None) -> list[str]:
    """Day 13: lines with a hand-typed number but no citation. Placeholders and period labels are fine."""
    text = text if text is not None else TEMPLATE.read_text(encoding="utf-8")
    problems = []
    for no, line in enumerate(text.splitlines(), 1):
        if line.startswith(("<!--", "[^", "![")) or "[^" in line:
            continue
        bare = PERIOD.sub("", re.sub(r"\{[a-zA-Z0-9_]+\}", "", line))
        bare = re.sub(r"^\s*(#+|\d+\.|[-*])\s", "", bare)       # headings and list markers
        if re.search(r"\d", bare):
            problems.append(f"line {no}: {line.strip()[:110]}")
    return problems


if __name__ == "__main__":
    if sys.argv[1:] == ["check"]:
        probs = check()
        n, _ = numbers()
        fill(n)  # raises if any placeholder has no value
        print("\n".join(probs) if probs else "check passed: every number is a placeholder, a period label or cited")
        sys.exit(1 if probs else 0)
    n, raw = numbers()
    (m.OUTPUTS / "report_numbers.json").write_text(json.dumps(n, indent=1), encoding="utf-8")
    charts(raw)
    pdf = render(n)
    print(f"wrote {BUILD / 'senco_initiation.html'}" + (f" and {pdf}" if pdf.exists() else " (no PDF: Edge not found)"))
