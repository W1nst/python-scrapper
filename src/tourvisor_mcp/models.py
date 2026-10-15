"""Data models used by the Tourvisor MCP server."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SearchQuery:
    """A human-friendly tour search query.

    All fields are optional except the departure date range; the client is
    responsible for turning names into Tourvisor numeric ids.
    """

    date_from: str  # DD.MM.YYYY
    date_to: str  # DD.MM.YYYY
    departure_city: str | int | None = None
    country: str | int | None = None
    resorts: list[str | int] = field(default_factory=list)
    hotels: list[str | int] = field(default_factory=list)
    stars: int | None = None
    rating: int | None = None
    meal: str | int | None = None
    adults: int = 2
    children_ages: list[int] = field(default_factory=list)
    nights_from: int = 6
    nights_to: int = 14
    price_from: int = 0
    price_to: int = 0
    operators: list[str | int] = field(default_factory=list)
    hotel_types: list[int] = field(default_factory=list)
    only_charter: bool = True
    direct_flight: bool = False
    currency: int = 0  # 0 = RUB

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def children_count(self) -> int:
        return len(self.children_ages)


@dataclass
class TourOffer:
    """A single normalised tour offer ready for the agent to consume."""

    hotel_id: int
    hotel_name: str
    stars: str | None
    rating: str | None
    region: str | None
    subregion: str | None
    sea_distance: int | None
    hotel_link: str | None
    picture: str | None
    operator: str | None
    operator_id: int | None
    price: int
    price_before_discount: int | None
    fuel_surcharge: int | None
    currency: str
    departure_date: str
    nights: int
    placement: str | None
    meal: str | None
    room: str | None
    is_hot: bool
    tour_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
