"""Regression tests for the triage fixes: scoring, fit scale, cost, loader, guard."""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["OFFLINE"] = "1"

import config, cost, guard, loader, run, score  # noqa: E402


def v(verdict):
    return {"verdict": verdict, "citation": "x"}


class ScoreTests(unittest.TestCase):
    def test_insufficient_data_scores_zero(self):
        self.assertEqual(score.raw_score({"a": v("insufficient-data"), "b": v("match")}), 1)

    def test_points(self):
        self.assertEqual(score.raw_score({"a": v("match"), "b": v("partial"), "c": v("no-match")}), 1.5)

    def test_omitted_criterion_counts_as_missing(self):
        verdicts = {c: v("match") for c in config.CRITERIA if c != "geography"}
        self.assertEqual(score.missing(verdicts), ["geography"])

    def test_recommend(self):
        self.assertEqual(score.recommend(7.0, 0, None), "ADVANCE TO CALL")
        self.assertEqual(score.recommend(6.9, 0, None), "PASS")
        self.assertEqual(score.recommend(9, config.MIN_EVIDENCE + 1, None), "INSUFFICIENT DATA TO RECOMMEND")
        self.assertTrue(score.recommend(9, 0, "crypto").startswith("PASS (anti-thesis"))


class CostTests(unittest.TestCase):
    def test_cost_is_in_rupees(self):
        usd = 1_000_000 * cost.INPUT_USD_PER_M / 1_000_000
        self.assertAlmostEqual(cost.cost_inr(1_000_000, 0), usd * cost.USD_INR)


class GuardTests(unittest.TestCase):
    def app(self, **kw):
        base = {"sector": "B2B software", "model": "saas", "deck": "We sell software."}
        return {**base, **kw}

    def test_clean_app_passes(self):
        self.assertIsNone(guard.anti_thesis(self.app()))

    def test_hits_form_fields(self):
        self.assertEqual(guard.anti_thesis(self.app(sector="D2C snack brand")), "d2c")

    def test_hits_deck_text(self):
        self.assertEqual(guard.anti_thesis(self.app(deck="A web3 gaming studio")), "gaming")

    def test_works_without_deck(self):
        self.assertIsNone(guard.anti_thesis({"sector": "b2b", "model": "saas"}))


class LoaderAndRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for d in ("data", "decks"):
            shutil.copytree(ROOT / d, Path(self.tmp, d))
        self.cwd = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.tmp)

    def test_loader_handles_padded_header(self):
        apps = loader.load("data/applications_v2.csv")
        self.assertEqual(len(apps), 6)
        self.assertEqual(apps[0]["round_size_cr"], "80")

    def run_quiet(self, path):
        with contextlib.redirect_stdout(io.StringIO()):
            run.run(path)
        return {l.split()[0]: l for l in Path("runs/run_log.jsonl").read_text().splitlines()}

    def test_end_to_end_fit_and_recommendations(self):
        import json
        self.run_quiet("data/applications.csv")
        rows = {json.loads(l)["id"]: json.loads(l) for l in Path("runs/run_log.jsonl").read_text().splitlines()}
        self.assertEqual(rows["A06"]["fit"], 10.0)
        self.assertEqual(rows["A01"]["fit"], 3.3)          # not inflated to 10
        self.assertEqual(rows["A01"]["rec"], "PASS")
        self.assertEqual(rows["A02"]["rec"], "INSUFFICIENT DATA TO RECOMMEND")
        self.assertIn("anti-thesis: nbfc", rows["A05"]["rec"])
        self.assertIn("anti-thesis: d2c", rows["A04"]["rec"])
        self.assertGreater(rows["A06"]["cost_inr"], 1)     # rupees, not dollars

    def test_v2_csv_runs(self):
        self.run_quiet("data/applications_v2.csv")

    def test_prompt_lists_criteria(self):
        p = run.build_prompt(loader.load("data/applications.csv")[0])
        for c in config.CRITERIA:
            self.assertIn(c, p)


if __name__ == "__main__":
    unittest.main()
