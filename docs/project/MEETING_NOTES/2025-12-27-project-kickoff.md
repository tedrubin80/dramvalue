# Project Kickoff: Secondary Market Spirits Price Intelligence Platform

**Date:** 2025-12-27
**Participants:** PM (Alex), Tech Lead (Jordan), Product Owner (Sam), QA Lead (Riley)
**Context:** Initial project kickoff to align on vision, scope, technical approach, and address open questions from the project brief.

---

## Opening

**[PM] Alex:** Good morning, team. We're here to kick off the "Spirits Price Intelligence Platform" - codename "WTracker." This is an ambitious project: a price tracking and valuation engine for secondary market bourbon and scotch. Before we dive in, let me frame what we're dealing with.

The primary user is the project owner themselves - a power user and collector who wants transparency in an opaque market. Secondary users are enthusiast collectors. We need to build something that's personally powerful but publicly presentable.

The MVP scope includes data aggregation from auctions and retail, a searchable bottle database, price trend visualization, personal collection valuation, and - this is where it gets interesting - a Monte Carlo simulation engine for price projections plus a fraud detection system for crowdsourced submissions.

Let's go around and get initial reactions. Sam, from a product perspective, what stands out?

---

## Initial Perspectives

**[PO] Sam:** This is a genuinely valuable problem space. The secondary spirits market is notoriously opaque - prices vary wildly between platforms, there's no central pricing authority, and collectors often overpay or undersell because they lack good data.

What excites me most is the trust-weighted submission system. That's the differentiator. Anyone can scrape auction data, but building a reputation system that makes crowdsourced data reliable? That's the moat.

My concern: we're building for a power user first, but the brief says "homepage should be consumer-friendly." We need to be careful not to optimize so hard for advanced features that we lose approachability. The first-time visitor experience should be dead simple: search for a bottle, see its price history. Everything else is progressive disclosure.

**[Tech Lead] Jordan:** From a technical standpoint, this is a fascinating architecture challenge. We're essentially building three systems in one:

1. **A data ingestion pipeline** - scraping, normalization, deduplication
2. **An analytics engine** - time series forecasting, anomaly detection, Monte Carlo simulations
3. **A trust and reputation system** - behavioral analysis, fraud detection, weighted scoring

The algorithm stack in the brief is comprehensive - maybe too comprehensive for MVP. I count 20+ algorithms mentioned. We need to ruthlessly prioritize. My recommendation: start with the statistical approaches (Z-score, Prophet, basic Bayesian reputation) and only add ML complexity when we have the data volume to justify it.

The brief's architecture notes are spot-on: we need a clean abstraction layer so algorithms are swappable. Feature flags for algorithm rollout is essential.

One thing I want to flag early: the scraping requirement. "Respectful scraping" with rate limiting and robots.txt compliance is non-negotiable for sustainability, but we should also design for API integration where available. Some auction houses may offer data feeds - that's always preferable to scraping.

**[QA] Riley:** I'm looking at this from a quality and risk perspective, and several things concern me:

1. **Data quality is the foundation.** If our ingested data is garbage, every algorithm built on top produces garbage. We need rigorous validation at the ingestion layer - not just fraud detection on user submissions, but sanity checks on scraped data too. Auction houses have typos, price errors, duplicate listings.

2. **The trust system is adversarial by nature.** We're explicitly designing for bad actors. That means our test strategy needs to include adversarial testing - can we break the fraud detection? What happens if a sophisticated actor submits plausible-looking fake data over months?

3. **Monte Carlo projections carry liability risk.** If we project "70% chance of $X-$Y in 90 days" and someone makes a $10,000 purchase decision based on that, we need disclaimers, confidence thresholds, and very clear communication that these are statistical models, not financial advice.

4. **The "no credentials in repo" requirement is absolute.** I want environment variable usage verified in CI. No exceptions.

**[PM] Alex:** All excellent points. Let's structure our discussion around the open questions from the brief, then synthesize into decisions.

---

## Open Questions Discussion

