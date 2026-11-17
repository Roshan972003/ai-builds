import os
from dotenv import load_dotenv

load_dotenv()

OFFLINE = os.getenv("OFFLINE", "1") == "1"
API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.0-flash"
TEMPERATURE = 0

CRITERIA = ["stage", "sector", "geography", "founder_profile", "business_model", "round_size"]
ADVANCE_AT = 7.0       # fit score out of 10 needed to advance to a call
MIN_EVIDENCE = 3       # more missing criteria than this: no recommendation
COST_CEILING_INR = 20  # per application
QUARTERLY_VOLUME = 380
