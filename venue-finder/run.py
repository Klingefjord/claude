#!/usr/bin/env python3
"""Venue finder for aerial rope-net leads near Paris.

Pipeline: OSM Overpass → deduplicate → enrich (website scrape) →
LLM-score (Claude Haiku) → rank → export top-N CSV.

Usage:
    python run.py                      # full run
    python run.py --dry-run            # smoke test on 5km Vincennes bbox
    python run.py --no-llm             # skip LLM scoring (rule-based fallback)
    python run.py --skip-fetch         # reuse cached OSM dump
    python run.py --skip-enrich        # skip website scraping
    python run.py --archetype camping  # one archetype only
    python run.py --top 100            # export top N (default 1000)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    DRY_RUN_BBOX,
    LOG_FILE,
    PARIS_BBOX,
    TOP_N,
    ensure_dirs,
    validate_config,
)
from src import deduplicate, enrich, exporter, score
from src.sources import osm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger("venue-finder")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="small bbox + limit; quick smoke test")
    parser.add_argument("--no-llm", action="store_true",
                        help="skip LLM scoring; use rule-based heuristic")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="reuse cached data/raw/osm.jsonl")
    parser.add_argument("--skip-enrich", action="store_true",
                        help="skip website scraping (much faster, less contact info)")
    parser.add_argument("--archetype", type=str, action="append",
                        help="limit to specific archetype(s); repeatable")
    parser.add_argument("--top", type=int, default=TOP_N,
                        help=f"export top N venues (default {TOP_N})")
    parser.add_argument("--enrich-limit", type=int, default=None,
                        help="cap number of websites to scrape (debug)")
    args = parser.parse_args()

    ensure_dirs()

    errors = validate_config(require_llm=not args.no_llm)
    if errors:
        for e in errors:
            logger.warning(e)
        if any("TAXONOMY" in e for e in errors):
            return 1

    bbox = DRY_RUN_BBOX if args.dry_run else PARIS_BBOX
    logger.info("=" * 60)
    logger.info("Venue Finder — %s", "DRY RUN" if args.dry_run else "FULL RUN")
    logger.info("bbox: S=%.2f W=%.2f N=%.2f E=%.2f",
                bbox["south"], bbox["west"], bbox["north"], bbox["east"])
    logger.info("=" * 60)

    # 1. Fetch
    if args.skip_fetch:
        venues = osm.load_cached()
        logger.info("Loaded %d cached venues from data/raw/osm.jsonl", len(venues))
    else:
        venues = osm.fetch_all(bbox=bbox, archetypes_filter=args.archetype)

    if not venues:
        logger.error("No venues fetched — aborting")
        return 1

    # 2. Deduplicate
    venues = deduplicate.deduplicate(venues)
    deduplicate.write_jsonl(venues)

    # 3. Enrich (website scrape)
    if not args.skip_enrich:
        venues = enrich.enrich_all(venues, limit=args.enrich_limit)

    # 4. Score
    venues = score.score_all(venues, use_llm=not args.no_llm)
    score.write_jsonl(venues)

    # 5. Export top-N
    n_exported = exporter.export_top(venues, top_n=args.top)

    cov = exporter.coverage_summary(venues)
    logger.info("=" * 60)
    logger.info("Done. %d total → %d exported", cov["total"], n_exported)
    logger.info("Coverage: phone=%d email=%d website=%d",
                cov["with_phone"], cov["with_email"], cov["with_website"])
    logger.info("By tier: %s", cov["by_tier"])
    logger.info("=" * 60)

    report = {
        "args": vars(args),
        "bbox": bbox,
        "summary": cov,
        "exported": n_exported,
    }
    (Path(__file__).parent / "data" / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
