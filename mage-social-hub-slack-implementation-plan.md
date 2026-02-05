# Mage Social Hub — Detailed Implementation Plan (Slack POC → Minimal Scalable Architecture)

Date: 2026-01-27

This plan expands the roadmap into concrete tasks, file locations, API surfaces, and deliverables. It assumes the current Slack POC is in `mage-Slack/` and the target architecture follows the minimal scalable model outlined previously, with **single-tenant behavior** and **tenant-ready data shape**.

---

## Assumptions
- Near real-time delivery is acceptable (seconds).
- Single-tenant behavior for desktop, tenant-ready data shape for later migration.
- Attachments are references only (metadata + URLs), not stored binaries.
- Dashboard supports delete single entry and clear all events.
- Future providers will reuse the same provider interface.

---

## Phase 0 — Architecture Baseline (2–4 days)

### Goals
- Define the minimal contracts and data model that won’t change when adding new providers.

### Tasks
1. **Define core interfaces and types**
   - Create `backend/services/base.py` with `ServiceProvider`, `UnifiedEvent`, `WatchlistFilter`.
   - Add provider capability flags: `supports_webhooks`, `supports_edits`, `supports_threads`, `supports_reactions`.
   - Define normalized event fields and required IDs.

2. **Database schema (tenant-ready)**
   - Add tables: `tenants`, `users`, `service_creds`, `watchlists`, `source_events`, `event_user_map`.
   - Include indexing strategy: `(tenant_id, timestamp)`, `(source_event_id)`, `(user_id, timestamp)`.
   - Add soft-delete field for events: `deleted_at`.
   - Default all records to `tenant_id=default` for desktop behavior.

3. **Router Core skeleton**
   - Create `backend/core/router.py` with:
     - `ingest(event)`
     - `normalize(event)`
     - `match_watchlists(event)`
     - `persist(event)`
     - `publish(event)`

4. **Queue abstraction**
   - Define `backend/core/queue.py` with a minimal interface:
     - `enqueue(event)`
     - `consume(handler)`
   - Implement a simple Postgres queue or Redis queue (choose in Phase 0).

### Deliverables
- Minimal backend skeleton with contracts.
- Initial migrations ready for Phase 1.

---

## Phase 1 — Slack Ingestion + Persistence (4–7 days)

### Goals
- Slack messages flow into storage with dedupe and tenant scoping (single-tenant behavior).

### Tasks
1. **Slack provider extraction**
   - Create `backend/services/slack/provider.py`.
   - Implement:
     - `connect(credentials)`
     - `get_events(filter)` (optional for backfill)
     - `subscribe(filter, callback)` (Socket Mode)
     - `unsubscribe(subscription_id)`

2. **Normalize Slack events**
   - Map Slack message to `UnifiedEvent`.
   - Add dedupe key: `source_event_id = event_id || ts`.

3. **Ingestion pipeline**
   - On socket message, enqueue normalized event to queue.
   - Router consumes queue and writes to DB.

4. **Persistence**
   - Insert into `source_events` and `event_user_map`.
   - Ensure idempotency on `(tenant_id, source_event_id)`.

### Deliverables
- Slack events stored in DB with `tenant_id=default`.

---

## Phase 2 — Near Real-Time Delivery (3–5 days)

### Goals
- Events delivered to dashboard in seconds.

### Tasks
1. **WebSocket gateway**
   - Add `backend/core/session.py` or `backend/realtime/ws.py`.
   - Implement tenant-scoped channels (single-tenant behavior uses `default`).

2. **Router publish**
   - After persistence, push event to tenant WebSocket channel.

3. **Frontend update**
   - Add WebSocket client to dashboard.
   - Replace polling `/state` endpoint with WS feed.

### Deliverables
- Live event feed, no manual refresh.

---

## Phase 3 — Single-Tenant Auth + Tenant-Ready Credential Storage (4–8 days)

### Goals
- Slack OAuth onboarding for a single tenant with tenant-ready storage.

### Tasks
1. **OAuth endpoints**
   - Add `/oauth/slack/install` and `/oauth/slack/callback`.
   - Store `access_token`, `refresh_token`, `team_id` with `tenant_id=default`.

2. **Token refresh**
   - Add background refresh or refresh-on-use.

3. **Credential encryption**
   - Encrypt `service_creds.credentials_encrypted` with a master key.

### Deliverables
- Desktop app can connect one workspace without local `.env` tokens.

---

## Phase 4 — Dashboard Controls (2–4 days)

### Goals
- Deletion controls per user request.

### Tasks
1. **Delete single event**
   - API: `DELETE /events/{event_id}`
   - Soft-delete in `event_user_map` or set `deleted_at`.

2. **Clear all events**
   - API: `POST /events/clear`
   - Deletion scoped to `tenant_id=default`.

3. **UI buttons**
   - Add delete icon per event.
   - Add “Clear all events” button with confirmation.

### Deliverables
- Dashboard supports event cleanup and reset.

---

## Phase 5 — Async Enrichment (optional, 4–7 days)

### Goals
- Summaries and importance scoring without blocking ingestion.

### Tasks
1. **Worker process**
   - Consume events from queue.
   - Call summarization pipeline.

2. **DB update + UI refresh**
   - Update `summary`, `importance_score` fields.
   - Notify UI via WS update.

### Deliverables
- Summaries delivered asynchronously.

---

## Phase 6 — Attachments (future)

### Goals
- Add Slack file references and metadata.

### Tasks
1. **Store Slack file metadata**
   - Fields: `file_id`, `url_private`, `mimetype`, `size`.
   - No binary storage.

2. **UI rendering**
   - Show file type + filename + link.

---

## Testing Plan (All Phases)

- **Unit tests**: provider normalization, dedupe, watchlist matching.
- **Integration tests**: Slack event → DB persistence → WS publish.
- **Load checks**: burst of events, queue backlog, WS fanout.
- **Tenant-ready checks**: `tenant_id=default` enforced on reads/writes.

---

## Deliverables Checklist (MVP)
- Slack events ingested with `tenant_id=default`.
- Watchlist matching and storage.
- Near real-time event delivery.
- Delete single event and clear all events.
- OAuth and credential storage.

---

## Suggested File Layout (Target)

```
mage-social-hub/
├── backend/
│   ├── core/
│   │   ├── router.py
│   │   ├── queue.py
│   │   └── session.py
│   ├── services/
│   │   ├── base.py
│   │   └── slack/
│   │       └── provider.py
│   ├── api/
│   │   ├── events.py
│   │   └── oauth.py
│   ├── database/
│   │   └── migrations/
│   └── main.py
└── frontend/
    ├── src/
    │   ├── services/ws.ts
    │   └── components/
    └── package.json
```
