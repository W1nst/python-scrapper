"""Async HTTP client for the public Tourvisor endpoints.

Tourvisor has no official API, but the search widget on tourvisor.ru talks to a
set of public JSON endpoints that work without a browser session.  This module
wraps that flow:

1. ``POST /api/v1.2/sessions``            -> obtain a ``session`` key
2. ``GET  /xml/modsearch.php``            -> start a search, get a ``requestid``
3. ``GET  https://search3.tourvisor.ru/modresult.php``
                                          -> poll until ``status.finished == 1``

Reference data (countries, resorts, hotels, meals, ...) is fetched lazily and
cached on disk under ``.cache/`` to avoid hammering the site.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import httpx

from .models import TourOffer

BASE_URL = "https://tourvisor.ru"
SEARCH_RESULT_URL = "https://search3.tourvisor.ru"
REFERRER = f"{BASE_URL}/search.php"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": REFERRER,
}

CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"
REFERENCE_TTL = 24 * 60 * 60  # seconds

# Mapping of human meal names -> numeric meal id used by modsearch.php.
MEAL_ALIASES: dict[str, int] = {
    "ob": 1,
    "bb": 4,
    "hb": 5,
    "fb": 6,
    "ai": 7,
    "uai": 9,
    "ro": 2,
}


class TourvisorError(RuntimeError):
    """Raised for any Tourvisor API or transport failure."""


@dataclass
class ReferenceLists:
    """Cached reference data for a specific (country, departure) pair."""

    countries: list[dict[str, Any]]
    departures: list[dict[str, Any]]
    regions: list[dict[str, Any]]
    subregions: list[dict[str, Any]]
    hotels: list[dict[str, Any]]
    hotel_types: list[dict[str, Any]]


class TourvisorClient:
    """Thin async wrapper around the public Tourvisor endpoints."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        poll_interval: float = 1.5,
        poll_timeout: float = 90.0,
        cache_dir: Path | None = None,
    ) -> None:
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._poll_timeout = poll_timeout
        self._cache_dir = cache_dir or CACHE_DIR
        self._session: str | None = None
        self._reference_cache: dict[str, ReferenceLists] = {}

    # ------------------------------------------------------------------
    # Low level transport
    # ------------------------------------------------------------------
    async def _get_session(self, client: httpx.AsyncClient, *, force: bool = False) -> str:
        if self._session and not force:
            return self._session
        resp = await client.post(
            f"{BASE_URL}/api/v1.2/sessions",
            content="{}",
            headers={"Origin": BASE_URL, "Referer": REFERRER, "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        key = data.get("k")
        if not key:
            raise TourvisorError(f"Could not obtain a session key: {data!r}")
        self._session = key
        return key

    async def _request_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        client: httpx.AsyncClient | None = None,
        retry_auth: bool = True,
    ) -> Any:
        params = dict(params or {})
        owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=self._timeout, headers=DEFAULT_HEADERS)
        try:
            session = await self._get_session(client)
            params.setdefault("format", "json")
            params.setdefault("referrer", REFERRER)
            params["session"] = session
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            try:
                data = resp.json()
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                raise TourvisorError(f"Invalid JSON from {url}: {resp.text[:200]!r}") from exc

            error = data.get("error") if isinstance(data, dict) else None
            if error and str(error.get("errormessage", "")).lower().startswith("authorisation"):
                if retry_auth:
                    await self._get_session(client, force=True)
                    return await self._request_json(
                        url, params=params, client=client, retry_auth=False
                    )
                raise TourvisorError(str(error))
            if error:
                raise TourvisorError(str(error))
            return data
        finally:
            if owns_client:
                await client.aclose()

    # ------------------------------------------------------------------
    # Reference data
    # ------------------------------------------------------------------
    def _cache_path(self, name: str) -> Path:
        return self._cache_dir / f"{name}.json"

    def _read_disk_cache(self, name: str) -> Any | None:
        path = self._cache_path(name)
        if not path.exists():
            return None
        if time.time() - path.stat().st_mtime > REFERENCE_TTL:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _write_disk_cache(self, name: str, data: Any) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path(name).write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    async def _cached(self, name: str, coro_factory) -> Any:
        cached = self._read_disk_cache(name)
        if cached is not None:
            return cached
        data = await coro_factory()
        self._write_disk_cache(name, data)
        return data

    async def get_countries(self) -> list[dict[str, Any]]:
        async def fetch() -> list[dict[str, Any]]:
            data = await self._request_json(
                f"{BASE_URL}/xml/listdev.php",
                params={"type": "allcountry", "formmode": 0},
            )
            lists = data.get("lists", {})
            return lists.get("allcountry", {}).get("country", [])

        return await self._cached("countries", fetch)

    async def get_departures(self) -> list[dict[str, Any]]:
        async def fetch() -> list[dict[str, Any]]:
            data = await self._request_json(
                f"{BASE_URL}/xml/listdev.php",
                params={"type": "departure", "formmode": 0},
            )
            lists = data.get("lists", {})
            return lists.get("departures", {}).get("departure", [])

        return await self._cached("departures", fetch)

    async def get_regions(self, country_id: int) -> list[dict[str, Any]]:
        async def fetch() -> list[dict[str, Any]]:
            data = await self._request_json(
                f"{BASE_URL}/api/v1.2/regions/all", params={"countryId": country_id}
            )
            return data if isinstance(data, list) else []

        return await self._cached(f"regions_{country_id}", fetch)

    async def get_subregions(self, country_id: int) -> list[dict[str, Any]]:
        async def fetch() -> list[dict[str, Any]]:
            data = await self._request_json(
                f"{BASE_URL}/api/v1.2/subregions/all", params={"countryId": country_id}
            )
            return data if isinstance(data, list) else []

        return await self._cached(f"subregions_{country_id}", fetch)

    async def get_hotels(self, country_id: int) -> list[dict[str, Any]]:
        async def fetch() -> list[dict[str, Any]]:
            data = await self._request_json(
                f"{BASE_URL}/xml/listdev.php",
                params={"type": "allhotel", "hotcountry": country_id, "formmode": 0},
            )
            lists = data.get("lists", {})
            hotels = lists.get("hotels", {})
            # ``lists.hotels`` is normally a dict keyed by hotel-id groups whose
            # values are lists of hotel dicts; flatten it. Older/other shapes
            # return a plain list or an ``allhotel.hotel`` list.
            if isinstance(hotels, dict):
                return [h for group in hotels.values() for h in group]
            if isinstance(hotels, list):
                return hotels
            return lists.get("allhotel", {}).get("hotel", [])

        return await self._cached(f"hotels_{country_id}", fetch)

    async def get_hotel_types(self, country_id: int) -> list[dict[str, Any]]:
        async def fetch() -> list[dict[str, Any]]:
            data = await self._request_json(
                f"{BASE_URL}/api/v1.2/hotel-actypes/all",
                params={"active": "true", "sortProp": "order", "countryId": country_id},
            )
            return data if isinstance(data, list) else []

        return await self._cached(f"hotel_types_{country_id}", fetch)

    # ------------------------------------------------------------------
    # Name -> id resolution
    # ------------------------------------------------------------------
    @staticmethod
    def _normalise(value: str) -> str:
        return " ".join(value.lower().replace("ё", "е").split())

    @classmethod
    def _find_in(cls, items: Iterable[dict[str, Any]], key: str, needle: str) -> dict[str, Any] | None:
        needle_n = cls._normalise(needle)
        # exact
        for item in items:
            if cls._normalise(str(item.get(key, ""))) == needle_n:
                return item
        # startswith
        for item in items:
            if cls._normalise(str(item.get(key, ""))).startswith(needle_n):
                return item
        # substring
        for item in items:
            if needle_n in cls._normalise(str(item.get(key, ""))):
                return item
        return None

    async def resolve_country(self, value: str | int) -> int:
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            return int(value)
        countries = await self.get_countries()
        match = self._find_in(countries, "name", str(value))
        if not match:
            raise TourvisorError(f"Country not found: {value!r}")
        return int(match["id"])

    async def resolve_departure(self, value: str | int) -> int:
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            return int(value)
        departures = await self.get_departures()
        match = self._find_in(departures, "name", str(value))
        if not match:
            raise TourvisorError(f"Departure city not found: {value!r}")
        return int(match["id"])

    async def resolve_resorts(self, country_id: int, values: list[str | int]) -> list[int]:
        if not values:
            return []
        regions = await self.get_regions(country_id)
        subregions = await self.get_subregions(country_id)
        resolved: list[int] = []
        for value in values:
            if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
                resolved.append(int(value))
                continue
            # Tourvisor's ``regions`` search parameter mixes regions and
            # subregions, so we try regions first and then subregions.
            match = self._find_in(regions, "region_name", str(value))
            if match:
                resolved.append(int(match["region_code"]))
                continue
            match = self._find_in(subregions, "name", str(value))
            if match:
                # subregions share the region namespace in the API (e.g. 221)
                resolved.append(int(match["id"]))
                continue
            raise TourvisorError(f"Resort not found: {value!r}")
        # de-duplicate while keeping order
        return list(dict.fromkeys(resolved))

    async def resolve_hotels(self, country_id: int, values: list[str | int]) -> list[int]:
        if not values:
            return []
        resolved: list[int] = []
        need_names = [v for v in values if not (isinstance(v, int) or str(v).isdigit())]
        hotels = await self.get_hotels(country_id) if need_names else []
        for value in values:
            if isinstance(value, int) or (isinstance(value, str) and str(value).isdigit()):
                resolved.append(int(value))
                continue
            match = self._find_in(hotels, "name", str(value))
            if not match:
                raise TourvisorError(f"Hotel not found: {value!r}")
            resolved.append(int(match["id"]))
        return resolved

    def resolve_meal(self, value: str | int | None) -> int:
        if value is None:
            return 0
        if isinstance(value, int) or (isinstance(value, str) and str(value).isdigit()):
            return int(value)
        key = self._normalise(str(value))
        if key in MEAL_ALIASES:
            return MEAL_ALIASES[key]
        raise TourvisorError(f"Unknown meal type: {value!r}")

    # ------------------------------------------------------------------
    # Search flow
    # ------------------------------------------------------------------
    @staticmethod
    def _dotted(date_str: str) -> str:
        """Convert ISO (YYYY-MM-DD) to Tourvisor's DD.MM.YYYY if needed."""
        if "-" in date_str and len(date_str) == 10 and date_str[4] == "-":
            y, m, d = date_str.split("-")
            return f"{d}.{m}.{y}"
        return date_str

    async def start_search(self, params: dict[str, Any]) -> dict[str, Any]:
        """Call modsearch.php and return the ``result`` payload."""
        data = await self._request_json(f"{BASE_URL}/xml/modsearch.php", params=params)
        result = data.get("result")
        if not result or not result.get("requestid"):
            raise TourvisorError(f"Search did not start: {data!r}")
        return result

    async def fetch_results(self, request_id: int | str) -> dict[str, Any]:
        """Poll modresult.php once and return the ``data`` payload."""
        data = await self._request_json(
            f"{SEARCH_RESULT_URL}/modresult.php", params={"requestid": request_id}
        )
        return data.get("data", {})

    async def search_raw(
        self, params: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Run a full search and return ``(start_result, final_results)``."""
        start = await self.start_search(params)
        request_id = start["requestid"]
        deadline = time.monotonic() + self._poll_timeout
        final: dict[str, Any] = {}
        while time.monotonic() < deadline:
            final = await self.fetch_results(request_id)
            status = final.get("status", {})
            if int(status.get("finished", 0) or 0) == 1:
                break
            await asyncio.sleep(self._poll_interval)
        return start, final

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------
    @staticmethod
    def _decode_name(container: dict[str, Any], key: Any) -> str | None:
        if key is None:
            return None
        entry = container.get(str(key)) or container.get(key)
        if isinstance(entry, dict):
            return entry.get("name")
        if isinstance(entry, str):
            return entry
        return None

    def normalise(self, final: dict[str, Any]) -> list[TourOffer]:
        decode = final.get("decode", {}) or {}
        hotels_meta = decode.get("hotels", {}) or {}
        rooms = decode.get("rooms", {}) or {}
        meals = decode.get("meal", {}) or {}
        places = decode.get("place", {}) or {}
        operators_meta = {
            int(op["id"]): op.get("name")
            for op in (final.get("operators", []) or [])
            if op.get("id") is not None
        }
        offers: list[TourOffer] = []

        for block in final.get("block", []) or []:
            operator_id = block.get("operator")
            operator_name = (
                operators_meta.get(int(operator_id)) if operator_id is not None else None
            )
            for hotel in block.get("hotel", []) or []:
                hotel_id = hotel.get("id")
                meta = hotels_meta.get(str(hotel_id)) or hotels_meta.get(hotel_id) or {}
                for tour in hotel.get("tour", []) or []:
                    price = int(tour.get("pr") or hotel.get("price") or 0)
                    offers.append(
                        TourOffer(
                            hotel_id=int(hotel_id),
                            hotel_name=meta.get("name", f"Hotel {hotel_id}"),
                            stars=meta.get("stars"),
                            rating=meta.get("rating"),
                            region=meta.get("region"),
                            subregion=meta.get("subregion"),
                            sea_distance=meta.get("seadistance"),
                            hotel_link=(
                                f"{BASE_URL}/countries#!/hotel={meta.get('link')}"
                                if meta.get("link")
                                else None
                            ),
                            picture=meta.get("pic"),
                            operator=operator_name,
                            operator_id=int(operator_id) if operator_id is not None else None,
                            price=price,
                            price_before_discount=(
                                int(tour["prbef"]) if tour.get("prbef") else None
                            ),
                            fuel_surcharge=(
                                int(tour["prfuel"]) if tour.get("prfuel") else None
                            ),
                            currency=final.get("currency") or "RUB",
                            departure_date=str(tour.get("dt") or ""),
                            nights=int(tour.get("nt") or 0),
                            placement=self._decode_name(places, tour.get("pl")),
                            meal=self._decode_name(meals, tour.get("ml")),
                            room=self._decode_name(rooms, tour.get("rmd") or tour.get("rm")),
                            is_hot=bool(tour.get("hp") or tour.get("ntf")),
                            tour_id=str(tour.get("id")) if tour.get("id") else None,
                        )
                    )
        return offers
