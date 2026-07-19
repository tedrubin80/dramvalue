# DramValue Private Feed API — Reference

Private, API-key-authenticated JSON API for bottle pricing, search, and trends.
Built for personal integrations and OpenClaw promo automation.

> **Credentials live in** `docs/secure/keychain.md` (gitignored, chmod 600).  
> This file documents endpoints only — no secrets.

## Base URL

| Environment | URL |
|-------------|-----|
| Production  | `https://dramvalue.com/api/v1/feed` |
| Local       | `http://localhost:8002/api/v1/feed` |

## Authentication

Every request requires one of:

```
X-API-Key: <your-key>
```

```
Authorization: Bearer <your-key>
```

Missing/invalid key → `401`. Key not configured on server → `503`.

## Response envelope

```json
{
  "success": true,
  "data": { },
  "meta": { },
  "error": null,
  "timestamp": "2026-07-19T16:00:00"
}
```

Paginated endpoints nest items under `data.<item_key>` and put page info in `meta.pagination`.

## Endpoints

### `GET /` — Index

Lists available endpoints and API version.

### `GET /stats` — Database summary

| Field | Description |
|-------|-------------|
| `bottles` | Total bottles |
| `prices` | Total price records |
| `market_stats` | Monthly auction aggregates |
| `new_prices_7d` | Prices ingested in last 7 days |

### `GET /search?q=` — Find a bottle

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `q` | string | required | Min 2 chars — name, distillery, or brand |
| `limit` | int | 20 | Max 50 |
| `category` | enum | — | Optional spirit category filter |

Returns promo-ready bottle objects with `avg_price_usd`, `price_trend_90d_pct`, and `page_url`.

### `GET /bottles/{id}` — Bottle detail + recent prices

Primary lookup for promoting a specific bottle.

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `recent_limit` | int | 10 | Recent sales to include (1–50) |

Response highlights:

- Pricing: `avg_price_usd`, `min_price_usd`, `max_price_usd`, `last_price_usd`
- Trend: `price_trend_90d_pct`, `trend_label` (`rising` / `falling` / `stable`)
- `recent_prices[]` — latest sales
- `promo` — `headline_hint`, `trend_hint`, `cta_url` for social copy
- `page_url` — `https://dramvalue.com/bottles/{id}`

### `GET /bottles/{id}/prices` — Price history

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `days` | int | 365 | Lookback window (max 1825) |
| `page` | int | 1 | |
| `page_size` | int | 50 | Max 200 |

### `GET /bottles` — Catalog

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `page` / `page_size` | int | 1 / 100 | Max page_size 500 |
| `category` | enum | — | |
| `has_prices` | bool | true | Only bottles with price data |

### `GET /trending` — Hot bottles

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `days` | int | 30 | Activity window (7–90) |
| `limit` | int | 15 | Max 50 |
| `category` | enum | — | |

Sorted by recent sale count, then 90-day trend. Each item includes `recent_price_count` and `page_url`.

### `GET /movers` — Biggest price swings

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `direction` | `up` \| `down` \| `both` | `both` | |
| `limit` | int | 10 | Per side, max 30 |
| `min_prices` | int | 5 | Min data points |
| `category` | enum | — | |

Returns `{ "gainers": [...], "losers": [...] }` depending on `direction`.

### `GET /prices` — Filtered price feed

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `days` | int | 30 | Max 365 |
| `page` / `page_size` | int | 1 / 100 | Max 500 |
| `source` | enum | — | `AUCTION` / `RETAIL` / `IMPORT` |
| `source_name` | string | — | Partial match |
| `category` | enum | — | |
| `bottle_id` | int | — | |

### `GET /prices/recent` — Incremental poll

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `since` | ISO datetime | 24h ago | Prices created after this time |
| `limit` | int | 100 | Max 500 |
| `source_name` | string | — | |

Use `meta.generated_at` from the response as `since` on the next poll.

### `GET /market` — Auction market aggregates

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `months` | int | 12 | Max 60 |
| `auction_slug` | string | — | Filter one house |

## Rate limits

| Endpoint | Limit |
|----------|-------|
| Most endpoints | 120 req/hour |
| `/prices/recent` | 300 req/hour |
| `/bottles` catalog, `/market` | 60 req/hour |

## OpenClaw usage

1. Read key from `docs/secure/keychain.md` (or env `FEED_API_KEY` / `DRAMVALUE_API_KEY`).
2. Call `/trending` or `/movers` for content ideas.
3. Call `/search?q=...` then `/bottles/{id}` for a specific bottle.
4. Always link `page_url` / `promo.cta_url` back to DramValue.

Example skill env:

```bash
export DRAMVALUE_API_KEY="<from keychain.md>"
export DRAMVALUE_API_BASE="https://dramvalue.com/api/v1/feed"
```

```bash
curl -s -H "X-API-Key: $DRAMVALUE_API_KEY" \
  "$DRAMVALUE_API_BASE/trending?limit=10" | jq .
```

## Rotate / regenerate key

```bash
./scripts/setup_feed_api.sh
docker compose restart api
```

Updates `.env`, `docs/api/API_KEY.txt`, `docs/api/CONNECTION.md`, and `docs/secure/keychain.md`.
