"""
Configuration for the Tax Receipt Finder system.

Before running, you need to:
1. Set up Google Cloud OAuth credentials (see README)
2. Configure your email accounts below
3. Set your Anthropic API key as an environment variable: ANTHROPIC_API_KEY
"""

import os
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
RECEIPTS_DIR = PROJECT_ROOT / "receipts"
MATCHED_DIR = RECEIPTS_DIR / "matched"
MANUAL_REVIEW_DIR = RECEIPTS_DIR / "manual_review"
TRANSACTIONS_FILE = PROJECT_ROOT / "taxes.csv"

# Gmail accounts to search
# Add your email addresses here
EMAIL_ACCOUNTS = [
    {
        "email": "your-email-1@gmail.com",
        "token_file": PROJECT_ROOT / "token_account1.json",
    },
    {
        "email": "your-email-2@gmail.com",
        "token_file": PROJECT_ROOT / "token_account2.json",
    },
]

# Gmail API scopes
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Tax-deductible categories to process
DEDUCTIBLE_CATEGORIES = [
    "Professional Travel",
    "Software",
    "Phone/Internet",
    "Co-Working Space",
    "Computer Hardware",
    "Professional Services",
]

# Search parameters
DATE_RANGE_DAYS = 7  # Search emails within ±7 days of transaction date

# LLM configuration
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
CONFIDENCE_THRESHOLD_HIGH = 0.8
CONFIDENCE_THRESHOLD_MEDIUM = 0.5

# Logging
LOG_FILE = PROJECT_ROOT / "receipt_finder.log"

# Anthropic API key (set via environment variable)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


def validate_config():
    """Validate that required configuration is present."""
    errors = []

    if not CREDENTIALS_FILE.exists():
        errors.append(
            f"Google OAuth credentials not found at {CREDENTIALS_FILE}. "
            "Please download from Google Cloud Console."
        )

    if not ANTHROPIC_API_KEY:
        errors.append(
            "ANTHROPIC_API_KEY environment variable not set. "
            "Please set it to use LLM-powered matching."
        )

    if EMAIL_ACCOUNTS[0]["email"] == "your-email-1@gmail.com":
        errors.append(
            "Please configure your email accounts in config.py"
        )

    return errors
