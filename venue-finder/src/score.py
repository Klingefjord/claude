"""Score venues for fit with a $5k aerial rope-net installation.

Two modes:
- LLM scoring (default): Claude Haiku 4.5, batched, JSON-schema constrained
- Heuristic scoring (--no-llm): rule-based, free, ~70% as good as LLM
"""

from __future__ import annotations

import json
import logging

from config import (
    ANTHROPIC_API_KEY,
    LLM_BATCH_SIZE,
    LLM_MODEL,
    SCORED_JSONL,
    TIER_WEIGHTS,
)
from src.venue import Venue

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You score venues near Paris for fit with a ~$5,000 aerial \
rope-net installation — rope bridges and climbing nets strung between mature \
trees, similar to a small accrobranche feature. Good fits have:

- Mature trees on-site (anchor points) OR existing aerial / climbing infrastructure
- An audience that values active outdoor play (families, kids, adventure-seekers)
- Discretionary budget around $5k (private operators, premium positioning)
- Outdoor space they own or control long-term

Bad fits: dense-urban venues with no trees, indoor-only spaces, very small \
operators with no obvious budget, public spaces requiring municipal procurement \
(unless explicitly leisure parks).

You will receive a batch of venues. For each, output a JSON object with:
- fit_score: 1-10 (10 = obvious yes, 1 = obvious no)
- reasoning: 1-2 sentences explaining the score
- has_trees_likely: true if the name/tags suggest mature trees on-site

Be calibrated. Most venues should score 3-7. Only score 9-10 for unusually \
strong fits. Score 1-2 only for clear mismatches (urban café with no green \
space, indoor trampoline park).
"""


SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "fit_score": {"type": "integer"},
                    "reasoning": {"type": "string"},
                    "has_trees_likely": {"type": "boolean"},
                },
                "required": ["id", "fit_score", "reasoning", "has_trees_likely"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["scores"],
    "additionalProperties": False,
}


def _venue_summary(v: Venue) -> dict:
    """Compact representation for the LLM prompt."""
    interesting_tags = {
        k: v.raw_tags[k]
        for k in (
            "tourism", "leisure", "amenity", "sport", "outdoor_seating",
            "playground", "stars", "operator:type", "name:en", "description",
            "natural", "landuse", "addr:city",
        )
        if k in v.raw_tags
    }
    return {
        "id": v.source_id,
        "name": v.name,
        "archetype": v.archetype,
        "tier": v.tier,
        "commune": v.commune,
        "description": v.description[:200] if v.description else "",
        "tags": interesting_tags,
    }


def heuristic_score(v: Venue) -> tuple[float, str]:
    """Cheap rule-based score when --no-llm is set or API is unavailable."""
    score = 5.0
    reasons = []

    tags = v.raw_tags
    if tags.get("natural") == "tree" or tags.get("landuse") == "forest":
        score += 1.5
        reasons.append("trees on/near site")
    if v.archetype in ("accrobranche", "treehouse_hotel", "camping", "agritourism"):
        score += 1.5
        reasons.append("strong-fit archetype")
    if v.archetype in ("waldorf_school", "forest_school"):
        score += 2.0
        reasons.append("nature-pedagogy fit")
    if tags.get("outdoor_seating") == "yes":
        score += 0.5
    if tags.get("operator:type") == "private":
        score += 0.5
        reasons.append("private operator (likely budget)")
    if tags.get("operator:type") == "public":
        score -= 1.0
        reasons.append("public operator (procurement)")
    if v.archetype in ("guinguette", "gite"):
        score -= 0.5  # depends heavily on the specific site

    score = max(1.0, min(10.0, score))
    return score, "; ".join(reasons) if reasons else "default heuristic baseline"


def score_batch_llm(venues: list[Venue], client) -> list[Venue]:
    """Score a batch of up to LLM_BATCH_SIZE venues in one Claude call."""
    summaries = [_venue_summary(v) for v in venues]
    user_msg = "Score these venues:\n\n" + json.dumps(summaries, ensure_ascii=False, indent=2)

    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_msg}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )

    text = next(b.text for b in response.content if b.type == "text")
    parsed = json.loads(text)

    by_id = {s["id"]: s for s in parsed["scores"]}
    for v in venues:
        s = by_id.get(v.source_id)
        if s:
            v.fit_score = float(s["fit_score"])
            v.reasoning = s["reasoning"]
        else:
            # LLM dropped this row — fall back to heuristic
            v.fit_score, v.reasoning = heuristic_score(v)
            v.reasoning = "[heuristic fallback] " + v.reasoning
    return venues


def score_all(venues: list[Venue], use_llm: bool = True) -> list[Venue]:
    if not use_llm or not ANTHROPIC_API_KEY:
        if use_llm and not ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY not set — falling back to heuristic scoring")
        for v in venues:
            v.fit_score, v.reasoning = heuristic_score(v)
        logger.info("Heuristic-scored %d venues", len(venues))
        return venues

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    n = len(venues)
    for i in range(0, n, LLM_BATCH_SIZE):
        batch = venues[i : i + LLM_BATCH_SIZE]
        try:
            score_batch_llm(batch, client)
        except (anthropic.APIError, json.JSONDecodeError) as e:
            logger.error("LLM batch %d-%d failed (%s) — using heuristic", i, i + len(batch), e)
            for v in batch:
                v.fit_score, v.reasoning = heuristic_score(v)
        if (i // LLM_BATCH_SIZE) % 5 == 0:
            logger.info("scored %d/%d", min(i + LLM_BATCH_SIZE, n), n)
    logger.info("LLM-scored %d venues", n)
    return venues


def ranked_score(v: Venue) -> float:
    """Final ranking key: fit_score × tier weight."""
    return (v.fit_score or 0.0) * TIER_WEIGHTS.get(v.tier, 1.0)


def write_jsonl(venues: list[Venue], path=SCORED_JSONL) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for v in venues:
            f.write(json.dumps(v.to_dict(), ensure_ascii=False) + "\n")


def load_jsonl(path=SCORED_JSONL) -> list[Venue]:
    if not path.exists():
        return []
    with open(path) as f:
        return [Venue.from_dict(json.loads(line)) for line in f if line.strip()]
