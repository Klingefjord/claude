"""Configuration for the venue finder."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"
TAXONOMY_FILE = PROJECT_ROOT / "taxonomy.yaml"
LOG_FILE = PROJECT_ROOT / "venue_finder.log"

# Geographic scope: Île-de-France + 100km buffer.
# Île-de-France bbox is roughly (1.45, 48.12) to (3.56, 49.24).
# +100km buffer ≈ +0.9° lat, +1.4° lon at this latitude.
PARIS_BBOX = {
    "south": 47.20,
    "west": 0.05,
    "north": 50.15,
    "east": 4.95,
}
PARIS_CENTER = (48.8566, 2.3522)
SEARCH_RADIUS_KM = 100  # buffer beyond IDF perimeter

# A small dev bbox for --dry-run (~5km around Vincennes).
DRY_RUN_BBOX = {
    "south": 48.82,
    "west": 2.40,
    "north": 48.87,
    "east": 2.48,
}

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = 180
HTTP_USER_AGENT = "venue-finder/0.1 (outreach research; contact: your-email@example.com)"

# LLM scoring (optional; --no-llm skips this step)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LLM_MODEL = "claude-haiku-4-5-20251001"
LLM_BATCH_SIZE = 20  # venues per scoring call

# Tier weights for ranking (multiplied with fit_score 1-10)
TIER_WEIGHTS = {
    "A": 1.4,
    "B": 1.2,
    "C": 1.0,
    "D": 0.8,
}

# Output
TOP_N = 1000
EXPORT_CSV = DATA_DIR / "top_1000.csv"
SCORED_JSONL = DATA_DIR / "scored.jsonl"
DEDUPED_JSONL = DATA_DIR / "deduped.jsonl"


def validate_config(require_llm: bool = True):
    errors = []
    if not TAXONOMY_FILE.exists():
        errors.append(f"Missing {TAXONOMY_FILE}")
    if require_llm and not ANTHROPIC_API_KEY:
        errors.append(
            "ANTHROPIC_API_KEY not set. Set it, or run with --no-llm to skip scoring."
        )
    return errors


def ensure_dirs():
    for d in (DATA_DIR, RAW_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
