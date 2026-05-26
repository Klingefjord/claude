#!/usr/bin/env python3
"""
Sync engagement-type classifications from The_Network_Classified.csv
back into the Notion 'The Network' database.

Reads NOTION_TOKEN and THE_NETWORK_ID from .env.
Matches rows by Name, updates the 'Engagement Type' select property.
"""

import csv
import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"
CSV_PATH = Path(__file__).parent / "The_Network_Classified.csv"

ENGAGEMENT_DISPLAY = {
    "honorarium-commission": "Honorarium commission",
    "advisory": "Advisory",
    "buyout-or-sabbatical": "Buyout / sabbatical",
    "embedded-postdoc": "Embedded postdoc",
    "convene-only": "Convene-only",
    "internal": "Internal",
}


def load_env():
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def notion_request(method, path, body=None):
    token = os.environ["NOTION_TOKEN"]
    url = f"https://api.notion.com/v1{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Notion-Version", "2022-06-28")
    req.add_header("Content-Type", "application/json")

    for attempt in range(5):
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 2 ** attempt
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            body_text = e.read().decode() if e.fp else ""
            raise RuntimeError(f"Notion API {e.code}: {body_text}") from e
    raise RuntimeError("Too many retries")


def fetch_all_pages(database_id):
    """Fetch all pages from the database, handling pagination."""
    pages = []
    start_cursor = None
    while True:
        body = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor
        result = notion_request("POST", f"/databases/{database_id}/query", body)
        pages.extend(result["results"])
        if not result.get("has_more"):
            break
        start_cursor = result["next_cursor"]
    return pages


def get_page_name(page):
    title_prop = page["properties"].get("Name", {}).get("title", [])
    if title_prop:
        return title_prop[0]["plain_text"].strip()
    return ""


def main():
    load_env()
    database_id = os.environ["THE_NETWORK_ID"]

    # Load classifications from CSV
    classifications = {}
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row.get("Name", "").strip()
            eng = row.get("Engagement Type", "").strip()
            if name and eng:
                classifications[name.lower()] = eng

    print(f"Loaded {len(classifications)} classifications from CSV")

    # Fetch all pages from Notion
    print("Fetching pages from Notion...")
    pages = fetch_all_pages(database_id)
    print(f"Found {len(pages)} pages in Notion")

    # Match and update
    updated = 0
    skipped = 0
    not_found = 0

    for page in pages:
        name = get_page_name(page)
        if not name:
            skipped += 1
            continue

        eng_key = classifications.get(name.lower())
        if not eng_key:
            print(f"  No classification for: {name}")
            not_found += 1
            continue

        display_name = ENGAGEMENT_DISPLAY.get(eng_key, eng_key)

        notion_request("PATCH", f"/pages/{page['id']}", {
            "properties": {
                "Engagement Type": {
                    "select": {"name": display_name}
                }
            }
        })

        print(f"  ✓ {name:<30} → {display_name}")
        updated += 1
        time.sleep(0.35)  # stay under rate limit

    print(f"\nDone: {updated} updated, {skipped} skipped (empty), {not_found} not in CSV")


if __name__ == "__main__":
    main()
