# Project Charter: Secondary Market Spirits Price Intelligence Platform

**Project Codename:** WTracker
**Created:** 2025-12-27
**Last Updated:** 2025-12-27
**Status:** Approved

---

## Executive Summary

WTracker is a price tracking and valuation engine for secondary market bourbon and scotch whisky. It aggregates public auction data, retail pricing, and crowdsourced transaction reports into a searchable database with trend analysis, predictive modeling, and personal collection valuation. The platform addresses the opacity of the secondary spirits market by providing collectors with data-driven insights and trustworthy price intelligence.

---

## Problem Statement

The secondary market for collectible spirits (bourbon, scotch) is notoriously opaque:

- **No central pricing authority:** Prices vary wildly between auction houses, retailers, and private sales
- **Information asymmetry:** Experienced collectors have access to price history that newcomers lack
- **Manipulation risk:** Without aggregated data, it's difficult to detect price manipulation or outliers
- **Collection valuation uncertainty:** Collectors cannot accurately assess the market value of their holdings
- **Fragmented data sources:** Price information is scattered across auction sites, forums, and private transactions

Collectors regularly overpay when buying or undersell when liquidating due to lack of reliable, aggregated market data.

---

## Vision & Goals

**Vision:** Become the trusted source of truth for secondary market spirits pricing, empowering collectors with transparent, data-driven market intelligence.

**Goals:**

| # | Goal | Measurable Outcome |
|---|------|-------------------|
| 1 | Aggregate pricing data from multiple sources | 3+ data sources integrated within 6 months |
| 2 | Provide accurate price history and trends | <5% variance from actual transaction prices |
| 3 | Enable personal collection valuation | Users can track portfolio value over time |
| 4 | Predict future price movements | Monte Carlo projections with confidence bands |
| 5 | Maintain data integrity | <1% of displayed data from fraudulent submissions |
| 6 | Protect user privacy | Zero credential exposure, pseudonymous accounts |

---

## Success Criteria

| Criteria | Measurement | Target |
|----------|-------------|--------|
| Core search functionality | User can search and find bottle | 95% of known bottles searchable |
| Price history accuracy | Variance from source data | <2% transcription error |
| Collection valuation | Estimate vs. actual sale prices | Within 15% of market |
| Forecast reliability | Actual price within confidence bands | 70%+ of the time |
| Fraud detection | Suspicious submissions caught | 90%+ flagged before affecting averages |
| Security | Credential exposure incidents | Zero |
| Performance | Homepage load time | <2 seconds |
| User experience | First-time visitor can search | No account required for basic search |

---

## Scope

### In Scope (MVP)

**Data Aggregation:**
- Scrape/ingest public auction results (starting with one source)
- Accept crowdsourced transaction submissions from verified users
- Normalize bottle naming variations

**Bottle Database:**
- Searchable by name, distillery, age, release year, bottle size
- Each bottle page shows: price history chart, data source breakdown, confidence score

**Price Intelligence:**
- Time-series visualization per bottle
- Prophet-based price projections with confidence bands
- Anomaly flagging for sudden spikes/drops

**Personal Collection:**
- User can input bottles they own
- System estimates current market value
- Track collection value over time

**User System:**
- Pseudonymous accounts (display name only)
- Email verification for submission privileges
- Trust-weighted submission scoring

**Fraud Detection:**
- Price outlier detection (>2 std dev)
- New account high-volume flagging
- Single-user influence capping
- Moderation queue for flagged submissions

**Admin Tools:**
- Basic moderation queue with flag reasons
- Audit log of moderation actions

### Out of Scope (MVP)

- Marketplace functionality (no buying/selling)
- Mobile application
- Public API
- Social features beyond submissions
- Multiple auction source integrations (Phase 2)
- Advanced ML algorithms (LSTM, collaborative filtering)
- Release cycle awareness in projections
- PageRank-style trust propagation

### Future Considerations (Phase 2+)

- Additional auction source integrations
- Retail pricing aggregation
- Advanced anomaly detection (Isolation Forest, LOF)
- Release cycle price modeling
- Market segmentation analysis
- Recommendation engine ("bottles similar to yours")
- Public API for third-party integrations

---

## Stakeholders

