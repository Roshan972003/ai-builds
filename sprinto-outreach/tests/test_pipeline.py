"""Offline regression tests. Run: python -m unittest discover -s tests -v"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["OFFLINE"] = "1"

import config, contacts, drafts, impact, llm, qualify, run, scrape  # noqa: E402


def reply(score, needs_more=False):
    return lambda step, d, p: {"score": score, "reason": "r", "needs_more": needs_more}


class Qualify(unittest.TestCase):
    def test_threshold_uses_0_100_scale(self):
        for score, expected in ((12, False), (35, False), (69, False), (70, True), (86, True)):
            with mock.patch.object(llm, "ask", reply(score)):
                self.assertEqual(qualify.qualify("x", {})["qualified"], expected, score)

    def test_string_score_is_coerced(self):
        with mock.patch.object(llm, "ask", reply("86")):
            self.assertTrue(qualify.qualify("x", {})["qualified"])

    def test_unusable_score_raises_clear_error(self):
        for bad in ({"reason": "r"}, {"score": None}, {"score": "high"}):
            with mock.patch.object(llm, "ask", lambda s, d, p, b=bad: b):
                with self.assertRaises(ValueError):
                    qualify.qualify("x", {})

    def test_missing_needs_more_means_false(self):
        with mock.patch.object(llm, "ask", lambda s, d, p: {"score": 80}):
            self.assertFalse(qualify.qualify("x", {})["needs_more"])

    def test_each_retry_round_fetches_a_new_page_and_is_capped(self):
        pages = []
        with mock.patch.object(llm, "ask", reply(50, needs_more=True)), \
             mock.patch.object(scrape, "fetch_once", lambda d, p: (pages.append(p) or "text", scrape.OK)), \
             mock.patch.object(qualify.extract, "extract", lambda d, t: {}):
            r = qualify.qualify("x", {})
        self.assertEqual(pages, config.EXTRA_PAGES[:config.MAX_ROUNDS])
        self.assertEqual(len(set(pages)), len(pages))
        self.assertFalse(r["qualified"])

    def test_missing_followup_fixture_keeps_first_result(self):
        def ask(step, d, p):
            if step == "qualify":
                return {"score": 50, "reason": "r", "needs_more": True}
            raise LookupError("no fixture")
        with mock.patch.object(llm, "ask", ask), \
             mock.patch.object(scrape, "fetch_once", lambda d, p: ("text", scrape.OK)), \
             mock.patch.object(qualify.extract, "extract", lambda d, t: {}):
            self.assertEqual(qualify.qualify("x", {})["score"], 50)


class Scrape(unittest.TestCase):
    def test_failed_fetch_is_retried_at_most_max_times(self):
        calls = []
        def boom(*a, **k):
            calls.append(1)
            raise scrape.requests.RequestException("down")
        with mock.patch.object(config, "OFFLINE", False), \
             mock.patch.object(scrape.requests, "get", boom), \
             mock.patch.object(scrape.time, "sleep"):
            self.assertEqual(scrape.fetch("x.com"), "")
        self.assertEqual(len(calls), config.MAX_FETCH_RETRIES)

    def test_http_error_counts_as_failure_then_success_returns_text(self):
        bad = mock.Mock(); bad.raise_for_status.side_effect = scrape.requests.HTTPError("500")
        good = mock.Mock(text="word " * 9, raise_for_status=lambda: None)
        with mock.patch.object(config, "OFFLINE", False), \
             mock.patch.object(scrape.requests, "get", side_effect=[bad, good]), \
             mock.patch.object(scrape.time, "sleep"):
            self.assertIn("word", scrape.fetch("x.com"))

    def test_missing_offline_fixture_returns_empty(self):
        self.assertEqual(scrape.fetch("ghostco.example"), "")


class Misc(unittest.TestCase):
    def test_llm_strips_code_fences(self):
        self.assertEqual(json.loads(llm._strip_fences('```json\n{"a": 1}\n```')), {"a": 1})
        self.assertEqual(json.loads(llm._strip_fences('{"a": 1}')), {"a": 1})

    def test_contact_lookup_is_case_insensitive(self):
        self.assertEqual(contacts.find_contact("FINLYTIC.example", str(ROOT / "data/contacts.csv"))["name"], "Rhea Menon")
        self.assertIsNone(contacts.find_contact("nobody.example", str(ROOT / "data/contacts.csv")))

    def test_draft_survives_missing_company_fields(self):
        with mock.patch.object(llm, "ask", lambda s, d, p: {"subject": "s", "body": "b"}):
            self.assertEqual(drafts.draft("x.example", {"company": None, "compliance_signals": None},
                                          {"name": "a", "title": "b"})["subject"], "s")

    def test_monthly_summary_is_monthly(self):
        s = impact.monthly_summary()
        self.assertAlmostEqual(s["hours_saved_per_month"], 15.2, places=1)
        self.assertGreater(s["net_value_per_month_inr"], 0)

    def test_parse_domains(self):
        self.assertEqual(run.parse_domains("A.example\n\n# note\nb.example # tail\na.example\n"),
                         ["a.example", "b.example"])


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.getcwd()
        os.chdir(self.tmp)
        shutil.copytree(ROOT / "data", "data")
        run.LOG = Path("runs/run_log.jsonl")

    def tearDown(self):
        os.chdir(self.old)
        shutil.rmtree(self.tmp)

    def rows(self):
        return [json.loads(l) for l in Path("runs/run_log.jsonl").read_text().splitlines()]

    def test_full_offline_run(self):
        domains = run.parse_domains((ROOT / "data/domains.txt").read_text())
        with mock.patch.object(scrape, "PAGES", ROOT / "fixtures/pages"), \
             mock.patch.object(llm, "_CANNED", ROOT / "fixtures/llm_responses.json"):
            run.run(domains, "data/contacts.csv")
        by = {r["domain"]: r for r in self.rows()}
        for d in ("finlytic.example", "cartwheel.example", "zenstack.example"):
            self.assertTrue(by[d]["qualified"], d)
            self.assertEqual(by[d]["send"], "written to outbox/")
            self.assertTrue(Path(f"outbox/{d}.txt").exists())
        for d in ("brickbox.example", "orbitdocs.example"):
            self.assertFalse(by[d]["qualified"], d)
            self.assertFalse(Path(f"outbox/{d}.txt").exists())
        self.assertEqual(by["ghostco.example"]["reason"], "no data: page unavailable")
        self.assertEqual(sorted(os.listdir("outbox")),
                         ["cartwheel.example.txt", "finlytic.example.txt", "zenstack.example.txt"])
        self.assertIn(config.TO_ADDRESS, Path("outbox/finlytic.example.txt").read_text())

    def test_one_failing_domain_does_not_stop_the_run_and_is_logged(self):
        real = run.process
        def process(d, c):
            if d == "b.example":
                raise KeyError("boom")
            return {"domain": d, "score": 90, "qualified": True, "reason": "r"}
        with mock.patch.object(run, "process", process):
            rows = run.run(["a.example", "b.example", "c.example"], "data/contacts.csv")
        self.assertEqual([("error" in r) for r in rows], [False, True, False])
        self.assertEqual(len(self.rows()), 3)

    def test_already_sent_domain_is_not_emailed_again(self):
        Path("runs").mkdir()
        Path("runs/run_log.jsonl").write_text(json.dumps({"domain": "a.example", "send": "sent"}) + "\n")
        with mock.patch.object(run, "process") as p:
            rows = run.run(["a.example"], "data/contacts.csv")
        p.assert_not_called()
        self.assertIn("skipped", rows[0])

    def test_qualified_but_no_contact_is_reported_not_sent(self):
        company = {"company": "X", "compliance_signals": []}
        with mock.patch.object(scrape, "fetch_with_status", lambda d, p="home": ("text", scrape.OK)), \
             mock.patch.object(run.extract, "extract", lambda d, t: company), \
             mock.patch.object(llm, "ask", reply(95)):
            row = run.process("nocontact.example", "data/contacts.csv")
        self.assertEqual(row["send"], "skipped: no contact")


if __name__ == "__main__":
    unittest.main()
