import csv


def find_contact(domain, path="data/contacts.csv", live=False):
    if live:
        raise NotImplementedError("live contact lookup (Hunter) is not implemented; use the CSV")

    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if row["domain"].strip().lower() == domain.strip().lower():
                return {"name": row["name"], "title": row["title"], "email": row["email"]}
    return None
