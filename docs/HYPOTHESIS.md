# Hypothesis

Written from the model runs and `docs/research/`. Rewrite this in your own words before you rely on it. Figures
come from `outputs/report_numbers.json` (run 10 Oct 2026) or the cited file.

## The question

At Rs 317.4 (1 Oct 2026), Senco trades at 7.5x FY26 EV/EBITDA and 9.1x P/E. Its listed peers (Kalyan,
Thangamayil, P N Gadgil) trade at 15.9x to 27.7x EV/EBITDA. Why is it so cheap, and is the market right?

## Answer

1. **The price sits below management's plan.** At an 11% WACC, 5% terminal growth and management's growth path,
   the price implies an EBITDA margin of 7.64%. Management guides 7.5% to 7.8% (Q1FY27 call, p.5-6); FY24 was 7.4% and the
   FY22-FY26 median is 8.06%.
2. **The discount is about cash.** Operating cash flow was negative every year from FY22 to FY26 (a total of
   Rs -1,181.78 cr). Closing inventory days went from 143 (FY21) to 229 (FY26). This is the strongest argument for
   the low multiple, and it is real.
3. **FY26 working capital was flattered.** Other liabilities rose from Rs 716.64 cr to Rs 1,848.71 cr. Most of the
   increase is customer advances, trade payables (incl. Rs 229.47 cr of acceptances) and Rs 134.97 cr of current
   tax; gold metal loans are a separate line and fell (`docs/research/fy26_liabilities.md`). Some of this will
   reverse.

## Answers to the Day 2 questions (PLAN.md)

1. **Why the FY26 margin nearly doubled.** Likely gold-price gains on inventory, not yet quantified for the full year: Senco's reported gold price rose
   63% between 31 Mar 2025 and 31 Mar 2026 (`docs/research/industry.md`), and management said Q1FY26 included
   1.5 to 2 points of inventory gains (Q1FY27 call, p.6). The negative "Other Expenses" line is still unexplained.
2. **Annual vs quarterly interest gap.** Open. Not checked against the annual report notes.
3. **Why the low multiple.** Answer above: cash burn and working capital, with a margin that the market
   does not believe is sustainable.
4. **FY16-FY20 data gap.** Open. The model uses FY22-FY26 only.

## What would prove this wrong

- H1FY27 operating cash flow (due with Q2FY27 results) turns positive with inventory days at or below the 152 management cited (Q1FY27 call, p.8).
- The FY27 margin lands inside management's 7.5% to 7.8% without a gold-price tailwind.
- Customer advances and payables hold at FY26 levels in the H1FY27 balance sheet.
