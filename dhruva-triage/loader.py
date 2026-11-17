import csv
from pathlib import Path


def load(path="data/applications.csv"):
    apps = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [h.strip() for h in reader.fieldnames]
        for row in reader:
            apps.append({
                "id": row["id"],
                "name": row["name"],
                "stage": row["stage"],
                "sector": row["sector"],
                "hq": row["hq"],
                "founders": row["founders"],
                "model": row["model"],
                "round_size_cr": row["round_size_cr"],
                "deck": Path("decks", row["id"] + ".txt").read_text(),
            })
    return apps
