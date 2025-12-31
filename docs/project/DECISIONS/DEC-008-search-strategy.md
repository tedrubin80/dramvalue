# DEC-008: Use ILIKE for MVP Search

**Date:** 2025-12-31
**Status:** Accepted
**Deciders:** Tech Lead (Jordan), PO (Sam)

## Context

We need to implement bottle search functionality. Options range from simple LIKE queries to full-text search engines. The decision affects development time, infrastructure complexity, and search quality.

## Options Considered

### Option 1: PostgreSQL ILIKE
**Description:** Use SQL ILIKE pattern matching for case-insensitive substring search.

```sql
WHERE name ILIKE '%search_term%'
   OR distillery ILIKE '%search_term%'
```

**Pros:**
- Zero additional infrastructure
- Simple to implement
- Good enough for MVP data volumes (thousands of bottles)
- Fast for indexed columns with prefix matches

**Cons:**
- No relevance ranking
- Substring matches can be slow on large datasets
- No fuzzy matching or typo tolerance

### Option 2: PostgreSQL Full-Text Search (ts_vector)
**Description:** Use PostgreSQL's built-in full-text search with ts_vector and ts_query.

**Pros:**
- Native PostgreSQL, no external dependencies
- Relevance ranking with ts_rank
- Stemming and stop words
- Good for moderate scale

**Cons:**
- More complex to set up
- Requires maintaining search indexes
- Still limited compared to dedicated engines

### Option 3: Elasticsearch / OpenSearch
**Description:** Dedicated search engine for full-text search.

**Pros:**
- Excellent relevance ranking
- Fuzzy matching, typo tolerance
- Scales to millions of documents
- Rich query DSL

**Cons:**
- Additional infrastructure to manage
- Sync complexity between PostgreSQL and Elasticsearch
- Overkill for MVP scale
- Operational overhead

### Option 4: pg_trgm Extension
**Description:** PostgreSQL trigram matching extension for fuzzy text matching.

**Pros:**
- Fuzzy matching built-in
- Similarity scoring
- Native PostgreSQL

**Cons:**
- Requires extension installation
- Index maintenance
- More complex queries

## Decision

**Option 1: ILIKE for MVP** with architecture prepared for upgrade.

## Rationale

1. **MVP scale** - Expected data volume (thousands of bottles) is well within ILIKE performance limits
2. **Development speed** - Ship faster, iterate based on real user feedback
3. **Infrastructure simplicity** - No additional services to manage
4. **Upgrade path** - Can add pg_trgm or Elasticsearch later if needed

## Implementation

```python
# Phase 3A: ILIKE implementation
query = select(Bottle).where(
    or_(
        Bottle.name.ilike(f"%{search_term}%"),
        Bottle.distillery.ilike(f"%{search_term}%"),
        Bottle.brand.ilike(f"%{search_term}%"),
    )
)

# Alias search via subquery
alias_bottle_ids = (
    select(BottleAlias.bottle_id)
    .where(BottleAlias.alias.ilike(f"%{search_term}%"))
)
query = query.where(or_(..., Bottle.id.in_(alias_bottle_ids)))
```

## Upgrade Path

If search quality becomes an issue:

1. **Phase 5 (Polish)**: Add pg_trgm for fuzzy matching
2. **Post-MVP**: Consider Elasticsearch if scale warrants

## Monitoring

Track these metrics to inform future decisions:
- Average search response time
- Zero-result search rate
- User feedback on search quality

## Consequences

- Simple, fast development
- May need upgrade if data scales significantly
- Limited fuzzy matching until upgrade

## Related

- [Phase 3 Kickoff](../MEETING_NOTES/2025-12-31-phase3-kickoff.md)
- [Phase 3A Implementation Plan](../PHASE3A_IMPLEMENTATION_PLAN.md)
