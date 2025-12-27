# Technical Architecture: WTracker

**Created:** 2025-12-27
**Last Updated:** 2025-12-27
**Version:** 1.0
**Status:** Approved

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Technology Stack](#technology-stack)
4. [Database Design](#database-design)
5. [API Design](#api-design)
6. [Infrastructure Specification](#infrastructure-specification)
7. [Algorithm Integration Layer](#algorithm-integration-layer)
8. [Security Architecture](#security-architecture)
9. [Caching Strategy](#caching-strategy)
10. [Background Processing](#background-processing)
11. [Monitoring & Observability](#monitoring--observability)
12. [Architecture Decision Records](#architecture-decision-records)

---

## System Overview

WTracker is a price tracking and valuation engine for secondary market spirits. The system consists of four primary subsystems:

1. **Data Ingestion Pipeline** - Scrapes auction data, normalizes bottle names, validates prices
2. **Price Intelligence Engine** - Forecasting, anomaly detection, trust scoring
3. **User Platform** - Authentication, collections, submissions
4. **Admin & Moderation** - Queue management, audit logging, system health

### Component Architecture

```
                                    +------------------+
                                    |   Cloudflare     |
                                    |   (CDN/WAF)      |
                                    +--------+---------+
                                             |
                                    +--------v---------+
                                    |   Nginx          |
                                    |   (Reverse Proxy)|
                                    +--------+---------+
                                             |
              +------------------------------+------------------------------+
              |                              |                              |
    +---------v----------+        +----------v---------+        +-----------v---------+
    |    FastAPI Web     |        |   Celery Worker    |        |   Celery Beat       |
    |    Application     |        |   (Background)     |        |   (Scheduler)       |
    +----+------+--------+        +----+------+--------+        +----------+----------+
         |      |                      |      |                            |
         |      +----------------------+------+----------------------------+
         |                             |
    +----v----+                   +----v----+
    |  Redis  |                   |PostgreSQL|
    | (Cache) |                   | (Data)   |
    +---------+                   +----------+
```

### Data Flow

```
[Auction Sites] --> [Scrapy Spider] --> [Normalization] --> [Validation] --> [PostgreSQL]
                                                                                   |
                                                                                   v
[User Submission] --> [Fraud Detection] --> [Moderation Queue] --> [Approval] --> [PostgreSQL]
                                                                                   |
                                                                                   v
[PostgreSQL] --> [Algorithm Service] --> [Forecasts] --> [Cache] --> [API] --> [User]
```

---

## Technology Stack

| Layer | Technology | Version | Rationale |
|-------|------------|---------|-----------|
| **Language** | Python | 3.11+ | Data science ecosystem, async support |
| **Web Framework** | FastAPI | 0.104+ | High performance, automatic OpenAPI, type hints |
| **Database** | PostgreSQL | 15 | Time-series + relational, JSONB, extensible |
| **Cache/Queue** | Redis | 7 | Rate limiting, caching, Celery broker |
| **Task Queue** | Celery | 5.3+ | Background processing, scheduling |
| **Scraping** | Scrapy | 2.11+ | Robust, rate-limited, middleware support |
| **JS Rendering** | Playwright | 1.40+ | Headless browser for dynamic sites |
| **Forecasting** | Prophet | 1.1+ | Handles gaps, seasonality, uncertainty |
| **ORM** | SQLAlchemy | 2.0+ | Async support, powerful querying |
| **Migrations** | Alembic | 1.13+ | Version-controlled schema changes |
| **Validation** | Pydantic | 2.5+ | FastAPI integration, strict typing |
| **Auth** | python-jose | 3.3+ | JWT handling |
| **Hashing** | passlib | 1.7+ | bcrypt password hashing |
| **HTTP Client** | httpx | 0.25+ | Async HTTP for external APIs |
| **Templating** | Jinja2 | 3.1+ | Server-side rendering |
| **Frontend** | Alpine.js | 3.x | Minimal reactive JavaScript |
| **Charts** | Chart.js | 4.x | Price history visualization |
| **Container** | Docker | 24+ | Environment parity |
| **CI/CD** | GitHub Actions | N/A | Automated testing, deployment |

---

## Database Design

### Entity Relationship Diagram

```
                    +---------------+
                    |  data_sources |
                    +-------+-------+
                            |
                            | 1:N
                            v
+---------------+   +-------+-------+   +---------------+
| bottle_aliases|   |    prices     |   | scrape_runs   |
+-------+-------+   +-------+-------+   +---------------+
        |                   |
        | N:1               | N:1
        v                   v
+-------+-------+   +-------+-------+
|    bottles    |<--| submissions   |
+-------+-------+   +-------+-------+
        ^                   |
        |                   | N:1
        | N:1               v
+-------+-------+   +-------+-------+   +-------------------+
|collection_items|   |    users     |-->| moderation_queue  |
+-------+-------+   +-------+-------+   +--------+----------+
        |                                        |
        | N:1                                    | 1:N
        v                                        v
+-------+-------+                       +--------+----------+
|  collections  |                       | moderation_actions|
+---------------+                       +-------------------+

+-------------------+   +-------------------+
| price_forecasts   |   | algorithm_metrics |
+-------------------+   +-------------------+
```

### Table Definitions

#### bottles
Primary entity representing a unique bottle/release.

```sql
CREATE TABLE bottles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    distillery VARCHAR(255),
    bottle_type VARCHAR(50) NOT NULL DEFAULT 'bourbon',
    age_statement INTEGER,
    proof DECIMAL(5,2),
    size_ml INTEGER DEFAULT 750,
    release_year INTEGER,
    is_allocated BOOLEAN DEFAULT false,
    description TEXT,
    image_url VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT chk_bottle_type CHECK (bottle_type IN ('bourbon', 'scotch', 'rye', 'irish', 'japanese', 'other')),
    CONSTRAINT chk_age_positive CHECK (age_statement IS NULL OR age_statement > 0),
    CONSTRAINT chk_proof_range CHECK (proof IS NULL OR (proof >= 0 AND proof <= 200)),
    CONSTRAINT chk_size_positive CHECK (size_ml > 0)
);

CREATE INDEX idx_bottles_name ON bottles(name);
CREATE INDEX idx_bottles_distillery ON bottles(distillery);
CREATE INDEX idx_bottles_type ON bottles(bottle_type);
CREATE INDEX idx_bottles_created ON bottles(created_at DESC);
```

#### bottle_aliases
Maps alternative names to canonical bottles.

```sql
CREATE TABLE bottle_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bottle_id UUID NOT NULL REFERENCES bottles(id) ON DELETE CASCADE,
    alias_name VARCHAR(255) NOT NULL,
    is_primary BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT uq_alias_name UNIQUE (alias_name)
);

CREATE INDEX idx_aliases_bottle ON bottle_aliases(bottle_id);
CREATE INDEX idx_aliases_name ON bottle_aliases(alias_name);
CREATE INDEX idx_aliases_name_lower ON bottle_aliases(LOWER(alias_name));
```

#### users
User accounts with pseudonymous identity.

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL,
    email_hash VARCHAR(64) NOT NULL,  -- SHA-256 for lookups without exposing email
    email_verified BOOLEAN DEFAULT false,
    display_name VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    trust_score DECIMAL(3,2) DEFAULT 0.50,
    submission_count INTEGER DEFAULT 0,
    approved_count INTEGER DEFAULT 0,
    rejected_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    is_admin BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login_at TIMESTAMP WITH TIME ZONE,
    email_verification_token VARCHAR(255),
    email_verification_sent_at TIMESTAMP WITH TIME ZONE,
    password_reset_token VARCHAR(255),
    password_reset_sent_at TIMESTAMP WITH TIME ZONE,

    CONSTRAINT uq_email_hash UNIQUE (email_hash),
    CONSTRAINT uq_display_name UNIQUE (display_name),
    CONSTRAINT chk_trust_range CHECK (trust_score >= 0 AND trust_score <= 1)
);

CREATE INDEX idx_users_email_hash ON users(email_hash);
CREATE INDEX idx_users_display_name ON users(display_name);
CREATE INDEX idx_users_trust ON users(trust_score DESC);
```

#### data_sources
External data sources (auction houses, retailers).

```sql
CREATE TABLE data_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    base_url VARCHAR(500),
    is_active BOOLEAN DEFAULT true,
    priority INTEGER DEFAULT 100,  -- Lower = higher priority
    scrape_config JSONB DEFAULT '{}',
    last_scraped_at TIMESTAMP WITH TIME ZONE,
    last_successful_at TIMESTAMP WITH TIME ZONE,
    error_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT chk_source_type CHECK (source_type IN ('auction_house', 'retailer', 'other'))
);

CREATE INDEX idx_sources_active ON data_sources(is_active, priority);
```

#### scrape_runs
Audit log of scraping operations.

```sql
CREATE TABLE scrape_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES data_sources(id),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) DEFAULT 'running',
    items_found INTEGER DEFAULT 0,
    items_new INTEGER DEFAULT 0,
    items_updated INTEGER DEFAULT 0,
    items_skipped INTEGER DEFAULT 0,
    errors JSONB DEFAULT '[]',

    CONSTRAINT chk_run_status CHECK (status IN ('running', 'completed', 'failed', 'cancelled'))
);

CREATE INDEX idx_scrape_runs_source ON scrape_runs(source_id, started_at DESC);
CREATE INDEX idx_scrape_runs_status ON scrape_runs(status);
```

#### prices
Core time-series data for bottle prices.

```sql
CREATE TABLE prices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bottle_id UUID NOT NULL REFERENCES bottles(id) ON DELETE CASCADE,
    price_cents INTEGER NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    transaction_date DATE NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    source_id UUID REFERENCES data_sources(id),
    submission_id UUID,  -- FK added after submissions table
    external_id VARCHAR(255),  -- Original ID from source
    confidence_score DECIMAL(3,2) DEFAULT 1.00,
    is_verified BOOLEAN DEFAULT false,
    is_outlier BOOLEAN DEFAULT false,
    outlier_reason VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT chk_price_positive CHECK (price_cents > 0),
    CONSTRAINT chk_source_type CHECK (source_type IN ('auction', 'retail', 'crowdsourced')),
    CONSTRAINT chk_confidence CHECK (confidence_score >= 0 AND confidence_score <= 1)
);

CREATE INDEX idx_prices_bottle_date ON prices(bottle_id, transaction_date DESC);
CREATE INDEX idx_prices_date ON prices(transaction_date DESC);
CREATE INDEX idx_prices_source ON prices(source_type, source_id);
CREATE INDEX idx_prices_verified ON prices(is_verified, is_outlier);
CREATE INDEX idx_prices_external ON prices(source_id, external_id);
```

#### submissions
User-submitted price reports.

```sql
CREATE TABLE submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    bottle_id UUID NOT NULL REFERENCES bottles(id),
    price_cents INTEGER NOT NULL,
    transaction_date DATE NOT NULL,
    transaction_type VARCHAR(50) DEFAULT 'purchase',
    notes TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    confidence_score DECIMAL(3,2),
    moderation_flags JSONB DEFAULT '[]',
    flag_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    reviewed_by UUID REFERENCES users(id),
    review_notes TEXT,

    CONSTRAINT chk_submission_status CHECK (status IN ('pending', 'approved', 'rejected', 'flagged')),
    CONSTRAINT chk_transaction_type CHECK (transaction_type IN ('purchase', 'sale', 'trade', 'auction'))
);

-- Add FK to prices table
ALTER TABLE prices ADD CONSTRAINT fk_prices_submission
    FOREIGN KEY (submission_id) REFERENCES submissions(id);

CREATE INDEX idx_submissions_user ON submissions(user_id, created_at DESC);
CREATE INDEX idx_submissions_bottle ON submissions(bottle_id);
CREATE INDEX idx_submissions_status ON submissions(status);
CREATE INDEX idx_submissions_pending ON submissions(status, created_at) WHERE status = 'pending';
```

#### collections
User bottle collections.

```sql
CREATE TABLE collections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL DEFAULT 'My Collection',
    description TEXT,
    is_public BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_collections_user ON collections(user_id);
CREATE INDEX idx_collections_public ON collections(is_public) WHERE is_public = true;
```

#### collection_items
Bottles within a collection.

```sql
CREATE TABLE collection_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    bottle_id UUID NOT NULL REFERENCES bottles(id),
    quantity INTEGER DEFAULT 1,
    purchase_price_cents INTEGER,
    purchase_date DATE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT uq_collection_bottle UNIQUE (collection_id, bottle_id),
    CONSTRAINT chk_quantity_positive CHECK (quantity > 0)
);

CREATE INDEX idx_collection_items_collection ON collection_items(collection_id);
CREATE INDEX idx_collection_items_bottle ON collection_items(bottle_id);
```

#### moderation_queue
Items flagged for moderator review.

```sql
CREATE TABLE moderation_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id UUID NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    flag_type VARCHAR(50) NOT NULL,
    flag_reason TEXT,
    severity VARCHAR(20) DEFAULT 'medium',
    status VARCHAR(50) DEFAULT 'pending',
    assigned_to UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE,

    CONSTRAINT chk_flag_type CHECK (flag_type IN (
        'price_outlier', 'high_volume', 'new_account',
        'duplicate', 'velocity', 'manual', 'pattern'
    )),
    CONSTRAINT chk_severity CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT chk_mod_status CHECK (status IN ('pending', 'in_review', 'resolved', 'escalated'))
);

CREATE INDEX idx_mod_queue_status ON moderation_queue(status, severity DESC, created_at);
CREATE INDEX idx_mod_queue_submission ON moderation_queue(submission_id);
CREATE INDEX idx_mod_queue_assigned ON moderation_queue(assigned_to) WHERE assigned_to IS NOT NULL;
```

#### moderation_actions
Audit log of moderation decisions.

```sql
CREATE TABLE moderation_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_item_id UUID NOT NULL REFERENCES moderation_queue(id),
    moderator_id UUID NOT NULL REFERENCES users(id),
    action VARCHAR(50) NOT NULL,
    previous_status VARCHAR(50),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT chk_mod_action CHECK (action IN (
        'approve', 'reject', 'adjust_weight', 'ban_user',
        'escalate', 'assign', 'unassign', 'request_info'
    ))
);

CREATE INDEX idx_mod_actions_queue ON moderation_actions(queue_item_id);
CREATE INDEX idx_mod_actions_moderator ON moderation_actions(moderator_id, created_at DESC);
```

#### price_forecasts
Stored algorithm predictions.

```sql
CREATE TABLE price_forecasts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bottle_id UUID NOT NULL REFERENCES bottles(id) ON DELETE CASCADE,
    algorithm VARCHAR(50) NOT NULL,
    forecast_date DATE NOT NULL,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    price_low_cents INTEGER NOT NULL,
    price_mid_cents INTEGER NOT NULL,
    price_high_cents INTEGER NOT NULL,
    confidence_level DECIMAL(3,2) DEFAULT 0.70,
    data_points_used INTEGER NOT NULL,
    is_current BOOLEAN DEFAULT true,

    CONSTRAINT chk_price_order CHECK (price_low_cents <= price_mid_cents AND price_mid_cents <= price_high_cents),
    CONSTRAINT chk_forecast_confidence CHECK (confidence_level > 0 AND confidence_level < 1)
);

