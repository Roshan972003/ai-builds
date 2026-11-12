import config
import llm
import scrape
import extract

PROMPT = """Sprinto sells compliance automation (SOC 2, ISO 27001, GDPR) to SaaS
companies at Series A-C that are preparing for an audit or pressed by enterprise
customers. Score this company's fit and say if more information is needed.
Return JSON: score (0-100), reason, needs_more (bool).

COMPANY: {company}"""


def qualify(domain, company):
    result = llm.ask("qualify", domain, PROMPT.format(company=company))
    pages = config.EXTRA_PAGES[:config.MAX_ROUNDS]
    for page in pages:
        if not result["needs_more"]:
            break
        more = scrape.fetch(domain, page)
        if not more:
            continue  # page unavailable after retries; try the next one
        company = {**company, **extract.extract(domain, more)}
        result = llm.ask("qualify_more", domain, PROMPT.format(company=company))
    result["qualified"] = result["score"] >= config.QUALIFY_THRESHOLD
    return result
