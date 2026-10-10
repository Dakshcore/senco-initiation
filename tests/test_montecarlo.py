import unittest

from senco import cases as cs
from senco import financials as fin
from senco import model as m
from senco import montecarlo as mc

T = fin.load()
SIM = mc.simulate(200, t=T)


class Draws(unittest.TestCase):
    def test_same_seed_same_draws(self):
        again = mc.simulate(200, t=T)
        self.assertTrue((again["value"] == SIM["value"]).all())

    def test_draws_stay_inside_the_history(self):
        for k, (lo, _, hi) in mc.ranges(m.history(T)).items():
            self.assertTrue(SIM[k].between(lo, hi).all(), msg=k)
        self.assertTrue(SIM["terminal_growth"].between(0.04, 0.06).all())

    def test_base_override_is_the_mode(self):
        lo, mode, hi = mc.ranges(m.history(T), T)["other_liab_days"]
        self.assertAlmostEqual(mode, cs.overrides(T)[("base", "other_liab_days")][0])
        self.assertTrue(lo < mode < hi)

    def test_every_driver_in_cases_is_drawn(self):
        self.assertEqual(set(mc.ranges(m.history(T))), set(cs.BETTER))

    def test_summary_is_ordered(self):
        s = mc.summary(SIM)
        self.assertTrue(s["p5"] <= s["p25"] <= s["median"] <= s["p75"] <= s["p95"])
        self.assertAlmostEqual(s["share above price %"], (SIM["value"] > 317.4).mean() * 100)

    def test_margin_raises_value(self):
        self.assertGreater(mc.drivers(SIM)["ebitda_margin"], 0)


if __name__ == "__main__":
    unittest.main()
