import json
from pathlib import Path
import config

_CANNED = Path(__file__).parent / "fixtures" / "llm_responses.json"


def assess(app_id, prompt):
    """Return the model's per-criterion verdicts and token counts for one application."""
    if config.OFFLINE:
        return json.loads(_CANNED.read_text())[app_id]

    from google import genai
    client = genai.Client(api_key=config.API_KEY)
    resp = client.models.generate_content(
        model=config.MODEL, contents=prompt, config={"temperature": config.TEMPERATURE,
                "response_mime_type": "application/json"})
    reply = json.loads(resp.text)
    usage = resp.usage_metadata
    reply["tokens_in"] = usage.prompt_token_count
    reply["tokens_out"] = usage.candidates_token_count
    return reply
