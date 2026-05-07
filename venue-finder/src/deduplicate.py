"""Deduplicate venues across sources by name + geographic proximity."""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict

from rapidfuzz import fuzz

from config import DEDUPED_JSONL
from src.venue import Venue

logger = logging.getLogger(__name__)

NAME_MATCH_THRESHOLD = 85   # rapidfuzz token_set_ratio
GEO_MATCH_RADIUS_M = 150    # within this many meters, names that match merge


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _completeness(v: Venue) -> int:
    """Pick the more-filled record as canonical when merging."""
    return sum(
        bool(getattr(v, f))
        for f in ("address", "phone", "email", "website", "description", "commune")
    )


def _merge(a: Venue, b: Venue) -> Venue:
    """Merge b into a, keeping a's identity but filling blank fields from b."""
    keeper = a if _completeness(a) >= _completeness(b) else b
    other = b if keeper is a else a
    for fld in ("address", "commune", "postcode", "phone", "email", "website", "description"):
        if not getattr(keeper, fld) and getattr(other, fld):
            setattr(keeper, fld, getattr(other, fld))
    keeper.sources = sorted(set(keeper.sources + other.sources))
    return keeper


def deduplicate(venues: list[Venue]) -> list[Venue]:
    """Group by commune (rough bucket), then within each bucket merge near-duplicates."""
    buckets: dict[str, list[Venue]] = defaultdict(list)
    for v in venues:
        # Bucket by 0.05° grid cell to limit O(n²) comparisons
        if v.lat is not None and v.lon is not None:
            key = f"{round(v.lat / 0.05) * 0.05:.2f},{round(v.lon / 0.05) * 0.05:.2f}"
        else:
            key = f"_noxy:{v.commune}"
        buckets[key].append(v)

    merged: list[Venue] = []
    for bucket in buckets.values():
        canonical: list[Venue] = []
        for v in bucket:
            best_idx = -1
            best_score = 0
            for i, c in enumerate(canonical):
                if v.lat is None or c.lat is None:
                    continue
                if _haversine_m((v.lat, v.lon), (c.lat, c.lon)) > GEO_MATCH_RADIUS_M:
                    continue
                score = fuzz.token_set_ratio(v.name.lower(), c.name.lower())
                if score >= NAME_MATCH_THRESHOLD and score > best_score:
                    best_idx, best_score = i, score
            if best_idx >= 0:
                canonical[best_idx] = _merge(canonical[best_idx], v)
            else:
                canonical.append(v)
        merged.extend(canonical)

    logger.info("Deduplicated %d -> %d venues", len(venues), len(merged))
    return merged


def write_jsonl(venues: list[Venue], path=DEDUPED_JSONL) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for v in venues:
            f.write(json.dumps(v.to_dict(), ensure_ascii=False) + "\n")


def load_jsonl(path=DEDUPED_JSONL) -> list[Venue]:
    if not path.exists():
        return []
    with open(path) as f:
        return [Venue.from_dict(json.loads(line)) for line in f if line.strip()]
