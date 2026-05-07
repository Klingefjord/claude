"""Shared data shape for raw and processed venues."""

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Venue:
    name: str
    archetype: str
    tier: str
    source: str
    source_id: str          # e.g. "osm:node/12345"
    lat: float | None = None
    lon: float | None = None
    address: str = ""
    commune: str = ""
    postcode: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    description: str = ""
    raw_tags: dict[str, Any] = field(default_factory=dict)

    # Filled by score step
    fit_score: float | None = None
    reasoning: str = ""
    sources: list[str] = field(default_factory=list)  # all sources for merged record

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Venue":
        return cls(**d)