### Question 1: Recommended Scraping Framework

**[Tech Lead] Jordan:** For Python-based scraping with rate limiting requirements, I'd recommend **Scrapy** as the primary framework. Here's my reasoning:

- Built-in rate limiting and auto-throttling
- Respect for robots.txt out of the box
- Excellent for structured data extraction
- Middleware system for custom logic (caching, retries, proxies if needed)
- Can export directly to databases or message queues

For JavaScript-rendered pages (some modern auction sites), we'd pair it with **Playwright** or **Selenium** as needed, but Scrapy should handle 80%+ of sources.

Alternative considered: **BeautifulSoup + requests** is simpler but lacks Scrapy's built-in politeness features and scaling capabilities.

**[QA] Riley:** Whatever we choose, I want comprehensive logging. Every scrape attempt, success/failure, response times. We need to detect if a source changes their HTML structure or blocks us immediately.

**[PO] Sam:** From a product perspective, scraping is a means to an end. The key is that we surface data provenance clearly to users. "Last updated from Unicorn Auctions: 2 hours ago" type indicators.

**[PM] Alex:** Decision: **Scrapy as primary framework, with Playwright for JS-rendered pages.** Jordan, you'll own the technical spec for the scraping architecture.

---

### Question 2: Database Recommendation

**[Tech Lead] Jordan:** This is a nuanced one. Let me break down the options:

| Option | Pros | Cons |
|--------|------|------|
| **SQLite** | Zero config, single file, great for dev | Concurrency limits, no time-series optimization |
| **PostgreSQL** | Robust, excellent ecosystem, JSON support | More ops overhead than SQLite |
| **TimescaleDB** | Purpose-built for time series, PostgreSQL-compatible | Additional complexity, may be overkill initially |

My recommendation: **PostgreSQL from day one, with TimescaleDB extension as optional optimization later.**

Reasoning:
- Price data is fundamentally time-series, but our access patterns are mixed (time-series queries AND relational queries for bottle metadata, users, etc.)
- PostgreSQL handles both well
- TimescaleDB is a PostgreSQL extension, so migration is seamless if we need time-series optimization
- We avoid the SQLite-to-Postgres migration pain that always happens when projects scale
- PostgreSQL's JSONB support is excellent for storing semi-structured auction data before normalization

**[QA] Riley:** I support PostgreSQL. SQLite's concurrency model would become a bottleneck as soon as we have multiple scrapers running alongside user requests. And testing with the same database we'll run in production avoids "works on my machine" issues.

**[PO] Sam:** As long as it doesn't slow down development velocity, I'm aligned. The key product requirement is fast search and responsive charts. Jordan, can Postgres handle the query patterns for price history charts efficiently?

**[Tech Lead] Jordan:** Absolutely. With proper indexing on (bottle_id, timestamp), price history queries will be sub-100ms even at scale. We can add read replicas later if needed.

**[PM] Alex:** Decision: **PostgreSQL from day one, architect for TimescaleDB extension if time-series performance becomes a bottleneck.** This balances operational simplicity with future scalability.

---

### Question 3: Auth System Recommendation

**[Tech Lead] Jordan:** The brief specifies pseudonymous accounts with email verification. Options:

| Option | Pros | Cons |
|--------|------|------|
| **Self-rolled (bcrypt + JWT)** | Full control, no dependencies | Security responsibility on us, more code to maintain |
| **Passport.js** | Flexible, many strategies | Node.js only, still significant custom code |
| **Auth0/Clerk/Supabase Auth** | Battle-tested security, handles edge cases | External dependency, cost at scale, less control |
| **Django's auth** | Built-in, well-tested | Python/Django only |

Given the privacy-conscious user requirement and the "no credentials exposed" mandate, I'd lean toward **a well-tested library within our framework** rather than a third-party SaaS.

If we're building in Python (which aligns with our data science needs), **Flask-Login + Flask-Security or FastAPI with JWT** would work well. If Node.js, **Passport.js with local strategy**.

