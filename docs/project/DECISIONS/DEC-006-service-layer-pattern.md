# DEC-006: Service Layer Pattern for Business Logic

**Date:** 2025-12-31
**Status:** Accepted
**Deciders:** Tech Lead (Jordan), QA Lead (Riley)

## Context

As we begin Phase 3 (Core Platform), we need to decide how to organize business logic. Currently, route handlers in `src/api/routes/` contain both HTTP handling and business logic. This works for simple endpoints but creates issues for:

1. **Testing**: Unit testing business logic requires setting up HTTP request contexts
2. **Reusability**: Business logic cannot be easily called from Celery tasks or CLI commands
3. **Complexity**: Route handlers become large and hard to maintain
4. **Consistency**: Similar logic is duplicated across endpoints

## Options Considered

### Option 1: Keep Logic in Route Handlers
**Description:** Continue current approach - business logic stays in route files.

**Pros:**
- No refactoring needed
- Simpler for very small applications
- Fewer files to navigate

**Cons:**
- Harder to unit test (need HTTP mocking)
- Cannot reuse logic in Celery tasks
- Route handlers become bloated
- Violates Single Responsibility Principle

### Option 2: Service Layer Pattern
**Description:** Create dedicated service classes/modules that encapsulate business logic. Routes become thin wrappers that handle HTTP concerns and delegate to services.

```
src/
  services/
    __init__.py
    bottle_service.py    # Bottle CRUD, stats, search logic
    price_service.py     # Price history, aggregation, trends
    search_service.py    # Search indexing, autocomplete
```

**Pros:**
- Clean separation of concerns
- Easy to unit test without HTTP
- Services reusable from routes, Celery tasks, CLI
- Industry standard pattern (Django services, Rails service objects)
- Easier to add caching at service level

**Cons:**
- More files/boilerplate
- Extra layer of abstraction
- Requires refactoring existing routes

### Option 3: Repository + Service Pattern
**Description:** Full DDD-style with repositories for data access and services for business logic.

**Pros:**
- Maximum separation of concerns
- Database abstraction could ease migrations

**Cons:**
- Overkill for MVP
- SQLAlchemy already provides good abstraction
- Significantly more boilerplate

## Decision

**Option 2: Service Layer Pattern**

We will create service modules in `src/services/` that encapsulate business logic. Route handlers will remain responsible for:
- Request validation (via Pydantic schemas)
- Authentication/authorization checks
- HTTP response formatting
- Error handling and status codes

Services will be responsible for:
- Database queries and mutations
- Business rule validation
- Calculations and aggregations
- Caching logic

## Implementation

### Service Structure

```python
# src/services/bottle_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.bottle import Bottle

class BottleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_bottle(self, bottle_id: int) -> Bottle | None:
        """Get a single bottle by ID."""
        ...

    async def search_bottles(
        self,
        query: str | None = None,
        category: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Bottle], int]:
        """Search bottles with pagination. Returns (bottles, total_count)."""
        ...

    async def get_trending_bottles(self, limit: int = 10) -> list[Bottle]:
        """Get bottles with highest price trends."""
        ...
```

### Dependency Injection

Services receive database session via constructor:

```python
# src/api/routes/bottles.py
@router.get("/{bottle_id}")
async def get_bottle(
    bottle_id: int,
    db: AsyncSession = Depends(get_db),
):
    service = BottleService(db)
    bottle = await service.get_bottle(bottle_id)
    if not bottle:
        raise HTTPException(status_code=404, detail="Bottle not found")
    return bottle
```

### Services to Create

| Service | Responsibility |
|---------|----------------|
| `BottleService` | Bottle CRUD, search, statistics |
| `PriceService` | Price history, aggregations, trends |
| `SearchService` | Autocomplete, suggestions (Phase 3A+) |
| `CollectionService` | Collection management (Phase 3C) |
| `SubmissionService` | User submissions (Phase 4C) |
| `AlgorithmService` | Forecasting, anomaly detection (Phase 4) |

## Consequences

### Positive
- Cleaner, more testable code
- Service logic reusable from Celery tasks
- Easier to add caching layer
- Standard pattern familiar to Python developers

### Negative
- Requires refactoring existing route handlers
- Slight increase in code organization complexity

### Migration Path
1. Create `src/services/` directory with `__init__.py`
2. Implement `BottleService` and `PriceService`
3. Refactor `bottles.py` and `prices.py` routes to use services
4. Add unit tests for service methods
5. New features use service pattern from start

## Related

- [Phase 3 Kickoff Meeting](../MEETING_NOTES/2025-12-31-phase3-kickoff.md)
- [ARCHITECTURE.md](../ARCHITECTURE.md) - Overall system design
