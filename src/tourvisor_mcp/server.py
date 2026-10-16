"""FastMCP server exposing three tour-search tools backed by tourvisor.ru.

Tools
-----
``resolve_filters``
    Translate human names ("Kemer", "Turkey", "Moscow", "all inclusive") into
    the numeric ids Tourvisor expects.

``search_tours``
    Run a full tour search from a human-friendly query and return normalised
    offers.

``list_reference``
    Dump a reference list (countries / resorts / departures / meal types) so
    the calling agent can ask clarifying questions.
"""

from __future__ import annotations

import json
from typing import Any

from fastmcp import FastMCP

from .client import MEAL_ALIASES, TourvisorClient, TourvisorError
from .models import SearchQuery
from .search import run_search

mcp = FastMCP(
    name="tourvisor",
    instructions=(
        "Search package tours on tourvisor.ru. Use resolve_filters first if you "
        "are unsure about country/resort/departure/meal ids, then call "
        "search_tours. Data comes from Tourvisor's public (unofficial) "
        "endpoints, so results may be rate-limited."
    ),
)

_client = TourvisorClient()


def _error(exc: Exception) -> str:
    return json.dumps({"error": str(exc)}, ensure_ascii=False)


@mcp.tool
async def resolve_filters(
    country: str | None = None,
    resort: str | None = None,
    hotel: str | None = None,
    departure_city: str | None = None,
    meal: str | None = None,
    services: list[str] | None = None,
) -> str:
    """Resolve human-readable filter values into Tourvisor ids.

    Args:
        country: Country name or id, e.g. "Турция" or "4".
        resort: Resort/region or subregion name, e.g. "Кемер" or "Бельдиби".
        hotel: Hotel name or id, e.g. "Akka Alinda".
        departure_city: Departure city name or id, e.g. "Москва".
        meal: Meal type, e.g. "AI", "UAI", "HB", "BB", "RO", "OB", "FB".
        services: Extended filters, e.g. ["Первая линия", "Бассейн с подогревом",
            "Водные горки", "Мини-клуб"]. Names come from list_reference(kind="services").

    Returns a JSON object with the resolved ids.
    """
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
        return _error(exc)


@mcp.tool
async def search_tours(
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
    """Search for package tours on Tourvisor and return normalised offers.

    Args:
        date_from: Departure window start, ISO (YYYY-MM-DD) or DD.MM.YYYY.
        date_to: Departure window end.
        country: Country name or id, e.g. "Турция".
        resorts: Resort/region names, e.g. ["Кемер", "Белек"]. The city "Кемер"
            is a region; "Кемер - центр"/"Бельдиби" are subregions.
        hotels: Optional explicit hotel names or ids to restrict the search.
        departure_city: Departure city, e.g. "Москва".
        stars: Hotel class 1-5.
        rating: Minimum hotel rating, e.g. 4 (Tourvisor stores ratings >= 3).
        meal: Meal type: AI, UAI, HB, FB, BB, RO, OB.
        adults: Number of adults.
        children_ages: Ages of children, e.g. [5].
        nights_from: Minimum nights.
        nights_to: Maximum nights.
        price_from: Minimum price in RUB.
        price_to: Maximum price in RUB.
        operators: Operator names or ids to restrict, e.g. ["Anex"].
        services: Extended hotel filters, e.g. ["Первая линия", "Свой пляж",
            "Бассейн с подогревом", "Водные горки", "Мини-клуб", "Семейный"].
            Use list_reference(kind="services") to see all available names.
            Note: Tourvisor applies these only together with resort filters.
        only_charter: Keep only charter flights (recommended).
        direct_flight: Keep only direct flights.
        sort: "price" (default), "price_desc" or "rating".
        limit: Maximum number of offers to return.

    Returns a JSON object with ``offers`` plus search metadata.
    """
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
    except Exception as exc:  # noqa: BLE001 - surfaced to the agent
        return _error(exc)


@mcp.tool
async def list_reference(
    kind: str,
    country: str | None = None,
) -> str:
    """Return a Tourvisor reference list so the agent can offer choices.

    Args:
        kind: One of "countries", "departures", "regions", "subregions",
            "hotels", "hotel_types", "services", "service_groups", "meals".
        country: Country name or id — required for "regions", "subregions",
            "hotels", "hotel_types", "services" and "service_groups".

    Returns a JSON array of reference entries.
    """
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
        return _error(exc)


def main() -> None:
    """Console-script entry point."""
    mcp.run()


if __name__ == "__main__":
    main()
