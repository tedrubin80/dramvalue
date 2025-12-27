# Risk Register: WTracker

**Created:** 2025-12-27
**Last Updated:** 2025-12-27
**Version:** 1.0
**Status:** Active

---

## Risk Summary Dashboard

| Severity | Count | Status |
|----------|-------|--------|
| Critical | 1 | Active |
| High | 4 | Active |
| Medium | 6 | Active |
| Low | 3 | Active |
| **Total Active** | **14** | - |
| Mitigated | 0 | - |
| Closed | 0 | - |

**Overall Risk Profile:** Medium-High
**Last Review:** 2025-12-27
**Next Review:** 2026-01-10

---

## Risk Scoring Matrix

### Probability Scale
| Level | Score | Description |
|-------|-------|-------------|
| High | 3 | >70% likely to occur |
| Medium | 2 | 30-70% likely to occur |
| Low | 1 | <30% likely to occur |

### Impact Scale
| Level | Score | Description |
|-------|-------|-------------|
| Critical | 4 | Project failure, data breach, legal exposure |
| High | 3 | Major delay (>2 weeks), significant rework |
| Medium | 2 | Minor delay (1-2 weeks), workaround needed |
| Low | 1 | Minimal impact, easily addressed |

### Risk Score Calculation
**Score = Probability x Impact**

| Score | Severity | Action |
|-------|----------|--------|
| 9-12 | Critical | Immediate escalation, stop work if needed |
| 6-8 | High | Active mitigation, weekly review |
| 3-5 | Medium | Mitigation plan, bi-weekly review |
| 1-2 | Low | Monitor, monthly review |

---

## Active Risks

### R-001: Credential Exposure in Repository
**Category:** Security
**Identified:** 2025-12-27
**Owner:** Tech Lead (Jordan)

| Attribute | Value |
|-----------|-------|
| Probability | Low (1) |
| Impact | Critical (4) |
| Score | **4 (Critical)** |
| Status | Active |
| Response | Prevent |

**Description:**
Accidental commit of API keys, database passwords, or other secrets to the Git repository could lead to security breach, unauthorized access, or data exposure.

**Triggers:**
- New developer joins project
- Rushed commits
- Configuration file changes
- CI/CD pipeline modifications

**Consequences:**
- Unauthorized database access
- API abuse
- Reputational damage
- Potential legal liability
- Emergency credential rotation

**Mitigation Strategy:**
1. **Pre-commit hooks** - Implement `detect-secrets` as mandatory pre-commit hook
2. **CI scanning** - GitHub Actions step to scan for secrets on every PR
3. **Environment variables** - All secrets loaded from environment, never hardcoded
4. **Documentation** - Clear guidelines in CONTRIBUTING.md
5. **Code review** - Mandatory review for all configuration changes
6. **.gitignore** - Comprehensive ignore rules for .env, credentials files

**Monitoring:**
- Weekly: Review pre-commit hook effectiveness
- Per PR: CI scan results
- Monthly: Audit environment variable usage

**Contingency:**
If exposure occurs:
1. Immediately rotate affected credentials
2. Review access logs for unauthorized use
3. Update affected systems
4. Post-mortem to prevent recurrence

---

### R-002: Data Source Instability (Scraping)
**Category:** Technical
**Identified:** 2025-12-27
**Owner:** Tech Lead (Jordan)

| Attribute | Value |
|-----------|-------|
| Probability | High (3) |
| Impact | High (3) |
| Score | **9 (Critical)** |
| Status | Active |
| Response | Mitigate |

**Description:**
External auction websites may change their HTML structure, implement anti-bot measures, or become unavailable, breaking our data ingestion pipeline.

**Triggers:**
- Website redesign
- Anti-bot measure deployment
- IP blocking
- Rate limit enforcement
- Website downtime

**Consequences:**
- Stale pricing data
- Missing recent transactions
- User trust erosion
- Manual data entry fallback
- Development time for spider updates

**Mitigation Strategy:**
1. **Multiple sources** - Integrate at least 2 auction sources by Phase 2 end
2. **Graceful degradation** - System functions with cached data if scraping fails
3. **Monitoring and alerting** - Scrape health dashboard with failure alerts
4. **Respectful scraping** - Rate limiting, user agent identification, robots.txt compliance
5. **HTML structure monitoring** - Automated tests that detect structure changes
6. **Backup manual entry** - Admin interface to manually add prices if needed

**Monitoring:**
- Per scrape: Success rate, items found, errors
- Daily: Scrape health report
- Weekly: Source structure change detection