The key is: bcrypt for password hashing, JWT or secure sessions for auth state, rate limiting on login endpoints, and email verification flow.

**[QA] Riley:** I want to emphasize: auth is security-critical. Whatever we build needs:
- Password hashing with bcrypt (cost factor >= 12)
- Rate limiting on auth endpoints
- Secure session management (HttpOnly, Secure, SameSite cookies)
- CSRF protection
- Account lockout after failed attempts
- Secure password reset flow

If we self-roll, I'm adding auth penetration testing to the QA plan.

**[PO] Sam:** From a user perspective, the flow should be frictionless. Pseudonymous signup, email verification for trust, done. No OAuth for now - it complicates the pseudonymous model.

**[PM] Alex:** Decision: **Self-rolled auth using FastAPI with python-jose (JWT) and passlib (bcrypt), with comprehensive security controls.** We'll document the security requirements explicitly. Riley, please include auth testing in the QA plan.

---

### Question 4: Hosting Environment Preference

**[Tech Lead] Jordan:** The brief doesn't specify budget constraints, but I'm assuming we want cost-efficiency for what starts as a personal project. Options:

| Option | Pros | Cons |
|--------|------|------|
| **VPS (DigitalOcean, Linode, Vultr)** | Simple, predictable cost, full control | Manual ops, scaling requires effort |
| **PaaS (Railway, Render, Fly.io)** | Easy deployment, auto-scaling | Cost can grow, less control |
| **AWS/GCP/Azure** | Maximum flexibility, every service available | Complexity, potential cost surprises |
| **Self-hosted (home server)** | Maximum privacy, no recurring cost | Reliability, security, internet dependency |

My recommendation: **Start with a VPS (DigitalOcean or Linode)**, with Docker for containerization. This gives us:
- Predictable $20-50/month cost
- Full control over the environment
- Easy migration path to Kubernetes or cloud if we scale
- Docker Compose for local dev parity

For a privacy-conscious personal project, avoiding big cloud providers also has appeal.

**[PO] Sam:** I'd add: the homepage needs to be snappy. Whatever we choose, we should have a CDN in front for static assets. Cloudflare's free tier would work.

**[QA] Riley:** Docker is essential for environment parity. "Works on my machine" is unacceptable. I want the same containers running in dev, CI, and production.

**[PM] Alex:** Decision: **DigitalOcean VPS with Docker Compose, Cloudflare CDN for static assets.** We can re-evaluate if traffic demands it. Jordan, include the infrastructure setup in the technical spec.

---

### Question 5: Prophet vs. statsmodels for Initial Forecasting

**[Tech Lead] Jordan:** Both are excellent. Let me compare:

| Criteria | Prophet | statsmodels (ARIMA/SARIMAX) |
|----------|---------|------------------------------|
| Ease of use | Very high - just fit and predict | Moderate - requires parameter tuning |
| Missing data handling | Excellent - built for gaps | Requires preprocessing |
| Seasonality | Automatic detection | Manual specification |
| Interpretability | Good - decomposition is clear | Good - statistical foundations |
| Speed | Slower (MCMC sampling) | Faster |
| Dependencies | Heavier (pystan) | Lighter |

My recommendation: **Prophet for MVP.**

Reasoning:
- Our price data will have gaps (not every bottle sells every day)
- We want to detect seasonality automatically (release cycles, holidays)
- The brief already specifies Prophet as MVP priority
- We can add ARIMA/SARIMA in Phase 2 for bottles with strong regular seasonality

The key is our abstraction layer. Both should implement the same interface so they're swappable.

**[QA] Riley:** Prophet's dependency on PyStan/CmdStan has historically been painful to install. Jordan, please verify the installation story in our Docker environment early.

**[Tech Lead] Jordan:** Noted. I'll spike the Prophet installation in Docker as a first task.

**[PO] Sam:** From a product perspective, the forecasting output needs to be crystal clear. "Projected price range" with confidence bands, not just a single number. And always with a "based on X data points over Y time period" disclaimer.