CREATE INDEX idx_forecasts_bottle_current ON price_forecasts(bottle_id, is_current) WHERE is_current = true;
CREATE INDEX idx_forecasts_algorithm ON price_forecasts(algorithm, generated_at DESC);
```

#### algorithm_metrics
Performance tracking for algorithms.

```sql
CREATE TABLE algorithm_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    algorithm VARCHAR(50) NOT NULL,
    bottle_id UUID REFERENCES bottles(id),  -- NULL for aggregate metrics
    metric_name VARCHAR(50) NOT NULL,
    metric_value DECIMAL(10,4) NOT NULL,
    sample_size INTEGER,
    measured_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    period_start DATE,
    period_end DATE
);

CREATE INDEX idx_metrics_algorithm ON algorithm_metrics(algorithm, metric_name, measured_at DESC);
CREATE INDEX idx_metrics_bottle ON algorithm_metrics(bottle_id) WHERE bottle_id IS NOT NULL;
```

### Materialized Views

For frequently accessed aggregations:

```sql
-- Bottle price statistics
CREATE MATERIALIZED VIEW mv_bottle_stats AS
SELECT
    b.id AS bottle_id,
    COUNT(p.id) AS price_count,
    MIN(p.price_cents) AS price_min,
    MAX(p.price_cents) AS price_max,
    AVG(p.price_cents)::INTEGER AS price_avg,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY p.price_cents)::INTEGER AS price_median,
    STDDEV(p.price_cents)::INTEGER AS price_stddev,
    MIN(p.transaction_date) AS first_sale,
    MAX(p.transaction_date) AS last_sale,
    COUNT(p.id) FILTER (WHERE p.transaction_date > CURRENT_DATE - INTERVAL '30 days') AS sales_30d,
    AVG(p.price_cents) FILTER (WHERE p.transaction_date > CURRENT_DATE - INTERVAL '30 days')::INTEGER AS avg_30d
