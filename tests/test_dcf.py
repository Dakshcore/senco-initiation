import unittest
from dataclasses import replace

from senco import dcf as d
from senco import financials as fin
from senco import model as m

T = fin.load()
A, _ = m.read_assumptions(m.ASSUMPTIONS / "management.csv")
I = d.Inputs()
V = d.value(A, I, T)
F = m.project(A, T)
TOL = 1e-6


class Workings(unittest.TestCase):
    def test_fcff_builds_from_its_parts(self):
        for r in V["rows"]:
            self.assertAlmostEqual(r["fcff"], r["nopat"] + r["depreciation"] - r["capex"] - r["nwc_change"],
                                   delta=TOL, msg=r["fy"])

    def test_explicit_fcff_ties_to_model_cash_flows(self):
        # FCFF = CFO + CFI with other income taken out and interest added back, both after tax.
        for r in V["rows"][:len(F.columns)]:
            c, tax = F[r["fy"]], A.loc["tax_rate", r["fy"]] / 100
            expected = c["cfo"] + c["cfi"] + (c["interest"] - c["other_income"]) * (1 - tax)
            self.assertAlmostEqual(r["fcff"], expected, delta=TOL, msg=r["fy"])

    def test_fade_ends_at_terminal_growth(self):
        rows = V["rows"]
        self.assertEqual(len(rows), len(F.columns) + I.fade_years)
        self.assertAlmostEqual(rows[-1]["revenue"] / rows[-2]["revenue"] - 1, I.terminal_growth, delta=TOL)

    def test_stub_and_discounting(self):
        first = V["rows"][0]
        self.assertAlmostEqual(V["stub"], 181 / 365, delta=TOL)
        self.assertAlmostEqual(first["pv"], first["fcff"] * V["stub"] / (1 + V["wacc"]) ** V["stub"], delta=TOL)
        self.assertAlmostEqual(V["rows"][1]["factor"], 1 / (1 + V["wacc"]) ** (V["stub"] + 1), delta=TOL)

    def test_gordon_by_hand(self):
        v = d.value(A, replace(I, fade_years=0), T)
        last = v["rows"][-1]
        rev, g = last["revenue"] * (1 + I.terminal_growth), I.terminal_growth
        fcff = (rev * last["ebit"] / last["revenue"] * (1 - last["tax_rate"])
                + rev * (last["depreciation"] - last["capex"]) / last["revenue"] - rev * g / (1 + g) * last["nwc"] / last["revenue"])
        self.assertAlmostEqual(v["fcff_next"], fcff, delta=TOL)
        self.assertAlmostEqual(v["terminal"], fcff / (v["wacc"] - g), delta=TOL)

    def test_ev_to_value_per_share(self):
        self.assertAlmostEqual(V["ev"], sum(r["pv"] for r in V["rows"]) + V["pv_terminal"], delta=TOL)
        shares = T["balance"].loc["No. of Equity Shares", "FY26"]
        self.assertAlmostEqual(V["per_share"], (V["ev"] - V["net_debt"]) * 1e7 / shares, delta=TOL)
        self.assertAlmostEqual(V["net_debt"], 2699.11 - 516.64, delta=0.01)


class DiscountRate(unittest.TestCase):
    def test_cost_of_equity_is_capm(self):
        self.assertAlmostEqual(V["cost_of_equity"], 0.072 + 0.78 * 0.043, delta=TOL)

    def test_wacc_weights(self):
        e, debt = V["market_cap"], V["debt"]
        self.assertAlmostEqual(e, 317.4 * 163806700 / 1e7, delta=0.01)
        expected = (e * V["cost_of_equity"] + debt * V["cost_of_debt"] * (1 - d.TAX_SHIELD)) / (e + debt)
        self.assertAlmostEqual(V["wacc_built"], expected, delta=TOL)
        self.assertAlmostEqual(d.value(A, replace(I, wacc=None), T)["wacc"], expected, delta=TOL)

    def test_terminal_growth_set_by_hand(self):
        self.assertEqual(I.terminal_growth, 0.05)

    def test_wacc_set_by_hand_is_used(self):
        self.assertEqual(I.wacc, 0.11)
        self.assertEqual(V["wacc"], 0.11)

    def test_wacc_must_exceed_growth(self):
        with self.assertRaises(ValueError):
            d.value(A, replace(I, wacc=0.05), T)


class Reverse(unittest.TestCase):
    def test_implied_values_reproduce_the_price(self):
        w = d.implied("wacc", A, I, I.terminal_growth + 1e-3, 0.40, T)
        self.assertAlmostEqual(d.value(A, replace(I, wacc=w), T)["per_share"], d.PRICE, delta=1e-4)
        x = d.implied("ebitda_margin", A, I, 1.0, 30.0, T)
        self.assertAlmostEqual(d.value(d.flat(A, "ebitda_margin", x), I, T)["per_share"], d.PRICE, delta=1e-4)

    def test_value_falls_with_wacc_and_rises_with_growth(self):
        g = d.grid(A, I, T, [0.09, 0.10, 0.11], [0.04, 0.05, 0.06])
        self.assertTrue((g.diff(axis=0).iloc[1:] < 0).all().all())
        self.assertTrue((g.diff(axis=1).iloc[:, 1:] > 0).all().all())


if __name__ == "__main__":
    unittest.main()
