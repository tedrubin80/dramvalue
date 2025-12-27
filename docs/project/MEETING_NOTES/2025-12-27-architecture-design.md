# Architecture & Design Discussion: WTracker

**Date:** 2025-12-27
**Participants:** PM (Alex), Tech Lead (Jordan), Product Owner (Sam), QA Lead (Riley)
**Context:** Following completion of Discovery & Requirements, the team convenes to finalize architectural decisions for database schema, API design, Docker infrastructure, and algorithm abstraction layer.

---

## Opening

**[PM] Alex:** Good afternoon, team. We've completed Discovery & Requirements and it's time to solidify our technical architecture. Today we need to make concrete decisions on four key areas:

1. Database schema design - tables, relationships, indexes
2. API structure for our FastAPI backend
3. Docker Compose configuration for local development
4. Algorithm abstraction layer for swappable forecasting and anomaly detection

Let's start with the database schema since everything else depends on it. Jordan, take us through your proposed design.

---

## Database Schema Discussion

**[Tech Lead] Jordan:** I've designed a schema that balances normalization with practical query performance. Let me walk through the core entities:

### Core Entities

**Bottles Table** - The heart of our system:
```
bottles:
  - id (UUID, PK)
  - name (VARCHAR, indexed)
  - distillery (VARCHAR, indexed)
  - bottle_type (ENUM: bourbon, scotch, rye, other)
  - age_statement (INTEGER, nullable)
  - proof (DECIMAL)
  - size_ml (INTEGER)
  - release_year (INTEGER, nullable)
  - is_allocated (BOOLEAN)
  - created_at, updated_at
```

I'm using UUID for primary keys to support future distributed scenarios and prevent enumeration attacks.

**[QA] Riley:** What about the naming normalization challenge we identified? How do we handle "BT Stagg" vs "George T. Stagg"?

**[Tech Lead] Jordan:** Good catch. I'm proposing a separate **bottle_aliases** table:

```
bottle_aliases:
  - id (UUID, PK)
  - bottle_id (FK -> bottles)
  - alias_name (VARCHAR, indexed)
  - is_primary (BOOLEAN)
  - created_at
```

This lets us map multiple names to a single canonical bottle. The search will query both `bottles.name` and `bottle_aliases.alias_name`.

**[PO] Sam:** I like that approach. It also gives us flexibility for user-reported aliases in the future. What about the price data structure?

**[Tech Lead] Jordan:** **Prices** is our time-series core:

```
prices:
  - id (UUID, PK)
  - bottle_id (FK -> bottles, indexed)
  - price_cents (INTEGER) -- stored as cents to avoid float issues
  - currency (VARCHAR, default 'USD')
  - transaction_date (TIMESTAMP, indexed)
  - source_type (ENUM: auction, retail, crowdsourced)
  - source_id (FK -> data_sources, nullable)
  - submission_id (FK -> submissions, nullable for scraped data)
  - confidence_score (DECIMAL 0-1)
  - is_verified (BOOLEAN)
  - is_outlier (BOOLEAN)
  - created_at
```

The composite index on `(bottle_id, transaction_date)` is critical for our price history queries. I'm storing prices as integers (cents) to avoid floating-point precision issues.

**[QA] Riley:** Why both `source_type` and `source_id`? Seems redundant.

**[Tech Lead] Jordan:** `source_type` enables fast filtering without joins. `source_id` links to the specific auction house or retailer for provenance display. For crowdsourced data, we use `submission_id` instead.

### User System Tables

```
users:
  - id (UUID, PK)
  - email (VARCHAR, UNIQUE, indexed) -- hashed for privacy
  - email_verified (BOOLEAN)
  - display_name (VARCHAR, UNIQUE)
  - password_hash (VARCHAR)
  - trust_score (DECIMAL, default 0.5)
  - is_active (BOOLEAN)
  - is_admin (BOOLEAN)
  - created_at, updated_at, last_login_at

submissions:
  - id (UUID, PK)
  - user_id (FK -> users)
  - bottle_id (FK -> bottles)
  - price_cents (INTEGER)
  - transaction_date (DATE)
  - notes (TEXT, nullable)
  - status (ENUM: pending, approved, rejected, flagged)
  - moderation_flags (JSONB) -- stores flag reasons
  - confidence_score (DECIMAL)
  - created_at, reviewed_at, reviewed_by
```

