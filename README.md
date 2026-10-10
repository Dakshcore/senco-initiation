# Senco Gold: initiating coverage

An initiating-coverage report on Senco Gold (NSE: SENCO), built on a Python model from public filings and a
guidance-vs-delivery table from 13 earnings calls (Q1FY24 to Q1FY27). Rating: Buy, target Rs 449 (10 Oct 2026).
The report is `report/build/senco_initiation.pdf`.

## Data

- `data/raw/screener/SENCO.xlsx`: Screener.in consolidated export, same file as jewellery-peer-comps.
- `data/transcripts/sources.csv`: BSE links to each earnings-call transcript. The PDFs, their text and the Screener
  export are not in this repo; download them to `data/transcripts/` and `data/raw/screener/`, then run
  `python -m senco.transcripts` to write the page-marked text the quote checks read.
- `data/guidance.csv`: one row per guidance statement (filled from the transcripts).

## Run

```
pip install -r requirements.txt
python -m senco.financials
python -m unittest -v
python -m senco.guidance check
python -m senco.delivery
python -m senco.model data/assumptions/management.csv
python -m senco.dcf data/assumptions/management.csv
python -m senco.comps
python -m senco.cases draft
python -m senco.cases
python -m senco.montecarlo
python -m senco.report
python -m senco.report check
```

`senco/report.py` builds the initiation report. The text is `report/senco_initiation.md`; every model figure in
it is a `{placeholder}` filled from the model, and the charts are redrawn from the same run. It writes
`report/build/senco_initiation.{md,html,pdf}` (PDF through headless Edge). `check` fails on any number in the
text that is not a placeholder, a period label or on a cited line. The target follows the rule in `numbers()`;
`RATING` in `senco/report.py` holds the rating (Buy, set 10 Oct 2026).

`senco/montecarlo.py` draws each value driver from a triangular distribution over its FY22-FY26 minimum, median
and maximum (WACC and terminal growth each within one point of the base), values every draw with the DCF, and writes
`outputs/montecarlo.xlsx` and `outputs/montecarlo.png`. The seed is fixed, so reruns match.

`senco/cases.py` drafts bear, base and bull assumption files from Senco's FY22-FY26 history (base = median year;
bear and bull = 25th and 75th percentiles in the worse and better direction; hand overrides are listed in
`overrides()`, currently base other liabilities at the FY26 level excluding tax and acceptances) and runs every case in
`data/assumptions/` through the model and the DCF, side by side (`outputs/cases.xlsx`). The drafts are a
starting point; edit the CSVs and rerun without `draft` to keep your edits.

`senco/dcf.py` values one operating case with a free-cash-flow-to-the-firm DCF adapted from titan-valuation:
FY27-FY31 from the model, a straight-line fade to terminal growth over ten years, then a Gordon terminal value,
discounted from the 1 Oct 2026 price date. It also solves the reverse DCF (the EBITDA margin, same-store growth,
inventory days, terminal growth or WACC that equals the price, one at a time) and a WACC x terminal-growth grid,
and writes `outputs/dcf_<case>.xlsx`. The WACC used is 11% (Daksh); the CAPM build from Alpha Spread inputs (9.30%) is kept as a cross-check (`wacc_built`).

`senco/comps.py` (`python -m senco.comps`) applies the peer multiples from jewellery-peer-comps, run with Senco
as the target and saved in `data/comps/` (Kalyan, Thangamayil and P N Gadgil; Titan and Trent shown for
reference only), to Senco's FY26 numbers as reported and at other EBITDA margins, because FY26's 11.7% includes
gold-price gains. It also solves the FY26 margin at which a peer multiple gives the share price, and writes
`outputs/comps_senco.xlsx`.

`senco/model.py` rolls FY26 forward to FY31 from one assumptions file per case (one row per driver, one column
per year, and a source for every row). It writes `outputs/model_<case>.xlsx` with the forecast, the assumptions
and the same drivers measured on FY22-FY26. The management case uses only Senco's own guidance (cited by
guidance id) and holds unguided drivers at their FY26 values.

`senco/delivery.py` scores every guidance statement whose period has ended against what Senco reported: the
audited consolidated figure from the Screener export where one exists, otherwise the figure management stated
on a later call (with a verbatim, page-checked quote). The guided ranges and scoring basis for each statement are
in `data/delivery_rules.csv`; the full detail is written to `data/delivery.csv`.

`senco/guidance.py check` confirms every quote in `data/guidance.csv` appears on the transcript page it cites.

`senco/financials.py` loads the P&L, quarters, balance sheet and cash flow into pandas tables and computes
annual ratios. The tests check that every year ties out: the P&L builds to profit before tax, PBT less tax
equals net profit, the balance sheet balances, cash flows sum to the net, quarters build to PBT, and the four
FY26 quarters add up to the annual figures.
