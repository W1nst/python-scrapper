"""FastMCP server exposing three tour-search tools backed by tourvisor.ru.

This module uses the full FastMCP framework and is convenient on normal
machines.  On resource-constrained hosts where the MCP SDK import time exceeds
the client's connect deadline, use :mod:`tourvisor_mcp.stdio_server` instead —
it exposes the identical tools with a much faster start-up.
"""

from __future__ import annotations

from fastmcp import FastMCP

from . import tools as _tools

mcp = FastMCP(
    name="tourvisor",
    instructions=(
        "Search package tours on tourvisor.ru. Use resolve_filters first if you "
        "are unsure about country/resort/departure/meal ids, then call "
        "search_tours. Data comes from Tourvisor's public (unofficial) "
        "endpoints, so results may be rate-limited."
    ),
)


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
        services: Extended filters, e.g. ["Первая линия", "Бассейн с подогревом"].

    Returns a JSON object with the resolved ids.
    """
    return await _tools.resolve_filters(
        country=country,
        resort=resort,
        hotel=hotel,
        departure_city=departure_city,
        meal=meal,
        services=services,
    )


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
        resorts: Resort/region names, e.g. ["Кемер", "Белек"].
        hotels: Optional explicit hotel names or ids to restrict the search.
        departure_city: Departure city, e.g. "Москва".
        stars: Hotel class 1-5.
        rating: Minimum hotel rating, e.g. 4.
        meal: Meal type: AI, UAI, HB, FB, BB, RO, OB.
        adults: Number of adults.
        children_ages: Ages of children, e.g. [5].
        nights_from: Minimum nights.
        nights_to: Maximum nights.
        price_from: Minimum price in RUB.
        price_to: Maximum price in RUB.
        operators: Operator names or ids to restrict, e.g. ["Anex"].
        services: Extended hotel filters, e.g. ["Первая линия", "Водные горки"].
            Use list_reference(kind="services") to see all available names.
            Tourvisor applies these only together with resort filters.
        only_charter: Keep only charter flights (recommended).
        direct_flight: Keep only direct flights.
        sort: "price" (default), "price_desc" or "rating".
        limit: Maximum number of offers to return.

    Returns a JSON object with ``offers`` plus search metadata.
    """
    return await _tools.search_tours(
        date_from=date_from,
        date_to=date_to,
        country=country,
        resorts=resorts,
        hotels=hotels,
        departure_city=departure_city,
        stars=stars,
        rating=rating,
        meal=meal,
        adults=adults,
        children_ages=children_ages,
        nights_from=nights_from,
        nights_to=nights_to,
        price_from=price_from,
        price_to=price_to,
        operators=operators,
        services=services,
        only_charter=only_charter,
        direct_flight=direct_flight,
        sort=sort,
        limit=limit,
    )


@mcp.tool
async def list_reference(kind: str, country: str | None = None) -> str:
    """Return a Tourvisor reference list so the agent can offer choices.

    Args:
        kind: One of "countries", "departures", "regions", "subregions",
            "hotels", "hotel_types", "services", "service_groups", "meals".
        country: Country name or id — required for "regions", "subregions",
            "hotels", "hotel_types", "services" and "service_groups".

    Returns a JSON array of reference entries.
    """
    return await _tools.list_reference(kind=kind, country=country)


def main() -> None:
    """Console-script entry point."""
    mcp.run()


if __name__ == "__main__":
    main()
