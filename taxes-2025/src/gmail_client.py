"""
Gmail Client - Wrapper for Gmail API with multi-account support.
"""

import base64
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    CREDENTIALS_FILE,
    EMAIL_ACCOUNTS,
    GMAIL_SCOPES,
    DATE_RANGE_DAYS,
)


@dataclass
class EmailAttachment:
    """Represents an email attachment."""

    filename: str
    mime_type: str
    attachment_id: str
    size: int = 0
    data: Optional[bytes] = None


@dataclass
class Email:
    """Represents an email message."""

    message_id: str
    thread_id: str
    subject: str
    sender: str
    date: datetime
    snippet: str
    body_plain: str = ""
    body_html: str = ""
    attachments: list[EmailAttachment] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    account_email: str = ""

    def has_pdf_attachment(self) -> bool:
        """Check if email has any PDF attachments."""
        return any(
            att.mime_type == "application/pdf" or att.filename.lower().endswith(".pdf")
            for att in self.attachments
        )


class GmailClient:
    """Gmail API client with support for multiple accounts."""

    def __init__(
        self,
        credentials_file: Optional[Path] = None,
        accounts: Optional[list[dict]] = None,
    ):
        """
        Initialize the Gmail client.

        Args:
            credentials_file: Path to OAuth credentials JSON file.
            accounts: List of account configs with 'email' and 'token_file' keys.
        """
        self.credentials_file = credentials_file or CREDENTIALS_FILE
        self.accounts = accounts or EMAIL_ACCOUNTS
        self._services: dict[str, any] = {}  # Cache of authenticated services

    def authenticate(self, account_index: int = 0) -> bool:
        """
        Authenticate with a specific Gmail account.

        Args:
            account_index: Index of the account in the accounts list.

        Returns:
            True if authentication successful.
        """
        if account_index >= len(self.accounts):
            raise ValueError(f"Invalid account index: {account_index}")

        account = self.accounts[account_index]
        email = account["email"]
        token_file = Path(account["token_file"])

        creds = None

        # Load existing token if available
        if token_file.exists():
            creds = Credentials.from_authorized_user_file(str(token_file), GMAIL_SCOPES)

        # Refresh or get new credentials if needed
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_file.exists():
                    raise FileNotFoundError(
                        f"OAuth credentials file not found: {self.credentials_file}\n"
                        "Please download it from Google Cloud Console."
                    )

                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_file), GMAIL_SCOPES
                )
                print(f"\nAuthenticating {email}...")
                print("A browser window will open for authentication.")
                creds = flow.run_local_server(port=0)

            # Save the credentials for next run
            token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(token_file, "w") as f:
                f.write(creds.to_json())

        # Build the service
        service = build("gmail", "v1", credentials=creds)
        self._services[email] = service
        return True

    def authenticate_all(self) -> dict[str, bool]:
        """
        Authenticate all configured accounts.

        Returns:
            Dict mapping email addresses to authentication success status.
        """
        results = {}
        for i, account in enumerate(self.accounts):
            email = account["email"]
            try:
                results[email] = self.authenticate(i)
            except Exception as e:
                print(f"Failed to authenticate {email}: {e}")
                results[email] = False
        return results

    def _get_service(self, email: str):
        """Get the authenticated service for an email account."""
        if email not in self._services:
            # Try to authenticate
            for i, account in enumerate(self.accounts):
                if account["email"] == email:
                    self.authenticate(i)
                    break

        if email not in self._services:
            raise ValueError(f"No authenticated service for {email}")

        return self._services[email]

    def build_search_query(
        self,
        keywords: list[str],
        date_center: datetime,
        date_range_days: int = DATE_RANGE_DAYS,
        sender: Optional[str] = None,
    ) -> str:
        """
        Build a Gmail search query.

        Args:
            keywords: List of keywords to search for.
            date_center: Center date for the search window.
            date_range_days: Number of days before/after the center date.
            sender: Optional sender email to filter by.

        Returns:
            Gmail search query string.
        """
        # Date range
        start_date = date_center - timedelta(days=date_range_days)
        end_date = date_center + timedelta(days=date_range_days)

        query_parts = [
            f"after:{start_date.strftime('%Y/%m/%d')}",
            f"before:{end_date.strftime('%Y/%m/%d')}",
        ]

        # Keywords (OR together, wrap in quotes if spaces)
        if keywords:
            keyword_parts = []
            for kw in keywords:
                if " " in kw:
                    keyword_parts.append(f'"{kw}"')
                else:
                    keyword_parts.append(kw)
            query_parts.append(f"({' OR '.join(keyword_parts)})")

        # Sender filter
        if sender:
            query_parts.append(f"from:{sender}")

        # Common receipt-related terms
        query_parts.append("(receipt OR invoice OR order OR confirmation OR payment)")

        return " ".join(query_parts)

    def search_emails(
        self,
        email: str,
        query: str,
        max_results: int = 20,
    ) -> list[Email]:
        """
        Search for emails matching a query.

        Args:
            email: Email account to search.
            query: Gmail search query string.
            max_results: Maximum number of results to return.

        Returns:
            List of Email objects matching the query.
        """
        service = self._get_service(email)
        emails = []

        try:
            # Search for messages
            results = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )

            messages = results.get("messages", [])

            # Handle pagination if needed
            while "nextPageToken" in results and len(messages) < max_results:
                results = (
                    service.users()
                    .messages()
                    .list(
                        userId="me",
                        q=query,
                        maxResults=max_results - len(messages),
                        pageToken=results["nextPageToken"],
                    )
                    .execute()
                )
                messages.extend(results.get("messages", []))

            # Fetch full message details
            for msg in messages[:max_results]:
                email_obj = self.get_email(email, msg["id"])
                if email_obj:
                    emails.append(email_obj)

        except HttpError as e:
            print(f"Error searching emails in {email}: {e}")

        return emails

    def get_email(self, email: str, message_id: str) -> Optional[Email]:
        """
        Get full details of a specific email.

        Args:
            email: Email account.
            message_id: Gmail message ID.

        Returns:
            Email object or None if not found.
        """
        service = self._get_service(email)

        try:
            message = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

            # Parse headers
            headers = {h["name"].lower(): h["value"] for h in message["payload"]["headers"]}

            # Parse date
            date_str = headers.get("date", "")
            try:
                from email.utils import parsedate_to_datetime
                date = parsedate_to_datetime(date_str)
            except (ValueError, TypeError):
                date = datetime.now()

            # Extract body and attachments
            body_plain, body_html, attachments = self._parse_payload(
                service, message["payload"], message_id
            )

            return Email(
                message_id=message_id,
                thread_id=message.get("threadId", ""),
                subject=headers.get("subject", "(No Subject)"),
                sender=headers.get("from", ""),
                date=date,
                snippet=message.get("snippet", ""),
                body_plain=body_plain,
                body_html=body_html,
                attachments=attachments,
                labels=message.get("labelIds", []),
                account_email=email,
            )

        except HttpError as e:
            print(f"Error fetching email {message_id}: {e}")
            return None

    def _parse_payload(
        self, service, payload: dict, message_id: str
    ) -> tuple[str, str, list[EmailAttachment]]:
        """
        Parse email payload to extract body and attachments.

        Returns:
            Tuple of (plain_text_body, html_body, attachments_list)
        """
        body_plain = ""
        body_html = ""
        attachments = []

        def process_part(part):
            nonlocal body_plain, body_html

            mime_type = part.get("mimeType", "")
            body = part.get("body", {})
            filename = part.get("filename", "")

            # Check if this is an attachment
            if filename and body.get("attachmentId"):
                attachments.append(
                    EmailAttachment(
                        filename=filename,
                        mime_type=mime_type,
                        attachment_id=body["attachmentId"],
                        size=body.get("size", 0),
                    )
                )
            elif mime_type == "text/plain" and body.get("data"):
                body_plain = base64.urlsafe_b64decode(body["data"]).decode("utf-8", errors="ignore")
            elif mime_type == "text/html" and body.get("data"):
                body_html = base64.urlsafe_b64decode(body["data"]).decode("utf-8", errors="ignore")
            elif "parts" in part:
                for subpart in part["parts"]:
                    process_part(subpart)

        # Handle different payload structures
        if "parts" in payload:
            for part in payload["parts"]:
                process_part(part)
        else:
            process_part(payload)

        return body_plain, body_html, attachments

    def download_attachment(
        self, email: str, message_id: str, attachment_id: str
    ) -> Optional[bytes]:
        """
        Download an attachment from an email.

        Args:
            email: Email account.
            message_id: Gmail message ID.
            attachment_id: Attachment ID.

        Returns:
            Attachment data as bytes, or None if failed.
        """
        service = self._get_service(email)

        try:
            attachment = (
                service.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=message_id, id=attachment_id)
                .execute()
            )

            data = attachment.get("data", "")
            return base64.urlsafe_b64decode(data)

        except HttpError as e:
            print(f"Error downloading attachment: {e}")
            return None

    def search_all_accounts(
        self,
        query: str,
        max_results_per_account: int = 10,
    ) -> list[Email]:
        """
        Search for emails across all authenticated accounts.

        Args:
            query: Gmail search query string.
            max_results_per_account: Maximum results per account.

        Returns:
            List of Email objects from all accounts.
        """
        all_emails = []

        for email in self._services.keys():
            emails = self.search_emails(email, query, max_results_per_account)
            all_emails.extend(emails)

        # Sort by date (most recent first)
        all_emails.sort(key=lambda e: e.date, reverse=True)

        return all_emails


