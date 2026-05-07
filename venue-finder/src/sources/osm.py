"""OpenStreetMap Overpass API source.

Queries the Overpass API for each archetype's tag combinations within the
configured bbox, and emits Venue records.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests
import yaml

from config import (
    HTTP_USER_AGENT,
    OVERPASS_TIMEOUT,
    OVERPASS_URL,
    PARIS_BBOX,
    RAW_DIR,
    TAXONOMY_FILE,
)
from src.venue import Venue

logger = logging.getLogger(__name__)


def load_taxonomy() -> dict:
    with open(TAXONOMY_FILE) as f:
        return yaml.safe_load(f)["archetypes"]


def build_overpass_query(filters: list[str], bbox: dict) -> str:
    """Compose an Overpass QL query for one archetype's filters.

    `nwr` matches nodes, ways and relations; `out center tags;` returns a
    single representative point per element with its tags.
    """
    bbox_str = f"({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']})"
    body = "\n".join(f"  nwr{f}{bbox_str};" for f in filters)
    return f"[out:json][timeout:{OVERPASS_TIMEOUT}];\n(\n{body}\n);\nout center tags;"


def query_overpass(query: str, max_retries: int = 3) -> dict:
    """Post a query to Overpass with retry on 429/504."""
    headers = {"User-Agent": HTTP_USER_AGENT}
    for attempt in range(max_retries):
        resp = requests.post(
            OVERPASS_URL, data={"data": query}, headers=headers,
            timeout=OVERPASS_TIMEOUT + 30,
        )
        if resp.status_code in (429, 504, 502) and attempt < max_retries - 1:
            backoff = 5 * (2 ** attempt)
            logger.warning("Overpass %d, retrying in %ds", resp.status_code, backoff)
            time.sleep(backoff)
            continue
        resp.raise_for_status()
        return resp.json()
    raise requests.HTTPError("Overpass retries exhausted")


def element_to_venue(element: dict, archetype: str, tier: str) -> Venue | None:
    tags = element.get("tags", {})
    name = tags.get("name") or tags.get("operator") or tags.get("brand")
    if not name:
        return None  # unnamed nodes are not actionable for outreach

    if "lat" in element and "lon" in element:
        lat, lon = element["lat"], element["lon"]
    elif "center" in element:
        lat, lon = element["center"]["lat"], element["center"]["lon"]
    else:
        lat = lon = None

    addr_parts = [
        tags.get("addr:housenumber", ""),
        tags.get("addr:street", ""),
    ]
    address = " ".join(p for p in addr_parts if p).strip()

    return Venue(
        name=name,
        archetype=archetype,
        tier=tier,
        source="osm",
        source_id=f"osm:{element['type']}/{element['id']}",
        lat=lat,
        lon=lon,
        address=address,
        commune=tags.get("addr:city", ""),
        postcode=tags.get("addr:postcode", ""),
        phone=tags.get("phone") or tags.get("contact:phone", ""),
        email=tags.get("email") or tags.get("contact:email", ""),
        website=tags.get("website") or tags.get("contact:website", ""),
        description=tags.get("description", ""),
        raw_tags=tags,
        sources=["osm"],
    )


def fetch_archetype(archetype: str, spec: dict, bbox: dict) -> list[Venue]:
    query = build_overpass_query(spec["osm_filters"], bbox)
    logger.info("Overpass: querying archetype=%s", archetype)
    data = query_overpass(query)
    venues = []
    for el in data.get("elements", []):
        v = element_to_venue(el, archetype=archetype, tier=spec["tier"])
        if v:
            venues.append(v)
    logger.info("  -> %d venues from %d elements", len(venues), len(data.get("elements", [])))
    return venues


def fetch_all(
    bbox: dict | None = None,
    archetypes_filter: list[str] | None = None,
    sleep_between: float = 3.0,
) -> list[Venue]:
    """Run Overpass for every archetype (or a filtered subset) and return all venues."""
    bbox = bbox or PARIS_BBOX
    taxonomy = load_taxonomy()

    if archetypes_filter:
        taxonomy = {k: v for k, v in taxonomy.items() if k in archetypes_filter}

    out_path = RAW_DIR / "osm.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    all_venues: list[Venue] = []
    with open(out_path, "w") as f:
        for archetype, spec in taxonomy.items():
            try:
                venues = fetch_archetype(archetype, spec, bbox)
            except requests.HTTPError as e:
                logger.error("Overpass error for %s: %s", archetype, e)
                continue
            for v in venues:
                f.write(json.dumps(v.to_dict(), ensure_ascii=False) + "\n")
            all_venues.extend(venues)
            if sleep_between:
                time.sleep(sleep_between)  # be polite to the public Overpass instance

    logger.info("Wrote %d venues to %s", len(all_venues), out_path)
    return all_venues


def load_cached(path: Path | None = None) -> list[Venue]:
    path = path or (RAW_DIR / "osm.jsonl")
    if not path.exists():
        return []
    with open(path) as f:
        return [Venue.from_dict(json.loads(line)) for line in f if line.strip()]
