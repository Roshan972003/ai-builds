import time
from pathlib import Path
import requests
import config

PAGES = Path(__file__).parent / "fixtures" / "pages"


def fetch(domain, path="home"):
    """Return cleaned page text for a domain (home or about page).

    Network failures are retried up to config.MAX_FETCH_RETRIES attempts;
    after that, log the failure and return "".
    """
    if config.OFFLINE:
        f = PAGES / f"{domain}_{path}.txt"
        return f.read_text() if f.exists() else ""

    url = f"https://{domain}/" + ("" if path == "home" else path)
    for attempt in range(1, config.MAX_FETCH_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            return clean(resp.text)
        except requests.RequestException as e:
            print(f"scrape: {url} attempt {attempt}/{config.MAX_FETCH_RETRIES} failed: {e}")
            if attempt < config.MAX_FETCH_RETRIES:
                time.sleep(2 ** (attempt - 1))
    return ""


def clean(html):
    lines = [l.strip() for l in html.splitlines() if len(l.split()) >= 8]
    seen, out = set(), []
    for l in lines:
        if l not in seen:
            seen.add(l)
            out.append(l)
    return "\n".join(out)[:8000]