| Role | Name/Entity | Interest | Involvement |
|------|-------------|----------|-------------|
| Project Sponsor | Project Owner | Primary user, collector | Final decisions, testing, feedback |
| End Users (Primary) | Project Owner | Personal collection tracking, market intelligence | Daily use, feature prioritization |
| End Users (Secondary) | Enthusiast Collectors | Market transparency, fair pricing | Future users, beta testers |
| Technical | Development Team | Building sustainable, maintainable system | Implementation |
| Data Sources | Auction Houses | Providing market data | Passive (public data) |
| Community | Verified Submitters | Crowdsourced price data | Active contributors |

---

## Constraints & Assumptions

### Constraints

| Constraint | Impact | Mitigation |
|------------|--------|------------|
| Solo developer (initially) | Limits velocity, no redundancy | Comprehensive documentation, clean code |
| Budget-conscious hosting | Limits compute resources | Efficient algorithms, caching |
| Scraping dependency | Subject to source changes | Multiple sources, graceful degradation |
| No real identity requirements | Limits accountability | Trust scoring, fraud detection |
| Ethical scraping requirements | Rate limits, robots.txt compliance | Caching, respectful intervals |

### Assumptions

| Assumption | Risk if Invalid |
|------------|-----------------|
| Public auction data is legally scrapeable | May need to pivot to manual entry or partnerships |
| Prophet handles our data patterns well | May need alternative forecasting approach |
| Users will submit legitimate transactions | Trust system may need strengthening |
| PostgreSQL handles our scale | May need optimization or migration |
| Single VPS is sufficient for MVP traffic | May need scaling earlier than planned |

---

## Technical Approach Summary

| Component | Decision | Rationale |
|-----------|----------|-----------|
| Language | Python (FastAPI) | Data science ecosystem, async support |
| Database | PostgreSQL | Time-series + relational, TimescaleDB-ready |
| Scraping | Scrapy + Playwright | Built-in politeness, JS rendering |
| Forecasting | Facebook Prophet | Handles gaps, auto-seasonality |
| Auth | JWT + bcrypt (self-rolled) | Privacy control, no external dependencies |
| Hosting | DigitalOcean VPS + Docker | Predictable cost, full control |
| CDN | Cloudflare (free tier) | Static asset performance |
| CI/CD | GitHub Actions | Automated testing, secrets scanning |

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed technical specifications.

---

## High-Level Timeline

| Phase | Duration | Target Completion | Key Deliverables |
|-------|----------|-------------------|------------------|
| Phase 0: Initiation | 1 week | Week 1 | Charter, documentation structure |
| Phase 1: Infrastructure | 1 week | Week 2 | Docker, Postgres, CI/CD, scaffold |
| Phase 2: Data Ingestion | 2-3 weeks | Week 5 | Scrapy pipeline, first auction source |
| Phase 3: Core Platform | 3 weeks | Week 8 | Bottle DB, search, auth, basic UI |
| Phase 4: Intelligence | 3 weeks | Week 11 | Forecasting, fraud detection |
| Phase 5: Polish | 2 weeks | Week 13 | Collections, UX refinement |
| Phase 6: QA & Launch | 2 weeks | Week 15 | Testing, bug fixes, deployment |

**Total MVP Timeline:** 14-16 weeks

See [TIMELINE.md](./TIMELINE.md) for detailed milestone breakdown.

---

## Risks Summary

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Data source instability | High | High | Multiple sources, monitoring, caching |
| Credential exposure | Low | Critical | Pre-commit hooks, CI scanning, env vars |
| Naming normalization complexity | Medium | Medium | Iterative improvement, manual overrides |
| Trust system gaming | Medium | Medium | Human moderation backstop, iteration |
| Prophet installation issues | Medium | Low | Early spike, containerized environment |
| Scope creep | Medium | Medium | Strict MVP discipline, Phase 2 backlog |

See [RISK_REGISTER.md](./RISK_REGISTER.md) for full risk management details.

---

## Communication Plan

| Communication | Frequency | Participants | Format |
|---------------|-----------|--------------|--------|
| Progress updates | Weekly | All stakeholders | PROJECT_STATUS.md update |
| Technical decisions | As needed | Tech Lead, PM | Decision records (ADRs) |
| Milestone demos | Per milestone | All stakeholders | Live demonstration |
| Retrospectives | Per phase | Full team | Meeting notes |

---

## Approval

### Sign-off Checklist

- [x] Vision and goals clearly defined
- [x] MVP scope agreed upon
- [x] Technical approach validated
- [x] Timeline realistic and accepted
- [x] Risks identified with mitigations
- [x] Success criteria measurable
- [x] Stakeholders identified

**Charter Approved:** 2025-12-27

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-27 | PM Team | Initial charter creation |