FROM bottles b
LEFT JOIN prices p ON b.id = p.bottle_id AND p.is_verified = true AND p.is_outlier = false
GROUP BY b.id;

CREATE UNIQUE INDEX idx_mv_bottle_stats ON mv_bottle_stats(bottle_id);

-- Refresh strategy: Every 15 minutes via Celery Beat
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mv_bottle_stats;
```

---

## API Design

### Base URL Structure

```
Production: https://api.wtracker.app/api/v1
Development: http://localhost:8000/api/v1
```

### Response Format

All responses use a consistent JSON envelope:

**Success Response:**
```json
{
    "status": "success",
    "data": { },
    "meta": {
        "page": 1,
        "limit": 20,
        "total": 150,
        "has_more": true
    }
}
```

**Error Response:**
```json
{
    "status": "error",
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Human-readable error message",
        "details": {
            "field": "price",
            "issue": "must be positive integer"
        }
    }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Invalid request parameters |
| `UNAUTHORIZED` | 401 | Missing or invalid authentication |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `NOT_FOUND` | 404 | Resource does not exist |
| `CONFLICT` | 409 | Resource already exists |
| `RATE_LIMITED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Server error |
| `SERVICE_UNAVAILABLE` | 503 | Service temporarily unavailable |

### Authentication

JWT-based authentication with Bearer tokens:

```
Authorization: Bearer <access_token>
```

Token structure:
- Access token: 24-hour expiry
- Refresh token: 7-day expiry, stored in HttpOnly cookie

### Endpoint Specification

#### Public Endpoints

##### GET /bottles
List and search bottles.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | Full-text search query |
| `distillery` | string | Filter by distillery |
| `type` | enum | bourbon, scotch, rye, irish, japanese, other |
| `min_price` | integer | Minimum average price (cents) |
| `max_price` | integer | Maximum average price (cents) |
| `age_min` | integer | Minimum age statement |
| `age_max` | integer | Maximum age statement |
| `allocated` | boolean | Filter allocated bottles |
| `sort` | string | name, price_avg, last_sale, created_at |
| `order` | string | asc, desc |
| `page` | integer | Page number (default: 1) |
| `limit` | integer | Results per page (default: 20, max: 100) |

**Response:**
```json
{
    "status": "success",
    "data": {
        "bottles": [
            {
                "id": "uuid",
                "name": "George T. Stagg",
                "distillery": "Buffalo Trace",
                "type": "bourbon",
                "age_statement": null,
                "proof": 116.9,
                "size_ml": 750,
                "is_allocated": true,
                "stats": {
                    "price_avg": 85000,
                    "price_min": 60000,
                    "price_max": 120000,
                    "last_sale": "2025-12-15",
                    "sale_count": 47
                }
            }
        ]
    },
    "meta": {
        "page": 1,
        "limit": 20,
        "total": 1523
    }
}
```

##### GET /bottles/{id}
Get bottle details.

**Response:**
```json
{
    "status": "success",
    "data": {
        "id": "uuid",
        "name": "George T. Stagg",
        "aliases": ["GTS", "Stagg", "BT Stagg"],
        "distillery": "Buffalo Trace",
        "type": "bourbon",
        "age_statement": null,
        "proof": 116.9,
        "size_ml": 750,
        "release_year": 2024,
        "is_allocated": true,
        "description": "Annual limited release...",
        "stats": {
            "price_avg": 85000,
            "price_median": 82500,
            "price_min": 60000,
            "price_max": 120000,
            "price_stddev": 15000,
            "first_sale": "2024-10-15",
            "last_sale": "2025-12-15",
            "total_sales": 47,
            "sales_30d": 12,
            "avg_30d": 87500
        },
        "data_sources": {
            "auction": 35,
            "retail": 8,
            "crowdsourced": 4
        }
    }
}
```

##### GET /bottles/{id}/prices
Get price history for a bottle.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `start_date` | date | Start of date range |
| `end_date` | date | End of date range |
| `source` | enum | auction, retail, crowdsourced |
| `verified_only` | boolean | Exclude outliers (default: true) |
| `limit` | integer | Max results (default: 500) |

**Response:**
```json
{
    "status": "success",
    "data": {
        "bottle_id": "uuid",
        "prices": [
            {
                "date": "2025-12-15",
                "price_cents": 85000,
                "source_type": "auction",
                "source_name": "Unicorn Auctions",
                "is_verified": true
            }
        ],
        "aggregations": {
            "by_month": [
                {"month": "2025-12", "avg": 85000, "count": 5},
                {"month": "2025-11", "avg": 82000, "count": 8}
            ]
        }
    }
}
```

##### GET /bottles/{id}/forecasts
Get price forecasts for a bottle.

**Response:**
```json
{
    "status": "success",
    "data": {
        "bottle_id": "uuid",
        "generated_at": "2025-12-27T10:00:00Z",
        "algorithm": "prophet",
        "data_points_used": 47,
        "confidence_level": 0.70,
        "forecasts": [
            {
                "horizon_days": 30,
                "forecast_date": "2026-01-27",
                "price_low": 80000,
                "price_mid": 87000,
                "price_high": 95000
            },
            {
                "horizon_days": 90,
                "forecast_date": "2026-03-27",
                "price_low": 78000,
                "price_mid": 90000,
                "price_high": 105000
            }
        ],
        "disclaimer": "Forecasts are statistical projections based on historical data. Actual prices may vary significantly."
    }
}
```

##### GET /bottles/search
Full-text search with suggestions.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | Search query (required, min 2 chars) |
| `limit` | integer | Max results (default: 10) |

**Response:**
```json
{
    "status": "success",
    "data": {
        "results": [
            {
                "id": "uuid",
                "name": "George T. Stagg",
                "distillery": "Buffalo Trace",
                "type": "bourbon",
                "price_avg": 85000,
                "match_type": "name"
            }
        ],
        "suggestions": ["Stagg Jr", "Stagg Antique Collection"]
    }
}
```

#### Authentication Endpoints

##### POST /auth/register
Create a new account.

**Request:**
```json
{
    "email": "user@example.com",
    "display_name": "WhiskeyCollector",
    "password": "SecurePassword123!"
}
```

**Response:**
```json
{
    "status": "success",
    "data": {
        "user_id": "uuid",
        "display_name": "WhiskeyCollector",
        "email_verification_sent": true
    }
}
```

##### POST /auth/login
Authenticate and receive tokens.

**Request:**
```json
{
    "email": "user@example.com",
    "password": "SecurePassword123!"
}
```

**Response:**
```json
{
    "status": "success",
    "data": {
        "access_token": "eyJ...",
        "token_type": "bearer",
        "expires_in": 86400,
        "user": {
            "id": "uuid",
            "display_name": "WhiskeyCollector",
            "trust_score": 0.75,
            "is_admin": false
        }
    }
}
```

##### POST /auth/verify-email
Verify email address.

**Request:**
```json
{
    "token": "verification-token-from-email"
}
```

##### POST /auth/refresh
Refresh access token.

**Response:**
```json
{
    "status": "success",
    "data": {
        "access_token": "eyJ...",
        "expires_in": 86400
    }
}
```

##### POST /auth/password-reset
Initiate password reset.

**Request:**
```json
{
    "email": "user@example.com"
}
```

##### POST /auth/password-reset/confirm
Complete password reset.

**Request:**
```json
{
    "token": "reset-token-from-email",
    "new_password": "NewSecurePassword123!"
}
```

#### User Endpoints (Authenticated)

##### GET /users/me
Get current user profile.

##### PUT /users/me
Update profile.

**Request:**
```json
{
    "display_name": "NewDisplayName"
}
```

#### Submission Endpoints (Authenticated)

##### POST /submissions
Submit a price report.

**Request:**
```json
{
    "bottle_id": "uuid",
    "price_cents": 85000,
    "transaction_date": "2025-12-20",
    "transaction_type": "purchase",
    "notes": "Local shop, great condition"
}
```

**Response:**
```json
{
    "status": "success",
    "data": {
        "submission_id": "uuid",
        "status": "pending",
        "message": "Submission received. Pending review."
    }
}
```

##### GET /submissions/mine
Get user's submission history.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | enum | pending, approved, rejected, flagged |
| `page` | integer | Page number |
| `limit` | integer | Results per page |

#### Collection Endpoints (Authenticated)

##### GET /collections
List user's collections.

##### POST /collections
Create a new collection.

**Request:**
```json
{
    "name": "Kentucky Gems",
    "description": "My best bourbon finds",
    "is_public": false
}
```

##### GET /collections/{id}
Get collection with items and valuation.

**Response:**
```json
{
    "status": "success",
    "data": {
        "id": "uuid",
        "name": "Kentucky Gems",
        "items": [
            {
                "id": "uuid",
                "bottle": {
                    "id": "uuid",
                    "name": "George T. Stagg",
                    "current_value": 85000
                },
                "quantity": 2,
                "purchase_price_cents": 60000,
                "purchase_date": "2024-11-01"
            }
        ],
        "valuation": {
            "total_value": 170000,
            "total_cost": 120000,
            "gain_loss": 50000,
            "gain_loss_pct": 41.67
        }
    }
}
```

##### POST /collections/{id}/items
Add bottle to collection.

**Request:**
```json
{
    "bottle_id": "uuid",
    "quantity": 1,
    "purchase_price_cents": 60000,
    "purchase_date": "2024-11-01",
    "notes": "Birthday gift"
}
```

##### DELETE /collections/{id}/items/{item_id}
Remove bottle from collection.

#### Admin Endpoints (Admin Only)

##### GET /admin/moderation/queue
Get moderation queue.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | enum | pending, in_review, resolved, escalated |
| `severity` | enum | low, medium, high, critical |
| `flag_type` | enum | price_outlier, high_volume, etc. |
| `assigned_to` | uuid | Filter by assignee |

##### POST /admin/moderation/{id}/approve
Approve a flagged submission.

**Request:**
```json
{
    "notes": "Verified against auction records",
    "adjust_weight": 1.0
}
```

##### POST /admin/moderation/{id}/reject
Reject a flagged submission.

**Request:**
```json
{
    "notes": "Price inconsistent with market",
    "ban_user": false
}
```

##### GET /admin/users
List users with management info.

##### PUT /admin/users/{id}/trust
Adjust user trust score.

**Request:**
```json
{
    "trust_score": 0.25,
    "reason": "Multiple rejected submissions"
}
```

##### GET /admin/scrape/status
Get scraping system status.

##### POST /admin/scrape/{source_id}/run
Trigger manual scrape.

##### GET /admin/algorithms/metrics
Get algorithm performance metrics.

### Rate Limiting

| Endpoint Category | Limit | Window |
|-------------------|-------|--------|
| Public (unauthenticated) | 60 requests | 1 minute |
| Authenticated | 120 requests | 1 minute |
| Submissions | 10 submissions | 1 hour |
| Auth endpoints | 10 requests | 1 minute |
| Admin | Unlimited | N/A |

Rate limit headers:
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1703680000
```

