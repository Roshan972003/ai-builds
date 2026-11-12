import argparse
import json
import time
import traceback
from pathlib import Path

import contacts
import drafts
import extract
import qualify
import scrape
import send
import impact

LOG = Path("runs/run_log.jsonl")


def parse_domains(text):
    """One domain per line; blank lines and # comments are ignored."""
    out = []
    for line in text.splitlines():
        line = scrape.normalize_domain(line.split("#", 1)[0])
        if line and line not in out:
            out.append(line)
    return out


def already_sent():
    if not LOG.exists():
        return set()
    done = set()
    for line in LOG.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("send") == "sent":
            done.add(r["domain"])
    return done


def process(d, contacts_path):
    text, status = scrape.fetch_with_status(d)
    company = extract.extract(d, text) if text else {}
    if company:
        q = qualify.qualify(d, company)
    else:
        why = {scrape.TRANSIENT: "scrape failed after retries", scrape.PERMANENT: "page unavailable"}.get(
            status, "empty page" if not text else "extraction returned nothing")
        q = {"score": 0, "qualified": False, "reason": f"no data: {why}"}
    row = {"domain": d, "score": q["score"], "qualified": q["qualified"], "reason": q["reason"]}
    for key in ("scrape_failed", "followup_error", "incomplete"):
        if q.get(key):
            row[key] = q[key]
    if q["qualified"]:
        contact = contacts.find_contact(d, contacts_path)
        if contact:
            mail = drafts.draft(d, company, contact)
            row["contact"] = contact["name"]
            row["subject"] = mail["subject"]
            row["send"] = send.send(d, mail["subject"], mail["body"])
        else:
            row["send"] = "skipped: no contact"
    return row


def run(domains, contacts_path):
    """Process every domain; one failure is logged and never stops the rest.
    Each row is appended to the log as soon as it is done."""
    LOG.parent.mkdir(exist_ok=True)
    sent_before = already_sent()
    rows = []
    for d in domains:
        t0 = time.time()
        if d in sent_before:
            row = {"domain": d, "skipped": "already sent in an earlier run"}
        else:
            try:
                row = process(d, contacts_path)
            except Exception as e:
                traceback.print_exc()
                row = {"domain": d, "error": f"{type(e).__name__}: {e}"}
        row["seconds"] = round(time.time() - t0, 2)
        rows.append(row)
        with open(LOG, "a") as f:
            f.write(json.dumps(row) + "\n")
        status = row.get("error") or row.get("skipped") or f"score={row['score']:<4} qualified={row['qualified']!s:5} {row.get('contact', '-')}"
        print(f"{d:22} {status}")
    failed = [r["domain"] for r in rows if "error" in r]
    if failed:
        print(f"{len(failed)} domain(s) failed: {', '.join(failed)}")
    print(impact.monthly_summary())
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", default="data/domains.txt")
    ap.add_argument("--contacts", default="data/contacts.csv")
    a = ap.parse_args()
    rows = run(parse_domains(Path(a.domains).read_text()), a.contacts)
    raise SystemExit(1 if any("error" in r for r in rows) else 0)
