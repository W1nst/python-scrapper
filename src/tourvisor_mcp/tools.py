"""Shared tool implementations and JSON schemas.

The heavy FastMCP server (``server.py``) and the minimal stdio server
(``stdio_server.py``) both expose exactly the same three tools.  Keeping the
handlers and their JSON-Schema definitions here guarantees parity and avoids
duplicating logic (and keeps the light server free of the heavy MCP SDK).
"""

from __future__ import annotations

import json
from typing import Any

from .client import MEAL_ALIASES, TourvisorClient, TourvisorError
from .models import SearchQuery
from .rate_limit import RateLimiter
from .search import run_search

_client = TourvisorClient()

# Guard the (rate-limited) search endpoint: at most 6 searches per minute.
# Tourvisor answers rapidly repeated searches with 401/403 and an agent would
# otherwise retry in a tight loop for minutes.
_search_limiter = RateLimiter(max_calls=6, period=60.0)


def _error_payload(message: str, *, retryable: bool, retry_after: float | None = None) -> str:
    """Build a JSON error that tells the agent whether to retry."""
    payload: dict[str, Any] = {"error": message, "retryable": retryable}
    if retry_after is not None:
        payload["retry_after_seconds"] = round(retry_after)
    if not retryable:
        payload["hint"] = (
            "Do not call this tool again in the same turn; report this to the "
            "user and wait for a new request."
        )
    return json.dumps(payload, ensure_ascii=False)


async def resolve_filters(
    *,
    country: str | None = None,
    resort: str | None = None,
    hotel: str | None = None,
    departure_city: str | None = None,
    meal: str | None = None,
    services: list[str] | None = None,
) -> str:
    """Resolve human-readable filter values into Tourvisor ids (JSON string)."""
    try:
        result: dict[str, Any] = {}
        country_id: int | None = None
        if country is not None:
            country_id = await _client.resolve_country(country)
            result["country_id"] = country_id
        if departure_city is not None:
            result["departure_id"] = await _client.resolve_departure(departure_city)
        if resort is not None:
            if country_id is None:
                raise TourvisorError("`country` is required to resolve a resort")
            result["resort_ids"] = await _client.resolve_resorts(country_id, [resort])
        if hotel is not None:
            if country_id is None:
                raise TourvisorError("`country` is required to resolve a hotel")
            result["hotel_ids"] = await _client.resolve_hotels(country_id, [hotel])
        if meal is not None:
            result["meal_id"] = _client.resolve_meal(meal)
        if services is not None:
            if country_id is None:
                raise TourvisorError("`country` is required to resolve services")
            result["service_ids"] = await _client.resolve_services(country_id, services)
        result["available_meals"] = MEAL_ALIASES
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001 - surfaced to the agent
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


async def search_tours(
    *,
    date_from: str,
    date_to: str,
    country: str | None = None,
    resorts: list[str] | None = None,
    hotels: list[str] | None = None,
    departure_city: str | None = None,
    stars: int | None = None,
    rating: int | None = None,
    meal: str | None = None,
    adults: int = 2,
    children_ages: list[int] | None = None,
    nights_from: int = 6,
    nights_to: int = 14,
    price_from: int = 0,
    price_to: int = 0,
    operators: list[str] | None = None,
    services: list[str] | None = None,
    only_charter: bool = True,
    direct_flight: bool = False,
    sort: str = "price",
    limit: int = 20,
) -> str:
    """Run a tour search and return normalised offers (JSON string)."""
    wait = await _search_limiter.acquire()
    if wait > 0:
        return _error_payload(
            "Too many tour searches were requested in a short time. "
            "Tourvisor rate-limits the search endpoint.",
            retryable=True,
            retry_after=wait,
        )
    try:
        query = SearchQuery(
            date_from=date_from,
            date_to=date_to,
            country=country,
            resorts=resorts or [],
            hotels=hotels or [],
            departure_city=departure_city,
            stars=stars,
            rating=rating,
            meal=meal,
            adults=adults,
            children_ages=children_ages or [],
            nights_from=nights_from,
            nights_to=nights_to,
            price_from=price_from,
            price_to=price_to,
            operators=operators or [],
            services=services or [],
            only_charter=only_charter,
            direct_flight=direct_flight,
        )
        payload = await run_search(_client, query, sort=sort, limit=limit)
        return json.dumps(payload, ensure_ascii=False)
    except TourvisorError as exc:
        # Auth/rate-limit failures are not worth retrying immediately; a retry
        # would keep Tourvisor (and the agent) in a loop.
        return _error_payload(str(exc), retryable=False)
    except Exception as exc:  # noqa: BLE001 - surfaced to the agent
        return _error_payload(str(exc), retryable=False)


