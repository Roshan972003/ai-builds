POINTS = {"match": 1, "partial": 0.5, "no-match": 0, "insufficient-data": 0}


def normalise(reply):
    """Return a verdicts dict covering every criterion. Anything malformed becomes
    insufficient-data, as does a match/partial with no citation (the brief wants one per criterion)."""
    import config
    raw = reply.get("criteria") if isinstance(reply, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for c in config.CRITERIA:
        v = raw.get(c)
        verdict = str(v.get("verdict", "")).strip().lower() if isinstance(v, dict) else ""
        cite = str(v.get("citation") or "").strip() if isinstance(v, dict) else ""
        if verdict not in POINTS:
            verdict, cite = "insufficient-data", cite or "model reply missing or invalid"
        elif verdict != "no-match" and not cite:
            verdict, cite = "insufficient-data", "no citation given"
        out[c] = {"verdict": verdict, "citation": cite or None}
    return out


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
