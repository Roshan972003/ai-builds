import config
import llm
import scrape
import extract

PROMPT = """Sprinto sells compliance automation (SOC 2, ISO 27001, GDPR) to SaaS
companies at Series A-C that are preparing for an audit or pressed by enterprise
customers. Score this company's fit and say if more information is needed.
Return JSON: score (0-100), reason, needs_more (bool).

COMPANY: {company}"""


def _normalise(raw):
    """Coerce a model reply into {score: float, reason: str, needs_more: bool}."""
    try:
        score = float(raw["score"])
        score = int(score) if score.is_integer() else score
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"model reply has no usable score: {raw!r}") from None
    return {**raw, "score": score, "reason": raw.get("reason") or "",
            "needs_more": raw.get("needs_more") is True}


def qualify(domain, company):
    result = _normalise(llm.ask("qualify", domain, PROMPT.format(company=company)))
    pages = config.EXTRA_PAGES[:config.MAX_ROUNDS]
    for page in pages:
        if not result["needs_more"]:
            break
        more = scrape.fetch(domain, page)
        if not more:
            continue  # page unavailable after retries; try the next one
        company = {**company, **extract.extract(domain, more)}
        try:
            result = _normalise(llm.ask("qualify_more", domain, PROMPT.format(company=company)))
        except LookupError:
            break  # no follow-up reply available (offline); keep the first result
    result["qualified"] = result["score"] >= config.QUALIFY_THRESHOLD
    return result
