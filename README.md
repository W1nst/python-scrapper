# tourvisor-mcp

MCP server for searching package tours on [tourvisor.ru](https://tourvisor.ru/search.php).
Tourvisor has **no official API**, but its search widget talks to public JSON
endpoints that work without a browser. This server wraps that flow and exposes it
to an LLM agent through three MCP tools.

## How it works

```
POST /api/v1.2/sessions          -> session key                (free, no cookies)
GET  /xml/modsearch.php          -> start search, get requestid
GET  search3.tourvisor.ru/modresult.php?requestid=... -> poll until finished=1
```

Reference data (countries, resorts, hotels, meals) is fetched lazily and cached
on disk under `.cache/` (24 h TTL).

## Install

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"
```

## Run the server

```bash
tourvisor-mcp                 # stdio transport (default for FastMCP)
# or
python -m tourvisor_mcp.server
```

### Example MCP client config (Claude Desktop / any MCP host)

```json
{
  "mcpServers": {
    "tourvisor": {
      "command": "D:/Work/Projects/python-scrapper/.venv/Scripts/python.exe",
      "args": ["-m", "tourvisor_mcp.server"]
    }
  }
}
```

## Tools

### `resolve_filters`

Turns human names into Tourvisor ids.

```json
{ "country": "Турция", "resort": "Кемер", "departure_city": "Москва", "meal": "AI",
  "services": ["Первая линия", "Бассейн с подогревом"] }
```
→ `{ "country_id": 4, "departure_id": 1, "resort_ids": [22], "meal_id": 7, "service_ids": [15, 24] }`

### `search_tours`

```json
{
  "date_from": "2026-11-10",
  "date_to": "2026-11-20",
  "country": "Турция",
  "resorts": ["Кемер"],
  "stars": 5,
  "adults": 2,
  "children_ages": [5],
  "nights_from": 7,
  "nights_to": 10,
  "meal": "AI",
  "rating": 4,
  "services": ["Первая линия", "Водные горки"],
  "sort": "price",
  "limit": 20
}
```

Returns normalised offers (hotel, stars, rating, resort, dates, nights, meal,
operator, price, hot flag, link), sorted by price (or `rating`).

### `list_reference`

```json
{ "kind": "regions", "country": "Турция" }
```
`kind` ∈ `countries | departures | regions | subregions | hotels | hotel_types | services | service_groups | meals`.

## Extended filters (`services`)

The `services` parameter drives Tourvisor's **"Расширенные фильтры"** panel and is
passed to `modsearch.php` as a comma-separated list of service ids. Names are
resolved case/ё-insensitively, e.g. `"первая линия"` → `15`.

| Group | Services (id) |
|---|---|
| Пляж и расположение | Первая линия (15), Свой пляж (16), Песчаный пляж (17), Галечный пляж (18) |
| Услуги и территория | Бассейн (23), Бассейн с подогревом (24), Водные горки (25), SPA (26), Ресторан или кафе (27), Спортзал (28), Теннис (30), Футбол (31), Анимация (33), Дискотека (34), Wi-Fi (36) |
| Удобства | Кухня (7), Балкон (8), Wi-Fi в номере (10), Кондиционер (12) |
| Детям | Водные горки для детей (1), Детское меню (2), Мини-клуб (3), Детская анимация (4), Детская площадка (6) |
| Особенности отеля | Можно с животными (14), Одиноким мужчинам (39), Семейный (44), VIP (45), Только для взрослых (48), Новый отель (49) |
| Доп.фильтры | Гарантия мест (46) |

⚠️ Tourvisor applies `services` **only together with resort filters** — always
pass `resorts` (or `hotels`) when using extended filters. Call
`list_reference(kind="services", country=...)` for the authoritative, current list.

## Parameter reference

| Field | Meaning |
|---|---|
| `date_from` / `date_to` | departure date window (ISO or DD.MM.YYYY) |
| `resorts` | region names (e.g. `Кемер`) or subregions (e.g. `Бельдиби`) |
| `stars` | hotel class 1–5 |
| `rating` | minimum hotel rating |
| `meal` | `AI`, `UAI`, `HB`, `FB`, `BB`, `RO`, `OB` |
| `adults`, `children_ages` | party composition |
| `nights_from` / `nights_to` | nights range |
| `operators` | operator names/ids |
| `services` | extended filters (Первая линия, Бассейн с подогревом, ...) |
| `only_charter` | charter flights only (recommended) |

Tourvisor ids used under the hood: Москва=1, С.Петербург=5, Турция=4,
Кемер=22, Бельдиби=219, Кемер-центр=221.

## Tests

```bash
pytest -m "not live" -v     # offline unit tests (fast)
pytest -m live -v           # real requests to tourvisor.ru
```

## Disclaimer

Not affiliated with Tourvisor. Uses their public, undocumented endpoints; if the
site changes its widget internals these calls may break. Respect their rate
limits and terms of service.
