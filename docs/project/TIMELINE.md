# Project Timeline: WTracker

**Created:** 2025-12-27
**Last Updated:** 2025-12-27
**Version:** 1.0
**Status:** Approved

---

## Timeline Overview

**Total Duration:** 14-16 weeks
**Start Date:** 2025-12-30 (Week 1)
**Target MVP Launch:** 2026-04-14 (Week 16)

```
Week:  1    2    3    4    5    6    7    8    9   10   11   12   13   14   15   16
       |----|----|----|----|----|----|----|----|----|----|----|----|----|----|----|
Phase: |=P1=|====== P2 ======|======== P3 =========|===== P4 =====|== P5 ==|= P6 =|
       Infra   Data Ingestion      Core Platform       Intelligence   Polish  Launch

Milestones:
       M1                    M2                      M3             M4       M5
       Wk2                   Wk5                     Wk8            Wk11     Wk14
```

---

## Phase Definitions

### Phase 1: Infrastructure Setup
**Duration:** 1 week (Week 1-2)
**Owner:** Tech Lead (Jordan)

**Objectives:**
- Establish development environment
- Set up CI/CD pipeline
- Configure database and caching
- Implement security foundations

**Key Activities:**
| Activity | Duration | Dependencies |
|----------|----------|--------------|
| Docker Compose setup | 2 days | None |
| PostgreSQL schema creation | 1 day | Docker |
| Redis configuration | 0.5 day | Docker |
| FastAPI project scaffold | 1 day | Docker |
| GitHub Actions CI/CD | 1 day | Scaffold |
| Pre-commit hooks (secrets scanning) | 0.5 day | Scaffold |
| Environment configuration | 0.5 day | All above |

**Deliverables:**
- [ ] Working Docker Compose environment
- [ ] PostgreSQL with all tables created
- [ ] Redis running for caching
- [ ] FastAPI application responding at /health
- [ ] CI pipeline running tests on push
- [ ] Pre-commit hooks enforcing code quality

**Exit Criteria:**
- All developers can run `docker-compose up` and access the API
- CI passes on clean repository
- Database migrations work reliably
- No secrets in codebase (verified by detect-secrets)

---

### Phase 2: Data Ingestion Pipeline
**Duration:** 3 weeks (Week 2-5)
**Owner:** Tech Lead (Jordan)

**Objectives:**
- Build scraping infrastructure
- Integrate first auction source
- Implement bottle normalization
- Create data validation layer

**Key Activities:**
| Activity | Duration | Dependencies |
|----------|----------|--------------|
| Scrapy project setup | 2 days | P1 complete |
| First auction spider | 5 days | Scrapy setup |
| HTML parsing and extraction | 3 days | Spider |
| Rate limiting and politeness | 1 day | Spider |
| Bottle name normalization | 4 days | Extraction |
| Data validation pipeline | 2 days | Normalization |
| Price storage and deduplication | 2 days | Validation |
| Scrape monitoring and alerts | 1 day | All above |

**Deliverables:**
- [ ] Scrapy spider for primary auction source
- [ ] Automated rate-limited scraping
- [ ] Bottle normalization algorithm
- [ ] Data validation rules
- [ ] Scrape run logging and monitoring
- [ ] 1000+ bottles in database

**Exit Criteria:**
- Scraper runs successfully on schedule
- New auction results appear in database within 24 hours
- Normalization correctly maps 90%+ of bottle names
- No duplicate prices for same transaction

**Dependencies:**
- Phase 1 must be complete
- Auction source structure must be documented

---

### Phase 3: Core Platform
**Duration:** 3 weeks (Week 5-8)
**Owner:** Full Team

**Objectives:**
- Build bottle search and display
- Implement authentication system
- Create user collections
- Develop basic admin tools

**Sub-phases:**

#### 3A: Bottle Database & Search (Week 5-6)
| Activity | Duration | Dependencies | Owner |
|----------|----------|--------------|-------|
| Bottle API endpoints | 2 days | P2 data | Jordan |
| Price history API | 2 days | Bottle API | Jordan |
| Search functionality | 3 days | Bottle API | Jordan |
| Homepage template | 2 days | APIs | Jordan |
| Bottle detail page | 2 days | APIs | Jordan |
| Price history charts | 2 days | Detail page | Jordan |

