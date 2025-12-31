# DEC-007: Retrofit Response Envelope Format Now

**Date:** 2025-12-31
**Status:** Accepted
**Deciders:** Team (Phase 3 Kickoff)

## Context

Our existing API endpoints return raw data without a consistent envelope format. The ARCHITECTURE.md spec defines a standard response format:

```json
{
    "status": "success",
    "data": { ... },
    "meta": { "page": 1, "limit": 20, "total": 150 }
}
```

We need to decide whether to retrofit existing endpoints now or defer to Phase 5 polish.

## Decision

**Retrofit response envelope format now** during Phase 3A implementation.

## Rationale

1. **Technical debt compounds** - The longer we wait, the more endpoints diverge
2. **Frontend consistency** - UI components can rely on standard response shapes
3. **Error handling** - Standard error format makes client error handling easier
4. **API consumers** - External integrations benefit from predictable responses
5. **Marginal cost now** - Adding envelope during refactor is minimal overhead

## Implementation

All API responses will use:

```python
# Success response
{
    "status": "success",
    "data": { ... },
    "meta": { ... }  # Optional, for paginated responses
}

# Error response
{
    "status": "error",
    "error": {
        "code": "NOT_FOUND",
        "message": "Bottle not found",
        "details": null
    }
}
```

## Consequences

- Existing API consumers (if any) will need to update
- Slightly more verbose responses
- More consistent codebase

## Related

- [Phase 3 Kickoff](../MEETING_NOTES/2025-12-31-phase3-kickoff.md)
- [ARCHITECTURE.md - API Design](../ARCHITECTURE.md#api-design)