**Contingency:**
If primary source becomes unavailable:
1. Switch to backup source
2. Display "data may be delayed" notice
3. Prioritize spider repair (1-2 day turnaround)
4. Consider reaching out to source for API access

---

### R-003: Prophet Installation/Performance Issues
**Category:** Technical
**Identified:** 2025-12-27
**Owner:** Tech Lead (Jordan)

| Attribute | Value |
|-----------|-------|
| Probability | Medium (2) |
| Impact | Medium (2) |
| Score | **4 (Medium)** |
| Status | Active |
| Response | Mitigate |

**Description:**
Facebook Prophet has complex dependencies (PyStan/CmdStan) that can be difficult to install in containerized environments. Performance may also be slower than expected for real-time predictions.

**Triggers:**
- Docker base image changes
- Python version updates
- CmdStan compilation issues
- Memory constraints in containers

**Consequences:**
- Delayed forecasting feature
- Development time debugging installation
- Slower forecast generation
- Higher memory usage

**Mitigation Strategy:**
1. **Early spike** - Validate Prophet installation in Docker during Week 1
2. **Pinned versions** - Lock Prophet and PyStan versions in requirements.txt
3. **Pre-built image** - Create custom Docker image with Prophet pre-installed
4. **Fallback algorithm** - Simple moving average forecaster as backup
5. **Background processing** - Generate forecasts via Celery, not synchronously
6. **Caching** - Cache forecasts for 24 hours to reduce computation

**Monitoring:**
- Development: Installation success/failure
- Runtime: Forecast generation time
- Production: Memory usage during forecast jobs

**Contingency:**
If Prophet proves unworkable:
1. Use simple_average forecaster for MVP
2. Evaluate alternative libraries (statsforecast, Darts)
3. Defer advanced forecasting to Phase 2

---

### R-004: Bottle Name Normalization Complexity
**Category:** Technical
**Identified:** 2025-12-27
**Owner:** Tech Lead (Jordan)

| Attribute | Value |
|-----------|-------|
| Probability | High (3) |
| Impact | Medium (2) |
| Score | **6 (High)** |
| Status | Active |
| Response | Mitigate |

**Description:**
Normalizing bottle names across sources is a known-hard NLP problem. "BT Stagg", "George T. Stagg", "Stagg", and "GTS" all refer to the same bottle, but automated matching may fail.

**Triggers:**
- New bottle variants
- Inconsistent source naming
- International naming variations
- Limited editions with unique names

**Consequences:**
- Duplicate bottle entries
- Fragmented price history
- Incorrect valuations
- Manual merge overhead
- User confusion

**Mitigation Strategy:**
1. **Alias system** - Database table for name aliases (bottle_aliases)
2. **Fuzzy matching** - Implement Levenshtein distance matching for search
3. **Confidence scoring** - Flag low-confidence matches for manual review
4. **Manual override** - Admin tool to merge bottles and add aliases
5. **User reporting** - Allow users to report duplicate bottles
6. **Iterative improvement** - Continuously refine matching rules based on data

**Monitoring:**
- Daily: Count of bottles flagged for manual review
- Weekly: Merge rate (bottles merged / total bottles)
- Monthly: User duplicate reports

**Contingency:**
If automated normalization proves insufficient:
1. Increase manual review capacity
2. Implement user-assisted aliasing
3. Consider ML-based matching (Phase 2)

---

### R-005: Trust System Gaming
**Category:** Business/Security
**Identified:** 2025-12-27
**Owner:** QA Lead (Riley)

| Attribute | Value |
|-----------|-------|
| Probability | Medium (2) |
| Impact | High (3) |
| Score | **6 (High)** |
| Status | Active |
| Response | Mitigate |

**Description:**
Sophisticated bad actors may attempt to manipulate price data by submitting fake transactions, building trust over time, or coordinating with multiple accounts.

**Triggers:**
- Financial incentive to manipulate prices
- Seller wanting to inflate perceived value
- Buyer wanting to depress prices
- Coordinated manipulation rings

**Consequences:**
- Inaccurate price averages
- User trust erosion
- Incorrect valuations
- Market manipulation
- Reputational damage

**Mitigation Strategy:**
1. **Multiple detection layers** - Z-score, velocity, volume, pattern detection
2. **Human moderation backstop** - All flagged submissions reviewed by moderator
3. **Trust score weighting** - New accounts have minimal impact on averages
4. **Single-user caps** - No user can dominate a bottle's price data
5. **Corroboration requirement** - Outlier submissions need corroboration
6. **Adversarial testing** - Regular attempts to break fraud detection

**Monitoring:**
- Real-time: Flagged submission rate
- Daily: Moderation queue depth
- Weekly: Fraud detection accuracy review
- Monthly: Adversarial testing exercises