---

## Infrastructure Specification

### Docker Compose Configuration

#### docker-compose.yml (Development)

```yaml
version: '3.8'

services:
  web:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: wtracker-web
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=development
      - DEBUG=true
    env_file:
      - .env
    volumes:
      - ./backend:/app
      - ./backend/static:/app/static
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    networks:
      - wtracker-network

  db:
    image: postgres:15-alpine
    container_name: wtracker-db
    environment:
      POSTGRES_DB: ${DB_NAME:-wtracker}
      POSTGRES_USER: ${DB_USER:-wtracker}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./database/init.sql:/docker-entrypoint-initdb.d/01-init.sql
      - ./database/seed.sql:/docker-entrypoint-initdb.d/02-seed.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-wtracker} -d ${DB_NAME:-wtracker}"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - wtracker-network

  redis:
    image: redis:7-alpine
    container_name: wtracker-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    networks:
      - wtracker-network

  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: wtracker-worker
    env_file:
      - .env
    volumes:
      - ./backend:/app
    depends_on:
      - db
      - redis
    command: celery -A app.tasks.celery_app worker --loglevel=info --concurrency=2
    networks:
      - wtracker-network

  scheduler:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: wtracker-scheduler
    env_file:
      - .env
    volumes:
      - ./backend:/app
    depends_on:
      - db
      - redis
      - worker
    command: celery -A app.tasks.celery_app beat --loglevel=info
    networks:
      - wtracker-network

  # Optional: Adminer for database management
  adminer:
    image: adminer
    container_name: wtracker-adminer
    ports:
      - "8080:8080"
    depends_on:
      - db
    networks:
      - wtracker-network
    profiles:
      - debug

volumes:
  postgres_data:
  redis_data:

networks:
  wtracker-network:
    driver: bridge
```

#### docker-compose.test.yml (Testing)

```yaml
version: '3.8'

services:
  test:
    build:
      context: ./backend
      dockerfile: Dockerfile.test
    environment:
      - ENVIRONMENT=test
      - DB_HOST=db-test
      - DB_NAME=wtracker_test
      - REDIS_URL=redis://redis-test:6379/1
    env_file:
      - .env.test
    depends_on:
      db-test:
        condition: service_healthy
      redis-test:
        condition: service_started
    command: pytest --cov=app --cov-report=xml -v
    networks:
      - wtracker-test

  db-test:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: wtracker_test
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
    tmpfs:
      - /var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U test -d wtracker_test"]
      interval: 2s
      timeout: 2s
      retries: 5
    networks:
      - wtracker-test

  redis-test:
    image: redis:7-alpine
    networks:
      - wtracker-test

networks:
  wtracker-test:
    driver: bridge
```

#### docker-compose.prod.yml (Production)

