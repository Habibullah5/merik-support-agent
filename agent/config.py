"""Fixed run constants (scenario pack section 0) and model configuration."""

import os
from pathlib import Path

# Load .env if present
try:
    from dotenv import load_dotenv
    base_dir = Path(__file__).resolve().parent.parent
    load_dotenv(base_dir / ".env")
except ImportError:
    pass

# Scenario pack fixed date constants
TODAY_ISO = "2026-09-10"
TODAY_HUMAN = "Thursday 10 September 2026"

# Model configurations matching your Anthropic account
MODEL_NAME = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "claude-haiku-4-5-20251001")