**[PM] Alex:** Decision: **Prophet for MVP forecasting, with an abstraction layer for future algorithm additions.** Jordan to verify Docker installation early.

---

### Question 6: Queue System for Moderation

**[Tech Lead] Jordan:** The moderation queue needs to:
1. Hold flagged submissions
2. Allow admin review
3. Track status (pending, approved, rejected)
4. Maintain audit trail

Options:

| Option | Pros | Cons |
|--------|------|------|
| **Simple Postgres table** | No additional infrastructure, ACID, queryable | Not a "real" queue, but do we need one? |
| **Redis + RQ/Celery** | True async, pub/sub capability | Additional infrastructure, complexity |
| **Postgres-backed queue (pgqueue)** | Best of both - Postgres simplicity with queue semantics | Less ecosystem than Redis |

My recommendation: **Simple Postgres table with status enum for MVP.**

Why? The moderation queue isn't high-throughput. We're talking about human review of flagged submissions. A status table with (id, submission_id, flag_reason, status, reviewer_id, reviewed_at, action_taken) is sufficient.

We can add Redis for background job processing later (e.g., async scraping, forecast recalculation), but for moderation, Postgres is fine.

**[QA] Riley:** Agreed. Simpler is better for auditability. I want every moderation action logged with timestamp, actor, and reason. A Postgres table with audit triggers gives us that naturally.

**[PO] Sam:** The admin experience matters too. The moderation queue should show context: what's the current price, how does this submission compare, what's the submitter's history? All queryable from Postgres without additional complexity.

**[PM] Alex:** Decision: **Postgres table for moderation queue in MVP. Re-evaluate for Redis if we need async job processing.** Keep the audit trail complete.

---

### Question 7: Feature Store Approach for Future ML Integration

**[Tech Lead] Jordan:** The brief mentions future algorithms that will need precomputed features: bottle embeddings, user behavior vectors, etc. Feature store options:

| Option | Pros | Cons |
|--------|------|------|
| **Feast** | Open source, battle-tested | Operational complexity |
| **Postgres materialized views** | Simple, no new infrastructure | Limited to SQL-computable features |
| **Custom: Postgres + compute jobs** | Flexible, we control everything | More code to write |
| **No feature store (compute on demand)** | Simplest | Performance issues at scale |

My recommendation: **Start with Postgres materialized views + a simple compute pattern, architect for Feast later.**

For MVP, we need:
- Precomputed bottle price statistics (mean, std dev, percentiles)
- User trust scores
- Bottle similarity vectors (for "similar bottles" later)

Materialized views handle the first two elegantly. For embeddings, we can store them in a features table and refresh via a scheduled job.

We should design our schema with a clean separation: source tables vs. feature tables. This makes migration to Feast straightforward if we need it.

**[QA] Riley:** Materialized views have refresh timing considerations. We need to test that features are fresh enough when predictions run. No stale data bugs.

**[PO] Sam:** As long as the user experience doesn't lag. If I add a new transaction, I expect it to affect projections within reasonable time - say, hourly at worst for MVP.

**[Tech Lead] Jordan:** Agreed. We'll design for incremental updates where possible, batch refresh for complex features.

**[PM] Alex:** Decision: **Materialized views + feature tables in Postgres for MVP. Design schema to be Feast-compatible for future migration.** Document the feature computation schedule.

---

## Scope & Priority Alignment

**[PM] Alex:** Let's confirm MVP scope. The brief has MVP items tagged, but I want to make sure we're aligned. Sam, what's the absolute minimum for a usable product?

**[PO] Sam:** For me, the MVP must deliver on this promise: **"Search for a bottle, see its price history with confidence, add your collection, see its estimated value."**

That means:
1. Data ingestion from at least one auction source (working pipeline)
2. Bottle database with normalized names
3. Search functionality
4. Price history chart per bottle
5. Basic collection management (add bottles, see value)
6. Prophet-based projections with confidence bands
7. Basic fraud detection (Z-score, simple pattern flags)
8. Pseudonymous auth with email verification
9. Clean homepage for first-time visitors

