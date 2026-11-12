import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import requests
import config

PAGES = Path(__file__).parent / "fixtures" / "pages"
HEADERS = {"User-Agent": "sprinto-outreach/1.0 (research scraper)"}
SKIP_TAGS = {"script", "style", "noscript", "svg", "template", "iframe", "head"}
BLOCK_TAGS = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6", "section",
              "article", "header", "footer", "tr", "td", "ul", "ol", "main", "nav", "title"}
RETRY_STATUS = {408, 425, 429}  # plus every 5xx; other 4xx are permanent


def normalize_domain(value):
    """'https://Acme.com/path ' -> 'acme.com'."""
    v = value.strip().lower()
    if "//" in v:
        v = urlparse(v).netloc
    return v.split("/")[0]


def _retryable(exc):
    resp = getattr(exc, "response", None)
    if resp is None:  # timeout / connection / DNS error
        return True
    return resp.status_code >= 500 or resp.status_code in RETRY_STATUS


def fetch(domain, path="home"):
    """Return cleaned page text for a domain (home or about page).

    Timeouts, connection errors, 5xx and 408/425/429 are retried up to
    config.MAX_FETCH_RETRIES attempts with backoff; other 4xx (404, 403...)
    fail immediately. Failures are logged and return "".
    """
    domain = normalize_domain(domain)
    if config.OFFLINE:
        f = PAGES / f"{domain}_{path}.txt"
        return f.read_text() if f.exists() else ""

    url = f"https://{domain}/" + ("" if path == "home" else path)
    for attempt in range(1, config.MAX_FETCH_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=10, headers=HEADERS)
            resp.raise_for_status()
            return clean(resp.text)
        except requests.RequestException as e:
            retry = _retryable(e) and attempt < config.MAX_FETCH_RETRIES
            print(f"scrape: {url} attempt {attempt}/{config.MAX_FETCH_RETRIES} failed: {e}"
                  + ("" if retry else " (giving up)"))
            if not retry:
                return ""
            time.sleep(2 ** (attempt - 1))
    return ""


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.parts = []
        self.title = ""
        self.description = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            a = dict(attrs)
            if (a.get("name") or a.get("property") or "").lower() in ("description", "og:description"):
                self.description = self.description or (a.get("content") or "")
        if tag in SKIP_TAGS and tag != "head":
            self.skip += 1
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in SKIP_TAGS and tag != "head" and self.skip:
            self.skip -= 1
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.parts.append(data)


def clean(html):
    """HTML -> readable text: drop scripts/styles/markup, keep title, meta
    description and body lines of at least 8 words, de-duplicated, max 8000 chars."""
    p = _Text()
    try:
        p.feed(html)
        p.close()
    except Exception:
        pass  # malformed markup: use whatever was parsed
    lines = [" ".join(l.split()) for l in "".join(p.parts).splitlines()]
    head = [x.strip() for x in (p.title, p.description) if x.strip()]
    seen, out = set(), []
    for l in head + [l for l in lines if len(l.split()) >= 8]:
        if l not in seen:
            seen.add(l)
            out.append(l)
    return "\n".join(out)[:8000]
