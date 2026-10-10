import unittest

import numpy as np

from senco import cases as cs
from senco import financials as fin
from senco import model as m

T = fin.load()
H = m.history(T)
READ = {c: m.read_assumptions(m.ASSUMPTIONS / f"{c}.csv")[0] for c in cs.CASES}


class Draft(unittest.TestCase):
    def test_files_match_the_rule(self):
        # The CSVs on disk are what `python -m senco.cases draft` writes from the current history.
        for case, rows in cs.draft(H, T).items():
            for r in rows:
                for y in cs.YEARS:
                    want, got = r[y], READ[case].loc[r["driver"], y]
                    if want == "":
                        self.assertTrue(np.isnan(got), msg=(case, r["driver"]))
                    else:
                        self.assertAlmostEqual(got, want, delta=1e-9, msg=(case, r["driver"]))

    def test_base_is_the_median(self):
        over = {k for c, k in cs.overrides(T) if c == "base"}
        for k in (*cs.BETTER, *cs.NEUTRAL):
            if k == "revenue_growth" or k in over:
                continue
            self.assertAlmostEqual(READ["base"].loc[k, "FY27"], round(H.loc[k].median(), 2), msg=k)
        growth = READ["base"].loc["sssg", "FY27"] + READ["base"].loc["new_store_contribution", "FY27"]
        self.assertAlmostEqual(growth, round(H.loc["revenue_growth"].median(), 2), delta=1e-9)

    def test_bear_is_worse_and_bull_better(self):
        for k, better in cs.BETTER.items():
            key = "sssg" if k == "revenue_growth" else k
            bear, base, bull = (READ[c].loc[key, "FY27"] for c in cs.CASES)
            if better == "higher":
                self.assertTrue(bear <= base <= bull, msg=k)
            else:
                self.assertTrue(bear >= base >= bull, msg=k)

    def test_neutral_drivers_equal_across_cases(self):
        for k in cs.NEUTRAL:
            self.assertEqual(len({READ[c].loc[k, "FY27"] for c in cs.CASES}), 1, msg=k)

    def test_values_lie_inside_the_history(self):
        for c in cs.CASES:
            for k in (*cs.BETTER, *cs.NEUTRAL):
                if k == "revenue_growth":
                    continue
                x = READ[c].loc[k, "FY27"]
                self.assertTrue(H.loc[k].min() - 0.01 <= x <= H.loc[k].max() + 0.01, msg=(c, k))


class Override(unittest.TestCase):
    def test_base_other_liabilities_excludes_one_offs(self):
        li = cs.liabilities()
        keep = li.loc[li["one_off"] == "no", "FY26"].sum() / 10
        days = keep / fin.ratios(T).loc["Sales (Rs cr)", "FY26"] * 365
        self.assertAlmostEqual(READ["base"].loc["other_liab_days", "FY27"], round(days, 2), delta=1e-9)
        self.assertLess(days, H.loc["other_liab_days", "FY26"])

    def test_bull_other_liabilities_is_fy26_reported(self):
        self.assertAlmostEqual(READ["bull"].loc["other_liab_days", "FY27"], round(H.loc["other_liab_days", "FY26"], 2), delta=1e-9)


class Run(unittest.TestCase):
    def test_value_rises_from_bear_to_bull(self):
        v = [cs.run(c, T)["DCF value (Rs/share)"] for c in cs.CASES]
        self.assertTrue(v[0] < v[1] < v[2], msg=v)


if __name__ == "__main__":
    unittest.main()