**[PO] Sam:** For the user collections, how are we structuring that?

**[Tech Lead] Jordan:**

```
collections:
  - id (UUID, PK)
  - user_id (FK -> users, indexed)
  - name (VARCHAR, default 'My Collection')
  - is_public (BOOLEAN, default false)
  - created_at, updated_at

collection_items:
  - id (UUID, PK)
  - collection_id (FK -> collections)
  - bottle_id (FK -> bottles)
  - quantity (INTEGER, default 1)
  - purchase_price_cents (INTEGER, nullable)
  - purchase_date (DATE, nullable)
  - notes (TEXT, nullable)
  - created_at, updated_at
```

This supports multiple collections per user, which is a natural future extension, and tracks purchase price for ROI calculations.

### Moderation & Audit

```
moderation_queue:
  - id (UUID, PK)
  - submission_id (FK -> submissions)
  - flag_type (ENUM: price_outlier, high_volume, new_account, duplicate, manual)
  - flag_reason (TEXT)
  - severity (ENUM: low, medium, high)
  - status (ENUM: pending, reviewed, escalated)
  - assigned_to (FK -> users, nullable)
  - created_at, resolved_at

moderation_actions:
  - id (UUID, PK)
  - queue_item_id (FK -> moderation_queue)
  - moderator_id (FK -> users)
  - action (ENUM: approve, reject, adjust_weight, ban_user, escalate)
  - notes (TEXT)
  - created_at
```

**[QA] Riley:** I want a complete audit trail. Every moderation action must be logged with who did it and when. This table looks good for that.

**[PM] Alex:** What about the data sources for scraped data?

**[Tech Lead] Jordan:**

```
data_sources:
  - id (UUID, PK)
  - name (VARCHAR)
  - source_type (ENUM: auction_house, retailer, other)
  - base_url (VARCHAR)
  - is_active (BOOLEAN)
  - last_scraped_at (TIMESTAMP)
  - scrape_config (JSONB) -- selectors, rate limits
  - created_at, updated_at

scrape_runs:
  - id (UUID, PK)
  - source_id (FK -> data_sources)
  - started_at (TIMESTAMP)
  - completed_at (TIMESTAMP, nullable)
  - status (ENUM: running, completed, failed)
  - items_scraped (INTEGER)
  - errors (JSONB, nullable)
```

This gives us full observability into our scraping pipeline.

**[PO] Sam:** Perfect. This schema covers all our MVP needs. Jordan, what about indexes beyond the ones you mentioned?

**[Tech Lead] Jordan:** Here's my indexing strategy:

```
-- Primary query patterns:
CREATE INDEX idx_bottles_name ON bottles(name);
CREATE INDEX idx_bottles_distillery ON bottles(distillery);
CREATE INDEX idx_bottle_aliases_name ON bottle_aliases(alias_name);
CREATE INDEX idx_prices_bottle_date ON prices(bottle_id, transaction_date DESC);
CREATE INDEX idx_prices_date ON prices(transaction_date DESC);
CREATE INDEX idx_submissions_user ON submissions(user_id);
CREATE INDEX idx_submissions_status ON submissions(status);
CREATE INDEX idx_collection_items_bottle ON collection_items(bottle_id);

-- Full-text search (Phase 2 optimization):
-- CREATE INDEX idx_bottles_search ON bottles USING gin(to_tsvector('english', name));
```

**[QA] Riley:** What about the forecasting results? Are we storing those?

**[Tech Lead] Jordan:** Good question. I'm proposing a **price_forecasts** table:

```
price_forecasts:
  - id (UUID, PK)
  - bottle_id (FK -> bottles, indexed)
  - algorithm (VARCHAR) -- 'prophet', 'arima', 'monte_carlo'
  - forecast_date (DATE) -- the date being forecasted
  - generated_at (TIMESTAMP, indexed)
  - price_low_cents (INTEGER) -- lower confidence bound
  - price_mid_cents (INTEGER) -- median/expected
  - price_high_cents (INTEGER) -- upper confidence bound
  - confidence_level (DECIMAL) -- e.g., 0.7 for 70% CI
  - data_points_used (INTEGER)
  - is_current (BOOLEAN) -- latest forecast for this bottle/algorithm

algorithm_metrics:
  - id (UUID, PK)
  - algorithm (VARCHAR)
  - bottle_id (FK -> bottles, nullable) -- null for aggregate metrics
  - metric_name (VARCHAR) -- 'mape', 'rmse', 'coverage'
  - metric_value (DECIMAL)
  - measured_at (TIMESTAMP)
```