What can wait for Phase 2:
- Multiple auction sources (start with one, prove the pipeline)
- Advanced anomaly detection (Isolation Forest, LOF)
- Trust score propagation
- Release cycle awareness in projections
- Full admin moderation dashboard (start with basic flags visible)

**[Tech Lead] Jordan:** That scope is achievable. My concern is the breadth of the fraud detection requirements. The pattern table in the brief lists 6+ patterns. Can we prioritize?

**[QA] Riley:** From a risk perspective, I'd prioritize:
1. Price significantly outside range (>2 std dev) - catches obvious manipulation
2. New account submitting high volume - catches spam accounts
3. Single user dominates a bottle's price data - prevents single-actor manipulation

The others (exact price matches, round numbers, burst detection) are refinements.

**[PO] Sam:** Agreed. Let's ship the highest-impact fraud detection first, iterate based on what we see.

**[PM] Alex:** Scope confirmed. MVP is focused on the core value prop with essential fraud protection. We'll document Phase 2 items in the roadmap.

---

## Risk Identification

**[PM] Alex:** Riley, what are the top risks you see?

**[QA] Riley:** My risk register, in priority order:

1. **Data source instability** (HIGH) - Auction sites may change HTML, block scrapers, or shut down. Mitigation: Multiple sources, monitoring, graceful degradation.

2. **Prophet installation/performance** (MEDIUM) - PyStan dependencies are historically painful. Mitigation: Early spike, containerized environment.

3. **Trust system gaming** (MEDIUM) - Sophisticated actors may find ways around fraud detection. Mitigation: Human moderation backstop, iterative improvement.

4. **Scope creep** (MEDIUM) - The brief is ambitious. Mitigation: Strict MVP discipline, Phase 2 backlog for everything else.

5. **Credential exposure** (HIGH) - Any secret in the repo is a breach. Mitigation: Pre-commit hooks, CI checks, secrets scanning.

6. **Single point of failure** (LOW for MVP) - Personal project, single developer. Mitigation: Documentation, clean code, tests.

**[Tech Lead] Jordan:** I'd add: **naming normalization complexity** (MEDIUM). "BT Stagg" vs "George T. Stagg" vs "Stagg" is a known-hard NLP problem. We may underestimate the effort to build a good normalizer.

**[PO] Sam:** And **user experience of projections** (MEDIUM). If projections feel unreliable or confusing, users lose trust in the platform. We need to invest in clear communication design.

**[PM] Alex:** Excellent. We'll document all of these in the risk register. Top priorities: data source stability, credential exposure, and naming normalization.

---

## Timeline Discussion

**[PM] Alex:** Given the scope, what's a realistic timeline to MVP?

**[Tech Lead] Jordan:** Let me rough out the phases:

| Phase | Weeks | Focus |
|-------|-------|-------|
| **Infrastructure Setup** | 1 | Docker, Postgres, project scaffold, CI/CD |
| **Data Ingestion** | 2-3 | Scrapy pipeline, one auction source, normalization |
| **Core Database & API** | 2 | Bottle model, price model, search API |
| **Auth & User System** | 1 | Pseudonymous auth, email verification |
| **Frontend Foundation** | 2 | Homepage, search, bottle detail pages, charts |
| **Collection Management** | 1 | User collections, valuation |
| **Forecasting Engine** | 2 | Prophet integration, confidence bands |
| **Fraud Detection** | 1-2 | Core pattern detection, moderation basics |
| **Polish & QA** | 2 | Testing, bug fixes, UX refinement |

**Total: 14-16 weeks to MVP**, assuming focused effort.

**[QA] Riley:** That feels aggressive but achievable. I want QA integrated throughout, not just at the end. Testing should happen in parallel with development.

**[PO] Sam:** Can we ship incrementally? I'd love to have a working bottle search + price history by week 6-7, even without projections.

