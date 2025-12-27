# DEC-001: PostgreSQL as Primary Database

**Date:** 2025-12-27
**Status:** Accepted
**Deciders:** Tech Lead (Jordan), PM (Alex), QA Lead (Riley)

---

## Context

WTracker requires a database that can handle:
1. Time-series data (price history with timestamps)
2. Relational data (bottles, users, collections, submissions)
3. JSON storage (scrape configurations, moderation flags)
4. Complex queries (aggregations, joins, full-text search)
5. Concurrent access (multiple scrapers, user requests)

The database choice will impact development velocity, operational complexity, and future scalability.

---

## Options Considered

### Option 1: SQLite

**Description:** Lightweight, file-based relational database.

**Pros:**
- Zero configuration
- Single file deployment
- Perfect for development/testing
- No server process needed

**Cons:**
- Poor concurrency (single writer)
- No built-in time-series optimization
- Limited to single machine
- No JSON operators (basic only)
- Migration pain when scaling

**Evaluation:** Not suitable for production use case due to concurrency limitations.

---

### Option 2: PostgreSQL

**Description:** Full-featured relational database with extensive ecosystem.

**Pros:**
- Excellent relational capabilities
- Strong JSON/JSONB support
- Good time-series performance with proper indexing
- TimescaleDB extension available for future optimization
- Robust ecosystem (SQLAlchemy, Alembic, psycopg2)
- Full-text search built-in
- Strong concurrency support
- Industry standard

**Cons:**
- More operational overhead than SQLite
- Requires running server process
- More complex backup/restore

**Evaluation:** Best balance of features and complexity for MVP.

---

### Option 3: TimescaleDB

**Description:** PostgreSQL extension optimized for time-series data.

**Pros:**
- Purpose-built time-series optimization
- Automatic data partitioning
- Compression for historical data
- All PostgreSQL features
- Continuous aggregates

**Cons:**
- Additional complexity to install and manage
- Learning curve for hypertables
- May be overkill for MVP data volume
- License considerations (some features are paid)

**Evaluation:** Excellent future option, but premature optimization for MVP.

---

### Option 4: MongoDB

**Description:** Document-oriented NoSQL database.

**Pros:**
- Flexible schema
- Good for semi-structured data
- Horizontal scaling built-in

**Cons:**
- Weaker relational query support
- No native time-series optimization
- Different query language (not SQL)
- Team has stronger SQL experience
- ACID compliance requires more configuration

**Evaluation:** Poor fit for our mixed workload (relational + time-series).

---

## Decision

**Selected: PostgreSQL**

We will use PostgreSQL 15 as our primary database from day one, with schema designed for potential TimescaleDB migration if time-series performance becomes a bottleneck.

---

## Rationale

1. **Mixed workload support:** PostgreSQL handles both relational (users, bottles, collections) and time-series (prices) data well.

2. **Avoid migration pain:** Starting with SQLite would require a painful migration when concurrency needs increase. PostgreSQL scales with our needs.

3. **Ecosystem maturity:** Excellent Python support via SQLAlchemy 2.0, async drivers, and comprehensive tooling.

4. **Future-proof:** TimescaleDB is a PostgreSQL extension, so migration is adding an extension rather than changing databases.

5. **JSON support:** JSONB operators allow flexible schema for scrape configs and moderation flags without sacrificing query performance.

6. **Full-text search:** Built-in tsvector/tsquery capabilities for bottle search without additional infrastructure.

7. **Team expertise:** SQL is well-understood, reducing development friction.

---

## Consequences

### Positive
- Development and production parity
- No migration needed as we scale
- Rich query capabilities from day one
- Clear upgrade path to TimescaleDB if needed

### Negative
- Slightly more complex local setup (Docker required)
- Database server to manage in production
- Backup strategy needed

### Neutral
- Need to implement proper indexing strategy
- Will use Alembic for migrations

---

## Implementation Notes

1. Use Docker Compose for local PostgreSQL
2. Create indexes on (bottle_id, transaction_date) for price queries
3. Use JSONB for flexible fields (scrape_config, moderation_flags)
4. Implement materialized views for frequently accessed aggregations
5. Document TimescaleDB migration path for Phase 2+

---

## Related

- [ARCHITECTURE.md](../ARCHITECTURE.md) - Database schema details
- [2025-12-27-project-kickoff.md](../MEETING_NOTES/2025-12-27-project-kickoff.md) - Initial database discussion
