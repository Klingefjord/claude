"""
Receipt Exporter - Save emails as PDFs or download attachments.
"""

import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional

from weasyprint import HTML, CSS
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import MATCHED_DIR, MANUAL_REVIEW_DIR
from src.gmail_client import Email, GmailClient
from src.transactions import Transaction
from src.receipt_matcher import MatchResult, MatchConfidence


class ReceiptExporter:
    """Export matched receipts as PDFs or download attachments."""

    def __init__(
        self,
        gmail_client: GmailClient,
        matched_dir: Optional[Path] = None,
        manual_review_dir: Optional[Path] = None,
    ):
        """
        Initialize the exporter.

        Args:
            gmail_client: Authenticated GmailClient instance.
            matched_dir: Directory for high-confidence matches.
            manual_review_dir: Directory for matches needing review.
        """
        self.gmail_client = gmail_client
        self.matched_dir = matched_dir or MATCHED_DIR
        self.manual_review_dir = manual_review_dir or MANUAL_REVIEW_DIR

        # Ensure directories exist
        self.matched_dir.mkdir(parents=True, exist_ok=True)
        self.manual_review_dir.mkdir(parents=True, exist_ok=True)

    def export_match(self, match_result: MatchResult) -> Optional[Path]:
        """
        Export a matched receipt.

        Args:
            match_result: The match result to export.

        Returns:
            Path to the exported file, or None if export failed.
        """
        if not match_result.email:
            return None

        # Determine output directory based on confidence
        if match_result.confidence == MatchConfidence.HIGH:
            output_dir = self.matched_dir
        else:
            output_dir = self.manual_review_dir

        # Generate filename
        filename = self._generate_filename(
            match_result.transaction, match_result.email
        )

        # Try to download PDF attachment first
        if match_result.email.has_pdf_attachment():
            path = self._export_pdf_attachment(
                match_result.email, output_dir, filename
            )
            if path:
                return path

        # Fall back to converting email to PDF
        return self._export_email_as_pdf(match_result.email, output_dir, filename)

    def _generate_filename(self, transaction: Transaction, email: Email) -> str:
        """
        Generate a standardized filename for the receipt.

        Format: {date}_{merchant}_{amount}.pdf
        """
        date_str = transaction.date.strftime("%Y-%m-%d")

        # Clean merchant name for filename
        merchant = self._sanitize_filename(transaction.merchant_name)
        merchant = merchant[:50]  # Limit length

        amount_str = f"{transaction.amount:.2f}".replace(".", "_")

        return f"{date_str}_{merchant}_{amount_str}"

    def _sanitize_filename(self, name: str) -> str:
        """
        Sanitize a string for use as a filename.
        """
        # Normalize unicode characters
        name = unicodedata.normalize("NFKD", name)
        name = name.encode("ascii", "ignore").decode("ascii")

        # Replace spaces and special characters
        name = re.sub(r"[^\w\s-]", "", name)
        name = re.sub(r"[-\s]+", "_", name)

        return name.strip("_")

    def _export_pdf_attachment(
        self, email: Email, output_dir: Path, base_filename: str
    ) -> Optional[Path]:
        """
        Download and save a PDF attachment from an email.
        """
        for attachment in email.attachments:
            if (
                attachment.mime_type == "application/pdf"
                or attachment.filename.lower().endswith(".pdf")
            ):
                # Download the attachment
                data = self.gmail_client.download_attachment(
                    email.account_email,
                    email.message_id,
                    attachment.attachment_id,
                )

                if data:
                    output_path = output_dir / f"{base_filename}.pdf"

                    # Handle duplicate filenames
                    counter = 1
                    while output_path.exists():
                        output_path = output_dir / f"{base_filename}_{counter}.pdf"
                        counter += 1

                    with open(output_path, "wb") as f:
                        f.write(data)

                    return output_path

        return None

    def _export_email_as_pdf(
        self, email: Email, output_dir: Path, base_filename: str
    ) -> Optional[Path]:
        """
        Convert an email to PDF using WeasyPrint.
        """
        try:
            # Get HTML content (or convert plain text)
            if email.body_html:
                html_content = self._prepare_html(email)
            else:
                html_content = self._plain_to_html(email)

            output_path = output_dir / f"{base_filename}.pdf"

            # Handle duplicate filenames
            counter = 1
            while output_path.exists():
                output_path = output_dir / f"{base_filename}_{counter}.pdf"
                counter += 1

            # Convert to PDF
            html = HTML(string=html_content)
            css = CSS(
                string="""
                @page {
                    size: A4;
                    margin: 1cm;
                }
                body {
                    font-family: Arial, sans-serif;
                    font-size: 12px;
                    line-height: 1.4;
                }
                .email-header {
                    background-color: #f5f5f5;
                    padding: 10px;
                    margin-bottom: 20px;
                    border-bottom: 2px solid #ddd;
                }
                .email-header p {
                    margin: 5px 0;
                }
                .email-body {
                    padding: 10px;
                }
                img {
                    max-width: 100%;
                    height: auto;
                }
            """
            )

            html.write_pdf(str(output_path), stylesheets=[css])
            return output_path

        except Exception as e:
            print(f"Error converting email to PDF: {e}")
            return None

    def _prepare_html(self, email: Email) -> str:
        """
        Prepare email HTML for PDF conversion.
        """
        # Parse and clean the HTML
        soup = BeautifulSoup(email.body_html, "lxml")

        # Remove scripts and styles that might cause issues
        for tag in soup.find_all(["script", "style", "meta", "link"]):
            tag.decompose()

        # Add email header
        header_html = f"""
        <div class="email-header">
            <p><strong>From:</strong> {email.sender}</p>
            <p><strong>Subject:</strong> {email.subject}</p>
            <p><strong>Date:</strong> {email.date.strftime('%Y-%m-%d %H:%M')}</p>
        </div>
        """

        # Wrap in full HTML document
        body_content = str(soup.body) if soup.body else str(soup)

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{email.subject}</title>
        </head>
        <body>
            {header_html}
            <div class="email-body">
                {body_content}
            </div>
        </body>
        </html>
        """

        return html

    def _plain_to_html(self, email: Email) -> str:
        """
        Convert plain text email to HTML.
        """
        # Escape HTML characters
        import html

        body = html.escape(email.body_plain)

        # Convert line breaks to <br>
        body = body.replace("\n", "<br>\n")

        # Convert URLs to links
        url_pattern = r"(https?://[^\s<>\"]+)"
        body = re.sub(url_pattern, r'<a href="\1">\1</a>', body)

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{html.escape(email.subject)}</title>
        </head>
        <body>
            <div class="email-header">
                <p><strong>From:</strong> {html.escape(email.sender)}</p>
                <p><strong>Subject:</strong> {html.escape(email.subject)}</p>
                <p><strong>Date:</strong> {email.date.strftime('%Y-%m-%d %H:%M')}</p>
            </div>
            <div class="email-body">
                {body}
            </div>
        </body>
        </html>
        """

    def export_batch(
        self, match_results: list[MatchResult], progress_callback=None
    ) -> dict:
        """
        Export multiple match results.

        Args:
            match_results: List of match results to export.
            progress_callback: Optional callback(current, total) for progress updates.

        Returns:
            Summary dict with counts and paths.
        """
        summary = {
            "exported_high": [],
            "exported_review": [],
            "failed": [],
            "skipped": [],
        }

        exportable = [r for r in match_results if r.should_export()]

        for i, result in enumerate(exportable):
            if progress_callback:
                progress_callback(i + 1, len(exportable))

            path = self.export_match(result)

            if path:
                if result.confidence == MatchConfidence.HIGH:
                    summary["exported_high"].append(
                        {"path": path, "transaction": str(result.transaction)}
                    )
                else:
                    summary["exported_review"].append(
                        {
                            "path": path,
                            "transaction": str(result.transaction),
                            "reasoning": result.reasoning,
                        }
                    )
            else:
                summary["failed"].append(str(result.transaction))

        # Track skipped (no match or low confidence)
        for result in match_results:
            if not result.should_export():
                summary["skipped"].append(
                    {
                        "transaction": str(result.transaction),
                        "reason": result.reasoning,
                    }
                )

        return summary


if __name__ == "__main__":
    # Test the exporter
    print("Receipt Exporter Test")
    print("-" * 40)

    print(f"Matched directory: {MATCHED_DIR}")
    print(f"Manual review directory: {MANUAL_REVIEW_DIR}")

    # Check if directories exist
    print(f"\nMatched dir exists: {MATCHED_DIR.exists()}")
    print(f"Manual review dir exists: {MANUAL_REVIEW_DIR.exists()}")

    # Test filename sanitization
    exporter = ReceiptExporter.__new__(ReceiptExporter)
    test_names = [
        "GITHUB.COM",
        "Amazon Web Services",
        "Café Møcha",
        "Test/With:Special*Chars",
        "Very Long Merchant Name That Should Be Truncated For Filename Purposes",
    ]

    print("\nFilename sanitization tests:")
    for name in test_names:
        sanitized = exporter._sanitize_filename(name)
        print(f"  '{name}' -> '{sanitized}'")
