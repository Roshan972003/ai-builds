"""Regression tests: (1) null/empty extraction must not erase known facts,
(2) a bad follow-up reply must not discard the first result, (3) scores are validated."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["OFFLINE"] = "1"

import config, llm, qualify, run, scrape  # noqa: E402

KNOWN = {"company": "X", "stage": "Series B", "employees": 120, "is_saas": True,
         "compliance_signals": ["SOC 2 requested"]}


class MergeCompany(unittest.TestCase):
    def test_nulls_and_empties_do_not_overwrite_known_facts(self):
        new = {"company": "X", "stage": None, "employees": None, "product": "", "compliance_signals": []}
        merged = qualify.merge_company(KNOWN, new)
        self.assertEqual(merged["stage"], "Series B")
        self.assertEqual(merged["employees"], 120)
        self.assertEqual(merged["compliance_signals"], ["SOC 2 requested"])
        self.assertNotIn("product", merged)

    def test_new_facts_are_added_and_updated(self):
        merged = qualify.merge_company(KNOWN, {"employees": 150, "product": "API platform"})
        self.assertEqual((merged["employees"], merged["product"]), (150, "API platform"))

    def test_lists_are_unioned_without_duplicates(self):
        merged = qualify.merge_company(KNOWN, {"compliance_signals": ["ISO 27001 required", "SOC 2 requested"]})
        self.assertEqual(merged["compliance_signals"], ["SOC 2 requested", "ISO 27001 required"])

    def test_false_and_zero_are_real_values(self):
        merged = qualify.merge_company(KNOWN, {"is_saas": False, "employees": 0})
        self.assertIs(merged["is_saas"], False)
        self.assertEqual(merged["employees"], 0)

    def test_inputs_are_not_mutated_and_none_is_safe(self):
        before = json.dumps(KNOWN)
        qualify.merge_company(KNOWN, {"stage": "Series C"})
        self.assertEqual(json.dumps(KNOWN), before)
        self.assertEqual(qualify.merge_company(KNOWN, None), KNOWN)

    def test_second_scoring_call_sees_the_merged_company(self):
        prompts = []
        def ask(step, d, p):
            prompts.append(p)
            return {"score": 50, "needs_more": True} if step == "qualify" else {"score": 60, "needs_more": False}
        with mock.patch.object(llm, "ask", ask), \
             mock.patch.object(scrape, "fetch_once", lambda d, p: ("about text", scrape.OK)), \
             mock.patch.object(qualify.extract, "extract",
                               lambda d, t: {"stage": None, "employees": None, "compliance_signals": []}):
            qualify.qualify("x.com", dict(KNOWN))
        self.assertIn("Series B", prompts[-1])
        self.assertIn("120", prompts[-1])
        self.assertIn("SOC 2 requested", prompts[-1])


class BadFollowUp(unittest.TestCase):
    FIRST = {"score": 85, "reason": "strong fit", "needs_more": True}

    def run_q(self, followup, extract_fn=lambda d, t: {}):
        def ask(step, d, p):
            if step == "qualify":
                return dict(self.FIRST)
            if isinstance(followup, Exception):
                raise followup
            return followup
        with mock.patch.object(llm, "ask", ask), \
             mock.patch.object(scrape, "fetch_once", lambda d, p: ("about text", scrape.OK)), \
             mock.patch.object(qualify.extract, "extract", extract_fn):
            return qualify.qualify("x.com", dict(KNOWN))

    def test_bad_followups_keep_the_first_result(self):
        bad = [json.JSONDecodeError("bad json", "", 0), LookupError("no fixture"),
               ValueError("boom"), {"reason": "no score"}, {"score": "high"}, {"score": 500}, None]
        for followup in bad:
            r = self.run_q(followup)
            self.assertEqual(r["score"], 85, followup)
            self.assertTrue(r["qualified"], followup)
            self.assertEqual(r["reason"], "strong fit", followup)

    def test_error_is_recorded_for_the_log(self):
        r = self.run_q(json.JSONDecodeError("bad json", "", 0))
        self.assertIn("JSONDecodeError", r["followup_error"])

    def test_good_followup_still_replaces_the_result(self):
        r = self.run_q({"score": 40, "reason": "worse", "needs_more": False})
        self.assertEqual((r["score"], r["qualified"]), (40, False))
        self.assertNotIn("followup_error", r)

    def test_failing_extractor_skips_that_page_and_keeps_result(self):
        def boom(d, t):
            raise json.JSONDecodeError("bad json", "", 0)
        r = self.run_q({"score": 10, "needs_more": False}, extract_fn=boom)
        self.assertEqual(r["score"], 85)
        self.assertEqual(r["scrape_failed"], config.EXTRA_PAGES[:config.MAX_ROUNDS])

    def test_followup_error_reaches_the_run_log_row(self):
        company = {"company": "X", "compliance_signals": []}
        with mock.patch.object(scrape, "fetch", lambda d, p="home": "text"), \
             mock.patch.object(run.extract, "extract", lambda d, t: company), \
             mock.patch.object(run.qualify, "qualify", lambda d, c: {
                 "score": 85, "qualified": True, "reason": "r", "followup_error": "ValueError: x"}), \
             mock.patch.object(run.contacts, "find_contact", lambda d, p: None):
            row = run.process("x.com", "data/contacts.csv")
        self.assertEqual(row["followup_error"], "ValueError: x")

    def test_bad_first_reply_still_raises_so_the_run_logs_an_error(self):
        with mock.patch.object(llm, "ask", lambda s, d, p: {"reason": "no score"}):
            with self.assertRaises(ValueError):
                qualify.qualify("x.com", {})


class ScoreValidation(unittest.TestCase):
    def q(self, score):
        with mock.patch.object(llm, "ask", lambda s, d, p: {"score": score, "needs_more": False}):
            return qualify.qualify("x.com", {})

    def test_valid_scores(self):
        for score, expected in ((0, False), (1, False), (12, False), (69.9, False), (70, True),
                                (86, True), ("86", True), (86.0, True), (100, True)):
            self.assertEqual(self.q(score)["qualified"], expected, score)

    def test_integral_floats_become_ints(self):
        self.assertEqual(repr(self.q(86.0)["score"]), "86")
        self.assertEqual(self.q(72.5)["score"], 72.5)

    def test_invalid_scores_are_rejected_not_qualified(self):
        for score in (150, 100.01, -5, -0.1, float("inf"), float("-inf"), float("nan"), "inf", "nan",
                      True, False, None, "high", "86%", "", [], {}, 0.86, 0.5, "0.7"):
            with self.assertRaises(ValueError, msg=repr(score)):
                self.q(score)

    def test_non_dict_reply_is_rejected(self):
        for reply in (None, [], "86", 86):
            with mock.patch.object(llm, "ask", lambda s, d, p, r=reply: r):
                with self.assertRaises(ValueError, msg=repr(reply)):
                    qualify.qualify("x.com", {})


if __name__ == "__main__":
    unittest.main()
