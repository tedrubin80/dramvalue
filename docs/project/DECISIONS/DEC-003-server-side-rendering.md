# DEC-003: Server-Side Rendering for MVP Frontend

**Date:** 2025-12-27
**Status:** Accepted
**Deciders:** Tech Lead (Jordan), PM (Alex), PO (Sam)

---

## Context

WTracker needs a user interface for:
1. Homepage with search
2. Bottle detail pages with price charts
3. User authentication flows
4. Collection management
5. Admin moderation queue

We need to decide between:
- Server-side rendering (SSR) with templates
- Client-side Single Page Application (SPA)
- Hybrid approach

The decision impacts development velocity, team capacity, and user experience.

---

## Options Considered

### Option 1: Server-Side Rendering (Jinja2 + Alpine.js)

**Description:** FastAPI renders HTML templates using Jinja2, with Alpine.js for minimal client-side interactivity.

**Pros:**
- Single codebase (Python only)
- Simpler deployment (no separate frontend build)
- Better initial page load (no JS bundle to download)
- SEO-friendly out of the box
- Faster development for MVP
- No API versioning complexity (templates consume data directly)
- Lower hosting costs (no separate static hosting needed)

**Cons:**
- Full page reloads for navigation
- Less smooth interactions
- Mixing presentation in backend
- May need to rebuild for SPA later if complex interactions needed

**Evaluation:** Best fit for MVP timeline and team capacity.

---

### Option 2: React Single Page Application

**Description:** Separate React frontend consuming FastAPI backend via JSON API.

**Pros:**
- Rich, smooth user experience
- Clear separation of concerns
- Large ecosystem and community
- Easy to add complex interactions

**Cons:**
- Two codebases to maintain
- Additional build tooling (Webpack, etc.)
- Larger bundle size
- API versioning needed
- CORS configuration
- Slower initial development
- More hosting complexity

**Evaluation:** Overkill for MVP features.

---

### Option 3: Vue.js or Svelte SPA

**Description:** Similar to React but with lighter frameworks.

**Pros:**
- Similar to React but potentially simpler
- Svelte has excellent performance
- Vue has good learning curve

**Cons:**
- Same challenges as React (two codebases, API versioning)
- Smaller team expertise

**Evaluation:** Same concerns as React for MVP.

---

### Option 4: htmx for Progressive Enhancement

**Description:** Jinja2 templates with htmx for AJAX partial updates.

**Pros:**
- Server-side rendering benefits
- Partial page updates without full SPA
- HTML-focused (no JS framework)
- Progressive enhancement
- Growing community

**Cons:**
- Different paradigm (may not be familiar)
- Limited for very complex interactions
- Smaller ecosystem than React/Vue

**Evaluation:** Strong alternative to Option 1, slightly higher learning curve.

---

## Decision

**Selected: Server-Side Rendering with Jinja2 + Alpine.js**

We will use:
1. Jinja2 templates for all page rendering
2. Alpine.js for client-side interactivity (forms, dropdowns, modals)
3. Chart.js for price history visualization
4. Standard CSS (or Tailwind) for styling

---

## Rationale

1. **Team capacity:** Solo developer benefits from single codebase.

2. **Development speed:** Templates are faster to build than SPA for straightforward CRUD interfaces.

3. **MVP scope:** Our features (search, view, submit, moderate) don't require complex client-side state.

4. **Performance:** Initial page load is faster without large JS bundle.

5. **SEO:** Bottle pages should be crawlable for future discoverability.

6. **Simplicity:** No build step for frontend, no API versioning, simpler debugging.

7. **Migration path:** Can progressively enhance with htmx or migrate to SPA in Phase 2 if needed.

---

## Consequences

### Positive
- Faster MVP delivery
- Single deployment artifact
- Simpler stack to maintain
- Good performance for data-centric pages

### Negative
- Full page reloads for navigation (acceptable for MVP)
- Limited complex interactions
- May need significant rework if SPA required later

### Neutral
- Templates embedded in backend (acceptable trade-off)
- Chart.js adds some JS complexity

---

## Implementation Notes

1. **Template structure:**
   ```
   templates/
   ├── base.html          # Base layout with nav, footer
   ├── home.html          # Homepage with search
   ├── bottles/
   │   ├── list.html      # Search results
   │   └── detail.html    # Bottle page with chart
   ├── auth/
   │   ├── login.html
   │   └── register.html
   ├── collections/
   │   ├── list.html
   │   └── detail.html
   └── admin/
       └── moderation.html
   ```

2. **Alpine.js usage:**
   - Form validation
   - Modal dialogs
   - Dropdown menus
   - Loading states

3. **Chart.js usage:**
   - Price history line chart
   - Confidence band visualization
   - Collection value over time

4. **Styling approach:**
   - Tailwind CSS or custom CSS
   - Mobile-responsive design
   - Dark mode consideration for Phase 2

---

## Review Points

We will reassess this decision:
- At M3 (Core Platform Demo) - Based on user feedback
- At Phase 5 (Polish) - Based on interaction complexity

If complex interactions are needed, we can:
1. Add htmx for partial updates
2. Build specific SPA components (React islands)
3. Full SPA migration (significant effort)

---

## Related

- [ARCHITECTURE.md](../ARCHITECTURE.md) - Frontend file structure
- [TIMELINE.md](../TIMELINE.md) - Frontend development schedule
