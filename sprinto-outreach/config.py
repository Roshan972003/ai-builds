import os
from dotenv import load_dotenv

load_dotenv()

OFFLINE = os.getenv("OFFLINE", "1") == "1"
API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyDEMO-0000-not-a-real-key")
MODEL = "gemini-2.0-flash"
TEMPERATURE = 0.7          # default (creative drafting)
TEMPERATURES = {"extract": 0, "qualify": 0, "qualify_more": 0}  # scoring/extraction: repeatable

QUALIFY_THRESHOLD = 70    # minimum ICP fit (0-100, same scale as the LLM score) to email
MAX_ROUNDS = 2            # extra page fetches the qualifier may ask for
EXTRA_PAGES = ["about", "security"]  # one new page per round, in order
MAX_FETCH_RETRIES = 3     # max attempts per page when a fetch fails
TO_ADDRESS = "growth.lead@example.com"  # case rule: all mail goes to the student's own inbox

if MAX_ROUNDS > len(EXTRA_PAGES):
    raise ValueError(f"MAX_ROUNDS={MAX_ROUNDS} but only {len(EXTRA_PAGES)} EXTRA_PAGES are configured")
