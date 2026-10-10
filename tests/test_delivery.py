import re
import unittest

from senco import delivery as dv
from senco.guidance import read, problems

DETAIL, QUOTE_PROBLEMS = dv.score()
RULES = {r["id"]: r for r in read(dv.RULES)}
GUIDANCE = {r["id"]: r for r in read()}
SA = dv.screener_actuals()


class Verdict(unittest.TestCase):
    def test_higher_is_better(self):
        self.assertEqual(dv.verdict(19, 18, 20, "higher"), "met")
        self.assertEqual(dv.verdict(21, 18, 20, "higher"), "beat")
        self.assertEqual(dv.verdict(17, 18, 20, "higher"), "missed")

    def test_lower_is_better(self):
        self.assertEqual(dv.verdict(1.1, 1.0, 1.2, "lower"), "met")
        self.assertEqual(dv.verdict(0.9, 1.0, 1.2, "lower"), "beat")
        self.assertEqual(dv.verdict(640, None, 350, "lower"), "missed")

    def test_open_ends(self):
        self.assertEqual(dv.verdict(8430, 7400, None, "higher"), "met")
        self.assertEqual(dv.verdict(-79, None, 0, "higher"), "met")


class Sources(unittest.TestCase):
    def test_guidance_quotes_on_their_pages(self):
        self.assertEqual(problems(list(GUIDANCE.values())), [])

    def test_actual_quotes_on_their_pages(self):
        self.assertEqual(QUOTE_PROBLEMS, [])

    def test_rules_cover_exactly_the_due_rows(self):
        due = {"FY24", "H2FY24", "Q2FY24", "Q4FY24", "FY25", "Q3FY25", "Q4FY25", "9MFY25", "Q2FY25-Q3FY25",
               "FY26", "Q2FY26", "Q3FY26", "Q4FY26", "rest of FY26", "FY26 (March 2026)", "FY25-FY26", "FY24-FY26"}
        self.assertEqual(set(RULES), {i for i, g in GUIDANCE.items() if g["target_period"] in due})

    def test_screener_matches_call_where_both_exist(self):
        # Revenue growth and gross margin from the audited export agree with what management said on the call.
        self.assertAlmostEqual(SA["rev_growth:FY24"], 28.5, delta=0.1)
        self.assertAlmostEqual(SA["gross_margin:FY24"], 15.3, delta=0.05)
        self.assertAlmostEqual(SA["revenue:FY26"], 8430, delta=1)
        self.assertAlmostEqual(SA["q_rev_growth:Q4FY26"], 45, delta=0.5)


class Scoring(unittest.TestCase):
    def test_every_due_row_has_a_verdict(self):
        for d in DETAIL:
            if d["id"] in RULES:
                self.assertIn(d["verdict"], {"met", "beat", "missed", "no actual", "not scorable"}, msg=d["id"])

    def test_call_scored_rows_have_a_source(self):
        actuals = dv.load_actuals()
        for d in DETAIL:
            if d["scored_on"] == "call":
                self.assertTrue(actuals[d["id"]]["src_quote"], msg=d["id"])

    def test_call_verdict_holds_on_screener_figure(self):
        # Where a call-scored row also has an audited figure, report any row whose verdict would flip.
        flips = []
        for d in DETAIL:
            if d["scored_on"] == "call" and d["screener_actual"] != "":
                r = RULES[d["id"]]
                alt = dv.verdict(float(d["screener_actual"]), dv._num(r["lo"]), dv._num(r["hi"]), r["better"])
                if (alt == "missed") != (d["verdict"] == "missed"):
                    flips.append(d["id"])
        self.assertEqual(flips, [])


if __name__ == "__main__":
    unittest.main()
