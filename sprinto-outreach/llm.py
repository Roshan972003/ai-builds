import json
from pathlib import Path
import config

_CANNED = Path(__file__).parent / "fixtures" / "llm_responses.json"


def ask(step, domain, prompt):
    """Return the model's JSON reply as a dict."""
    if config.OFFLINE:
        canned = json.loads(_CANNED.read_text())
        try:
            return canned[step][domain]
        except KeyError:
            raise LookupError(f"no canned reply for step={step!r} domain={domain!r}") from None

    from google import genai
    client = genai.Client(api_key=config.API_KEY)
    resp = client.models.generate_content(
        model=config.MODEL,
        contents=prompt,
        config={"temperature": config.TEMPERATURES.get(step, config.TEMPERATURE)},
    )
    return json.loads(_strip_fences(resp.text))


def _strip_fences(text):
    """Models often wrap JSON in ```json fences; remove them."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rsplit("```", 1)[0]
    return t.strip()
