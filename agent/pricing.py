"""
Rough per-token pricing used only to estimate spend for the loop's cost cap.
Override via env vars if published prices drift; this is not billing-accurate.
"""

import os

INPUT_PRICE_PER_TOKEN = float(os.environ.get("PRICE_INPUT_PER_TOKEN", 3.0 / 1_000_000))
OUTPUT_PRICE_PER_TOKEN = float(os.environ.get("PRICE_OUTPUT_PER_TOKEN", 15.0 / 1_000_000))


def estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return input_tokens * INPUT_PRICE_PER_TOKEN + output_tokens * OUTPUT_PRICE_PER_TOKEN
