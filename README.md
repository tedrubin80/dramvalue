# WTracker

Secondary Market Spirits Price Intelligence Platform

## Quick Start

```bash
# Copy environment template
cp .env.example .env

# Start services
docker compose up -d

# Run migrations
docker compose exec api alembic upgrade head

# Access the API
open http://localhost:8000/docs
```

## Development

See [docs/project/](docs/project/) for project documentation.