```yaml
version: '3.8'

services:
  web:
    image: wtracker/web:${VERSION:-latest}
    container_name: wtracker-web
    restart: unless-stopped
    environment:
      - ENVIRONMENT=production
      - DEBUG=false
    env_file:
      - .env.prod
    depends_on:
      - db
      - redis
    command: gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
    networks:
      - wtracker-network
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 1G

  db:
    image: postgres:15-alpine
    container_name: wtracker-db
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - wtracker-network
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M

  redis:
    image: redis:7-alpine
    container_name: wtracker-redis
    restart: unless-stopped
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes --maxmemory 128mb --maxmemory-policy allkeys-lru
    networks:
      - wtracker-network

  worker:
    image: wtracker/web:${VERSION:-latest}
    container_name: wtracker-worker
    restart: unless-stopped
    env_file:
      - .env.prod
    depends_on:
      - db
      - redis
    command: celery -A app.tasks.celery_app worker --loglevel=warning --concurrency=2
    networks:
      - wtracker-network

  scheduler:
    image: wtracker/web:${VERSION:-latest}
    container_name: wtracker-scheduler
    restart: unless-stopped
    env_file:
      - .env.prod
    depends_on:
      - worker
    command: celery -A app.tasks.celery_app beat --loglevel=warning
    networks:
      - wtracker-network

  nginx:
    image: nginx:alpine
    container_name: wtracker-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - ./backend/static:/var/www/static:ro
    depends_on:
      - web
    networks:
      - wtracker-network

volumes:
  postgres_data:
  redis_data:

networks:
  wtracker-network:
    driver: bridge
```

### Backend Dockerfile

```dockerfile
# backend/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Environment Variables

```bash
# .env.example
# Database
DB_HOST=db
DB_PORT=5432
DB_NAME=wtracker
DB_USER=wtracker
DB_PASSWORD=<generate-secure-password>

# Redis
REDIS_URL=redis://redis:6379/0

# Security
SECRET_KEY=<generate-secure-key>
JWT_SECRET_KEY=<generate-secure-key>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Email (for verification)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=<email-user>
SMTP_PASSWORD=<email-password>
FROM_EMAIL=noreply@wtracker.app

# Application
ENVIRONMENT=development
DEBUG=true
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000

# Scraping
SCRAPE_USER_AGENT=WTracker/1.0 (contact@wtracker.app)
SCRAPE_DELAY_SECONDS=2

# Feature Flags
FEATURE_PROPHET_ENABLED=true
FEATURE_ARIMA_ENABLED=false
```

---

## Algorithm Integration Layer

### Architecture Overview

```
+-------------------+     +-------------------+     +-------------------+
| Algorithm Registry|---->| Algorithm Service |---->| Result Store      |
+-------------------+     +-------------------+     +-------------------+
         |                        |                        |
         v                        v                        v
+-------------------+     +-------------------+     +-------------------+
| Forecasters       |     | Anomaly Detectors |     | price_forecasts   |
| - Prophet         |     | - ZScore          |     | algorithm_metrics |
| - SimpleAverage   |     | - Velocity        |     +-------------------+
| - MonteCarlo      |     | - IsolationForest |
+-------------------+     +-------------------+
```

### Base Interfaces

```python
# app/algorithms/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import List, Optional
from enum import Enum

class AlgorithmType(Enum):
    FORECASTER = "forecaster"
    ANOMALY_DETECTOR = "anomaly_detector"
    TRUST_SCORER = "trust_scorer"

@dataclass
class ForecastResult:
    """Result of a price forecast."""
    forecast_date: date
    price_low_cents: int
    price_mid_cents: int
    price_high_cents: int
    confidence_level: float
    data_points_used: int
    algorithm: str

    def to_dict(self) -> dict:
        return {
            "forecast_date": self.forecast_date.isoformat(),
            "price_low": self.price_low_cents,
            "price_mid": self.price_mid_cents,
            "price_high": self.price_high_cents,
            "confidence": self.confidence_level,
            "data_points": self.data_points_used,
            "algorithm": self.algorithm
        }

@dataclass
class AnomalyResult:
    """Result of anomaly detection."""
    is_anomaly: bool
    anomaly_score: float  # 0-1, higher = more anomalous
    reason: Optional[str]
    recommended_action: str  # 'accept', 'flag', 'reject'
    detector: str

    def to_dict(self) -> dict:
        return {
            "is_anomaly": self.is_anomaly,
            "score": self.anomaly_score,
            "reason": self.reason,
            "action": self.recommended_action,
            "detector": self.detector
        }

@dataclass
class TrustScore:
    """User trust score result."""
    score: float  # 0-1
    factors: dict
    updated_at: date

class BaseAlgorithm(ABC):
    """Base class for all algorithms."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique algorithm identifier."""
        pass

    @property
    @abstractmethod
    def algorithm_type(self) -> AlgorithmType:
        """Type of algorithm."""
        pass

    @property
    def version(self) -> str:
        """Algorithm version."""
        return "1.0.0"

    @property
    def description(self) -> str:
        """Human-readable description."""
        return ""

class ForecastingAlgorithm(BaseAlgorithm):
    """Base class for forecasting algorithms."""

    algorithm_type = AlgorithmType.FORECASTER

    @property
    @abstractmethod
    def min_data_points(self) -> int:
        """Minimum data points required."""
        pass

    @abstractmethod
    def fit(self, prices: List[tuple[date, int]]) -> None:
        """
        Train on historical price data.

        Args:
            prices: List of (date, price_cents) tuples, sorted by date
        """
        pass

    @abstractmethod
    def predict(
        self,
        horizon_days: List[int],
        confidence_level: float = 0.70
    ) -> List[ForecastResult]:
        """
        Generate predictions for specified horizons.

        Args:
            horizon_days: List of days into the future [30, 60, 90]
            confidence_level: Confidence interval (0-1)

        Returns:
            List of ForecastResult objects
        """
        pass

    def can_predict(self, data_points: int) -> bool:
        """Check if sufficient data for prediction."""
        return data_points >= self.min_data_points

class AnomalyDetector(BaseAlgorithm):
    """Base class for anomaly detection algorithms."""

    algorithm_type = AlgorithmType.ANOMALY_DETECTOR

    @abstractmethod
    def fit(self, prices: List[int]) -> None:
        """
        Train on historical prices for a bottle.

        Args:
            prices: List of price values in cents
        """
        pass

    @abstractmethod
    def detect(self, price: int, context: dict = None) -> AnomalyResult:
        """
        Check if a price is anomalous.

        Args:
            price: Price to check in cents
            context: Optional context (user_id, submission_count, etc.)

        Returns:
            AnomalyResult with detection details
        """
        pass

class TrustScorer(BaseAlgorithm):
    """Base class for user trust scoring."""

    algorithm_type = AlgorithmType.TRUST_SCORER

    @abstractmethod
    def calculate(self, user_stats: dict) -> TrustScore:
        """
        Calculate trust score for a user.

        Args:
            user_stats: Dict with submission history, approval rates, etc.

        Returns:
            TrustScore with score and contributing factors
        """
        pass
```

### Concrete Implementations

```python
# app/algorithms/forecasters/prophet_forecaster.py
from prophet import Prophet
import pandas as pd
from datetime import date, timedelta
from typing import List
from app.algorithms.base import ForecastingAlgorithm, ForecastResult

