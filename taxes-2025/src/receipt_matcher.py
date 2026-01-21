"""
Receipt Matcher - LLM-powered matching of transactions to emails.
"""

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from anthropic import Anthropic

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    CONFIDENCE_THRESHOLD_HIGH,
    CONFIDENCE_THRESHOLD_MEDIUM,
)
from src.transactions import Transaction
from src.gmail_client import Email


class MatchConfidence(Enum):
    """Confidence level for a receipt match."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NO_MATCH = "no_match"


@dataclass
class MatchResult:
    """Result of matching a transaction to an email."""

    transaction: Transaction
    email: Optional[Email]
    confidence: MatchConfidence
    reasoning: str
    score: float = 0.0

    def should_export(self) -> bool:
        """Whether this match should be automatically exported."""
        return self.confidence in [MatchConfidence.HIGH, MatchConfidence.MEDIUM]

    def needs_review(self) -> bool:
        """Whether this match needs manual review."""
        return self.confidence == MatchConfidence.MEDIUM


class ReceiptMatcher:
    """
    Uses Claude to intelligently match transactions to receipt emails.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize the receipt matcher.

        Args:
            api_key: Anthropic API key. Defaults to config or environment variable.
            model: Model to use. Defaults to config setting.
        """
        self.api_key = api_key or ANTHROPIC_API_KEY
        self.model = model or ANTHROPIC_MODEL

        if not self.api_key:
            raise ValueError(
                "Anthropic API key not provided. "
                "Set ANTHROPIC_API_KEY environment variable or pass to constructor."
            )

        self.client = Anthropic(api_key=self.api_key)

    def match_transaction(
        self,
        transaction: Transaction,
        candidate_emails: list[Email],
    ) -> MatchResult:
        """
        Find the best matching email for a transaction.

        Args:
            transaction: The transaction to match.
            candidate_emails: List of potential matching emails.

        Returns:
            MatchResult with the best match (or no match).
        """
        if not candidate_emails:
            return MatchResult(
                transaction=transaction,
                email=None,
                confidence=MatchConfidence.NO_MATCH,
                reasoning="No candidate emails found for this transaction.",
                score=0.0,
            )

        # Build the prompt for Claude
        prompt = self._build_matching_prompt(transaction, candidate_emails)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse the response
            return self._parse_response(transaction, candidate_emails, response)

        except Exception as e:
            print(f"Error calling Claude API: {e}")
            return MatchResult(
                transaction=transaction,
                email=None,
                confidence=MatchConfidence.NO_MATCH,
                reasoning=f"Error during matching: {str(e)}",
                score=0.0,
            )

    def _build_matching_prompt(
        self,
        transaction: Transaction,
        emails: list[Email],
    ) -> str:
        """Build the prompt for Claude to evaluate matches."""

        email_summaries = []
        for i, email in enumerate(emails):
            summary = f"""
Email {i + 1}:
- Subject: {email.subject}
- From: {email.sender}
- Date: {email.date.strftime('%Y-%m-%d %H:%M')}
- Snippet: {email.snippet[:200]}...
- Has PDF attachment: {email.has_pdf_attachment()}
- Number of attachments: {len(email.attachments)}
"""
            email_summaries.append(summary)

        emails_text = "\n".join(email_summaries)

        prompt = f"""You are helping match a financial transaction to a receipt/invoice email.

TRANSACTION DETAILS:
- Date: {transaction.date.strftime('%Y-%m-%d')}
- Merchant/Description: {transaction.description}
- Extracted Merchant Name: {transaction.merchant_name}
- Amount: {transaction.currency} {transaction.amount:.2f}
- Category: {transaction.category}

CANDIDATE EMAILS:
{emails_text}

TASK:
Analyze each email and determine which one (if any) is most likely to be the receipt or invoice for this transaction.

Consider:
1. Date proximity (receipt usually sent same day or within a few days)
2. Merchant name matching (may be abbreviated or slightly different)
3. Amount mentioned in subject or snippet
4. Email appears to be transactional (receipt, invoice, order confirmation)
5. PDF attachments are often receipts

