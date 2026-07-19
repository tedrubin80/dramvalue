# Private Feed API Documentation

This folder holds **public API docs** plus **gitignored credential files** for the DramValue private JSON feed.

## Files

| File | Committed? | Description |
|------|------------|-------------|
| `API.md` | Yes | Full endpoint reference (no secrets) |
| `README.md` | Yes | This file |
| `CONNECTION.example.md` | Yes | Template without a live key |
| `API_KEY.txt` | **No** | Secret key (one line) |
| `CONNECTION.md` | **No** | Short connection card with live key |

Secure folder (also gitignored):

| File | Description |
|------|-------------|
| `docs/secure/keychain.md` | API key + OpenClaw env + quick curls |
| `docs/secure/API.md` | Full docs + live-key examples |

## Access

Credential files are **not served over HTTP**. Retrieve via FTP/SFTP:

```
/var/www/wtracker/docs/secure/keychain.md
/var/www/wtracker/docs/secure/API.md
/var/www/wtracker/docs/api/CONNECTION.md
```

## Setup / rotate key

```bash
./scripts/setup_feed_api.sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart api
```

## Quick start

1. Read the key from `docs/secure/keychain.md`
2. Follow endpoint docs in `docs/api/API.md`
3. Call `GET /trending` or `GET /search?q=` for promo content
