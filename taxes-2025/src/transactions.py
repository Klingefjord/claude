"""
Transaction Parser - Load and filter tax-deductible transactions from CSV.
"""

import pandas as pd
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DEDUCTIBLE_CATEGORIES, TRANSACTIONS_FILE


@dataclass
class Transaction:
    """Represents a single transaction that needs a receipt."""

    date: datetime
    description: str
    amount: float
    currency: str
    category: str
    original_row: int
    has_receipt: bool = False
    merchant_name: Optional[str] = None

    def __post_init__(self):
        """Extract merchant name from description."""
        if self.merchant_name is None:
            self.merchant_name = self._extract_merchant_name()

    def _extract_merchant_name(self) -> str:
        """
        Extract a likely merchant name from the transaction description.
        This handles common patterns in bank transaction descriptions.
        """
        desc = self.description

        # Remove common prefixes
        prefixes_to_remove = [
            "PURCHASE AUTHORISED",
            "PURCHASE AUTHORIZED",
            "CARD PAYMENT TO",
            "CARD PURCHASE",
            "PAYMENT TO",
            "DIRECT DEBIT TO",
            "DIRECT DEBIT",
            "DEBIT CARD",
            "POS ",
            "PAYPAL *",
            "PAYPAL*",
            "SQ *",
            "TST* ",
        ]

        for prefix in prefixes_to_remove:
            if desc.upper().startswith(prefix.upper()):
                desc = desc[len(prefix) :].strip()
                break

        # Remove trailing reference numbers and dates
        # Common patterns: numbers at end, dates in various formats
        import re

        # Remove card numbers and reference IDs
        desc = re.sub(r"\s+\d{4,}$", "", desc)
        desc = re.sub(r"\s+REF:?\s*\S+$", "", desc, flags=re.IGNORECASE)

        # Remove dates at end (DD/MM/YYYY, MM/DD/YYYY, etc.)
        desc = re.sub(r"\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$", "", desc)

        # Remove location suffixes (city, state, country codes)
        desc = re.sub(r"\s+[A-Z]{2,3}\s*$", "", desc)

        # Take first part if there are multiple segments separated by special chars
        if " - " in desc:
            desc = desc.split(" - ")[0]

        return desc.strip() or self.description

    @property
    def search_keywords(self) -> list[str]:
        """Generate keywords for Gmail search."""
        keywords = [self.merchant_name]

        # Add amount as keyword (various formats)
        amount_str = f"{self.amount:.2f}"
        keywords.append(amount_str)

        # Without decimal for round amounts
        if self.amount == int(self.amount):
            keywords.append(str(int(self.amount)))

        return keywords

    def __str__(self) -> str:
        return (
            f"{self.date.strftime('%Y-%m-%d')} | {self.merchant_name} | "
            f"{self.currency} {self.amount:.2f} | {self.category}"
        )


