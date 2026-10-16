"""Live tests against the real tourvisor.ru API.

Run with::

    pytest -m live -v

These tests require network access and may be slow or occasionally fail if
Tourvisor's public endpoints are rate-limited.
"""

from __future__ import annotations

import pytest

from tourvisor_mcp.client import TourvisorClient
from tourvisor_mcp.models import SearchQuery
from tourvisor_mcp.search import run_search

pytestmark = pytest.mark.live


async def test_live_reference_countries(client: TourvisorClient):
    countries = await client.get_countries()
    assert len(countries) > 50
    turkey = client._find_in(countries, "name", "Турция")
    assert turkey is not None
    assert int(turkey["id"]) == 4


async def test_live_resolve_kemer_departure(client: TourvisorClient):
    turkey = await client.resolve_country("Турция")
    moscow = await client.resolve_departure("Москва")
    resorts = await client.resolve_resorts(turkey, ["Кемер"])
    assert turkey == 4
    assert moscow == 1
    assert 22 in resorts  # Кемер region


async def test_live_search_turkey_kemer_5star_family(client: TourvisorClient):
    query = SearchQuery(
        date_from="2026-11-10",
        date_to="2026-11-20",
        country="Турция",
        departure_city="Москва",
        resorts=["Кемер"],
        stars=5,
        adults=2,
        children_ages=[5],
        nights_from=7,
        nights_to=10,
        only_charter=True,
    )
    payload = await run_search(client, query, sort="price", limit=10)
    assert payload["request_id"]
    assert payload["finished"] is True
    assert payload["total_found"] > 0
    assert payload["offers"]
    first = payload["offers"][0]
    # cheapest first
    prices = [offer["price"] for offer in payload["offers"]]
    assert prices == sorted(prices)
    assert first["hotel_name"]
    assert first["stars"] == "5"
    assert first["price"] > 0
    assert first["nights"] >= 7


async def test_live_search_with_explicit_hotel(client: TourvisorClient):
    query = SearchQuery(
        date_from="2026-11-10",
        date_to="2026-11-20",
        country="Турция",
        departure_city="Москва",
        hotels=["Akka Alinda"],
        stars=5,
        adults=2,
        children_ages=[5],
        nights_from=7,
        nights_to=10,
    )
    payload = await run_search(client, query, limit=5)
    assert payload["finished"] is True
    assert payload["total_found"] > 0
    names = {offer["hotel_name"] for offer in payload["offers"]}
    assert any("AKKA ALINDA" in name.upper() for name in names)


async def test_live_services_reference(client: TourvisorClient):
    turkey = await client.resolve_country("Турция")
    services = await client.get_services(turkey)
    names = {s["name"]: s["id"] for s in services}
    assert names.get("Первая линия") == 15
    assert names.get("Бассейн с подогревом") == 24
    assert names.get("Водные горки") == 25


async def test_live_services_filter_narrows_results(client: TourvisorClient):
    """Adding an extended filter must not increase the number of results."""
    base = SearchQuery(
        date_from="2026-11-24",
        date_to="2026-11-30",
        country="Турция",
        departure_city="Екатеринбург",
        resorts=["Кемер"],
        stars=5,
        adults=2,
        children_ages=[8],
        nights_from=6,
        nights_to=8,
        only_charter=False,
    )
    plain = await run_search(client, base, limit=1)

    filtered_query = SearchQuery(**{**base.to_dict(), "services": ["Первая линия"]})
    filtered = await run_search(client, filtered_query, limit=1)

    assert plain["finished"] and filtered["finished"]
    assert plain["total_found"] > 0
    assert filtered["total_found"] <= plain["total_found"]