**Contingency:**
If trust system is compromised:
1. Temporarily disable crowdsourced submissions
2. Increase moderation threshold
3. Review and remove manipulated data
4. Implement additional detection rules

---

### R-006: Scope Creep
**Category:** Project Management
**Identified:** 2025-12-27
**Owner:** PM (Alex)

| Attribute | Value |
|-----------|-------|
| Probability | Medium (2) |
| Impact | High (3) |
| Score | **6 (High)** |
| Status | Active |
| Response | Avoid |

**Description:**
The project brief is ambitious with many potential features. Adding features beyond MVP scope will delay delivery and increase complexity.

**Triggers:**
- "Just one more feature" requests
- Competitive pressure
- User feedback during development
- Technical discoveries suggesting new possibilities

**Consequences:**
- Timeline slip
- Quality reduction
- Team burnout
- Delayed MVP launch
- Feature bloat

**Mitigation Strategy:**
1. **Strict MVP definition** - Clear scope documented in charter
2. **Phase 2 backlog** - All non-MVP ideas go to Phase 2 list
3. **Change control process** - Formal discussion for any scope additions
4. **Regular scope reviews** - Weekly check against MVP definition
5. **Stakeholder alignment** - Regular demos to manage expectations
6. **Time-boxed phases** - Phases end on schedule, not when "complete"

**Monitoring:**
- Weekly: Scope change requests logged
- Per phase: Scope variance review
- Demo: Feature alignment with charter

**Contingency:**
If scope creep occurs:
1. Emergency scope review meeting
2. Identify what to defer to Phase 2
3. Reset timeline if necessary
4. Document lessons learned

---

### R-007: Single Point of Failure (Solo Developer)
**Category:** Resource
**Identified:** 2025-12-27
**Owner:** PM (Alex)

| Attribute | Value |
|-----------|-------|
| Probability | Low (1) |
| Impact | High (3) |
| Score | **3 (Medium)** |
| Status | Active |
| Response | Accept |

**Description:**
Initially, the project relies on a single developer. Developer unavailability (illness, vacation, other commitments) would halt progress.

**Triggers:**
- Personal emergency
- Illness
- Burnout
- Priority shift to other projects

**Consequences:**
- Development halt
- Timeline slip
- Knowledge loss risk
- No code review

**Mitigation Strategy:**
1. **Comprehensive documentation** - All decisions and architecture documented
2. **Clean code practices** - Self-documenting code, tests as documentation
3. **Regular commits** - Small, frequent commits with clear messages
4. **Knowledge transfer prep** - Documentation sufficient for new developer onboarding
5. **Sustainable pace** - Avoid overtime to prevent burnout
6. **Backup contacts** - Identify potential backup developers if needed

**Monitoring:**
- Weekly: Developer workload check-in
- Monthly: Documentation completeness review
- Ongoing: Code quality metrics

**Contingency:**
If developer becomes unavailable:
1. Pause active development
2. Assess documentation completeness
3. Engage backup developer if extended absence
4. Adjust timeline accordingly

---

### R-008: Database Performance at Scale
**Category:** Technical
**Identified:** 2025-12-27
**Owner:** Tech Lead (Jordan)

| Attribute | Value |
|-----------|-------|
| Probability | Low (1) |
| Impact | Medium (2) |
| Score | **2 (Low)** |
| Status | Active |
| Response | Monitor |

**Description:**
As price data grows over time, query performance may degrade, especially for price history retrieval and aggregations.

**Triggers:**
- 100,000+ prices in database
- Complex aggregation queries
- Multiple concurrent users
- Large collection valuations

**Consequences:**
- Slow page loads
- Timeout errors
- Poor user experience
- Infrastructure scaling needs

**Mitigation Strategy:**
1. **Proper indexing** - Composite indexes on (bottle_id, transaction_date)
2. **Materialized views** - Pre-computed aggregations refreshed periodically
3. **Query optimization** - EXPLAIN ANALYZE on critical queries
4. **Caching layer** - Redis caching for frequent queries
5. **Pagination** - Limit result sets with pagination
6. **TimescaleDB ready** - Schema designed for easy TimescaleDB migration

**Monitoring:**
- Ongoing: Query performance logging
- Weekly: Slow query review
- Monthly: Database size growth tracking

**Contingency:**
If performance degrades:
1. Enable TimescaleDB extension
2. Add read replicas
3. Implement more aggressive caching
4. Consider data archival for old prices

---

### R-009: User Experience of Projections
**Category:** Product
**Identified:** 2025-12-27
**Owner:** PO (Sam)

