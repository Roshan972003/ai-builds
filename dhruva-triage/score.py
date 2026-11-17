POINTS = {"match": 1, "partial": 0.5, "no-match": 0}


def raw_score(verdicts):
    """Sum of points across the six criteria, 0 to 6."""
    return sum(POINTS.get(v["verdict"], 0) for v in verdicts.values())


def missing(verdicts):
    import config
    return [c for c in config.CRITERIA
            if c not in verdicts or verdicts[c]["verdict"] == "insufficient-data"]


def recommend(fit, n_missing, term):
    import config
    if term:
        return f"PASS (anti-thesis: {term})"
    if n_missing > config.MIN_EVIDENCE:
        return "INSUFFICIENT DATA TO RECOMMEND"
    return "ADVANCE TO CALL" if fit >= config.ADVANCE_AT else "PASS"
