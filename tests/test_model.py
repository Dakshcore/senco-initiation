import unittest

from senco import financials as fin
from senco import model as m

T = fin.load()
ASSUMPTIONS, SOURCES = m.read_assumptions(m.ASSUMPTIONS / "management.csv")
F = m.project(ASSUMPTIONS, T)
TOL = 1e-6


class Identities(unittest.TestCase):
    def test_balance_sheet_balances(self):
        for y in F.columns:
            c = F[y]
            assets = (c["net_block"] + c["cwip"] + c["investments"] + c["inventory"] + c["receivables"]
                      + c["cash"] + c["other_assets"])
            liabilities = c["share_capital"] + c["reserves"] + c["borrowings"] + c["other_liabilities"]
            self.assertAlmostEqual(assets, liabilities, delta=TOL, msg=y)

    def test_cash_flows_sum_to_change_in_cash(self):
        for y in F.columns:
            c = F[y]
            self.assertAlmostEqual(c["cfo"] + c["cfi"] + c["cff"], c["cash_change"], delta=TOL, msg=y)

    def test_pnl_builds_to_net_profit(self):
        for y in F.columns:
            c = F[y]
            pbt = c["ebitda"] + c["other_income"] - c["depreciation"] - c["interest"]
            self.assertAlmostEqual(pbt - c["tax"], c["net_profit"], delta=TOL, msg=y)

    def test_interest_is_on_average_borrowings(self):
        prev = m.base_state(T)["borrowings"]
        for y in F.columns:
            rate = ASSUMPTIONS.loc["interest_rate", y] / 100
            self.assertAlmostEqual(F.loc["interest", y], (prev + F.loc["borrowings", y]) / 2 * rate, delta=TOL)
            prev = F.loc["borrowings", y]


class Replay(unittest.TestCase):
    """Rebuild FY26 from FY25 with FY26's own measured drivers: the model must land on the reported year."""

    def test_fy26_from_fy25(self):
        h = m.history(T)["FY26"]
        d = {k: h[k] for k in h.index if k in m.DRIVERS}
        d.update(sssg=h["revenue_growth"], new_store_contribution=0)
        b = T["balance"]["FY26"]
        actual = m.base_state(T, "FY26")
        keep = ("inventory", "cash", "cwip", "investments", "share_capital")
        s = m.step(m.base_state(T, "FY25"), d, overrides={k: actual[k] for k in keep})
        p = T["pnl"]["FY26"]
        self.assertAlmostEqual(s["revenue"], p["Sales"], delta=0.01)
        self.assertAlmostEqual(s["ebitda"] + s["other_income"] - s["depreciation"], p["Profit before tax"]
                               + p["Interest"], delta=0.05)
        # Reserves also moved by items outside profit and dividends (Rs 2.33 cr in FY26), which the plug absorbs.
        self.assertAlmostEqual(s["borrowings"], b["Borrowings"], delta=5)
        self.assertAlmostEqual(s["net_profit"], p["Net profit"], delta=1)


class Assumptions(unittest.TestCase):
    def test_every_driver_has_a_source(self):
        self.assertEqual(set(ASSUMPTIONS.index), set(m.DRIVERS))
        for k, s in SOURCES.items():
            self.assertTrue(s.strip(), msg=k)


if __name__ == "__main__":
    unittest.main()
