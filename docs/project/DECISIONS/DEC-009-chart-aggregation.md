# DEC-009: Time-Based Aggregation Strategy for Charts

**Date:** 2025-12-31
**Status:** Accepted
**Deciders:** Tech Lead (Jordan), PO (Sam)

## Context

Price history charts need to display data across varying time periods (30 days to 5+ years). Returning raw price points becomes impractical for longer periods - both for performance and visualization clarity.

## Decision

Implement **adaptive time-based aggregation**:

| Time Range | Aggregation Level | Rationale |
|------------|-------------------|-----------|
| 0-30 days | Daily averages | Recent data needs detail |
| 31-365 days | Weekly averages | Balance detail and density |
| 366+ days | Monthly averages | Long-term trends, manageable data |

## Rationale

1. **Data transfer** - Limits response size regardless of history length
2. **Visualization clarity** - Appropriate density for chart readability
3. **Performance** - Fewer data points to process and render
4. **User experience** - Recent data shows detail, older data shows trends

## Implementation

```python
# src/services/price_service.py

async def get_aggregated_history(
    self,
    bottle_id: int,
    days: int = 365,
    source: PriceSource | None = None,
) -> list[AggregatedPrice]:
    """
    Get aggregated price history optimized for charts.

    Aggregation strategy:
    - 0-30 days: Daily
    - 31-365 days: Weekly
    - 366+ days: Monthly
    """
    now = datetime.utcnow()

    for price in prices:
        age_days = (now - price.transaction_date).days

        if age_days <= 30:
            # Daily: Group by date
            period_key = price.transaction_date.strftime("%Y-%m-%d")
        elif age_days <= 365:
            # Weekly: Group by week start
            week_start = price.transaction_date - timedelta(
                days=price.transaction_date.weekday()
            )
            period_key = week_start.strftime("%Y-W%W")
        else:
            # Monthly: Group by month
            period_key = price.transaction_date.strftime("%Y-%m")
```

## Response Format

```python
@dataclass
class AggregatedPrice:
    period_start: datetime
    period_end: datetime
    period_label: str  # "2025-12-31" or "Week of 2025-12-23" or "2025-12"
    avg_price: float
    min_price: float
    max_price: float
    count: int
```

## Chart.js Integration

The aggregated data is formatted for Chart.js:

```json
{
    "labels": ["2025-12-01", "2025-12-08", "2025-12-15", ...],
    "datasets": [
        {
            "label": "Average Price",
            "data": [850.00, 875.50, 862.25, ...],
            "borderColor": "rgb(59, 130, 246)"
        }
    ]
}
```

## Consequences

### Positive
- Consistent chart performance regardless of history length
- Clear visualization at all time scales
- Predictable API response sizes

### Negative
- Detail lost in older data (acceptable trade-off)
- Slight complexity in aggregation logic

## Alternatives Considered

1. **Fixed aggregation (always weekly)** - Rejected: loses detail in recent data
2. **User-selectable aggregation** - Deferred: Can add later if needed
3. **No aggregation (raw points)** - Rejected: Impractical for long histories

## Related

- [Phase 3 Kickoff](../MEETING_NOTES/2025-12-31-phase3-kickoff.md)
- [Phase 3A Implementation Plan](../PHASE3A_IMPLEMENTATION_PLAN.md)
- [ARCHITECTURE.md](../ARCHITECTURE.md)
