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
{ "country": "Турция", "resort": "Кемер", "departure_city": "Москва", "meal": "AI" }
```
→ `{ "country_id": 4, "departure_id": 1, "resort_ids": [22], "meal_id": 7 }`

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
`kind` ∈ `countries | departures | regions | subregions | hotels | hotel_types | meals`.

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
