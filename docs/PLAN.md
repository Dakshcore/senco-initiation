# Senco Gold initiation: 15-day plan

Goal: a 12-15 page initiating-coverage report on Senco Gold (NSE: SENCO) with a rating, a target price,
a Python model built from filings, and a guidance-vs-delivery table from the earnings calls.

The rating, target price, thesis and writing are yours. Interviewers will ask you to defend every
assumption, so the judgment calls stay with you. Code, data cleaning and number checks can be shared.

| Day | Work | Owner | Status |
|---|---|---|---|
| 1 | Pick the company: Senco Gold. Check sell-side coverage. | You | Done: 4 brokers after Q4FY26, targets Rs 385-575 (`docs/research/coverage.md`) |
| 2 | Read the FY26 annual report and the last 4 calls (Q2FY26 to Q1FY27). Write a one-page hypothesis in `docs/HYPOTHESIS.md`. | You | Draft written from the research; your rewrite open |
| 3 | Load the financials into a clean dataset with tie-out tests. | Done | `senco/financials.py`, 10 tests pass |
| 4 | Get the 13 transcripts (`data/transcripts/sources.csv`) and pull out guidance statements into `data/guidance.csv`. | Both | 186 rows extracted, all quotes verified on their page; your review open |
| 5 | Guidance-vs-delivery table and a delivery rate. | Both | Scored: 39 of 60 delivered; rules in `data/delivery_rules.csv` for your review |
| 6 | Industry section: reuse the comps data; market structure and competitive position. | You | Drafted in the report from `docs/research/industry.md`; your review open |
| 7 | Operating model: stores, same-store growth, gold price, margins, inventory-heavy working capital. | Both | Engine and management case built (`senco/model.py`, `data/assumptions/management.csv`); your case open |
| 8 | DCF and reverse DCF, adapted from titan-valuation. | Both | Engine built (`senco/dcf.py`, 12 tests); WACC set to 11% (your call, 9 Oct 2026); terminal growth 5% (your call, 10 Oct 2026) |
| 9 | Comps, bull/base/bear, Monte Carlo. | Both | Built: `senco/comps.py`, `senco/cases.py`, `senco/montecarlo.py` (5 tests); your edit of the cases open |
| 10 | Rating, target price, three-point thesis, catalysts, risks. | You | Done: Buy, target Rs 449 (your call, 10 Oct 2026) |
| 11 | Draft summary, thesis and company sections. | You | Done: reviewed 10 Oct 2026 |
| 12 | Draft valuation, risks and charts. | You | Done: 5 charts in `report/fig`; reviewed 10 Oct 2026 |
| 13 | Check every number in the report against model output. Run the tests. | Both | `python -m senco.report check` passes; 66 tests pass |
| 14 | Publish: PDF on GitHub, portfolio page, LinkedIn post. | You | Open |
| 15 | Buffer. | | |

## What the Day 3 data shows (facts, not a view)

From `python -m senco.financials` and `ratios()`, consolidated, Rs crore, March year-end:

- Sales rose from 2,660.38 (FY21) to 8,430.03 (FY26); FY26 growth was 33.2%.
- EBITDA margin was 6.0% in FY25 and 11.7% in FY26.
- Inventory days rose from 143 (FY21) to 229 (FY26).
- Cash from operations was negative every year from FY22 to FY26; FY26 was -789.27.
- Net debt was 2,182.47 at FY26, 0.87x equity.
- At Rs 317.4 on 1 Oct 2026 the comps project has Senco at 7.5x EV/EBITDA and 9.1x P/E, the cheapest of the
  core jewellers (peer medians 19.6x and 30.7x include Senco).

## Questions for Day 2 reading

1. Why did EBITDA margin nearly double in FY26? Check how much came from gold price gains on inventory,
   hedging, or the negative "Other Expenses" line (-311.94 in FY26, -209.53 in FY25).
2. Annual interest is higher than the four quarters added up (FY25 by 13.21, FY26 by 15.01), while profit
   before tax matches. Which finance cost sits inside quarterly expenses? This changes the EBITDA you use.
3. Is the low multiple about the cash burn, the margin being one-off, the acquisition (AJPL / Melorra), or
   something else? Your answer to this is the thesis.
4. Data gap: the Screener export has FY14, FY15 and FY21 to FY26 only. FY16 to FY20 are missing, and Senco
   listed in July 2023, so older years may need the DRHP.