async def list_reference(*, kind: str, country: str | None = None) -> str:
    """Return a Tourvisor reference list (JSON string)."""
    try:
        if kind == "countries":
            data = await _client.get_countries()
        elif kind == "departures":
            data = await _client.get_departures()
        elif kind == "meals":
            data = [{"id": v, "name": k} for k, v in MEAL_ALIASES.items()]
        elif kind in {
            "regions",
            "subregions",
            "hotels",
            "hotel_types",
            "services",
            "service_groups",
        }:
            if country is None:
                raise TourvisorError(f"`country` is required for kind={kind!r}")
            country_id = await _client.resolve_country(country)
            if kind == "regions":
                data = await _client.get_regions(country_id)
            elif kind == "subregions":
                data = await _client.get_subregions(country_id)
            elif kind == "hotels":
                data = await _client.get_hotels(country_id)
            elif kind == "hotel_types":
                data = await _client.get_hotel_types(country_id)
            elif kind == "services":
                data = await _client.get_services(country_id)
            else:
                data = await _client.get_service_groups(country_id)
        else:
            raise TourvisorError(
                "Unknown kind. Use one of: countries, departures, regions, "
                "subregions, hotels, hotel_types, services, service_groups, meals."
            )
        return json.dumps(data, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001 - surfaced to the agent
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# JSON-Schema definitions (identical for both server front-ends).
# ---------------------------------------------------------------------------
SERVICE_LIST_SCHEMA = {
    "type": "array",
    "items": {"type": "string"},
    "description": (
        'Extended filters, e.g. ["Первая линия", "Бассейн с подогревом", '
        '"Водные горки", "Мини-клуб"]. See list_reference(kind="services").'
    ),
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "resolve_filters",
        "description": (
            "Resolve human-readable filter values (country, resort, hotel, "
            "departure city, meal, extended services) into Tourvisor ids."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "country": {"type": "string", "description": 'e.g. "Турция" or "4"'},
                "resort": {"type": "string", "description": 'e.g. "Кемер"'},
                "hotel": {"type": "string", "description": 'e.g. "Akka Alinda"'},
                "departure_city": {"type": "string", "description": 'e.g. "Москва"'},
                "meal": {"type": "string", "description": "AI, UAI, HB, FB, BB, RO, OB"},
                "services": SERVICE_LIST_SCHEMA,
            },
        },
    },
    {
        "name": "search_tours",
        "description": (
            "Search package tours on tourvisor.ru and return normalised offers "
            "sorted by price or rating."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "date_from": {
                    "type": "string",
                    "description": "Departure window start, ISO or DD.MM.YYYY",
                },
                "date_to": {"type": "string", "description": "Departure window end"},
                "country": {"type": "string"},
                "resorts": {"type": "array", "items": {"type": "string"}},
                "hotels": {"type": "array", "items": {"type": "string"}},
                "departure_city": {"type": "string"},
                "stars": {"type": "integer", "minimum": 1, "maximum": 5},
                "rating": {"type": "integer"},
                "meal": {"type": "string"},
                "adults": {"type": "integer", "default": 2},
                "children_ages": {"type": "array", "items": {"type": "integer"}},
                "nights_from": {"type": "integer", "default": 6},
                "nights_to": {"type": "integer", "default": 14},
                "price_from": {"type": "integer", "default": 0},
                "price_to": {"type": "integer", "default": 0},
                "operators": {"type": "array", "items": {"type": "string"}},
                "services": SERVICE_LIST_SCHEMA,
                "only_charter": {"type": "boolean", "default": True},
                "direct_flight": {"type": "boolean", "default": False},
                "sort": {
                    "type": "string",
                    "enum": ["price", "price_desc", "rating"],
                    "default": "price",
                },
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["date_from", "date_to"],
        },
    },
    {
        "name": "list_reference",
        "description": "Return a Tourvisor reference list so the agent can offer choices.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": [
                        "countries",
                        "departures",
                        "regions",
                        "subregions",
                        "hotels",
                        "hotel_types",
                        "services",
                        "service_groups",
                        "meals",
                    ],
                },
                "country": {"type": "string"},
            },
            "required": ["kind"],
        },
    },
]


_HANDLERS = {
    "resolve_filters": resolve_filters,
    "search_tours": search_tours,
    "list_reference": list_reference,
}


async def call_tool(name: str, arguments: dict[str, Any]) -> str:
    """Dispatch a tool call by name. Returns the JSON string result."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)
    return await handler(**(arguments or {}))