Respond in JSON format:
{{
    "best_match_index": <1-based index of best match, or 0 if no good match>,
    "confidence": "<high|medium|low|no_match>",
    "confidence_score": <0.0 to 1.0>,
    "reasoning": "<brief explanation of your decision>"
}}

Be conservative - only mark as "high" confidence if you're quite sure it's a match.
Mark as "medium" if it's likely but has some uncertainty.
Mark as "low" or "no_match" if uncertain or no good candidates."""

        return prompt

    def _parse_response(
        self,
        transaction: Transaction,
        emails: list[Email],
        response,
    ) -> MatchResult:
        """Parse Claude's response into a MatchResult."""

        try:
            # Extract text content from response
            text = response.content[0].text

            # Find JSON in response (may be wrapped in markdown code blocks)
            json_start = text.find("{")
            json_end = text.rfind("}") + 1
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")

            json_str = text[json_start:json_end]
            result = json.loads(json_str)

            # Extract fields
            best_match_idx = result.get("best_match_index", 0)
            confidence_str = result.get("confidence", "no_match").lower()
            score = float(result.get("confidence_score", 0.0))
            reasoning = result.get("reasoning", "No reasoning provided")

            # Map confidence string to enum
            confidence_map = {
                "high": MatchConfidence.HIGH,
                "medium": MatchConfidence.MEDIUM,
                "low": MatchConfidence.LOW,
                "no_match": MatchConfidence.NO_MATCH,
            }
            confidence = confidence_map.get(confidence_str, MatchConfidence.NO_MATCH)

            # Get matched email
            matched_email = None
            if best_match_idx > 0 and best_match_idx <= len(emails):
                matched_email = emails[best_match_idx - 1]

            # Override confidence based on score thresholds
            if score >= CONFIDENCE_THRESHOLD_HIGH:
                confidence = MatchConfidence.HIGH
            elif score >= CONFIDENCE_THRESHOLD_MEDIUM:
                confidence = max(confidence, MatchConfidence.MEDIUM, key=lambda x: x.value)

            return MatchResult(
                transaction=transaction,
                email=matched_email,
                confidence=confidence,
                reasoning=reasoning,
                score=score,
            )

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"Error parsing Claude response: {e}")
            print(f"Response text: {response.content[0].text[:500]}")
            return MatchResult(
                transaction=transaction,
                email=None,
                confidence=MatchConfidence.NO_MATCH,
                reasoning=f"Failed to parse matching response: {str(e)}",
                score=0.0,
            )

    def batch_match(
        self,
        transactions: list[Transaction],
        search_func,
        progress_callback=None,
    ) -> list[MatchResult]:
        """
        Match multiple transactions to emails.

        Args:
            transactions: List of transactions to match.
            search_func: Function that takes a Transaction and returns list of candidate Emails.
            progress_callback: Optional callback(current, total) for progress updates.

        Returns:
            List of MatchResults for each transaction.
        """
        results = []

        for i, transaction in enumerate(transactions):
            if progress_callback:
                progress_callback(i + 1, len(transactions))

            # Get candidate emails
            candidate_emails = search_func(transaction)

            # Match
            result = self.match_transaction(transaction, candidate_emails)
            results.append(result)

        return results


if __name__ == "__main__":
    # Test the matcher with mock data
    print("Receipt Matcher Test")
    print("-" * 40)

    if not ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        exit(1)

    # Create a mock transaction
    from datetime import datetime

    mock_transaction = Transaction(
        date=datetime(2024, 1, 15),
        description="GITHUB.COM - ANNUAL SUBSCRIPTION",
        amount=48.00,
        currency="USD",
        category="Software",
        original_row=10,
    )

    print(f"Transaction: {mock_transaction}")
    print(f"Extracted merchant: {mock_transaction.merchant_name}")
    print(f"Search keywords: {mock_transaction.search_keywords}")

    # Test matcher initialization
    try:
        matcher = ReceiptMatcher()
        print("\nMatcher initialized successfully")
    except ValueError as e:
        print(f"Error: {e}")
