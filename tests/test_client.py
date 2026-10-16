"""Offline unit tests — no network access."""

from __future__ import annotations

import json

import httpx
import pytest

from tourvisor_mcp.client import TourvisorClient, TourvisorError
from tourvisor_mcp.search import _sort_offers
from tourvisor_mcp.models import TourOffer


def test_dotted_conversion():
    assert TourvisorClient._dotted("2026-11-10") == "10.11.2026"
    assert TourvisorClient._dotted("10.11.2026") == "10.11.2026"


def test_resolve_meal(client: TourvisorClient):
    assert client.resolve_meal(None) == 0
    assert client.resolve_meal("AI") == 7
    assert client.resolve_meal("uai") == 9
    assert client.resolve_meal("HB") == 5
    assert client.resolve_meal(7) == 7
    assert client.resolve_meal("7") == 7
    with pytest.raises(TourvisorError):
        client.resolve_meal("nonsense")


def test_find_in_prefers_exact():
    items = [
        {"name": "Аланья"},
        {"name": "Алания-центр"},
        {"name": "Кемер"},
    ]
    assert TourvisorClient._find_in(items, "name", "Аланья")["name"] == "Аланья"
    assert TourvisorClient._find_in(items, "name", "алания")["name"] == "Алания-центр"


def test_normalise_decodes_operator_and_refs():
    final = {
        "currency": "RUB",
        "status": {"progress": 100, "finished": 1},
        "operators": [{"id": 18, "name": "Biblioglobus", "minprice": "149343"}],
        "block": [
            {
                "id": 1,
                "operator": 18,
                "hotel": [
                    {
                        "id": 28581,
                        "price": 149343,
                        "tour": [
                            {
                                "op": 18,
                                "dt": "2026-11-12",
                                "nt": 7,
                                "pl": 6,
                                "pr": 149343,
                                "id": "1829",
                                "ml": 9,
                                "rmd": 2196009,
                                "hp": 2,
                            }
                        ],
                    }
                ],
            }
        ],
        "decode": {
            "hotels": {
                "28581": {
                    "name": "AKKA ALINDA HOTEL",
                    "stars": "5",
                    "rating": "4.6",
                    "region": "Кемер",
                    "subregion": "Кириш",
                    "seadistance": 100,
                    "link": "akka-alinda-hotel",
                    "pic": "https://example/pic.jpg",
                }
            },
            "rooms": {"2196009": {"name": "standard land view"}},
            "meal": {"9": {"name": "UAI - Ультра Все Включено"}},
            "place": {"6": {"name": "2 взр + реб"}},
        },
    }
    offers = TourvisorClient(cache_dir="/tmp/nonexistent-cache").normalise(final)
    assert len(offers) == 1
    offer = offers[0]
    assert offer.hotel_name == "AKKA ALINDA HOTEL"
    assert offer.operator == "Biblioglobus"
    assert offer.stars == "5"
    assert offer.meal == "UAI - Ультра Все Включено"
    assert offer.room == "standard land view"
    assert offer.placement == "2 взр + реб"
    assert offer.price == 149343
    assert offer.is_hot is True
    assert offer.hotel_link.endswith("hotel=akka-alinda-hotel")


def _offer(price: int, rating: str) -> TourOffer:
    return TourOffer(
        hotel_id=1,
        hotel_name="H",
        stars="5",
        rating=rating,
        region="R",
        subregion=None,
        sea_distance=None,
        hotel_link=None,
        picture=None,
        operator="O",
        operator_id=1,
        price=price,
        price_before_discount=None,
        fuel_surcharge=None,
        currency="RUB",
        departure_date="2026-11-12",
        nights=7,
        placement=None,
        meal=None,
        room=None,
        is_hot=False,
        tour_id=None,
    )


def test_sort_offers():
    offers = [_offer(200, "4.0"), _offer(100, "3.5"), _offer(150, "4.9")]
    assert [o.price for o in _sort_offers(offers, "price")] == [100, 150, 200]
    assert [o.price for o in _sort_offers(offers, "price_desc")] == [200, 150, 100]
    assert [o.price for o in _sort_offers(offers, "rating")] == [150, 200, 100]


def test_flatten_services_from_groups():
    groups = [
        {
            "id": 3,
            "name": "Пляж и расположение",
            "childrens": [
                {"id": 15, "name": "Первая линия", "popular": True},
                {"id": 16, "name": "Свой пляж", "popular": True},
            ],
        },
        {
            "id": 5,
            "name": "Услуги и территория",
            "childrens": [{"id": 24, "name": "Бассейн с подогревом", "popular": False}],
        },
    ]
    services = []
    for group in groups:
        for child in group["childrens"]:
            services.append(
                {
                    "id": child["id"],
                    "name": child["name"],
                    "group": group["name"],
                    "groupId": group["id"],
                    "popular": child.get("popular", False),
                }
            )
    assert {s["name"]: s["id"] for s in services}[ "Первая линия"] == 15
    assert {s["name"]: s["id"] for s in services}["Бассейн с подогревом"] == 24
    # _find_in resolves names case/ё-insensitively
    assert TourvisorClient._find_in(services, "name", "первая линия")["id"] == 15
    assert TourvisorClient._find_in(services, "name", "БАССЕЙН С ПОДОГРЕВОМ")["id"] == 24


async def test_resolve_services(monkeypatch):
    client = TourvisorClient(cache_dir="/tmp/nonexistent-cache")
    fake = [
        {"id": 15, "name": "Первая линия", "group": "Пляж и расположение", "groupId": 3},
        {"id": 24, "name": "Бассейн с подогревом", "group": "Услуги и территория", "groupId": 5},
        {"id": 25, "name": "Водные горки", "group": "Услуги и территория", "groupId": 5},
    ]

    async def fake_get_services(country_id):
        return fake

    monkeypatch.setattr(client, "get_services", fake_get_services)
    assert await client.resolve_services(4, ["Первая линия", 24]) == [15, 24]
    assert await client.resolve_services(4, ["водные горки"]) == [25]
    assert await client.resolve_services(4, []) == []
    with pytest.raises(TourvisorError):
        await client.resolve_services(4, ["Несуществующий фильтр"])


async def test_session_retry_on_auth_error(monkeypatch, tmp_path):
    """A stale session triggers one re-auth and a retry."""
    client = TourvisorClient(cache_dir=tmp_path / "c")
    calls = {"sessions": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/sessions"):
            calls["sessions"] += 1
            return httpx.Response(200, json={"k": f"key-{calls['sessions']}"})
        calls["get"] += 1
        if calls["get"] == 1:
            return httpx.Response(200, json={"error": {"errormessage": "Authorisation Error."}})
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    # Patch httpx.AsyncClient so the handler is used inside _request_json.
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    data = await client._request_json("https://tourvisor.ru/xml/modsearch.php")
    assert data == {"ok": True}
    assert calls["sessions"] == 2  # initial + forced refresh