#### 3B: Authentication System (Week 6-7)
| Activity | Duration | Dependencies | Owner |
|----------|----------|--------------|-------|
| User model and registration | 2 days | None | Jordan |
| JWT token implementation | 2 days | User model | Jordan |
| Email verification flow | 2 days | JWT | Jordan |
| Password reset flow | 1 day | Email | Jordan |
| Login/logout UI | 1 day | All auth | Jordan |
| Rate limiting on auth | 0.5 day | Auth complete | Jordan |
| Auth penetration testing | 1 day | All auth | Riley |

#### 3C: Collections & User Features (Week 7-8)
| Activity | Duration | Dependencies | Owner |
|----------|----------|--------------|-------|
| Collection API endpoints | 2 days | Auth | Jordan |
| Collection item management | 2 days | Collection API | Jordan |
| Collection valuation | 2 days | Price data | Jordan |
| Collection UI | 2 days | APIs | Jordan |
| User profile page | 1 day | Auth | Jordan |

**Deliverables:**
- [ ] Searchable bottle database
- [ ] Price history visualization
- [ ] User registration and login
- [ ] Email verification
- [ ] Personal collections
- [ ] Collection valuation display

**Exit Criteria:**
- Users can search, view bottles, and see price history
- Authentication is secure (pen test passed)
- Collections show current market value
- Demo-ready for stakeholder review

**Milestone 2 Demo:** End of Week 5
- Show: Bottle search, price history charts
- Audience: Project sponsor

---

### Phase 4: Intelligence Engine
**Duration:** 3 weeks (Week 8-11)
**Owner:** Tech Lead (Jordan)

**Objectives:**
- Implement Prophet forecasting
- Build anomaly detection
- Create submission system
- Develop moderation queue

**Sub-phases:**

#### 4A: Forecasting Engine (Week 8-9)
| Activity | Duration | Dependencies | Owner |
|----------|----------|--------------|-------|
| Algorithm abstraction layer | 2 days | P3 complete | Jordan |
| Prophet integration | 3 days | Abstraction | Jordan |
| Simple average fallback | 1 day | Abstraction | Jordan |
| Forecast storage and caching | 2 days | Prophet | Jordan |
| Forecast API endpoints | 1 day | Storage | Jordan |
| Confidence band visualization | 2 days | API | Jordan |
| Forecast disclaimer UI | 0.5 day | Visualization | Jordan |

#### 4B: Anomaly Detection (Week 9-10)
| Activity | Duration | Dependencies | Owner |
|----------|----------|--------------|-------|
| Z-score detector | 2 days | Abstraction | Jordan |
| Velocity detector | 2 days | Abstraction | Jordan |
| Detector aggregation | 1 day | Detectors | Jordan |
| Submission flagging | 2 days | Aggregation | Jordan |
| Algorithm metrics tracking | 1 day | All detectors | Jordan |

#### 4C: Submission & Moderation (Week 10-11)
| Activity | Duration | Dependencies | Owner |
|----------|----------|--------------|-------|
| Submission API endpoint | 2 days | Anomaly detection | Jordan |
| Submission UI form | 2 days | API | Jordan |
| Moderation queue backend | 2 days | Submissions | Jordan |
| Moderation queue UI | 2 days | Backend | Jordan |
| Moderation actions | 1 day | Queue | Jordan |
| Audit logging | 1 day | Actions | Jordan |
| Trust score calculation | 2 days | Submissions | Jordan |

**Deliverables:**
- [ ] Prophet-based price forecasts
- [ ] Confidence band display
- [ ] Z-score anomaly detection
- [ ] Velocity-based fraud detection
- [ ] User submission system
- [ ] Admin moderation queue
- [ ] Audit trail for moderation

**Exit Criteria:**
- Forecasts generate for bottles with 10+ data points
- Anomalies are flagged before affecting averages
- Moderators can approve/reject submissions
- All moderation actions are logged

**Milestone 3 Demo:** End of Week 8
- Show: Forecasting, collections with valuation
- Audience: Project sponsor

---

### Phase 5: Polish & Hardening
**Duration:** 2 weeks (Week 11-13)
**Owner:** Full Team

**Objectives:**
- Improve user experience
- Performance optimization
- Security hardening
- Documentation

**Key Activities:**
| Activity | Duration | Dependencies | Owner |
|----------|----------|--------------|-------|
| Homepage UX improvements | 3 days | Core complete | Jordan |
| Mobile responsive design | 2 days | UX | Jordan |
| Performance profiling | 2 days | Core complete | Jordan |
| Query optimization | 2 days | Profiling | Jordan |
| Cache tuning | 1 day | Profiling | Jordan |
| Security audit | 2 days | Core complete | Riley |
| Penetration testing | 2 days | Audit | Riley |
| API documentation | 2 days | APIs stable | Jordan |
| User guide | 2 days | UI stable | Sam |
| Error handling improvements | 2 days | Testing | Jordan |