if __name__ == "__main__":
    # Test the Gmail client
    client = GmailClient()

    print("Gmail Client Test")
    print("-" * 40)

    # Check for credentials
    if not CREDENTIALS_FILE.exists():
        print(f"Error: credentials.json not found at {CREDENTIALS_FILE}")
        print("\nTo set up Gmail API access:")
        print("1. Go to Google Cloud Console")
        print("2. Create a project and enable Gmail API")
        print("3. Create OAuth 2.0 credentials (Desktop app)")
        print("4. Download and save as credentials.json")
        exit(1)

    # Try to authenticate
    print("\nAttempting to authenticate...")
    results = client.authenticate_all()

    for email, success in results.items():
        status = "OK" if success else "FAILED"
        print(f"  {email}: {status}")

    # Test search if any account authenticated
    authenticated = [e for e, s in results.items() if s]
    if authenticated:
        print(f"\nTesting search on {authenticated[0]}...")
        query = client.build_search_query(
            keywords=["receipt"],
            date_center=datetime.now(),
            date_range_days=30,
        )
        print(f"Query: {query}")

        emails = client.search_emails(authenticated[0], query, max_results=5)
        print(f"Found {len(emails)} emails")

        for email in emails[:3]:
            print(f"\n  Subject: {email.subject}")
            print(f"  From: {email.sender}")
            print(f"  Date: {email.date}")
            print(f"  Attachments: {len(email.attachments)}")
