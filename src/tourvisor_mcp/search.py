"""Runs a :class:`SearchQuery` through the Tourvisor client."""

from __future__ import annotations

from typing import Any

from .client import TourvisorClient
from .models import SearchQuery, TourOffer


async def run_search(
    client: TourvisorClient,
    query: SearchQuery,
    *,
    sort: str = "price",
    limit: int = 20,
) -> dict[str, Any]:
    """Execute ``query`` and return a normalised, sorted result payload.

    ``sort`` may be ``price`` (ascending) or ``rating`` (descending, then price).
    """
    country_id = await client.resolve_country(query.country) if query.country else 0
    departure_id = (
        await client.resolve_departure(query.departure_city)
        if query.departure_city
        else 0
    )

    params: dict[str, Any] = {
        "datefrom": client._dotted(query.date_from),
        "dateto": client._dotted(query.date_to),
        "nightsfrom": query.nights_from,
        "nightsto": query.nights_to,
        "adults": query.adults,
        "child": query.children_count,
        "departure": departure_id,
        "country": country_id,
        "regular": 1 if query.only_charter else 0,
        "directflight": 1 if query.direct_flight else 0,
        "meal": client.resolve_meal(query.meal),
        "rating": query.rating or 0,
        "pricefrom": query.price_from,
        "priceto": query.price_to,
        "currency": query.currency,
        "formmode": 0,
        "pricetype": 0,
    }
    for index, age in enumerate(query.children_ages, start=1):
        params[f"childage{index}"] = age
    if query.stars:
        params["stars"] = query.stars
    if query.resorts:
        regions = await client.resolve_resorts(country_id, query.resorts)
        if regions:
            params["regions"] = ",".join(str(r) for r in regions)
    if query.hotels:
        hotels = await client.resolve_hotels(country_id, query.hotels)
        if hotels:
            params["hotels"] = ",".join(str(h) for h in hotels)
    if query.operators:
        operators: list[str] = []
        for op in query.operators:
            operators.append(str(op))
        params["operators"] = ",".join(operators)
    if query.hotel_types:
        params["services"] = ",".join(str(s) for s in query.hotel_types)

    start, final = await client.search_raw(params)
    offers = client.normalise(final)
    offers = _sort_offers(offers, sort)

    return {
        "request_id": start.get("requestid"),
        "progress": final.get("status", {}).get("progress"),
        "finished": int(final.get("status", {}).get("finished", 0) or 0) == 1,
        "total_found": len(offers),
        "returned": min(limit, len(offers)),
        "offers": [o.to_dict() for o in offers[:limit]],
    }


def _sort_offers(offers: list[TourOffer], sort: str) -> list[TourOffer]:
    if sort == "rating":
        return sorted(
            offers,
            key=lambda o: (-float(o.rating or 0), o.price),
        )
    if sort == "price_desc":
        return sorted(offers, key=lambda o: -o.price)
    return sorted(offers, key=lambda o: o.price)