**Deliverables:**
- [ ] Responsive mobile design
- [ ] Sub-2s homepage load time
- [ ] Security audit report
- [ ] API documentation (OpenAPI)
- [ ] User guide
- [ ] Error pages and messaging

**Exit Criteria:**
- Performance targets met
- Security vulnerabilities addressed
- Documentation complete
- User experience approval from PO

---

### Phase 6: QA & Launch
**Duration:** 2 weeks (Week 13-16)
**Owner:** QA Lead (Riley)

**Objectives:**
- Comprehensive testing
- Bug fixes
- Production deployment
- Launch preparation

**Sub-phases:**

#### 6A: Testing (Week 13-14)
| Activity | Duration | Dependencies | Owner |
|----------|----------|--------------|-------|
| Integration test suite | 3 days | P5 complete | Riley |
| End-to-end testing | 3 days | Integration | Riley |
| Load testing | 2 days | E2E | Riley |
| Adversarial testing (fraud) | 2 days | E2E | Riley |
| Bug triage and fixes | 3 days | All testing | Jordan |
| Regression testing | 2 days | Bug fixes | Riley |

#### 6B: Deployment (Week 14-15)
| Activity | Duration | Dependencies | Owner |
|----------|----------|--------------|-------|
| Production environment setup | 2 days | Testing complete | Jordan |
| SSL/TLS configuration | 0.5 day | Prod env | Jordan |
| Cloudflare CDN setup | 0.5 day | SSL | Jordan |
| Database migration to prod | 1 day | Prod env | Jordan |
| Deployment automation | 1 day | All prod | Jordan |
| Production smoke tests | 1 day | Deployment | Riley |
| Monitoring setup | 1 day | Deployment | Jordan |

#### 6C: Launch (Week 15-16)
| Activity | Duration | Dependencies | Owner |
|----------|----------|--------------|-------|
| Final security check | 1 day | Prod ready | Riley |
| Backup verification | 0.5 day | Prod ready | Jordan |
| Launch checklist review | 0.5 day | All ready | Alex |
| Go-live | 1 day | Checklist | Jordan |
| Post-launch monitoring | 3 days | Go-live | All |
| Bug hotfixes | As needed | Monitoring | Jordan |

**Deliverables:**
- [ ] Test reports (all passing)
- [ ] Load test results
- [ ] Production environment
- [ ] Monitoring dashboards
- [ ] Backup strategy verified
- [ ] Live application

**Exit Criteria:**
- All critical/high bugs resolved
- Load test shows acceptable performance
- Production stable for 48 hours
- Stakeholder sign-off

---

## Milestones

### M1: Infrastructure Complete
**Target:** End of Week 2 (2026-01-10)
**Owner:** Tech Lead

**Criteria:**
- [x] Docker environment working
- [x] Database schema deployed
- [x] CI/CD pipeline operational
- [x] Development workflow documented

**Deliverables:**
- Working development environment
- CI/CD configuration
- Database schema SQL

---

### M2: Data Pipeline Operational
**Target:** End of Week 5 (2026-01-31)
**Owner:** Tech Lead

**Criteria:**
- [ ] First auction source integrated
- [ ] 1000+ bottles in database
- [ ] Normalization achieving 90%+ accuracy
- [ ] Scraping running on schedule

**Deliverables:**
- Scrapy spider
- Normalization rules
- Scrape monitoring

**Demo:** Stakeholder review of data quality

---

### M3: Core Platform Demo
**Target:** End of Week 8 (2026-02-21)
**Owner:** Full Team

**Criteria:**
- [ ] Search functionality working
- [ ] Price history charts displaying
- [ ] User authentication complete
- [ ] Collections with valuation

**Deliverables:**
- Functional web application
- User authentication system
- Collection management

**Demo:** Full walkthrough for stakeholder

---

### M4: Intelligence Engine Complete
**Target:** End of Week 11 (2026-03-14)
**Owner:** Tech Lead

**Criteria:**
- [ ] Forecasts generating for eligible bottles
- [ ] Anomaly detection flagging outliers
- [ ] Submission system operational
- [ ] Moderation queue functional

**Deliverables:**
- Forecasting engine
- Fraud detection
- Moderation tools

**Demo:** Algorithm demonstration, fraud scenarios

---

### M5: Launch Ready
**Target:** End of Week 14 (2026-04-04)
**Owner:** QA Lead

