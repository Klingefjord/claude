"""Enrich venues that have a website but no phone/email by scraping the homepage
and a /contact page. Cached on disk so re-runs are free."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config import CACHE_DIR, HTTP_USER_AGENT
from src.venue import Venue

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# French phone: 01 23 45 67 89 / +33 1 23 45 67 89 / 0123456789
PHONE_RE = re.compile(
    r"(?:\+33[\s.\-]?|0)[1-9](?:[\s.\-]?\d{2}){4}"
)
CONTACT_PATHS = ["/contact", "/contact/", "/contactez-nous", "/nous-contacter", "/coordonnees"]
HTTP_TIMEOUT = 10


def _cache_path(url: str) -> Path:
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{h}.html"


def _fetch(url: str) -> str | None:
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    cache = _cache_path(url)
    if cache.exists():
        return cache.read_text(errors="replace")
    try:
        r = requests.get(
            url, headers={"User-Agent": HTTP_USER_AGENT}, timeout=HTTP_TIMEOUT, allow_redirects=True
        )
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(r.text)
            return r.text
    except (requests.RequestException, UnicodeError) as e:
        logger.debug("fetch failed for %s: %s", url, e)
    return None


def _extract_contacts(html: str) -> tuple[str | None, str | None]:
    soup = BeautifulSoup(html, "lxml")

    # Email: prefer mailto: links, fall back to regex on visible text
    email = None
    for a in soup.select("a[href^='mailto:']"):
        candidate = a["href"].replace("mailto:", "").split("?")[0].strip()
        if EMAIL_RE.fullmatch(candidate):
            email = candidate
            break
    if not email:
        text = soup.get_text(" ", strip=True)
        m = EMAIL_RE.search(text)
        if m:
            email = m.group(0)

    # Phone: prefer tel: links, fall back to regex
    phone = None
    for a in soup.select("a[href^='tel:']"):
        candidate = a["href"].replace("tel:", "").strip()
        if candidate:
            phone = candidate
            break
    if not phone:
        text = soup.get_text(" ", strip=True)
        m = PHONE_RE.search(text)
        if m:
            phone = m.group(0)

    return email, phone


def enrich_one(venue: Venue) -> Venue:
    if not venue.website:
        return venue
    if venue.email and venue.phone:
        return venue  # already complete

    base = venue.website
    if not base.startswith(("http://", "https://")):
        base = "http://" + base

    candidates = [base]
    parsed = urlparse(base)
    if parsed.netloc:
        for p in CONTACT_PATHS:
            candidates.append(urljoin(base, p))

    for url in candidates:
        html = _fetch(url)
        if not html:
            continue
        email, phone = _extract_contacts(html)
        if email and not venue.email:
            venue.email = email
        if phone and not venue.phone:
            venue.phone = phone
        if venue.email and venue.phone:
            break
    return venue


def enrich_all(venues: list[Venue], limit: int | None = None) -> list[Venue]:
    n_before = sum(1 for v in venues if v.email)
    targets = [v for v in venues if v.website and not (v.email and v.phone)]
    if limit:
        targets = targets[:limit]
    logger.info("Enriching %d venues with websites...", len(targets))
    for i, v in enumerate(targets, 1):
        enrich_one(v)
        if i % 50 == 0:
            logger.info("  enriched %d/%d", i, len(targets))
    n_after = sum(1 for v in venues if v.email)
    logger.info("Email coverage: %d -> %d (+%d)", n_before, n_after, n_after - n_before)
    return venues
