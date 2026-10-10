import unittest

from senco import cases as cs
from senco import financials as fin
from senco import report as rp


class Check(unittest.TestCase):
    def test_flags_an_uncited_number(self):
        self.assertEqual(len(rp.check("Revenue grew 25% last year.")), 1)

    def test_allows_placeholders_periods_citations_and_list_markers(self):
        text = "Revenue was {sales_FY26} in FY26 and Q1FY27 (G160).\n1. Item\n## Heading\nDuty was 15%.[^duty]"
        self.assertEqual(rp.check(text), [])

    def test_template_passes(self):
        self.assertEqual(rp.check(), [])


class Numbers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.n, cls.raw = rp.numbers(fin.load())

    def test_every_placeholder_has_a_value(self):
        text = rp.fill(self.n)
        self.assertNotRegex(text, r"\{[a-zA-Z0-9_]+\}")

    def test_liabilities_file_ties_to_screener(self):
        b = fin.load()["balance"]
        for y in ("FY25", "FY26"):
            self.assertAlmostEqual(cs.liabilities()[y].sum() / 10, b.loc["Other Liabilities", y], places=1)

    def test_target_is_average_of_peer_minimum_values(self):
        cv = self.raw["comp_vals"]["guide"]
        expected = (cv.loc["EV/EBITDA", "minimum"] + cv.loc["P/E", "minimum"]) / 2
        self.assertAlmostEqual(self.raw["tp"], expected)

    def test_rating_follows_rule(self):
        up = self.raw["tp"] / 317.4 - 1
        rule = "Buy" if up > 0.15 else "Hold" if up > -0.10 else "Sell"
        self.assertEqual(self.n["rating"], rp.RATING or rule)


if __name__ == "__main__":
    unittest.main()