**Criteria:**
- [ ] All tests passing
- [ ] Performance targets met
- [ ] Security audit passed
- [ ] Documentation complete

**Deliverables:**
- Test reports
- Security audit
- User documentation

**Go/No-Go Decision:** Week 15 start

---

## Dependency Map

```
                              +----------------+
                              |  Phase 1       |
                              |  Infrastructure|
                              +-------+--------+
                                      |
                    +-----------------+-----------------+
                    |                                   |
            +-------v--------+                  +-------v--------+
            |  Phase 2       |                  |  Phase 3A      |
            |  Data Ingestion|                  |  Bottle DB     |
            +-------+--------+                  +-------+--------+
                    |                                   |
                    |                           +-------v--------+
                    |                           |  Phase 3B      |
                    |                           |  Authentication|
                    |                           +-------+--------+
                    |                                   |
                    |                           +-------v--------+
                    |                           |  Phase 3C      |
                    |                           |  Collections   |
                    |                           +-------+--------+
                    |                                   |
                    +-----------------+-----------------+
                                      |
                              +-------v--------+
                              |  Phase 4A      |
                              |  Forecasting   |
                              +-------+--------+
                                      |
                              +-------v--------+
                              |  Phase 4B      |
                              |  Anomaly Det.  |
                              +-------+--------+
                                      |
                              +-------v--------+
                              |  Phase 4C      |
                              |  Submissions   |
                              +-------+--------+
                                      |
                              +-------v--------+
                              |  Phase 5       |
                              |  Polish        |
                              +-------+--------+
                                      |
                              +-------v--------+
                              |  Phase 6       |
                              |  QA & Launch   |
                              +----------------+
```

### Critical Path

The critical path through the project:

1. **Infrastructure** (Week 1-2) - Blocks everything
2. **Data Ingestion** (Week 2-5) - Blocks forecasting
3. **Core Platform** (Week 5-8) - Blocks user features
4. **Forecasting** (Week 8-9) - Blocks intelligence demo
5. **Anomaly Detection** (Week 9-10) - Blocks submissions
6. **Submissions** (Week 10-11) - Blocks moderation
7. **QA** (Week 13-14) - Blocks launch

**Total Critical Path Duration:** 14 weeks

---

## Resource Allocation

### Team Capacity

| Role | Availability | Primary Phases |
|------|--------------|----------------|
| Tech Lead (Jordan) | Full-time | All phases |
| QA Lead (Riley) | Part-time P1-P4, Full-time P5-P6 | Testing, Security |
| PM (Alex) | Part-time throughout | Coordination, Status |
| PO (Sam) | Part-time throughout | Requirements, UX |

### Weekly Focus

| Week | Primary Focus | Secondary Focus |
|------|---------------|-----------------|
| 1-2 | Infrastructure | Documentation |
| 2-3 | Scraping | Schema refinement |
| 3-4 | Normalization | Data validation |
| 4-5 | Data pipeline | Initial UI |
| 5-6 | Search/Display | Auth design |
| 6-7 | Authentication | Security review |
| 7-8 | Collections | UX improvements |
| 8-9 | Forecasting | Algorithm testing |
| 9-10 | Anomaly detection | Performance |
| 10-11 | Submissions | Moderation |
| 11-12 | UX polish | Documentation |
| 12-13 | Performance | Security audit |
| 13-14 | Testing | Bug fixes |
| 14-15 | Deployment | Monitoring |
| 15-16 | Launch | Support |

---

## Risk Buffer

**Built-in buffers:**
- 2-week buffer in 16-week estimate (could be 14 weeks)
- Phase 2 has 1-week flexibility (could extend to 4 weeks if scraping complex)
- Phase 5 activities can overlap with Phase 4 if ahead

**Contingency triggers:**
- If Phase 2 exceeds 4 weeks: Reduce Phase 5 polish scope
- If security audit finds critical issues: Delay launch by 1 week
- If Prophet installation fails: Fall back to simple average for MVP

---

## Communication Schedule

| Event | Frequency | Participants | Format |
|-------|-----------|--------------|--------|
| Daily standup | Daily | Dev team | Async (Slack) |
| Weekly status | Weekly | All stakeholders | PROJECT_STATUS.md |
| Milestone demos | Per milestone | All stakeholders | Video call |
| Phase retrospective | Per phase | Full team | Meeting notes |
| Launch decision | Week 15 | All stakeholders | Go/No-Go meeting |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-27 | PM (Alex) | Initial timeline |
