# Mage Social Hub — Slack POC Integration Roadmap (Product + Technical Review)

Date: 2026-01-27

## Executive Summary
You have a solid Slack POC in `mage-Slack` that proves event capture and a simple rules dashboard. The next step is to wrap it in a minimal, scalable architecture that is **single-tenant in behavior** (desktop app) but **tenant-ready in data shape**, near real-time, and extensible to future providers without locking you into a brittle prototype.

This doc combines:
- **Product assessment**: what the POC proves and what users need next
- **Technical assessment**: gaps to address to make it scalable and tenant-ready
- **Concrete phased roadmap**: how to move the POC into the minimal architecture with clear deliverables

---

## Product Review (POC → Product)

### What the current Slack POC proves
- **Immediate value**: near real-time Slack message visibility through a local dashboard.
- **Rules-based relevance**: user/channel filters plus throttled assistant notifications.
- **Simple local UX loop**: dashboard + listener = fast feedback.

### What’s missing for a scalable product
- **Tenant-ready separation**: today’s POC assumes a single local workspace; you need tenant-ready storage and routing for future service expansion.
- **Team onboarding**: OAuth + workspace linking flows are required for adoption.
- **Event lifecycle UX**: delete single events + clear all events are required in the MVP (per your request).
- **Trust/visibility**: users need to understand “why did I see this event” and “why not.”

### Product constraints (confirmed)
- **Near real-time is acceptable** (no hard realtime requirement).
- **Single-tenant behavior** for desktop, but **tenant-ready data shape** for later migration.
- **Dashboard controls**: delete single entries and clear all events.
- **Attachments** can be deferred; store references only initially.
- **Other providers** can come later.

---

## Technical Review (Current Slack POC)

**POC location**: `mage-Slack/`

### Strengths
- **Socket Mode ingestion** works reliably.
- **Lightweight dashboard server** is easy to run.
- **Rule evaluation** is clear and fast.
- **Notification throttling** helps avoid spam.

### Gaps that block scalability
- **No multi-tenant boundary**: state is local JSON in a single workspace.
- **No durable queue**: drops/duplication are likely under load or restart.
- **No event dedupe/idempotency**: Slack retries can cause duplicates.
- **No OAuth/token rotation**: static tokens aren’t production-ready.
- **No delivery audit trail**: hard to debug missed events.
- **No separate source-event vs user-event**: makes multi-tenant scaling expensive.

### Immediate improvements that fit the minimal architecture
- Introduce **tenant + user IDs** in event ingestion.
- Use **persistent storage** (Postgres) instead of JSON state files.
- Add **event de-duplication key** (Slack `ts`, `event_id`).
- Separate **ingestion → routing → delivery** via a queue.

---

## Minimal Scalable Architecture (Target MVP)

### Core components (only what’s needed)
1. **Slack Provider** (normalized events)
2. **Router Core** (watchlist match + persistence)
3. **Queue** (Redis or PG queue)
4. **WebSocket Delivery** (near real-time push)
5. **Tenant-ready Storage** (Postgres, single-tenant behavior)
6. **Dashboard API** (event feed + delete/clear)

### Data model (minimal)
- `tenants`
- `users`
- `service_creds` (encrypted)
- `watchlists`
- `source_events` (raw Slack events)
- `event_user_map` (which user/tenant sees which event)
All tables include `tenant_id` with a default value of `default`, but the UI and API remain single-tenant for the desktop app.

---

## Phased Roadmap: Slack POC → Minimal Scalable Architecture (Tenant-Ready, Single-Tenant Behavior)

Each phase has explicit deliverables and ties back to the POC.

### Phase 0 — Architecture Baseline (2–4 days)
**Goal**: lock core contracts and DB model before moving code.

Deliverables:
- `ServiceProvider` + `UnifiedEvent` + `WatchlistFilter` definitions.
- Provider capability flags (supports_webhooks, supports_edits, supports_threads).
- Initial schema migrations with `tenant_id` everywhere (default to `default`).
- Router Core skeleton (ingest → normalize → persist → publish).

POC mapping:
- Extract and formalize `slack_mage.py` event handling into a provider interface.

### Phase 1 — Slack Ingestion + Persistence (4–7 days)
**Goal**: Slack events flow into DB with tenant scoping (single-tenant behavior).

Deliverables:
- Slack Socket Mode ingestion implemented as a provider service.
- Event normalization into `UnifiedEvent`.
- Deduplication on event_id + timestamp.
- Persist to `source_events` + `event_user_map` with `tenant_id=default`.

POC mapping:
- Replace local JSON state (`slack_mage_state.json`) with DB writes.

### Phase 2 — Near Real-Time Delivery (3–5 days)
**Goal**: events appear in dashboard within seconds.

Deliverables:
- WebSocket gateway + tenant-scoped subscriptions (single-tenant behavior).
- Router publishes events to WebSocket after persistence.
- UI updates without refresh.

POC mapping:
- Replace dashboard `/state` polling with WebSocket feed.

### Phase 3 — Single-Tenant Auth + Tenant-Ready Credential Storage (4–8 days)
**Goal**: desktop OAuth onboarding with tenant-ready storage for later migration.

Deliverables:
- OAuth install flow for a single Slack workspace.
- Token refresh + rotation support (still scoped to the single tenant).
- Encrypted credential storage with `tenant_id=default`.

POC mapping:
- Replace `.env` tokens with per-tenant credential storage.

### Phase 4 — Dashboard Controls (2–4 days)
**Goal**: meet MVP UX requirements.

Deliverables:
- **Delete event** endpoint + UI action (soft delete).
- **Clear all events** endpoint + UI action (scoped to `tenant_id=default`).
- Audit log for deletions (basic).

POC mapping:
- Replace `/state/reset` with proper DB deletion scoped to tenant.

### Phase 5 — Async Enrichment (optional next step, 4–7 days)
**Goal**: avoid blocking event delivery while adding summaries.

Deliverables:
- Async pipeline (queue + worker).
- Event updates to include summary/importance after processing.

POC mapping:
- Keep `ask_assistant` notifications optional and async.

### Phase 6 — Attachments & File References (future)
**Goal**: add references only, no binary storage.

Deliverables:
- Store file metadata + Slack file URLs.
- Optional preview render in UI.

---

## Risk Register (Short List)
- **Event duplication** without dedupe keys and idempotency.
- **Rate limits** if workspace fan-out isn’t optimized.
- **Token revocation/expiration** causing silent ingestion failure.
- **Visibility gaps** without tracing (“why didn’t I see this message?”).

---

## Recommended Next Actions
1. Confirm target DB (Postgres) and queue choice (Redis vs PG queue).
2. Approve the Phase 0 schemas and interfaces (with `tenant_id=default`).
3. Begin Phase 1 refactor from `mage-Slack` into the Router Core + Slack Provider.

---

## Files Reviewed
- `mage-Slack/README.md`
- `mage-Slack/slack_mage.py`
- `mage-social-hub-architecture.md`
