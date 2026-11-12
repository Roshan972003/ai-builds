"""Scraper tests: retry policy, HTML cleaning, input normalisation. Offline."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["OFFLINE"] = "1"

import config, scrape  # noqa: E402

R = scrape.requests


def resp(status=200, text="word " * 9):
    r = mock.Mock(status_code=status, text=text)
    def raise_for_status():
        if status >= 400:
            raise R.HTTPError(f"{status}", response=r)
    r.raise_for_status = raise_for_status
    return r


class Live(unittest.TestCase):
    def fetch(self, side_effect):
        get = mock.Mock(side_effect=side_effect)
        with mock.patch.object(config, "OFFLINE", False), \
             mock.patch.object(R, "get", get), \
             mock.patch.object(scrape.time, "sleep") as sleep:
            out = scrape.fetch("acme.com", "about")
        return out, get, sleep

    def test_success_first_try(self):
        out, get, _ = self.fetch([resp()])
        self.assertIn("word", out)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args[0][0], "https://acme.com/about")
        self.assertIn("User-Agent", get.call_args[1]["headers"])

    def test_permanent_4xx_is_not_retried(self):
        for status in (400, 401, 403, 404, 410):
            out, get, _ = self.fetch([resp(status)] * 3)
            self.assertEqual((out, get.call_count), ("", 1), status)

    def test_transient_errors_are_retried_up_to_the_cap(self):
        for status in (408, 429, 500, 503):
            out, get, _ = self.fetch([resp(status)] * 5)
            self.assertEqual((out, get.call_count), ("", config.MAX_FETCH_RETRIES), status)

    def test_timeout_and_connection_errors_are_retried_up_to_the_cap(self):
        for exc in (R.Timeout("t"), R.ConnectionError("c")):
            out, get, sleep = self.fetch([exc] * 5)
            self.assertEqual((out, get.call_count), ("", config.MAX_FETCH_RETRIES))
            self.assertEqual(sleep.call_count, config.MAX_FETCH_RETRIES - 1)  # no sleep after last

    def test_recovers_after_transient_failure(self):
        out, get, _ = self.fetch([resp(500), R.Timeout("t"), resp()])
        self.assertIn("word", out)
        self.assertEqual(get.call_count, 3)

    def test_backoff_grows(self):
        _, _, sleep = self.fetch([resp(500)] * 5)
        self.assertEqual([c[0][0] for c in sleep.call_args_list], [1, 2])


class Normalize(unittest.TestCase):
    def test_variants(self):
        for raw in ("acme.com", " ACME.com ", "https://acme.com", "http://Acme.com/about?x=1", "acme.com/"):
            self.assertEqual(scrape.normalize_domain(raw), "acme.com", raw)

    def test_url_is_built_correctly_from_scheme_input(self):
        get = mock.Mock(return_value=resp())
        with mock.patch.object(config, "OFFLINE", False), mock.patch.object(R, "get", get):
            scrape.fetch("https://acme.com/")
        self.assertEqual(get.call_args[0][0], "https://acme.com/")


class Clean(unittest.TestCase):
    PAGE = """<!doctype html><html><head><title>Acme Cloud</title>
      <meta name="description" content="Acme sells cloud software to banks">
      <style>body{color:red} .a{margin:0 auto 0 auto 1 2 3 4 5}</style>
      <script>var tracking = "one two three four five six seven eight nine ten";</script></head>
      <body><nav><a href="/">Home</a></nav>
      <h1>Acme</h1>
      <p>Acme builds cloud software for banks and needs SOC 2 soon for customers.</p>
      <p>Acme builds cloud software for banks and needs SOC 2 soon for customers.</p>
      <script>alert("one two three four five six seven eight nine ten")</script>
      <div>Short line</div><noscript>Enable JavaScript to see this page properly please thanks</noscript>
      <p>We&amp;re hiring across <b>Bengaluru</b> and Pune for several engineering roles now.</p>
      </body></html>"""

    def setUp(self):
        self.out = scrape.clean(self.PAGE)

    def test_no_markup_scripts_or_styles(self):
        for bad in ("<", ">", "var tracking", "alert(", "margin", "Enable JavaScript"):
            self.assertNotIn(bad, self.out)

    def test_keeps_title_description_and_body(self):
        self.assertIn("Acme Cloud", self.out)
        self.assertIn("Acme sells cloud software to banks", self.out)
        self.assertIn("needs SOC 2 soon", self.out)

    def test_inline_tags_do_not_split_sentences_and_entities_decode(self):
        self.assertIn("We&re hiring across Bengaluru and Pune for several engineering roles now.", self.out)

    def test_duplicates_and_short_lines_dropped(self):
        self.assertEqual(self.out.count("needs SOC 2 soon"), 1)
        self.assertNotIn("Short line", self.out)

    def test_truncated_to_8000(self):
        big = "".join(f"<p>line {i} has easily more than eight words inside it okay</p>" for i in range(1000))
        self.assertEqual(len(scrape.clean(big)), 8000)

    def test_malformed_and_empty_input(self):
        self.assertEqual(scrape.clean(""), "")
        self.assertIsInstance(scrape.clean("<p>unclosed <b>tag " + "word " * 10), str)
        self.assertIsInstance(scrape.clean("<<<>>> <script>"), str)


if __name__ == "__main__":
    unittest.main()
