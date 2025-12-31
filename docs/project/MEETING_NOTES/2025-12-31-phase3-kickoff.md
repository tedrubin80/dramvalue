# Phase 3 Kickoff: Core Platform

**Date:** 2025-12-31
**Participants:** PM (Alex), Tech Lead (Jordan), PO (Sam), QA Lead (Riley)
**Context:** Phase 2 (Data Ingestion) is complete. We have Scrapy spiders for 2 auction sources, Celery background tasks, and scraping infrastructure ready. Starting Phase 3 with focus on Bottle API, Price History, and Search.

---

## Discussion

**[PM] Alex:** Good morning team. We've just wrapped up Phase 2 ahead of schedule - excellent work on the scraping infrastructure. Let's kick off Phase 3: Core Platform. The user has requested we prioritize in this order: Bottle API endpoints, Price History API, then Search. Let me frame the discussion - what's our current state and what are the key decisions we need to make?

**[Tech Lead] Jordan:** Great timing. Let me summarize what we have to build on:

**Existing Assets:**
- **Bottle model** (`src/models/bottle.py`): Full model with cached stats fields (avg_price, min_price, max_price, price_trend, confidence_score), aliases relationship, and category enums
- **Price model** (`src/models/price.py`): Complete with source types, auction house enum, confidence weighting, outlier flagging
- **Bottles route** (`src/api/routes/bottles.py`): Basic search and detail endpoints already exist with pagination, filtering by category/distillery/price, and alias search
- **Prices route** (`src/api/routes/prices.py`): Has `/bottle/{id}/history` and `/bottle/{id}/stats` endpoints

So we're not starting from scratch - we have a foundation. But these are basic implementations. Phase 3A needs to enhance them significantly.

**[PO] Sam:** That's great context. From a user value perspective, here's what I see as the priority user stories:

1. **As a collector**, I want to search for bottles quickly and see relevant results so I can find bottles I'm interested in tracking
2. **As a collector**, I want to see detailed price history with charts so I can understand market trends
3. **As a collector**, I want a clean homepage that surfaces trending and notable bottles so I can discover what's happening in the market

The existing endpoints are functional but they're API-first. We need to think about the data shapes that serve the UI well, especially for charts.

**[Tech Lead] Jordan:** Agreed. Looking at the ARCHITECTURE.md spec, the API response format should follow a standard envelope:

```json
{
    "status": "success",
    "data": { ... },
    "meta": { "page": 1, "limit": 20, "total": 150 }
}
```

Our current endpoints don't follow this pattern. Question: do we retrofit now or defer to Phase 5 polish?

**[PM] Alex:** What's the impact on timeline if we retrofit now?

**[Tech Lead] Jordan:** Maybe half a day extra per endpoint. But it sets us up better for the frontend and any API consumers. I'd recommend doing it now - technical debt compounds.

**[QA] Riley:** I agree with retrofitting. From a testing perspective, consistent response formats are much easier to validate. Also, I've been thinking about edge cases:

1. **Empty states**: What happens when a bottle has no prices? No price history?
2. **Data quality**: Some scraped data might have issues - how do we handle bottles with only 1-2 data points?
3. **Performance**: When we have thousands of bottles, will the search perform well? Do we need full-text search or is ILIKE sufficient for MVP?
4. **Chart data format**: What aggregation level for price history? Daily? Weekly? Monthly?

**[PO] Sam:** Great questions Riley. For empty states, we should show meaningful messages rather than just empty results. For data quality, I'd say we show what we have but indicate confidence - "Limited data available" for bottles with < 5 prices.

On search performance - I think ILIKE is fine for MVP. We can add PostgreSQL full-text search or even Elasticsearch later if needed. Let's not over-engineer.

**[Tech Lead] Jordan:** I concur on ILIKE for now. For chart data, I propose:
- **Last 30 days**: Daily aggregation
- **30-365 days**: Weekly aggregation
- **Over 1 year**: Monthly aggregation

This keeps the data transfer manageable while still showing detail where it matters.

**[PM] Alex:** Good. Let's talk about the implementation order. User requested: Bottle API -> Price History -> Search. Jordan, does that make technical sense?

**[Tech Lead] Jordan:** Yes, it's the right dependency order:
1. **Bottle API enhancements** - add response envelope, improve stats calculation, add trending/featured bottles endpoint
2. **Price History API** - add chart-optimized aggregation endpoint, time-series format for Chart.js
3. **Search enhancements** - autocomplete/suggestions endpoint, relevance scoring