This lets us track algorithm performance over time and compare approaches.

**[PM] Alex:** Excellent. Let's capture this as our database design decision. Moving on to API design - Jordan?

---

## API Design Discussion

**[Tech Lead] Jordan:** For the FastAPI backend, I'm proposing a RESTful design with clear resource boundaries. Here's the endpoint structure:

### Public Endpoints (No Auth Required)

```
GET  /api/v1/bottles                    -- Search/list bottles
GET  /api/v1/bottles/{id}               -- Get bottle details
GET  /api/v1/bottles/{id}/prices        -- Get price history
GET  /api/v1/bottles/{id}/forecasts     -- Get price forecasts
GET  /api/v1/bottles/search?q={query}   -- Full-text search
GET  /api/v1/stats/market               -- Market-wide statistics
```

### Authenticated Endpoints

```
-- User Management
POST /api/v1/auth/register              -- Create account
POST /api/v1/auth/login                 -- Get JWT token
POST /api/v1/auth/verify-email          -- Verify email with token
POST /api/v1/auth/refresh               -- Refresh JWT
POST /api/v1/auth/password-reset        -- Initiate password reset
GET  /api/v1/users/me                   -- Get current user profile
PUT  /api/v1/users/me                   -- Update profile

-- Submissions
POST /api/v1/submissions                -- Submit a price
GET  /api/v1/submissions/mine           -- My submission history
GET  /api/v1/submissions/{id}           -- Get submission status

-- Collections
GET  /api/v1/collections                -- List my collections
POST /api/v1/collections                -- Create collection
GET  /api/v1/collections/{id}           -- Get collection with items
PUT  /api/v1/collections/{id}           -- Update collection
DELETE /api/v1/collections/{id}         -- Delete collection
POST /api/v1/collections/{id}/items     -- Add bottle to collection
DELETE /api/v1/collections/{id}/items/{item_id}  -- Remove item
GET  /api/v1/collections/{id}/valuation -- Get collection value
```

### Admin Endpoints

```
GET  /api/v1/admin/moderation/queue     -- Get pending items
POST /api/v1/admin/moderation/{id}/approve
POST /api/v1/admin/moderation/{id}/reject
GET  /api/v1/admin/users                -- List users
PUT  /api/v1/admin/users/{id}/trust     -- Adjust trust score
POST /api/v1/admin/users/{id}/ban
GET  /api/v1/admin/scrape/status        -- Scraping health
POST /api/v1/admin/scrape/{source}/run  -- Trigger scrape
GET  /api/v1/admin/algorithms/metrics   -- Algorithm performance
```

**[PO] Sam:** The public/authenticated split makes sense. For the search endpoint, what parameters are we supporting?

**[Tech Lead] Jordan:** Full search spec:

```
GET /api/v1/bottles/search
  ?q=string           -- Full-text search (name, distillery, aliases)
  &distillery=string  -- Filter by distillery
  &type=enum          -- bourbon, scotch, rye, other
  &min_price=int      -- Price range filter
  &max_price=int
  &age_min=int        -- Age statement filters
  &age_max=int
  &allocated=bool     -- Only allocated bottles
  &sort=field         -- name, price_avg, last_sale, created_at
  &order=asc|desc
  &page=int
  &limit=int          -- Max 100
```

**[QA] Riley:** What about rate limiting? We discussed that at kickoff.

**[Tech Lead] Jordan:** Yes, rate limiting will be enforced at the API gateway level:

- Public endpoints: 60 requests/minute per IP
- Authenticated endpoints: 120 requests/minute per user
- Submission endpoint: 10 submissions/hour per user
- Admin endpoints: No limit (but logged)

We'll use Redis for rate limit counters.

