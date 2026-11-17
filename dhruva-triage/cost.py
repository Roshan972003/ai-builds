# Illustrative rate card (USD per million tokens) and exchange rate. Check the live price sheet.
INPUT_USD_PER_M = 2.00
OUTPUT_USD_PER_M = 8.00
USD_INR = 85


def cost_inr(in_tokens, out_tokens):
    usd = in_tokens * INPUT_USD_PER_M / 1_000_000 + out_tokens * OUTPUT_USD_PER_M / 1_000_000
    return usd * USD_INR
