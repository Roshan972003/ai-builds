ANTI_THESIS = ["consumer social", "gaming", "creator economy", "nbfc", "lending licence",
               "d2c", "crypto", "web3"]


def anti_thesis(app):
    """Return the anti-thesis term an application hits, or None."""
    text = f"{app['sector']} {app['model']} {app.get('deck', '')}".lower()
    for term in ANTI_THESIS:
        if term in text:
            return term
    return None
