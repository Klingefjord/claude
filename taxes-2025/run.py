#!/usr/bin/env python3
"""
Tax Receipt Finder - Main entry point.

Automatically finds receipts/invoices in Gmail for tax-deductible transactions.

Usage:
    python run.py                    # Run full process
    python run.py --dry-run          # Test transaction parsing and Gmail auth only
    python run.py --single 5         # Process only transaction at row 5
    python run.py --limit 10         # Process only first 10 transactions
    python run.py --category Software  # Process only Software category
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    validate_config,
    DATE_RANGE_DAYS,
    MATCHED_DIR,
    MANUAL_REVIEW_DIR,
    LOG_FILE,
)
from src.transactions import TransactionParser, Transaction
from src.gmail_client import GmailClient
from src.receipt_matcher import ReceiptMatcher, MatchConfidence
from src.exporter import ReceiptExporter


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def print_progress(current: int, total: int, prefix: str = "Progress"):
    """Print a progress bar."""
    bar_length = 40
    filled = int(bar_length * current / total)
    bar = "=" * filled + "-" * (bar_length - filled)
    percent = 100 * current / total
    print(f"\r{prefix}: [{bar}] {percent:.1f}% ({current}/{total})", end="", flush=True)
    if current == total:
        print()  # New line when complete


def run_dry_run():
    """
    Dry run: test transaction parsing and Gmail authentication.
    """
    print("\n" + "=" * 60)
    print("TAX RECEIPT FINDER - DRY RUN")
    print("=" * 60)

    # Check configuration
    print("\n1. Checking configuration...")
    errors = validate_config()
    if errors:
        for error in errors:
            print(f"   WARNING: {error}")
    else:
        print("   Configuration OK")

    # Parse transactions
    print("\n2. Parsing transactions...")
    try:
        parser = TransactionParser()
        transactions = parser.get_deductible_transactions()
        summary = parser.get_summary()

        print(f"   Found {summary['total_transactions']} deductible transactions")
        print(f"   Total amount: ${summary['total_amount']:.2f}")
        print("\n   By category:")
        for category, data in summary["by_category"].items():
            print(f"     - {category}: {data['count']} transactions (${data['amount']:.2f})")

        if transactions:
            print("\n   Sample transactions:")
            for txn in transactions[:3]:
                print(f"     {txn}")

    except FileNotFoundError as e:
        print(f"   ERROR: {e}")
        return False
    except Exception as e:
        print(f"   ERROR: {e}")
        return False

    # Test Gmail authentication
    print("\n3. Testing Gmail authentication...")
    try:
        gmail_client = GmailClient()
        auth_results = gmail_client.authenticate_all()

        for email, success in auth_results.items():
            status = "OK" if success else "FAILED"
            print(f"   {email}: {status}")

        # Test search on first authenticated account
        authenticated = [e for e, s in auth_results.items() if s]
        if authenticated and transactions:
            print(f"\n4. Testing email search...")
            test_txn = transactions[0]
            query = gmail_client.build_search_query(
                keywords=test_txn.search_keywords,
                date_center=test_txn.date,
                date_range_days=DATE_RANGE_DAYS,
            )
            print(f"   Query: {query[:80]}...")

            emails = gmail_client.search_emails(authenticated[0], query, max_results=3)
            print(f"   Found {len(emails)} candidate emails")

    except FileNotFoundError as e:
        print(f"   ERROR: {e}")
        print("   Please set up Google OAuth credentials (see README)")
    except Exception as e:
        print(f"   ERROR: {e}")

    print("\n" + "=" * 60)
    print("DRY RUN COMPLETE")
    print("=" * 60)

    return True


def run_full(
    single_row: int = None,
    limit: int = None,
    category_filter: str = None,
):
    """
    Run the full receipt finding process.
    """
    print("\n" + "=" * 60)
    print("TAX RECEIPT FINDER")
    print("=" * 60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Validate configuration
    print("\nValidating configuration...")
    errors = validate_config()
    if errors:
        for error in errors:
            logger.error(error)
        print("\nPlease fix configuration errors before running.")
        return False

    # Initialize components
    print("\nInitializing components...")
    parser = TransactionParser()
    gmail_client = GmailClient()
    matcher = ReceiptMatcher()

    # Get transactions
    print("\nLoading transactions...")
    transactions = parser.get_deductible_transactions()

    # Apply filters
    if single_row:
        transactions = [t for t in transactions if t.original_row == single_row]
        if not transactions:
            print(f"No transaction found at row {single_row}")
            return False
        print(f"Processing single transaction at row {single_row}")

    if category_filter:
        transactions = [t for t in transactions if t.category == category_filter]
        print(f"Filtered to {len(transactions)} transactions in '{category_filter}'")

    if limit:
        transactions = transactions[:limit]
        print(f"Limited to first {len(transactions)} transactions")

    print(f"\nTotal transactions to process: {len(transactions)}")

    if not transactions:
        print("No transactions to process.")
        return True

    # Authenticate Gmail
    print("\nAuthenticating Gmail accounts...")
    auth_results = gmail_client.authenticate_all()
    authenticated = [e for e, s in auth_results.items() if s]

    if not authenticated:
        print("ERROR: No Gmail accounts authenticated. Please set up OAuth credentials.")
        return False

    print(f"Authenticated: {', '.join(authenticated)}")

    # Create exporter
    exporter = ReceiptExporter(gmail_client)

    # Process transactions
    print("\n" + "-" * 60)
    print("PROCESSING TRANSACTIONS")
    print("-" * 60)

    results = {
        "high_confidence": [],
        "medium_confidence": [],
        "low_confidence": [],
        "no_match": [],
    }

    def search_func(transaction: Transaction):
        """Search for candidate emails across all accounts."""
        query = gmail_client.build_search_query(
            keywords=transaction.search_keywords,
            date_center=transaction.date,
            date_range_days=DATE_RANGE_DAYS,
        )
        return gmail_client.search_all_accounts(query, max_results_per_account=10)

    for i, txn in enumerate(transactions):
        print_progress(i + 1, len(transactions), "Matching")

        # Search for candidates
        candidates = search_func(txn)

        # Match
        match_result = matcher.match_transaction(txn, candidates)

        # Categorize result
        if match_result.confidence == MatchConfidence.HIGH:
            results["high_confidence"].append(match_result)
        elif match_result.confidence == MatchConfidence.MEDIUM:
            results["medium_confidence"].append(match_result)
        elif match_result.confidence == MatchConfidence.LOW:
            results["low_confidence"].append(match_result)
        else:
            results["no_match"].append(match_result)

        # Export immediately if matched
        if match_result.should_export():
            path = exporter.export_match(match_result)
            if path:
                logger.info(f"Exported: {path}")

    # Summary
    print("\n" + "-" * 60)
    print("RESULTS SUMMARY")
    print("-" * 60)

    print(f"\nHigh confidence matches: {len(results['high_confidence'])}")
    print(f"Medium confidence (needs review): {len(results['medium_confidence'])}")
    print(f"Low confidence: {len(results['low_confidence'])}")
    print(f"No match found: {len(results['no_match'])}")

    print(f"\nExported to:")
    print(f"  Matched: {MATCHED_DIR}")
    print(f"  Manual review: {MANUAL_REVIEW_DIR}")

    # Write detailed report
    report_path = Path(__file__).parent / "receipt_finder_report.json"
    report = {
        "run_time": datetime.now().isoformat(),
        "total_processed": len(transactions),
        "summary": {
            "high_confidence": len(results["high_confidence"]),
            "medium_confidence": len(results["medium_confidence"]),
            "low_confidence": len(results["low_confidence"]),
            "no_match": len(results["no_match"]),
        },
        "high_confidence_matches": [
            {
                "transaction": str(r.transaction),
                "email_subject": r.email.subject if r.email else None,
                "score": r.score,
            }
            for r in results["high_confidence"]
        ],
        "needs_review": [
            {
                "transaction": str(r.transaction),
                "email_subject": r.email.subject if r.email else None,
                "score": r.score,
                "reasoning": r.reasoning,
            }
            for r in results["medium_confidence"]
        ],
        "no_match": [
            {"transaction": str(r.transaction), "reasoning": r.reasoning}
            for r in results["no_match"]
        ],
    }

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nDetailed report saved to: {report_path}")

    # List items needing review
    if results["medium_confidence"]:
        print("\n" + "-" * 60)
        print("ITEMS NEEDING MANUAL REVIEW")
        print("-" * 60)
        for r in results["medium_confidence"][:10]:  # Show first 10
            print(f"\n  Transaction: {r.transaction}")
            print(f"  Matched to: {r.email.subject if r.email else 'N/A'}")
            print(f"  Reasoning: {r.reasoning[:100]}...")

    # List unmatched items
    if results["no_match"]:
        print("\n" + "-" * 60)
        print("UNMATCHED TRANSACTIONS (first 10)")
        print("-" * 60)
        for r in results["no_match"][:10]:
            print(f"\n  {r.transaction}")
            print(f"  Reason: {r.reasoning[:100]}...")

    print("\n" + "=" * 60)
    print("PROCESS COMPLETE")
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    return True


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Automatically find receipts in Gmail for tax-deductible transactions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run.py --dry-run          # Test setup without processing
    python run.py --single 10        # Process only row 10
    python run.py --limit 5          # Process first 5 transactions
    python run.py --category Software  # Process only Software category
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test transaction parsing and Gmail auth without processing",
    )

    parser.add_argument(
        "--single",
        type=int,
        metavar="ROW",
        help="Process only the transaction at the specified CSV row number",
    )

    parser.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help="Process only the first N transactions",
    )

    parser.add_argument(
        "--category",
        type=str,
        metavar="NAME",
        help="Process only transactions in the specified category",
    )

    args = parser.parse_args()

    if args.dry_run:
        success = run_dry_run()
    else:
        success = run_full(
            single_row=args.single,
            limit=args.limit,
            category_filter=args.category,
        )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