**[Tech Lead] Jordan:** Yes, we should plan for incremental milestones:
- **Milestone 1 (Week 4):** Scraping pipeline + bottle database (internal use)
- **Milestone 2 (Week 7):** Search + price history (demo-able)
- **Milestone 3 (Week 10):** Auth + collections (usable for personal tracking)
- **Milestone 4 (Week 13):** Forecasting + fraud detection (feature-complete)
- **Milestone 5 (Week 15):** Polish + launch prep

**[PM] Alex:** I like the incremental approach. Let's plan for these milestones with internal demos. We'll track against them in the project status.

---

## Action Items

**[PM] Alex:** Let's capture action items:

1. **[Jordan]** Create technical architecture document with database schema, API design, and infrastructure spec
2. **[Jordan]** Spike Prophet installation in Docker environment (de-risk early)
3. **[Jordan]** Select and configure Scrapy for first auction source
4. **[Sam]** Write detailed user stories for MVP features with acceptance criteria
5. **[Sam]** Design first-time visitor homepage experience (wireframe or description)
6. **[Riley]** Define QA plan including auth penetration testing and adversarial fraud scenarios
7. **[Riley]** Create CI pipeline requirements including secrets scanning
8. **[Alex]** Finalize project charter and timeline
9. **[Alex]** Set up project tracking and documentation structure

---

## Closing

**[PM] Alex:** Great kickoff, team. We have a clear vision, scoped MVP, technical decisions made, and risks identified. I'll formalize the charter and timeline today. Jordan, start with the infrastructure setup and Prophet spike. Sam, get those user stories fleshed out. Riley, begin the QA plan.

Let's reconvene in one week for a progress check. Any final thoughts?

**[PO] Sam:** Just excited to build this. The market genuinely needs it.

**[Tech Lead] Jordan:** Agreed. The architecture is interesting - lots of good problems to solve.

**[QA] Riley:** Looking forward to breaking things before users do.

**[PM] Alex:** Meeting adjourned. Let's build something great.

---

### [Facilitator] Summary

**Decision Summary:**

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Scraping Framework | Scrapy + Playwright | Built-in rate limiting, robots.txt compliance, handles JS rendering |
| Database | PostgreSQL (TimescaleDB-ready) | Time-series + relational needs, avoids SQLite scaling pain |
| Auth System | FastAPI + JWT + bcrypt (self-rolled) | Full control, privacy-conscious, comprehensive security controls |
| Hosting | DigitalOcean VPS + Docker + Cloudflare | Predictable cost, full control, CDN for performance |
| Forecasting | Prophet for MVP | Handles gaps, auto-seasonality, per brief priority |
| Moderation Queue | Postgres table | Simplicity, auditability, sufficient for human-review throughput |
| Feature Store | Materialized views + feature tables | Simple MVP, Feast-compatible for future |

**Key Risks Identified:**
1. Data source instability (scraping fragility)
2. Credential exposure
3. Naming normalization complexity
4. Trust system gaming
5. Prophet installation challenges

**MVP Scope Confirmed:**
- Single auction source pipeline
- Bottle database with search
- Price history visualization
- Pseudonymous auth
- Collection management
- Prophet forecasting with confidence bands
- Core fraud detection (3 patterns)

**Timeline:** 14-16 weeks to MVP with 5 incremental milestones

**Next Phase:** Discovery & Requirements complete; moving to Architecture & Design

---

## Appendix A: Original Project Brief

The following is the original project brief that initiated this kickoff discussion.

---

# Project Brief: Secondary Market Spirits Price Intelligence Platform

## Overview
Build a price tracking and valuation engine for secondary market bourbon and scotch. Aggregates public auction data, retail pricing, and crowdsourced transaction reports into a searchable database with trend analysis, predictive modeling, and personal collection valuation.

## Target User
Primary: Myself (power user, collector, privacy-conscious)
Secondary: Enthusiast collectors navigating an opaque market
Homepage should be consumer-friendly even while building for personal use first.

---

## Core Features (MVP)

