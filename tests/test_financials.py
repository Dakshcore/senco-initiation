import unittest

from senco import financials as f

TOL = 0.05  # Rs crore; the export rounds each line to 2 decimals

T = f.load()
PNL, Q, BS, CF = T["pnl"], T["quarters"], T["balance"], T["cashflow"]


class Layout(unittest.TestCase):
    def test_periods(self):
        self.assertEqual(list(PNL.columns), ["FY14", "FY15", "FY21", "FY22", "FY23", "FY24", "FY25", "FY26"])
        self.assertEqual(list(BS.columns), list(PNL.columns))
        self.assertEqual(list(CF.columns), list(PNL.columns))
        self.assertEqual(Q.columns[0], "Q4FY24")
        self.assertEqual(Q.columns[-1], "Q1FY27")
        self.assertEqual(len(Q.columns), 10)

    def test_known_values(self):
        self.assertEqual(PNL.loc["Sales", "FY26"], 8430.03)
        self.assertEqual(BS.loc["Inventory", "FY26"], 5296.09)
        self.assertEqual(Q.loc["Sales", "Q1FY27"], 3056.03)


class TieOuts(unittest.TestCase):
    """Every year must add up to the totals the company reported."""

    def test_pnl_builds_to_pbt(self):
        built = (PNL.loc["Sales"] - f.operating_costs(PNL) + PNL.loc["Other Income"]
                 - PNL.loc["Depreciation"] - PNL.loc["Interest"])
        for y in PNL.columns:
            self.assertAlmostEqual(built[y], PNL.loc["Profit before tax", y], delta=TOL, msg=y)

    def test_pbt_less_tax_is_net_profit(self):
        for y in PNL.columns:
            self.assertAlmostEqual(PNL.loc["Profit before tax", y] - PNL.loc["Tax", y],
                                   PNL.loc["Net profit", y], delta=TOL, msg=y)

    def test_balance_sheet_balances(self):
        liabilities = BS.loc[["Equity Share Capital", "Reserves", "Borrowings", "Other Liabilities"]].sum()
        assets = BS.loc[["Net Block", "Capital Work in Progress", "Investments", "Other Assets"]].sum()
        for y in BS.columns:
            self.assertAlmostEqual(liabilities[y], BS.loc["Total", y], delta=TOL, msg=y)
            self.assertAlmostEqual(assets[y], BS.loc["Total", y], delta=TOL, msg=y)

    def test_cash_flows_sum_to_net(self):
        parts = CF.loc[["Cash from Operating Activity", "Cash from Investing Activity",
                        "Cash from Financing Activity"]].sum()
        for y in CF.columns:
            self.assertAlmostEqual(parts[y], CF.loc["Net Cash Flow", y], delta=TOL, msg=y)

    def test_quarters_build_to_pbt(self):
        for q in Q.columns:
            op = Q.loc["Sales", q] - Q.loc["Expenses", q]
            self.assertAlmostEqual(op, Q.loc["Operating Profit", q], delta=TOL, msg=q)
            pbt = op + Q.loc["Other Income", q] - Q.loc["Depreciation", q] - Q.loc["Interest", q]
            self.assertAlmostEqual(pbt, Q.loc["Profit before tax", q], delta=TOL, msg=q)

    def test_four_quarters_match_fy26(self):
        fy26 = ["Q1FY26", "Q2FY26", "Q3FY26", "Q4FY26"]
        for item in ("Sales", "Net profit"):
            self.assertAlmostEqual(Q.loc[item, fy26].sum(), PNL.loc[item, "FY26"], delta=TOL * 4, msg=item)


class Ratios(unittest.TestCase):
    def test_annual_ebitda_vs_quarterly_operating_profit(self):
        # Annual interest is higher than the four quarters added up (FY25 by 13.21, FY26 by 15.01) while
        # PBT matches, so the quarterly results carry that finance cost inside expenses. Annual EBITDA is
        # therefore higher than summed quarterly operating profit by exactly that gap.
        r = f.ratios(T)
        for fy in ("FY25", "FY26"):
            qs = [f"Q{i}{fy}" for i in range(1, 5)]
            gap = PNL.loc["Interest", fy] - Q.loc["Interest", qs].sum()
            self.assertGreater(gap, 10, msg=fy)
            self.assertAlmostEqual(r.loc["EBITDA (Rs cr)", fy], Q.loc["Operating Profit", qs].sum() + gap,
                                   delta=TOL * 4, msg=fy)

    def test_no_growth_across_missing_years(self):
        r = f.ratios(T)
        self.assertTrue(r.loc["Sales growth", "FY21"] != r.loc["Sales growth", "FY21"])  # NaN: FY16-FY20 missing
        self.assertAlmostEqual(r.loc["Sales growth", "FY26"], 8430.03 / 6328.07 - 1, places=6)


if __name__ == "__main__":
    unittest.main()