**[PO] Sam:** What response format are we using?

**[Tech Lead] Jordan:** Standard JSON envelope:

```json
{
  "status": "success",
  "data": { ... },
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 150
  }
}
```

For errors:

```json
{
  "status": "error",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable message",
    "details": { ... }
  }
}
```

**[QA] Riley:** I want consistent error codes we can document and test against. Let's define them upfront.

**[Tech Lead] Jordan:** Agreed. Standard error codes:

| Code | HTTP Status | Description |
|------|-------------|-------------|
| VALIDATION_ERROR | 400 | Invalid input |
| UNAUTHORIZED | 401 | Missing or invalid token |
| FORBIDDEN | 403 | Insufficient permissions |
| NOT_FOUND | 404 | Resource doesn't exist |
| RATE_LIMITED | 429 | Too many requests |
| INTERNAL_ERROR | 500 | Server error |
| SERVICE_UNAVAILABLE | 503 | Maintenance or overload |

**[PM] Alex:** Good. Now let's discuss the Docker setup.

---

## Docker Infrastructure Discussion

**[Tech Lead] Jordan:** For local development and production parity, I'm proposing this Docker Compose structure:

### Services

1. **web** - FastAPI application (uvicorn)
2. **db** - PostgreSQL 15
3. **redis** - For rate limiting, caching, and future job queue
4. **worker** - Celery worker for background tasks (scraping, forecasts)
5. **scheduler** - Celery Beat for scheduled tasks

### docker-compose.yml Structure

```yaml
services:
  web:
    build: ./backend
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [db, redis]
    volumes:
      - ./backend:/app  # Dev hot-reload
    command: uvicorn app.main:app --host 0.0.0.0 --reload

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: wtracker
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    ports: ["5432:5432"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes:
      - redis_data:/data

  worker:
    build: ./backend
    env_file: .env
    depends_on: [db, redis]
    command: celery -A app.tasks worker --loglevel=info

  scheduler:
    build: ./backend
    env_file: .env
    depends_on: [db, redis, worker]
    command: celery -A app.tasks beat --loglevel=info

volumes:
  postgres_data:
  redis_data:
```

**[QA] Riley:** I want a separate test configuration that uses a fresh database for each test run.

**[Tech Lead] Jordan:** Absolutely. We'll have:
- `docker-compose.yml` - Development
- `docker-compose.test.yml` - Testing (ephemeral DB)
- `docker-compose.prod.yml` - Production (no volume mounts, no reload)

**[PO] Sam:** What about the frontend?

**[Tech Lead] Jordan:** For MVP, I'm proposing server-side rendered templates with Jinja2 and minimal JavaScript (Alpine.js or htmx for interactivity). This keeps the stack simpler.

If we need a separate frontend build process later, we'd add a `frontend` service with Node.

**[PM] Alex:** Makes sense for MVP velocity. Now the algorithm abstraction layer - this is critical for our future extensibility.

---

## Algorithm Abstraction Layer Discussion

**[Tech Lead] Jordan:** This is where we architect for the future while building for today. Here's my proposed design:

### Base Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from datetime import date

@dataclass
class ForecastResult:
    forecast_date: date
    price_low: int      # cents
    price_mid: int      # cents
    price_high: int     # cents
    confidence: float   # 0-1
    data_points_used: int

@dataclass
class AnomalyResult:
    is_anomaly: bool
    anomaly_score: float  # 0-1, higher = more anomalous
    reason: Optional[str]
    recommended_action: str  # 'flag', 'reject', 'accept'

class ForecastingAlgorithm(ABC):
    """Base class for all forecasting algorithms."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Algorithm identifier."""
        pass

    @property
    @abstractmethod
    def min_data_points(self) -> int:
        """Minimum historical data points needed."""
        pass

    @abstractmethod
    def fit(self, prices: List[tuple[date, int]]) -> None:
        """Train the model on historical price data."""
        pass

    @abstractmethod
    def predict(
        self,
        horizon_days: List[int],
        confidence_level: float = 0.7
    ) -> List[ForecastResult]:
        """Generate predictions for specified horizons."""
        pass

    def can_predict(self, data_points: int) -> bool:
        """Check if we have enough data."""
        return data_points >= self.min_data_points