### Data Aggregation
- Scrape/ingest public auction results (Unicorn Auctions, Whisky Auctioneer, Scotch Whisky Auctions)
- Track retail pricing from secondary market shops
- Accept crowdsourced transaction submissions from verified users

### Bottle Database
- Searchable by name, distillery, age, release year, bottle size
- Normalize naming variations (e.g., "BT Stagg" vs "George T. Stagg")
- Each bottle page shows: price history chart, data source breakdown, confidence score

### Price Trends
- Time-series visualization per bottle
- Market-wide trends (category level: allocated bourbon, single malt scotch, etc.)
- Anomaly flagging (sudden spikes/drops)

### Personal Collection Valuation
- User can input bottles they own
- System estimates current market value based on aggregated data
- Track collection value over time

---

## User System

### Authentication
- Pseudonymous accounts (display name, no real identity required)
- Email verification required for submission privileges
- Email visible to admin only, never exposed publicly
- No hardcoded passwords or API keys anywhere in codebase
- Use environment variables for all secrets

### Trust Weighting
- Verified submitters (email confirmed) get base trust score
- Submissions from accounts with history weighted higher
- Auction/retail data weighted highest (verifiable source)
- Display data provenance on bottle pages

---

## Price Projection Engine

### Monte Carlo Simulation
- Project future price ranges based on historical transaction data
- Inputs: historical prices, time between transactions, volume trends, seasonal patterns
- Outputs: probability distribution of future prices (30/60/90/180 day projections)
- Display as confidence bands (e.g., "70% chance between $X-$Y in 90 days")
- Recalculate on new data ingestion
- Flag low-confidence projections (insufficient data points)

### Release Cycle Awareness
- Track annual/limited releases and their historical price decay or appreciation
- Factor release patterns into projection model
- Example: Birthday Bourbon historically peaks in October, declines through February

---

## Fraud Detection & Submission Integrity

### Pattern Recognition Algorithm
Detect and flag suspicious submission behavior:

| Pattern | Action |
|---------|--------|
| Same price submitted multiple times (exact match) | Auto-flag for moderator review |
| Price significantly outside current range (>2 std dev) | Soft flag, reduce weight, queue review |
| New account submitting high volume | Throttle + flag |
| Burst submissions (many in short window) | Rate limit + flag |
| Price always round numbers ($1000, $500) | Reduce confidence weight |
| Single user dominates a bottle's price data | Cap influence percentage |

### Weighted Submission Scoring
Each submission gets a confidence score based on:
- Account age and history
- Verification status
- Submission pattern health (no flags)
- Corroboration (other sources show similar price)
- Recency (newer data weighted slightly higher)

### Moderation Queue
- Flagged submissions held from affecting live averages until reviewed
- Admin dashboard shows: flag reason, submitter history, comparison to existing data
- Actions: approve (add to dataset), reject (discard), ban user, adjust weight manually

### Weighted Average Protection
- No single submission can move a bottle's average more than X% without corroboration
- Outliers included in raw data but excluded from displayed average until verified
- Show users "verified average" vs "all submissions" toggle

---

## Algorithm Stack

### Price Forecasting

| Algorithm | Purpose | Priority |
|-----------|---------|----------|
| Facebook Prophet | Primary forecasting — handles missing data, outliers, seasonality | MVP |
| Monte Carlo Simulation | Confidence bands and probability distributions | MVP |
| ARIMA/SARIMA | Time series with strong seasonal components | Phase 2 |
| Bayesian Regression | Probabilistic predictions with uncertainty quantification | Phase 2 |
| Exponential Smoothing | Fast trend computation for real-time updates | Phase 2 |
| LSTM | Deep learning for complex patterns (if data scale justifies) | Future |

### Anomaly Detection

