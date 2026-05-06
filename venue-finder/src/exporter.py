"""Export the top-N ranked venues to a CSV ready for outreach."""

from __future__ import annotations

import csv
import logging

from config import EXPORT_CSV, TOP_N
from src.score import ranked_score
from src.venue import Venue

logger = logging.getLogger(__name__)

CSV_FIELDS = [
    "rank", "name", "archetype", "tier", "fit_score", "ranked_score",
    "commune", "postcode", "address", "lat", "lon",
    "phone", "email", "website",
    "reasoning", "sources", "source_id",
]


def export_top(venues: list[Venue], top_n: int = TOP_N, path=EXPORT_CSV) -> int:
    ranked = sorted(
        (v for v in venues if v.fit_score is not None),
        key=ranked_score,
        reverse=True,
    )
    take = ranked[:top_n]

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for i, v in enumerate(take, 1):
            writer.writerow({
                "rank": i,
                "name": v.name,
                "archetype": v.archetype,
                "tier": v.tier,
                "fit_score": f"{v.fit_score:.1f}",
                "ranked_score": f"{ranked_score(v):.2f}",
                "commune": v.commune,
                "postcode": v.postcode,
                "address": v.address,
                "lat": v.lat or "",
                "lon": v.lon or "",
                "phone": v.phone,
                "email": v.email,
                "website": v.website,
                "reasoning": v.reasoning,
                "sources": ",".join(v.sources),
                "source_id": v.source_id,
            })

    logger.info("Exported top %d venues to %s", len(take), path)
    return len(take)


def coverage_summary(venues: list[Venue]) -> dict:
    total = len(venues)
    if not total:
        return {"total": 0}
    return {
        "total": total,
        "with_phone": sum(1 for v in venues if v.phone),
        "with_email": sum(1 for v in venues if v.email),
        "with_website": sum(1 for v in venues if v.website),
        "by_tier": {
            t: sum(1 for v in venues if v.tier == t) for t in ("A", "B", "C", "D")
        },
    }