class AnomalyDetector(ABC):
    """Base class for anomaly detection algorithms."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def fit(self, prices: List[int]) -> None:
        """Train on historical prices for a bottle."""
        pass

    @abstractmethod
    def detect(self, price: int) -> AnomalyResult:
        """Check if a price is anomalous."""
        pass
```

**[PO] Sam:** This is elegant. So we can swap Prophet for ARIMA without changing any calling code?

**[Tech Lead] Jordan:** Exactly. Here's how concrete implementations look:

```python
class ProphetForecaster(ForecastingAlgorithm):
    name = "prophet"
    min_data_points = 10  # Prophet needs some history

    def fit(self, prices):
        # Convert to Prophet's DataFrame format
        # Fit the model
        pass

    def predict(self, horizon_days, confidence_level=0.7):
        # Generate predictions with uncertainty intervals
        pass


class ZScoreAnomalyDetector(AnomalyDetector):
    name = "zscore"

    def __init__(self, threshold: float = 2.0):
        self.threshold = threshold

    def fit(self, prices):
        self.mean = statistics.mean(prices)
        self.std = statistics.stdev(prices)

    def detect(self, price) -> AnomalyResult:
        z = abs(price - self.mean) / self.std
        return AnomalyResult(
            is_anomaly=z > self.threshold,
            anomaly_score=min(z / 4, 1.0),  # Normalize to 0-1
            reason=f"Z-score: {z:.2f}" if z > self.threshold else None,
            recommended_action='flag' if z > self.threshold else 'accept'
        )
```

### Algorithm Registry

```python
class AlgorithmRegistry:
    """Central registry for algorithm instances."""

    _forecasters: Dict[str, Type[ForecastingAlgorithm]] = {}
    _detectors: Dict[str, Type[AnomalyDetector]] = {}

    @classmethod
    def register_forecaster(cls, algorithm: Type[ForecastingAlgorithm]):
        cls._forecasters[algorithm.name] = algorithm

    @classmethod
    def get_forecaster(cls, name: str) -> ForecastingAlgorithm:
        return cls._forecasters[name]()

    @classmethod
    def get_active_forecaster(cls) -> ForecastingAlgorithm:
        # Check feature flag / config for active algorithm
        active = config.get('active_forecaster', 'prophet')
        return cls.get_forecaster(active)
```

**[QA] Riley:** How do we handle algorithm failures gracefully? Prophet might throw exceptions on bad data.

**[Tech Lead] Jordan:** Good catch. We wrap in an Algorithm Service:

```python
class AlgorithmService:
    def generate_forecast(
        self,
        bottle_id: UUID,
        algorithm: str = None
    ) -> Optional[List[ForecastResult]]:
        try:
            forecaster = (
                AlgorithmRegistry.get_forecaster(algorithm)
                if algorithm
                else AlgorithmRegistry.get_active_forecaster()
            )

            prices = self.price_repo.get_verified_prices(bottle_id)

            if not forecaster.can_predict(len(prices)):
                logger.info(f"Insufficient data for {forecaster.name}")
                return None

            forecaster.fit(prices)
            return forecaster.predict([30, 60, 90, 180])

        except AlgorithmException as e:
            logger.error(f"Forecast failed: {e}")
            # Fallback to simpler algorithm or return None
            return self._fallback_forecast(bottle_id)
```

**[PO] Sam:** What about feature flags for rolling out new algorithms?

**[Tech Lead] Jordan:** The config layer handles that:

```python
# config/algorithms.py
ALGORITHM_CONFIG = {
    'forecasting': {
        'active': 'prophet',
        'fallback': 'simple_average',
        'enabled': ['prophet', 'simple_average'],
        'experimental': ['arima'],  # Admin-only or A/B test
    },
    'anomaly_detection': {
        'active': ['zscore', 'velocity'],
        'thresholds': {
            'zscore': 2.0,
            'velocity': 3.0,
        }
    }
}
```

We can gate experimental algorithms behind feature flags:

```python
def get_forecast(bottle_id: UUID, user: User = None):
    if user and user.is_admin and feature_flag('arima_preview'):
        return algorithm_service.generate_forecast(bottle_id, 'arima')
    return algorithm_service.generate_forecast(bottle_id)
```

**[QA] Riley:** I want comprehensive testing of the abstraction layer. Each algorithm implementation needs:
1. Unit tests with known datasets
2. Edge case tests (empty data, single point, outliers)
3. Performance benchmarks
4. Accuracy tracking over time (store predictions, compare to actuals)

**[Tech Lead] Jordan:** Agreed. We'll set up a test harness that runs all registered algorithms against reference datasets.

**[PM] Alex:** This abstraction layer is well-designed. It gives us the flexibility we need for Phase 2 algorithms without over-engineering MVP.

---

## Additional Architecture Decisions

**[Tech Lead] Jordan:** A few more architectural points to nail down:

### Caching Strategy

```
Redis caching:
- Bottle details: 1 hour TTL
- Price history: 15 minutes TTL
- Search results: 5 minutes TTL
- Forecasts: 24 hours TTL (invalidate on new verified price)
- User sessions: 24 hours TTL
- Rate limit counters: 1 minute sliding window
```

### Background Jobs

```
Celery tasks:
- scrape_source(source_id) - Run a scrape job
- generate_forecasts(bottle_id) - Regenerate forecasts
- calculate_trust_scores() - Daily trust score recalculation
- cleanup_expired_sessions() - Hourly cleanup
- send_email(user_id, template, data) - Email delivery
```

### Security Measures

- All passwords hashed with bcrypt (cost factor 12)
- JWT tokens with 24-hour expiry, refresh tokens with 7-day expiry
- HTTPS enforced in production
- CORS restricted to known origins
- SQL injection prevention via parameterized queries (SQLAlchemy)
- XSS prevention via template escaping
- CSRF tokens for state-changing operations
- Rate limiting on all endpoints
- Input validation via Pydantic models

**[QA] Riley:** Add pre-commit hooks for secrets scanning. No credentials in git, period.

**[Tech Lead] Jordan:** Absolutely. Our pre-commit config will include:
- `detect-secrets` - Catch hardcoded secrets
- `black` - Code formatting
- `isort` - Import sorting
- `mypy` - Type checking
- `pytest` - Run tests

---

## Decision Summary

**[PM] Alex:** Let's capture our decisions from this discussion.

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database Schema | UUID PKs, normalized with aliases table, cents for prices | Supports distribution, handles naming complexity, avoids float issues |
| API Design | RESTful with /api/v1 prefix, JSON envelope responses | Industry standard, versioned for evolution |
| Rate Limiting | Redis-backed, tiered by auth status | Protects resources, fair usage |
| Docker Setup | 5 services (web, db, redis, worker, scheduler) | Full stack locally, matches production |
| Algorithm Layer | Abstract base classes with registry | Swappable algorithms, feature-flagged rollout |
| Caching | Redis with tiered TTLs | Performance without stale data |
| Security | JWT + bcrypt, comprehensive measures | Defense in depth |

---

## Action Items

- [ ] [Jordan] Create ARCHITECTURE.md with full technical specification
- [ ] [Jordan] Write database migration scripts for schema
- [ ] [Jordan] Set up Docker Compose configuration
- [ ] [Jordan] Implement algorithm base classes
- [ ] [Riley] Define test strategy for algorithm layer
- [ ] [Alex] Create TIMELINE.md with milestone breakdown
- [ ] [Alex] Update RISK_REGISTER.md with architecture-related risks

---

### [Facilitator] Summary

**Phase:** Architecture & Design
**Status:** Decisions finalized, ready for documentation

**Key Decisions Made:**
1. PostgreSQL schema with 12 core tables, UUID primary keys, cents-based pricing
2. RESTful API with FastAPI, public/authenticated/admin endpoint tiers
3. Docker Compose with 5 services for full local development environment
4. Algorithm abstraction layer with registry pattern for swappable implementations

**Risks Identified:**
- Prophet installation complexity (mitigated by early Docker spike)
- Algorithm performance at scale (mitigated by caching and background processing)
- Schema migrations during development (mitigated by Alembic and clear versioning)

**Next Steps:**
1. Document architecture in ARCHITECTURE.md
2. Create detailed timeline with dependencies
3. Update risk register
4. Begin infrastructure setup

---