class ProphetForecaster(ForecastingAlgorithm):
    """Facebook Prophet-based price forecasting."""

    name = "prophet"
    min_data_points = 10
    description = "Time-series forecasting with automatic seasonality detection"

    def __init__(self):
        self.model = None
        self._fitted = False

    def fit(self, prices: List[tuple[date, int]]) -> None:
        # Convert to Prophet's expected format
        df = pd.DataFrame(prices, columns=['ds', 'y'])
        df['ds'] = pd.to_datetime(df['ds'])
        df['y'] = df['y'] / 100  # Convert cents to dollars for stability

        self.model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False,
            interval_width=0.70,  # 70% confidence interval
            changepoint_prior_scale=0.05  # Conservative changepoint detection
        )
        self.model.fit(df)
        self._fitted = True

    def predict(
        self,
        horizon_days: List[int],
        confidence_level: float = 0.70
    ) -> List[ForecastResult]:
        if not self._fitted:
            raise ValueError("Model must be fitted before prediction")

        # Get the maximum horizon needed
        max_horizon = max(horizon_days)
        future = self.model.make_future_dataframe(periods=max_horizon)
        forecast = self.model.predict(future)

        results = []
        today = date.today()

        for days in horizon_days:
            forecast_date = today + timedelta(days=days)
            row = forecast[forecast['ds'].dt.date == forecast_date].iloc[0]

            results.append(ForecastResult(
                forecast_date=forecast_date,
                price_low_cents=int(row['yhat_lower'] * 100),
                price_mid_cents=int(row['yhat'] * 100),
                price_high_cents=int(row['yhat_upper'] * 100),
                confidence_level=confidence_level,
                data_points_used=len(self.model.history),
                algorithm=self.name
            ))

        return results

# app/algorithms/forecasters/simple_average.py
class SimpleAverageForecaster(ForecastingAlgorithm):
    """Fallback forecaster using simple moving average."""

    name = "simple_average"
    min_data_points = 3
    description = "Simple moving average projection"

    def __init__(self, window: int = 10):
        self.window = window
        self.prices = []
        self.dates = []

    def fit(self, prices: List[tuple[date, int]]) -> None:
        self.dates = [p[0] for p in prices]
        self.prices = [p[1] for p in prices]

    def predict(
        self,
        horizon_days: List[int],
        confidence_level: float = 0.70
    ) -> List[ForecastResult]:
        import statistics

        recent = self.prices[-self.window:] if len(self.prices) >= self.window else self.prices
        avg = statistics.mean(recent)
        std = statistics.stdev(recent) if len(recent) > 1 else avg * 0.1

        # Z-score for confidence level
        z = 1.04  # Approximate for 70%

        results = []
        today = date.today()

        for days in horizon_days:
            forecast_date = today + timedelta(days=days)

            results.append(ForecastResult(
                forecast_date=forecast_date,
                price_low_cents=int(avg - z * std),
                price_mid_cents=int(avg),
                price_high_cents=int(avg + z * std),
                confidence_level=confidence_level,
                data_points_used=len(self.prices),
                algorithm=self.name
            ))

        return results
```

```python
# app/algorithms/anomaly/zscore_detector.py
import statistics
from typing import List, Optional
from app.algorithms.base import AnomalyDetector, AnomalyResult

class ZScoreDetector(AnomalyDetector):
    """Statistical Z-score based anomaly detection."""

    name = "zscore"
    description = "Detects prices outside normal distribution bounds"

    def __init__(self, threshold: float = 2.0):
        self.threshold = threshold
        self.mean = 0
        self.std = 0
        self._fitted = False

    def fit(self, prices: List[int]) -> None:
        if len(prices) < 2:
            self.mean = prices[0] if prices else 0
            self.std = self.mean * 0.2  # Default 20% std
        else:
            self.mean = statistics.mean(prices)
            self.std = statistics.stdev(prices)
        self._fitted = True

    def detect(self, price: int, context: dict = None) -> AnomalyResult:
        if not self._fitted:
            raise ValueError("Detector must be fitted first")

        if self.std == 0:
            z_score = 0 if price == self.mean else float('inf')
        else:
            z_score = abs(price - self.mean) / self.std

        is_anomaly = z_score > self.threshold

        # Determine action based on severity
        if z_score > self.threshold * 2:
            action = 'reject'
        elif z_score > self.threshold:
            action = 'flag'
        else:
            action = 'accept'

        return AnomalyResult(
            is_anomaly=is_anomaly,
            anomaly_score=min(z_score / 4, 1.0),  # Normalize to 0-1
            reason=f"Z-score: {z_score:.2f} (threshold: {self.threshold})" if is_anomaly else None,
            recommended_action=action,
            detector=self.name
        )

# app/algorithms/anomaly/velocity_detector.py
class VelocityDetector(AnomalyDetector):
    """Detects suspicious submission velocity patterns."""

    name = "velocity"
    description = "Detects abnormal submission frequency"

    def __init__(self, submissions_per_hour_threshold: int = 5):
        self.threshold = submissions_per_hour_threshold

    def fit(self, prices: List[int]) -> None:
        # No fitting required for velocity detection
        pass

    def detect(self, price: int, context: dict = None) -> AnomalyResult:
        if not context:
            return AnomalyResult(
                is_anomaly=False,
                anomaly_score=0,
                reason=None,
                recommended_action='accept',
                detector=self.name
            )

        submissions_last_hour = context.get('submissions_last_hour', 0)
        account_age_days = context.get('account_age_days', 365)

        # New accounts with high velocity are suspicious
        velocity_score = submissions_last_hour / self.threshold

        if account_age_days < 7:
            velocity_score *= 2  # Double penalty for new accounts

        is_anomaly = velocity_score > 1.0

        return AnomalyResult(
            is_anomaly=is_anomaly,
            anomaly_score=min(velocity_score, 1.0),
            reason=f"High submission velocity: {submissions_last_hour}/hour" if is_anomaly else None,
            recommended_action='flag' if is_anomaly else 'accept',
            detector=self.name
        )
```

### Algorithm Registry

```python
# app/algorithms/registry.py
from typing import Dict, Type, List, Optional
from app.algorithms.base import (
    BaseAlgorithm, ForecastingAlgorithm, AnomalyDetector,
    TrustScorer, AlgorithmType
)
from app.core.config import settings

class AlgorithmRegistry:
    """Central registry for algorithm implementations."""

    _forecasters: Dict[str, Type[ForecastingAlgorithm]] = {}
    _detectors: Dict[str, Type[AnomalyDetector]] = {}
    _trust_scorers: Dict[str, Type[TrustScorer]] = {}

    @classmethod
    def register(cls, algorithm_class: Type[BaseAlgorithm]) -> Type[BaseAlgorithm]:
        """Decorator to register an algorithm."""
        if algorithm_class.algorithm_type == AlgorithmType.FORECASTER:
            cls._forecasters[algorithm_class.name] = algorithm_class
        elif algorithm_class.algorithm_type == AlgorithmType.ANOMALY_DETECTOR:
            cls._detectors[algorithm_class.name] = algorithm_class
        elif algorithm_class.algorithm_type == AlgorithmType.TRUST_SCORER:
            cls._trust_scorers[algorithm_class.name] = algorithm_class
        return algorithm_class

    @classmethod
    def get_forecaster(cls, name: str) -> ForecastingAlgorithm:
        """Get a forecaster instance by name."""
        if name not in cls._forecasters:
            raise KeyError(f"Unknown forecaster: {name}")
        return cls._forecasters[name]()

    @classmethod
    def get_active_forecaster(cls) -> ForecastingAlgorithm:
        """Get the currently active forecaster based on config."""
        active = settings.ACTIVE_FORECASTER
        return cls.get_forecaster(active)

    @classmethod
    def get_detector(cls, name: str) -> AnomalyDetector:
        """Get a detector instance by name."""
        if name not in cls._detectors:
            raise KeyError(f"Unknown detector: {name}")
        return cls._detectors[name]()

    @classmethod
    def get_active_detectors(cls) -> List[AnomalyDetector]:
        """Get all active anomaly detectors."""
        active_names = settings.ACTIVE_ANOMALY_DETECTORS
        return [cls.get_detector(name) for name in active_names]

    @classmethod
    def list_algorithms(cls) -> Dict[str, List[str]]:
        """List all registered algorithms."""
        return {
            "forecasters": list(cls._forecasters.keys()),
            "detectors": list(cls._detectors.keys()),
            "trust_scorers": list(cls._trust_scorers.keys())
        }
