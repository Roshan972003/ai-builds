"""Retry behaviour of the qualifier when scraping an extra page fails."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["OFFLINE"] = "1"

import config, llm, qualify, run, scrape  # noqa: E402

OK, TR, PERM = scrape.OK, scrape.TRANSIENT, scrape.PERMANENT


def model(step, d, p):
    if step == "qualify":
        return {"score": 50, "reason": "need more", "needs_more": True}
    return {"score": 90, "reason": "now clear", "needs_more": False}


class QualifyScrapeRetry(unittest.TestCase):
    def run_q(self, outcomes, ask=model):
        """outcomes: list of (text, status) returned by successive fetch_once calls,
        or a dict page -> list. Returns (result, calls, sleeps)."""
        calls, sleeps = [], []
        def fetch_once(d, page):
            calls.append(page)
            seq = outcomes[page] if isinstance(outcomes, dict) else outcomes
            idx = sum(1 for c in calls if c == page) - 1 if isinstance(outcomes, dict) else len(calls) - 1
            return seq[min(idx, len(seq) - 1)]
        with mock.patch.object(llm, "ask", ask), \
             mock.patch.object(scrape, "fetch_once", fetch_once), \
             mock.patch.object(scrape.time, "sleep", sleeps.append), \
             mock.patch.object(qualify.extract, "extract", lambda d, t: {"stage": "Series B"}):
            return qualify.qualify("x.com", {"company": "X"}), calls, sleeps

    def test_transient_failure_is_retried_then_succeeds(self):
        r, calls, sleeps = self.run_q([("", TR), ("", TR), ("page text", OK)])
        self.assertEqual(calls, ["about", "about", "about"])
        self.assertEqual(sleeps, [1, 2])
        self.assertEqual(r["score"], 90)
        self.assertTrue(r["qualified"])
        self.assertNotIn("scrape_failed", r)

    def test_gives_up_after_max_attempts_per_page_then_moves_to_next_page(self):
        r, calls, _ = self.run_q({"about": [("", TR)], "security": [("sec text", OK)]})
        self.assertEqual(calls, ["about"] * config.MAX_FETCH_RETRIES + ["security"])
        self.assertEqual(r["scrape_failed"], ["about"])
        self.assertEqual(r["score"], 90)  # security page rescued the result

    def test_permanent_failure_is_not_retried(self):
        r, calls, sleeps = self.run_q({"about": [("", PERM)], "security": [("", PERM)]})
        self.assertEqual(calls, ["about", "security"])
        self.assertEqual(sleeps, [])
        self.assertEqual(r["scrape_failed"], ["about", "security"])

    def test_all_pages_fail_keeps_first_result_and_reports_it(self):
        r, calls, sleeps = self.run_q([("", TR)])
        self.assertEqual(len(calls), config.MAX_FETCH_RETRIES * len(config.EXTRA_PAGES[:config.MAX_ROUNDS]))
        self.assertEqual(len(sleeps), (config.MAX_FETCH_RETRIES - 1) * 2)  # none after the last attempt
        self.assertEqual(r["score"], 50)
        self.assertFalse(r["qualified"])
        self.assertEqual(r["scrape_failed"], ["about", "security"])

    def test_total_fetches_are_bounded(self):
        _, calls, _ = self.run_q([("", TR)])
        self.assertLessEqual(len(calls), config.MAX_ROUNDS * config.MAX_FETCH_RETRIES)

    def test_empty_200_page_counts_as_failed_without_retry(self):
        r, calls, _ = self.run_q({"about": [("", OK)], "security": [("t", OK)]})
        self.assertEqual(calls, ["about", "security"])
        self.assertEqual(r["scrape_failed"], ["about"])

    def test_no_fetch_when_model_is_already_confident(self):
        ask = lambda s, d, p: {"score": 88, "reason": "r", "needs_more": False}
        r, calls, _ = self.run_q([("", TR)], ask=ask)
        self.assertEqual(calls, [])
        self.assertNotIn("scrape_failed", r)

    def test_stops_fetching_once_a_page_resolves_it(self):
        _, calls, _ = self.run_q([("text", OK)])
        self.assertEqual(calls, ["about"])

    def test_scrape_failures_reach_the_run_log_row(self):
        company = {"company": "X", "compliance_signals": []}
        with mock.patch.object(scrape, "fetch", lambda d, p="home": "text"), \
             mock.patch.object(run.extract, "extract", lambda d, t: company), \
             mock.patch.object(run.qualify, "qualify",
                               lambda d, c: {"score": 40, "qualified": False, "reason": "r", "scrape_failed": ["about"]}):
            row = run.process("x.com", "data/contacts.csv")
        self.assertEqual(row["scrape_failed"], ["about"])


class FetchOnce(unittest.TestCase):
    def test_status_classification(self):
        R = scrape.requests
        def resp(code):
            r = mock.Mock(status_code=code, text="word " * 9)
            def rfs():
                if code >= 400:
                    raise R.HTTPError(str(code), response=r)
            r.raise_for_status = rfs
            return r
        cases = [(resp(200), OK), (resp(404), PERM), (resp(403), PERM),
                 (resp(429), TR), (resp(503), TR), (R.Timeout("t"), TR), (R.ConnectionError("c"), TR)]
        for outcome, expected in cases:
            with mock.patch.object(config, "OFFLINE", False), \
                 mock.patch.object(R, "get", mock.Mock(side_effect=[outcome])) as get:
                self.assertEqual(scrape.fetch_once("a.com", "about")[1], expected, outcome)
                self.assertEqual(get.call_count, 1)  # never retries by itself

    def test_offline_missing_fixture_is_permanent(self):
        self.assertEqual(scrape.fetch_once("ghostco.example", "about"), ("", PERM))


if __name__ == "__main__":
    unittest.main()
