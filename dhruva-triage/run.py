import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import config
import cost
import guard
import llm
import loader
import score


def build_prompt(app):
    return (
        "You are screening a startup application for Dhruva Capital. For each criterion in "
        f"{config.CRITERIA}, give a verdict of match, partial, no-match or insufficient-data, "
        "with a short citation quoting the form or deck. Do not guess: use insufficient-data "
        'when the material does not say. Reply with JSON only: {"criteria": {"<criterion>": '
        '{"verdict": "...", "citation": "..."}}}.\n\n'
        + "\n".join(f"{k}: {v}" for k, v in app.items()))


def run(path):
    apps = loader.load(path)
    rows = []
    for app in apps:
        reply = llm.assess(app["id"], build_prompt(app))
        verdicts = score.normalise(reply)
        raw = score.raw_score(verdicts)
        fit = round(raw / len(config.CRITERIA) * 10, 1)
        gaps = score.missing(verdicts)
        term = guard.anti_thesis(app)
        rec = score.recommend(fit, len(gaps), term)
        inr = cost.cost_inr(reply.get("tokens_in", 0), reply.get("tokens_out", 0))
        rows.append({"id": app["id"], "name": app["name"], "fit": fit, "rec": rec,
                     "could_not_establish": gaps, "cost_inr": round(inr, 2)})
        Path("reports").mkdir(exist_ok=True)
        Path("reports", app["id"] + ".json").write_text(json.dumps({**rows[-1], "criteria": verdicts}, indent=1))
    print(f"{'application':14}{'fit':>5}  recommendation")
    for r in sorted(rows, key=lambda r: -r["fit"]):
        print(f"{r['name']:14}{r['fit']:>5}  {r['rec']}")
    avg = sum(r["cost_inr"] for r in rows) / max(len(rows), 1)
    print(f"cost per application: Rs {avg:.2f} (ceiling Rs {config.COST_CEILING_INR}); "
          f"projected quarter ({config.QUARTERLY_VOLUME} apps): Rs {avg * config.QUARTERLY_VOLUME:,.0f}")
    Path("runs").mkdir(exist_ok=True)
    with open("runs/run_log.jsonl", "a") as f:
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for r in rows:
            f.write(json.dumps({"run_at": stamp, **r}) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apps", default="data/applications.csv")
    run(ap.parse_args().apps)
