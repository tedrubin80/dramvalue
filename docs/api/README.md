# Private Feed API Documentation

This folder contains **API credentials and connection details** for the DramValue private JSON feed.

## Access

These files are **not served over HTTP**. Retrieve them via FTP/SFTP from:

```
/var/www/wtracker/docs/api/
```

## Setup

On the server, run:

```bash
./scripts/setup_feed_api.sh
```

This generates `API_KEY.txt` and `CONNECTION.md`, updates `.env`, and sets restrictive permissions.

## Files

| File | Description |
|------|-------------|
| `API_KEY.txt` | Your secret API key (one line) |
| `CONNECTION.md` | Base URL, endpoints, curl examples |
| `README.md` | This file (safe to commit) |

`API_KEY.txt` and `CONNECTION.md` are gitignored and chmod 600.