| Attribute | Value |
|-----------|-------|
| Probability | Medium (2) |
| Impact | Medium (2) |
| Score | **4 (Medium)** |
| Status | Active |
| Response | Mitigate |

**Description:**
Price projections with confidence bands may confuse users or be misinterpreted as guarantees, leading to poor decisions or loss of trust in the platform.

**Triggers:**
- Users unfamiliar with statistical projections
- Projections that prove inaccurate
- Missing disclaimers
- Confusing visualization

**Consequences:**
- User distrust
- Poor purchase/sale decisions
- Potential liability claims
- Negative reviews
- Feature removal

**Mitigation Strategy:**
1. **Clear disclaimers** - "This is not financial advice" on every forecast
2. **Education** - Tooltips explaining confidence bands
3. **Confidence thresholds** - Hide projections with insufficient data
4. **Conservative estimates** - Prefer wider confidence bands
5. **Data transparency** - Show data points used for projection
6. **User testing** - Test forecast UX with real users before launch

**Monitoring:**
- Pre-launch: User testing feedback
- Post-launch: User feedback on forecasts
- Ongoing: Projection accuracy tracking

**Contingency:**
If projections cause user issues:
1. Add more prominent disclaimers
2. Default to showing historical trends only
3. Make projections opt-in
4. Provide educational content

---

### R-010: Email Delivery for Verification
**Category:** Technical
**Identified:** 2025-12-27
**Owner:** Tech Lead (Jordan)

| Attribute | Value |
|-----------|-------|
| Probability | Medium (2) |
| Impact | Medium (2) |
| Score | **4 (Medium)** |
| Status | Active |
| Response | Mitigate |

**Description:**
Email verification is required for submission privileges. Email delivery issues (spam filters, bounces, delays) could prevent user onboarding.

**Triggers:**
- Spam filter blocking
- Incorrect email addresses
- Email provider issues
- Configuration errors

**Consequences:**
- Users unable to verify accounts
- Reduced submission volume
- Support requests
- User frustration

**Mitigation Strategy:**
1. **Reputable email provider** - Use SendGrid, Mailgun, or similar
2. **SPF/DKIM configuration** - Proper email authentication
3. **Clear sender** - Recognizable from address and subject
4. **Resend capability** - Users can request new verification email
5. **Alternative verification** - Consider magic link as fallback
6. **Email testing** - Test delivery across major providers (Gmail, Yahoo, Outlook)

**Monitoring:**
- Per send: Delivery status tracking
- Weekly: Bounce rate, spam complaints
- Monthly: Verification success rate

**Contingency:**
If email delivery fails:
1. Switch email provider
2. Implement alternative verification (manual admin approval)
3. Allow limited functionality without verification

---

### R-011: Legal/Terms of Service Violations
**Category:** Legal
**Identified:** 2025-12-27
**Owner:** PM (Alex)

| Attribute | Value |
|-----------|-------|
| Probability | Low (1) |
| Impact | High (3) |
| Score | **3 (Medium)** |
| Status | Active |
| Response | Avoid |

**Description:**
Scraping auction websites may violate their Terms of Service, leading to legal challenges or cease-and-desist requests.

**Triggers:**
- Source discovers scraping activity
- Legal review of Terms of Service
- Complaint from source

**Consequences:**
- Cease and desist letter
- Loss of data source
- Potential legal action
- Development halt for that source
- Reputational risk

**Mitigation Strategy:**
1. **Legal review** - Review ToS of each source before integration
2. **Respectful scraping** - Rate limiting, caching, minimal requests
3. **robots.txt compliance** - Honor robots.txt directives
4. **User agent transparency** - Identify as WTracker bot with contact email
5. **Fallback sources** - Multiple sources so single source loss isn't critical
6. **API preference** - Seek official APIs where available

**Monitoring:**
- Before integration: ToS review
- Ongoing: Monitor for legal communications
- Quarterly: Review scraping practices

**Contingency:**
If legal challenge occurs:
1. Immediately cease scraping that source
2. Seek legal advice
3. Explore partnership or API access
4. Remove data if required

---

### R-012: Authentication Vulnerabilities
**Category:** Security
**Identified:** 2025-12-27
**Owner:** QA Lead (Riley)

| Attribute | Value |
|-----------|-------|
| Probability | Low (1) |
| Impact | Critical (4) |
| Score | **4 (High)** |
| Status | Active |
| Response | Prevent |

**Description:**
Self-rolled authentication system may have security vulnerabilities that could allow unauthorized access, account takeover, or session hijacking.

**Triggers:**
- Implementation bugs
- Missing security controls
- JWT misconfiguration
- Session management issues

