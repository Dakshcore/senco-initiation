import unittest

import pandas as pd

from senco import comps as c
from senco import financials as fin

T = fin.load()
PEERS, STATS, TARGET = c.load()
TOOL = pd.read_excel(c.COMPS, sheet_name="Implied values").set_index("Method")


class Inputs(unittest.TestCase):
    def test_peer_median_matches_peer_rows(self):
        for k in c.MULTIPLES:
            self.assertAlmostEqual(STATS.loc["Peer median", k], PEERS[k].median(), places=9)

    def test_senco_row_matches_filings(self):
        s = c.senco(T)
        self.assertAlmostEqual(TARGET["EBITDA (₹cr)"], s["ebitda"], delta=0.01)
        self.assertAlmostEqual(TARGET["Net debt (₹cr)"], s["net_debt"], delta=0.01)


class Implied(unittest.TestCase):
    def test_reported_basis_reproduces_the_comps_tool(self):
        # The tool takes market cap from Screener's META block (current share count); this project uses the FY26
        # balance-sheet count, 0.06% lower, so values agree to within 0.1%.
        tab = c.implied_table(STATS, c.senco(T))
        for k in c.MULTIPLES:
            self.assertAlmostEqual(tab.loc[k, "median"] / TOOL.loc[f"{k} (peers)", "Median (₹/share)"], 1, delta=0.001)

    def test_normalising_at_reported_margin_changes_nothing(self):
        s, r = c.senco(T, c.senco(T)["ebitda"] / c.senco(T)["sales"]), c.senco(T)
        self.assertAlmostEqual(s["net_profit"], r["net_profit"], delta=1e-9)

    def test_ev_sales_ignores_margin(self):
        self.assertAlmostEqual(c.implied("EV/Sales", 1.5, c.senco(T, 0.06)), c.implied("EV/Sales", 1.5, c.senco(T)))

    def test_margin_for_price_round_trip(self):
        for k in ("EV/EBITDA", "P/E"):
            x = STATS.loc["Peer median", k]
            mg = c.margin_for_price(k, x, T)
            self.assertAlmostEqual(c.implied(k, x, c.senco(T, mg)), c.PRICE, delta=1e-6, msg=k)


if __name__ == "__main__":
    unittest.main()