class TransactionParser:
    """Parse and filter transactions from the taxes CSV file."""

    def __init__(self, csv_path: Optional[Path] = None):
        """
        Initialize the parser.

        Args:
            csv_path: Path to the CSV file. Defaults to config.TRANSACTIONS_FILE.
        """
        self.csv_path = csv_path or TRANSACTIONS_FILE

    def load_all_transactions(self) -> pd.DataFrame:
        """Load the raw CSV file into a DataFrame."""
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Transactions file not found: {self.csv_path}")

        df = pd.read_csv(self.csv_path)
        return df

    def get_deductible_transactions(self) -> list[Transaction]:
        """
        Load and filter to only tax-deductible transactions that need receipts.

        Returns:
            List of Transaction objects for deductible items without receipts.
        """
        df = self.load_all_transactions()

        # Expected column names (adjust based on actual CSV structure)
        # Common variations handled below
        date_col = self._find_column(df, ["Date", "Transaction Date", "date"])
        desc_col = self._find_column(
            df, ["Description", "Merchant", "description", "Name"]
        )
        amount_col = self._find_column(df, ["Amount", "amount", "Value"])
        currency_col = self._find_column(
            df, ["Currency", "currency", "Ccy"], required=False
        )
        category_col = self._find_column(
            df, ["Tax Deductible Category", "Category", "category", "Tax Category"]
        )
        receipt_col = self._find_column(
            df,
            ["Has Invoice / Receipt", "Has Receipt", "Receipt", "has_receipt"],
            required=False,
        )

        transactions = []

        for idx, row in df.iterrows():
            # Check if tax deductible
            category = str(row[category_col]).strip() if pd.notna(row[category_col]) else "N/A"
            if category == "N/A" or category not in DEDUCTIBLE_CATEGORIES:
                continue

            # Check if already has receipt
            if receipt_col and pd.notna(row[receipt_col]):
                has_receipt = str(row[receipt_col]).upper() in ["TRUE", "YES", "1"]
                if has_receipt:
                    continue  # Skip - already has receipt

            # Parse date
            try:
                date = pd.to_datetime(row[date_col])
            except (ValueError, TypeError):
                print(f"Warning: Could not parse date for row {idx}: {row[date_col]}")
                continue

            # Parse amount
            try:
                amount = float(str(row[amount_col]).replace(",", "").replace("$", ""))
                amount = abs(amount)  # Ensure positive
            except (ValueError, TypeError):
                print(f"Warning: Could not parse amount for row {idx}: {row[amount_col]}")
                continue

            # Get currency (default to USD)
            currency = "USD"
            if currency_col and pd.notna(row[currency_col]):
                currency = str(row[currency_col]).upper()

            transaction = Transaction(
                date=date.to_pydatetime(),
                description=str(row[desc_col]),
                amount=amount,
                currency=currency,
                category=category,
                original_row=idx + 2,  # +2 for 1-indexed and header row
            )
            transactions.append(transaction)

        return transactions

    def _find_column(
        self, df: pd.DataFrame, candidates: list[str], required: bool = True
    ) -> Optional[str]:
        """
        Find a column name from a list of candidates.

        Args:
            df: DataFrame to search
            candidates: List of possible column names
            required: If True, raise error if not found

        Returns:
            The matching column name, or None if not found and not required.
        """
        for col in candidates:
            if col in df.columns:
                return col

        # Try case-insensitive matching
        df_cols_lower = {c.lower(): c for c in df.columns}
        for col in candidates:
            if col.lower() in df_cols_lower:
                return df_cols_lower[col.lower()]

        if required:
            raise ValueError(
                f"Could not find column. Tried: {candidates}. "
                f"Available columns: {list(df.columns)}"
            )
        return None

    def get_summary(self) -> dict:
        """Get a summary of transactions by category."""
        transactions = self.get_deductible_transactions()

        summary = {
            "total_transactions": len(transactions),
            "by_category": {},
            "total_amount": 0.0,
        }

        for txn in transactions:
            if txn.category not in summary["by_category"]:
                summary["by_category"][txn.category] = {"count": 0, "amount": 0.0}
            summary["by_category"][txn.category]["count"] += 1
            summary["by_category"][txn.category]["amount"] += txn.amount
            summary["total_amount"] += txn.amount

        return summary


if __name__ == "__main__":
    # Test the parser
    parser = TransactionParser()
    try:
        transactions = parser.get_deductible_transactions()
        print(f"Found {len(transactions)} deductible transactions needing receipts\n")

        summary = parser.get_summary()
        print("Summary by category:")
        for category, data in summary["by_category"].items():
            print(f"  {category}: {data['count']} transactions, ${data['amount']:.2f}")

        print(f"\nTotal: ${summary['total_amount']:.2f}")

        if transactions:
            print("\nFirst 5 transactions:")
            for txn in transactions[:5]:
                print(f"  {txn}")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Please ensure taxes.csv exists in the project root.")