**Consequences:**
- Unauthorized account access
- User data exposure
- Trust breach
- Platform compromise
- Regulatory issues

**Mitigation Strategy:**
1. **Security best practices** - bcrypt cost 12+, secure JWT, HttpOnly cookies
2. **Rate limiting** - Auth endpoints rate limited
3. **Account lockout** - Lockout after failed attempts
4. **Penetration testing** - Dedicated auth pen testing in Phase 3
5. **OWASP compliance** - Follow OWASP authentication guidelines
6. **Security headers** - Proper CSP, HSTS, X-Frame-Options

**Monitoring:**
- Real-time: Failed login attempts
- Daily: Suspicious auth activity
- Pre-launch: Full security audit

**Contingency:**
If vulnerability discovered:
1. Immediate patch
2. Force password reset if accounts compromised
3. Invalidate all sessions
4. Post-mortem and additional testing

---

### R-013: Third-Party Dependency Vulnerabilities
**Category:** Security
**Identified:** 2025-12-27
**Owner:** Tech Lead (Jordan)

| Attribute | Value |
|-----------|-------|
| Probability | Medium (2) |
| Impact | Medium (2) |
| Score | **4 (Medium)** |
| Status | Active |
| Response | Mitigate |

**Description:**
Python packages and Docker images may contain security vulnerabilities that could be exploited.

**Triggers:**
- New CVE published for dependency
- Outdated packages
- Supply chain attack

**Consequences:**
- Security vulnerability exposure
- Emergency patching required
- Potential exploitation
- Data breach risk

**Mitigation Strategy:**
1. **Dependabot** - Enable GitHub Dependabot for automatic alerts
2. **Regular updates** - Monthly dependency update cycle
3. **Pinned versions** - Pin major versions, allow patch updates
4. **Security scanning** - CI pipeline includes vulnerability scanning
5. **Minimal dependencies** - Only include necessary packages
6. **Docker image scanning** - Scan base images for vulnerabilities

**Monitoring:**
- Continuous: Dependabot alerts
- Weekly: Review and apply security patches
- Monthly: Full dependency audit

**Contingency:**
If critical vulnerability found:
1. Immediate assessment of exposure
2. Emergency patch deployment
3. Review for exploitation
4. Update incident response

---

### R-014: VPS/Hosting Outage
**Category:** Infrastructure
**Identified:** 2025-12-27
**Owner:** Tech Lead (Jordan)

| Attribute | Value |
|-----------|-------|
| Probability | Low (1) |
| Impact | Medium (2) |
| Score | **2 (Low)** |
| Status | Active |
| Response | Accept |

**Description:**
DigitalOcean VPS could experience outage, causing service unavailability.

**Triggers:**
- DigitalOcean data center issues
- Network problems
- Hardware failure
- Region-wide outage

**Consequences:**
- Service unavailability
- Lost scraping windows
- User frustration
- Data sync issues

**Mitigation Strategy:**
1. **Provider reliability** - DigitalOcean has 99.99% SLA
2. **Monitoring** - Uptime monitoring with alerts
3. **Backup strategy** - Regular database backups to external storage
4. **Stateless design** - Application can restart cleanly
5. **CDN buffer** - Cloudflare can serve static content during short outages

**Monitoring:**
- Continuous: Uptime monitoring (UptimeRobot or similar)
- Daily: Backup verification
- Post-incident: Outage post-mortem

**Contingency:**
If extended outage:
1. Communicate status to users (if possible)
2. Contact DigitalOcean support
3. Consider migration to backup region
4. Review multi-region strategy for Phase 2

---

## Risk Response Strategies Reference

| Strategy | Description | When to Use |
|----------|-------------|-------------|
| **Avoid** | Eliminate the risk by changing approach | Risk is unacceptable and preventable |
| **Mitigate** | Reduce probability or impact | Risk is significant but manageable |
| **Transfer** | Shift risk to third party (insurance, outsourcing) | Risk expertise exists elsewhere |
| **Accept** | Acknowledge and monitor | Risk is low or cost of mitigation exceeds impact |

---

## Risk Review Schedule

| Review Type | Frequency | Participants | Output |
|-------------|-----------|--------------|--------|
| Quick scan | Weekly | Tech Lead | Status update |
| Full review | Bi-weekly | Full team | Register update |
| Deep dive | Monthly | Full team | Risk reassessment |
| Phase transition | Per phase | Full team | New risk identification |

---

## Closed/Mitigated Risks

| ID | Risk | Resolution | Date Closed |
|----|------|------------|-------------|
| - | - | - | - |

*No risks closed yet - project in early phase.*

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-27 | QA Lead (Riley) | Initial risk register |
