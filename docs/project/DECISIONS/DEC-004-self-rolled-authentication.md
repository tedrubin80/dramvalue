# DEC-004: Self-Rolled Authentication (JWT + bcrypt)

**Date:** 2025-12-27
**Status:** Accepted
**Deciders:** Tech Lead (Jordan), QA Lead (Riley), PM (Alex)

---

## Context

WTracker requires user authentication with specific requirements:
1. Pseudonymous accounts (display name only, no real identity)
2. Email verification for submission privileges
3. Email visible only to admin, never exposed publicly
4. Privacy-conscious design
5. No hardcoded credentials

We need to decide between self-implemented authentication and third-party auth providers.

---

## Options Considered

### Option 1: Self-Rolled (JWT + bcrypt via FastAPI)

**Description:** Implement authentication using FastAPI dependencies, python-jose for JWT, and passlib for bcrypt password hashing.

**Pros:**
- Full control over authentication flow
- No external dependencies for auth
- Privacy guaranteed (no data shared with third parties)
- Can customize for pseudonymous model
- No recurring costs
- No vendor lock-in
- Offline operation possible

**Cons:**
- Security responsibility on us
- Must implement all features (reset, verification)
- More code to maintain
- Need thorough security testing

**Evaluation:** Best fit for privacy requirements and pseudonymous model.

---

### Option 2: Auth0

**Description:** Industry-standard authentication-as-a-service provider.

**Pros:**
- Battle-tested security
- Handles edge cases (brute force, session management)
- Social login options
- Compliance features (SOC2, GDPR)
- Good documentation

**Cons:**
- User data stored externally
- Cost at scale ($23+/month for basic features)
- External dependency for core functionality
- Harder to customize for pseudonymous model
- OAuth complexity for simple email/password

**Evaluation:** Overkill for MVP, privacy concerns.

---

### Option 3: Supabase Auth

**Description:** Open-source Firebase alternative with auth.

**Pros:**
- Good developer experience
- PostgreSQL native
- Self-hostable option
- Social providers included

**Cons:**
- Ties us to Supabase ecosystem
- Less control over flow
- External service dependency
- May not fit pseudonymous model well

**Evaluation:** Ecosystem lock-in concerns.

---

### Option 4: Django + django-allauth

**Description:** Use Django's built-in auth with allauth extension.

**Pros:**
- Mature, well-tested
- Many features out of box
- Strong community

**Cons:**
- Would require Django instead of FastAPI
- Heavier framework
- Less flexibility for async

**Evaluation:** Would require framework change, not ideal.

---

### Option 5: Firebase Authentication

**Description:** Google's auth service.

**Pros:**
- Easy integration
- Scales automatically
- Social providers

**Cons:**
- Google dependency
- User data in Google ecosystem
- Privacy concerns
- Cost at scale

**Evaluation:** Privacy concerns for target user.

---

## Decision

**Selected: Self-Rolled Authentication (JWT + bcrypt)**

We will implement:
1. Password hashing with bcrypt (passlib, cost factor 12)
2. JWT access tokens (python-jose, HS256, 24-hour expiry)
3. Refresh tokens (7-day expiry, stored in HttpOnly cookie)
4. Email verification flow
5. Password reset flow
6. Rate limiting on auth endpoints

---

## Rationale

1. **Privacy:** No user data shared with third parties. Critical for privacy-conscious target user.

2. **Pseudonymous model:** Full control to implement display-name-only public identity.

3. **No vendor lock-in:** Not dependent on external service availability or pricing.

4. **Cost:** No recurring auth costs (important for personal project).

5. **Simplicity:** Email/password auth is straightforward to implement correctly.

6. **FastAPI native:** Works seamlessly with FastAPI dependencies and async model.

---

## Consequences

### Positive
- Full privacy control
- No external auth dependencies
- Customizable for pseudonymous needs
- No recurring costs

### Negative
- Security responsibility on team
- Must implement email verification, password reset
- Requires security testing
- No social login (acceptable for MVP)

### Neutral
- Standard patterns to follow
- Well-documented approaches available

---

## Security Requirements

The following security controls are **mandatory**:

### Password Security
- [x] bcrypt with cost factor >= 12
- [x] Minimum password length: 8 characters
- [x] No password stored in plaintext ever

### Token Security
- [x] JWT signed with strong secret (256+ bits)
- [x] Access token expiry: 24 hours
- [x] Refresh token expiry: 7 days
- [x] Refresh token in HttpOnly cookie
- [x] Access token in response body (not cookie)

### Session Security
- [x] Secure, HttpOnly, SameSite=Lax cookies
- [x] CSRF protection on state-changing operations
- [x] Session invalidation on logout
- [x] Session invalidation on password change

### Rate Limiting
- [x] Login: 10 attempts per minute
- [x] Registration: 5 per hour per IP
- [x] Password reset: 3 per hour per email
- [x] Account lockout after 5 failed attempts (15 min)

### Email Verification
- [x] Verification token: single-use, 24-hour expiry
- [x] Email visible only to admin
- [x] Verification required for submission privileges

### Password Reset
- [x] Reset token: single-use, 1-hour expiry
- [x] Token invalidated after use
- [x] No indication if email exists (prevent enumeration)

---

## Implementation Checklist

### Authentication Endpoints
- [ ] POST /auth/register - Create account
- [ ] POST /auth/login - Get tokens
- [ ] POST /auth/logout - Invalidate session
- [ ] POST /auth/refresh - Refresh access token
- [ ] POST /auth/verify-email - Verify with token
- [ ] POST /auth/password-reset - Request reset
- [ ] POST /auth/password-reset/confirm - Set new password

### Security Testing
- [ ] Brute force protection verification
- [ ] Token validation testing
- [ ] Session management testing
- [ ] CSRF protection verification
- [ ] Password hashing verification
- [ ] Penetration testing (Phase 3)

---

## Security Headers

```python
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'",
    "Referrer-Policy": "strict-origin-when-cross-origin"
}
```

---

## Related

- [ARCHITECTURE.md](../ARCHITECTURE.md) - Security architecture section
- [RISK_REGISTER.md](../RISK_REGISTER.md) - R-012: Authentication Vulnerabilities
- [2025-12-27-project-kickoff.md](../MEETING_NOTES/2025-12-27-project-kickoff.md) - Auth discussion
