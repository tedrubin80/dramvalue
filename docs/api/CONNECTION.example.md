# DramValue Private Feed API

> Copy of the template. Run `./scripts/setup_feed_api.sh` to generate `CONNECTION.md` and `docs/secure/keychain.md` with your live key.

## Base URL

```
https://dramvalue.com/api/v1/feed
```

Local (server only):

```
http://localhost:8002/api/v1/feed
```

## Authentication

```
X-API-Key: YOUR_KEY_HERE
```

or

```
Authorization: Bearer YOUR_KEY_HERE
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Feed index |
| GET | `/stats` | Database summary counts |
| GET | `/search?q=` | Search bottles by name / brand |
| GET | `/bottles/{id}` | Bottle detail + trends + promo hints |
| GET | `/bottles/{id}/prices` | Bottle price history |
| GET | `/bottles` | Bottle catalog with aggregates |
| GET | `/trending` | Hot bottles for promo content |
| GET | `/movers` | Biggest 90d price gainers / losers |
| GET | `/prices` | Paginated price history |
| GET | `/prices/recent` | New prices since timestamp |
| GET | `/market` | Monthly auction market stats |

Full reference: [`API.md`](./API.md)

## Example — trending for promo

```bash
KEY="YOUR_KEY_HERE"
curl -s -H "X-API-Key: $KEY" \
  "https://dramvalue.com/api/v1/feed/trending?limit=10"
```

## Example — specific bottle

```bash
KEY="YOUR_KEY_HERE"
curl -s -H "X-API-Key: $KEY" \
  --get --data-urlencode "q=Macallan 18" \
  "https://dramvalue.com/api/v1/feed/search"
```

## Rate limits

- Most endpoints: 120 requests/hour
- `/prices/recent`: 300 requests/hour
- Catalog / market: 60 requests/hour