One architectural decision needed: should we create a **service layer** for business logic, or keep it in route handlers?

**[QA] Riley:** I vote for service layer. It makes unit testing much cleaner - I can test business logic without HTTP overhead.

**[Tech Lead] Jordan:** Agreed. I'll create `src/services/bottle_service.py` and `src/services/price_service.py` to encapsulate the business logic. Routes become thin wrappers.

**[PO] Sam:** What about the homepage? That needs data from multiple sources - trending bottles, recent prices, maybe featured bottles.

**[Tech Lead] Jordan:** Good point. I'll add a dedicated homepage endpoint that aggregates:
- Top trending bottles (by price_trend)
- Most active bottles (by recent price count)
- Newly added bottles
- Featured/allocated bottles

This can be one optimized query rather than multiple round trips.

**[PM] Alex:** Let's talk timeline. Phase 3A according to TIMELINE.md is Week 5-6. We're essentially at Week 5 start. What's realistic?

**[Tech Lead] Jordan:** Here's my estimate:

| Task | Days |
|------|------|
| Service layer setup + Bottle service | 1 |
| Response envelope + Bottle API enhancements | 1 |
| Price History aggregation endpoints | 1.5 |
| Chart data format optimization | 0.5 |
| Search autocomplete + suggestions | 1 |
| Homepage data endpoint | 0.5 |
| Testing + refinement | 1 |
| **Total** | 6.5 days |

So about 1.5 weeks, which fits our Week 5-6 window.

**[QA] Riley:** I'll need time to create test cases. Can we agree on:
1. Every new endpoint has at least 3 test cases (success, empty result, error)
2. Service layer functions have unit tests
3. We validate the Chart.js data format works before marking complete

**[Tech Lead] Jordan:** Absolutely. I'll write tests as I go.

**[PM] Alex:** Any risks we should flag?

**[Tech Lead] Jordan:** Main risk is performance once we have real data volume. The cached stats on the Bottle model help, but we'll need to ensure the background job that updates them runs reliably. It's already set up via Celery Beat - we just need to make sure it executes.

**[QA] Riley:** I want to flag data integrity - what if the scraped prices have errors? Should we have validation in the API layer too, or trust the pipeline?

**[Tech Lead] Jordan:** Good point. The scraping pipeline has validation, but the API should also be defensive. I'll add sanity checks - if avg_price is null or price_count is 0, we clearly indicate limited data.

**[PO] Sam:** One more thing - can we add a simple "last updated" indicator on price data? Users want to know how fresh the data is.

**[Tech Lead] Jordan:** Easy addition. The Price model has transaction_date and created_at. I'll include "last_price_date" in responses.

---

## [Facilitator] Summary

### Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| DEC-006 | Implement service layer pattern | Cleaner architecture, better testability, separation of concerns |
| DEC-007 | Retrofit response envelope format now | Avoid technical debt, consistent API patterns |
| DEC-008 | Use ILIKE for MVP search | Sufficient for expected data volume, can upgrade later |
| DEC-009 | Time-based aggregation for charts | Daily (30d), Weekly (30-365d), Monthly (>1y) |

### Architecture Decisions Needed
- [ ] Create ADR for service layer pattern (DEC-006)
- [ ] Create ADR for search strategy (DEC-008)

### Implementation Order (Phase 3A)
1. Service layer setup (BottleService, PriceService)
2. Response envelope wrapper
3. Bottle API enhancements (trending, featured, improved stats)
4. Price History aggregation (chart-optimized)
5. Search autocomplete/suggestions
6. Homepage data endpoint

### Action Items

| Owner | Action | Target |
|-------|--------|--------|
| Jordan | Create service layer structure | Day 1 |
| Jordan | Implement response envelope | Day 1 |
| Jordan | Bottle API enhancements | Day 2 |
| Jordan | Price History aggregation | Day 3-4 |
| Jordan | Search + Homepage endpoints | Day 5 |
| Riley | Create test plan for Phase 3A | Day 1 |
| Riley | Review and test each endpoint | Ongoing |
| Sam | Review UX of response data shapes | Day 3 |
| Alex | Update PROJECT_STATUS.md | Today |

### Quality Gates
- All new endpoints have test coverage
- Response times < 500ms for list endpoints
- Chart data renders correctly in Chart.js format
- Empty states handled gracefully

### Open Questions
- None at this time

---

### Next Meeting
Phase 3A midpoint review (Day 4)
