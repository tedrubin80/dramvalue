# DramValue Private Feed API

> Copy of the template. Run `./scripts/setup_feed_api.sh` to generate `CONNECTION.md` with your live key.

## Base URL

```
https://dramvalue.com/api/v1/feed
```

Local (server only):

```
http://localhost:8002/api/v1/feed
```

## Authentication

Pass your API key using either header:

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
| GET | `/prices` | Paginated price history (`?days=30&page=1&page_size=100`) |
| GET | `/prices/recent` | New prices since timestamp (`?since=2026-07-12T00:00:00Z`) |
| GET | `/bottles` | Bottle catalog with aggregates |
| GET | `/market` | Monthly auction market stats |

## Example — poll new prices

```bash
KEY="YOUR_KEY_HERE"
curl -s -H "X-API-Key: $KEY" \
  "https://dramvalue.com/api/v1/feed/prices/recent?limit=50"
```

## Example — incremental sync

```bash
KEY="YOUR_KEY_HERE"
SINCE="2026-07-12T03:00:00Z"
curl -s -H "X-API-Key: $KEY" \
  "https://dramvalue.com/api/v1/feed/prices/recent?since=${SINCE}&limit=500"
```

Save `meta.generated_at` from the response and use it as `since` on the next poll.

## Rate limits

- Most endpoints: 120 requests/hour
- `/prices/recent`: 300 requests/hour