| Algorithm | Purpose | Priority |
|-----------|---------|----------|
| Z-Score / Modified Z-Score | Simple statistical bounds, fast baseline | MVP |
| Isolation Forest | Robust outlier detection for price submissions | MVP |
| Local Outlier Factor (LOF) | Contextual anomalies relative to similar bottles | Phase 2 |
| DBSCAN | Density-based clustering that identifies outliers as noise | Phase 2 |
| Change Point Detection (PELT/Bayesian) | Identify market regime shifts (tariffs, closures, hype) | MVP |

### Trust & Reputation

| Algorithm | Purpose | Priority |
|-----------|---------|----------|
| Bayesian Reputation | Probabilistic trust scoring, updates with each submission | MVP |
| Velocity Scoring | Detect sudden behavior changes in established users | MVP |
| PageRank-style Propagation | Trust flows from verified users to their vouched connections | Phase 2 |
| Collaborative Filtering (inverted) | Detect coordinated manipulation rings | Phase 2 |

### Market Intelligence

| Algorithm | Purpose | Priority |
|-----------|---------|----------|
| K-Means Clustering | Segment bottles by price behavior patterns | MVP |
| Correlation Matrix | Identify bottles that move together | MVP |
| Hierarchical Clustering | Market segmentation (allocated, craft, scotch tiers) | Phase 2 |
| Dynamic Time Warping | Compare price curves offset in time | Phase 2 |
| Granger Causality | Predictive relationships between bottles | Phase 2 |
| Cosine Similarity | Find bottles with matching trajectory shapes | Phase 2 |
| Elasticity Modeling | Price sensitivity to supply/release changes | Future |
| Sentiment Analysis (NLP) | Chatter-to-price correlation if scraping forums | Future |

### Recommendation (Future — Architect for Easy Integration)

| Algorithm | Purpose | Priority |
|-----------|---------|----------|
| Content-Based Filtering | "Bottles similar to ones you own" | Future |
| Collaborative Filtering | "Collectors like you also watch..." | Future |

### Architecture Notes for Future Algorithms
- Abstract data access layer so algorithms consume normalized interfaces
- Feature store pattern: precompute bottle embeddings, user behavior vectors
- Event-driven ingestion so new algorithms can subscribe to data streams
- Model registry for versioning and A/B testing algorithm performance
- API contracts defined early so recommendation engine plugs in cleanly

---

## Admin Tools
- Moderation queue with flag reasons
- User trust score management
- Manual weight adjustment per submission
- Bulk approval/rejection
- Audit log of all moderation actions
- Algorithm performance dashboard (prediction accuracy, anomaly catch rate)

---

## Technical Constraints
- Environment variables for all credentials and API keys
- Secrets management from day one
- Scraping must be respectful (rate limiting, caching, robots.txt compliance)
- Database design should anticipate scale but start simple
- Future-proof for API exposure (clean data layer separation)
- Modular algorithm integration — each algorithm should be swappable/testable independently
- Feature flags for algorithm rollout

---

## Data Source Priority
1. Public auction houses (structured, reliable, timestamped)
2. Secondary retail shops (less structured, needs normalization)
3. Crowdsourced submissions (most granular but needs trust weighting)

---

## Success Criteria
- Can search for a bottle and see price history from multiple sources
- Can add my own bottles and see estimated value
- Can submit a transaction anonymously and see it reflected in trends
- Monte Carlo projections display with confidence bands
- Suspicious submissions flagged before affecting averages
- No credentials exposed in repo
- Homepage loads clean for a first-time visitor
- Algorithm layer is modular and documented for future additions

---

## Out of Scope (for now)
- Marketplace functionality (no buying/selling on platform)
- Mobile app
- Public API
- Social features beyond submissions
- Collaborative Filtering recommendations (architected but not implemented)

---

## Open Questions for PM Team
- Recommended scraping framework given rate limit requirements?
- Database recommendation (Postgres? SQLite to start? TimescaleDB for time series?)
- Auth system recommendation (self-rolled vs. library)?
- Hosting environment preference?
- Prophet vs. statsmodels for initial forecasting implementation?
- Queue system for moderation (Redis? Postgres-backed? Simple table?)
- Feature store approach for future ML integration?
