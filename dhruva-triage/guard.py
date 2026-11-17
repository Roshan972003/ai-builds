import re

ANTI_THESIS = ["consumer social", "gaming", "creator economy", "nbfc", "lending licence",
               "d2c", "crypto", "web3"]
# a negation word, then up to 4 plain words (no punctuation, no "but") before the term
_NEGATION = r"\b(?:no|not|never|without|don't|doesn't)\s+(?:(?!but\b)[\w']+\s+){0,4}"


def anti_thesis(app):
    """Return the anti-thesis term an application hits, or None. A negated mention
    ("we do not do gaming") is not a hit."""
    text = f"{app['sector']} {app['model']} {app.get('deck', '')}".lower()
    for term in ANTI_THESIS:
        for m in re.finditer(re.escape(term), text):
            if not re.search(_NEGATION + r"$", text[:m.start()]):
                return term
    return None