```

### Algorithm Service

```python
# app/services/algorithm_service.py
from typing import List, Optional
from uuid import UUID
from datetime import date
import logging

from app.algorithms.registry import AlgorithmRegistry
from app.algorithms.base import ForecastResult, AnomalyResult
from app.repositories.price_repository import PriceRepository
from app.repositories.forecast_repository import ForecastRepository

logger = logging.getLogger(__name__)

class AlgorithmService:
    """Service layer for algorithm operations."""

    def __init__(
        self,
        price_repo: PriceRepository,
        forecast_repo: ForecastRepository
    ):
        self.price_repo = price_repo
        self.forecast_repo = forecast_repo

    async def generate_forecast(
        self,
        bottle_id: UUID,
        algorithm: str = None,
        force_refresh: bool = False
    ) -> Optional[List[ForecastResult]]:
        """
        Generate price forecasts for a bottle.

        Args:
            bottle_id: UUID of the bottle
            algorithm: Specific algorithm to use (or active default)
            force_refresh: Regenerate even if recent forecast exists

        Returns:
            List of ForecastResult or None if insufficient data
        """
        try:
            # Check for cached forecast
            if not force_refresh:
                cached = await self.forecast_repo.get_current(bottle_id, algorithm)
                if cached:
                    return cached

            # Get forecaster
            forecaster = (
                AlgorithmRegistry.get_forecaster(algorithm)
                if algorithm
                else AlgorithmRegistry.get_active_forecaster()
            )

            # Get price history
            prices = await self.price_repo.get_verified_prices(bottle_id)

            if not forecaster.can_predict(len(prices)):
                logger.info(
                    f"Insufficient data for {forecaster.name} on bottle {bottle_id}: "
                    f"{len(prices)} points, need {forecaster.min_data_points}"
                )
                return None

            # Generate forecast
            forecaster.fit(prices)
            results = forecaster.predict([30, 60, 90, 180])

            # Store results
            await self.forecast_repo.store_forecasts(bottle_id, results)

            return results

        except Exception as e:
            logger.error(f"Forecast generation failed for {bottle_id}: {e}")
            # Try fallback algorithm
            return await self._fallback_forecast(bottle_id)

    async def _fallback_forecast(
        self,
        bottle_id: UUID
    ) -> Optional[List[ForecastResult]]:
        """Use simple average as fallback."""
        try:
            forecaster = AlgorithmRegistry.get_forecaster('simple_average')
            prices = await self.price_repo.get_verified_prices(bottle_id)

            if not forecaster.can_predict(len(prices)):
                return None

            forecaster.fit(prices)
            return forecaster.predict([30, 60, 90, 180])
        except Exception as e:
            logger.error(f"Fallback forecast failed: {e}")
            return None

    async def check_anomaly(
        self,
        bottle_id: UUID,
        price_cents: int,
        context: dict = None
    ) -> List[AnomalyResult]:
        """
        Run price through all active anomaly detectors.

        Args:
            bottle_id: UUID of the bottle
            price_cents: Price to check
            context: Additional context (user info, etc.)

        Returns:
            List of AnomalyResult from each detector
        """
        results = []

        # Get historical prices for fitting
        prices = await self.price_repo.get_prices_for_detection(bottle_id)

        for detector in AlgorithmRegistry.get_active_detectors():
            try:
                if prices:
                    detector.fit(prices)
                result = detector.detect(price_cents, context)
                results.append(result)
            except Exception as e:
                logger.error(f"Detector {detector.name} failed: {e}")
                continue

        return results

    def aggregate_anomaly_results(
        self,
        results: List[AnomalyResult]
    ) -> tuple[bool, str, float]:
        """
        Aggregate multiple detector results into final decision.

        Returns:
            (is_flagged, recommended_action, combined_score)
        """
        if not results:
            return False, 'accept', 0.0

        # Count votes
        flag_count = sum(1 for r in results if r.is_anomaly)
        max_score = max(r.anomaly_score for r in results)

        # Determine action
        if any(r.recommended_action == 'reject' for r in results):
            action = 'reject'
        elif flag_count >= len(results) / 2:
            action = 'flag'
        else:
            action = 'accept'

        is_flagged = action in ('flag', 'reject')

        return is_flagged, action, max_score
```

### Configuration

```python
# app/core/config.py (algorithm section)
from pydantic_settings import BaseSettings

class AlgorithmSettings(BaseSettings):
    # Forecasting
    ACTIVE_FORECASTER: str = "prophet"
    FALLBACK_FORECASTER: str = "simple_average"
    FORECAST_HORIZONS: list = [30, 60, 90, 180]
    FORECAST_CONFIDENCE: float = 0.70
    MIN_DATA_POINTS_PROPHET: int = 10
    MIN_DATA_POINTS_SIMPLE: int = 3

    # Anomaly Detection
    ACTIVE_ANOMALY_DETECTORS: list = ["zscore", "velocity"]
    ZSCORE_THRESHOLD: float = 2.0
    VELOCITY_THRESHOLD: int = 5  # submissions per hour

    # Trust Scoring
    ACTIVE_TRUST_SCORER: str = "bayesian"
    DEFAULT_TRUST_SCORE: float = 0.50

    # Feature Flags
    FEATURE_PROPHET_ENABLED: bool = True
    FEATURE_ARIMA_ENABLED: bool = False
    FEATURE_ISOLATION_FOREST_ENABLED: bool = False
```

---

## Security Architecture

### Authentication Flow

```
+--------+     +--------+     +--------+     +--------+
| Client | --> | Nginx  | --> | FastAPI| --> | Auth   |
|        |     | (TLS)  |     | (JWT)  |     | Service|
+--------+     +--------+     +--------+     +--------+
                                   |
                                   v
                              +--------+
                              |Password|
                              | Verify |
                              |(bcrypt)|
                              +--------+
```

### Security Controls

| Control | Implementation |
|---------|----------------|
| Password Hashing | bcrypt, cost factor 12 |
| Token Format | JWT (HS256), 24h access, 7d refresh |
| Session Storage | HttpOnly cookies for refresh token |
| HTTPS | Enforced via Cloudflare + Nginx |
| CORS | Whitelist of allowed origins |
| CSRF | Token validation on state-changing ops |
| Rate Limiting | Redis-backed, tiered by endpoint |
| SQL Injection | Parameterized queries (SQLAlchemy) |
| XSS | Template auto-escaping, CSP headers |
| Secrets | Environment variables, never in code |

### Secret Management

```bash
# Pre-commit hook: .pre-commit-config.yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
```

### Security Headers

```python
# app/middleware/security.py
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
    "Referrer-Policy": "strict-origin-when-cross-origin"
}
```

---

## Caching Strategy

### Cache Layers

```
+--------+     +---------+     +--------+     +----------+
| Client | --> |Cloudflare| --> | Redis  | --> |PostgreSQL|
| Cache  |     | CDN     |     | Cache  |     | Database |
+--------+     +---------+     +--------+     +----------+
   |              |                |
   | Browser      | Static         | Application
   | Cache        | Assets         | Data
```

### TTL Configuration

| Data Type | TTL | Invalidation |
|-----------|-----|--------------|
| Static assets | 1 year | Version hash in URL |
| Bottle details | 1 hour | On data update |
| Price history | 15 minutes | On new verified price |
| Search results | 5 minutes | Time-based |
| Forecasts | 24 hours | On new verified price |
| User sessions | 24 hours | On logout |
| Rate limits | 1 minute | Sliding window |

### Cache Keys

```python
# app/core/cache.py
class CacheKeys:
    @staticmethod
    def bottle(bottle_id: str) -> str:
        return f"bottle:{bottle_id}"

    @staticmethod
    def bottle_prices(bottle_id: str) -> str:
        return f"bottle:{bottle_id}:prices"

    @staticmethod
    def bottle_forecast(bottle_id: str, algorithm: str) -> str:
        return f"bottle:{bottle_id}:forecast:{algorithm}"

    @staticmethod
    def search(query_hash: str) -> str:
        return f"search:{query_hash}"

    @staticmethod
    def user_session(user_id: str) -> str:
        return f"session:{user_id}"

    @staticmethod
    def rate_limit(key: str) -> str:
        return f"ratelimit:{key}"
```

---

## Background Processing

### Celery Task Configuration

```python
# app/tasks/celery_app.py
from celery import Celery
from celery.schedules import crontab

celery_app = Celery(
    'wtracker',
    broker='redis://redis:6379/0',
    backend='redis://redis:6379/1'
)

celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)

# Scheduled tasks
celery_app.conf.beat_schedule = {
    # Scraping tasks
    'scrape-auction-sources': {
        'task': 'app.tasks.scraping.scrape_all_sources',
        'schedule': crontab(hour='*/6'),  # Every 6 hours
    },

    # Forecast regeneration
    'regenerate-forecasts': {
        'task': 'app.tasks.forecasting.regenerate_stale_forecasts',
        'schedule': crontab(hour='2', minute='0'),  # 2 AM daily
    },

    # Trust score recalculation
    'recalculate-trust-scores': {
        'task': 'app.tasks.trust.recalculate_all_scores',
        'schedule': crontab(hour='3', minute='0'),  # 3 AM daily
    },

    # Materialized view refresh
    'refresh-bottle-stats': {
        'task': 'app.tasks.maintenance.refresh_materialized_views',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
    },

    # Cleanup tasks
    'cleanup-expired-tokens': {
        'task': 'app.tasks.maintenance.cleanup_expired_tokens',
        'schedule': crontab(hour='*/1'),  # Every hour
    },
}
```

### Task Definitions

```python
# app/tasks/scraping.py
from app.tasks.celery_app import celery_app

@celery_app.task(bind=True, max_retries=3)
def scrape_source(self, source_id: str):
    """Scrape a single data source."""
    try:
        # Implementation
        pass
    except Exception as e:
        self.retry(exc=e, countdown=60 * 5)  # Retry in 5 minutes

@celery_app.task
def scrape_all_sources():
    """Queue scraping for all active sources."""
    from app.repositories.source_repository import SourceRepository
    sources = SourceRepository.get_active_sources()
    for source in sources:
        scrape_source.delay(str(source.id))

# app/tasks/forecasting.py
@celery_app.task
def generate_bottle_forecast(bottle_id: str, algorithm: str = None):
    """Generate forecast for a single bottle."""
    pass

@celery_app.task
def regenerate_stale_forecasts():
    """Regenerate forecasts older than 24 hours."""
    pass
```

---

## Monitoring & Observability

### Logging Configuration

```python
# app/core/logging.py
import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": JSONFormatter},
        "standard": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if settings.ENVIRONMENT == "production" else "standard",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {
        "uvicorn": {"level": "INFO"},
        "sqlalchemy": {"level": "WARNING"},
        "celery": {"level": "INFO"},
    },
}
```

### Health Check Endpoints

```python
# app/api/health.py
from fastapi import APIRouter, Depends
from app.core.database import get_db
from app.core.cache import redis_client

router = APIRouter(tags=["health"])

@router.get("/health")
async def health_check():
    return {"status": "healthy"}

@router.get("/health/detailed")
async def detailed_health(db=Depends(get_db)):
    checks = {
        "database": await check_database(db),
        "redis": await check_redis(),
        "celery": await check_celery(),
    }
    status = "healthy" if all(c["healthy"] for c in checks.values()) else "unhealthy"
    return {"status": status, "checks": checks}
```

### Metrics (Future)

- Request latency (P50, P95, P99)
- Error rates by endpoint
- Database query times
- Cache hit rates
- Celery queue depth
- Scraping success rates
- Algorithm accuracy metrics

---

## Architecture Decision Records

### ADR-001: PostgreSQL over TimescaleDB

**Status:** Accepted
**Date:** 2025-12-27

**Context:** Need time-series storage for price data.

**Decision:** Use PostgreSQL with standard indexing, architect for TimescaleDB migration.

**Rationale:** MVP scale doesn't require TimescaleDB optimizations. PostgreSQL composite indexes on (bottle_id, transaction_date) are sufficient. Migration path is seamless since TimescaleDB is a PostgreSQL extension.

### ADR-002: Algorithm Abstraction Layer

**Status:** Accepted
**Date:** 2025-12-27

**Context:** Need to support multiple forecasting and anomaly detection algorithms with ability to swap implementations.

**Decision:** Implement registry pattern with abstract base classes.

**Rationale:** Allows algorithm hot-swapping via configuration, A/B testing, and gradual rollout of new algorithms without code changes to calling services.

### ADR-003: Server-Side Rendering for MVP

**Status:** Accepted
**Date:** 2025-12-27

**Context:** Need to decide frontend architecture.

**Decision:** Use Jinja2 templates with Alpine.js for interactivity.

**Rationale:** Simplifies stack, reduces development complexity, acceptable for MVP. Can migrate to SPA (React/Vue) in Phase 2 if needed.

### ADR-004: Self-Rolled Authentication

**Status:** Accepted
**Date:** 2025-12-27

**Context:** Need authentication supporting pseudonymous accounts.

**Decision:** Implement JWT + bcrypt authentication in-house.

**Rationale:** Full control over privacy features, no external dependencies for auth data, acceptable complexity for a security-conscious team.

---

## Appendix: File Structure

```
wtracker/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── deps.py
│   │   │   ├── health.py
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── bottles.py
│   │   │       ├── auth.py
│   │   │       ├── submissions.py
│   │   │       ├── collections.py
│   │   │       └── admin.py
│   │   ├── algorithms/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   ├── forecasters/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── prophet_forecaster.py
│   │   │   │   └── simple_average.py
│   │   │   └── anomaly/
│   │   │       ├── __init__.py
│   │   │       ├── zscore_detector.py
│   │   │       └── velocity_detector.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   ├── cache.py
│   │   │   ├── security.py
│   │   │   └── logging.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── bottle.py
│   │   │   ├── price.py
│   │   │   ├── user.py
│   │   │   ├── submission.py
│   │   │   └── collection.py
│   │   ├── repositories/
│   │   │   ├── __init__.py
│   │   │   ├── bottle_repository.py
│   │   │   ├── price_repository.py
│   │   │   └── user_repository.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── algorithm_service.py
│   │   │   ├── auth_service.py
│   │   │   └── submission_service.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── bottle.py
│   │   │   ├── price.py
│   │   │   └── user.py
│   │   └── tasks/
│   │       ├── __init__.py
│   │       ├── celery_app.py
│   │       ├── scraping.py
│   │       ├── forecasting.py
│   │       └── maintenance.py
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── spiders/
│   │   │   └── auction_spider.py
│   │   ├── pipelines.py
│   │   └── settings.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── home.html
│   │   └── bottles/
│   │       ├── list.html
│   │       └── detail.html
│   ├── static/
│   │   ├── css/
│   │   └── js/
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_api/
│   │   ├── test_algorithms/
│   │   └── test_services/
│   ├── Dockerfile
│   └── requirements.txt
├── database/
│   ├── init.sql
│   ├── seed.sql
│   └── migrations/
├── nginx/
│   └── nginx.conf
├── docker-compose.yml
├── docker-compose.test.yml
├── docker-compose.prod.yml
├── .env.example
├── .pre-commit-config.yaml
└── README.md
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-27 | Tech Lead (Jordan) | Initial architecture document |
