# Mage Social Hub - Architecture Overview

A unified dashboard for chat services and social media feeds with customizable summarized information.

---

## Core Abstraction: Service Provider Interface

Every external system implements the same contract:

```python
class ServiceProvider(ABC):
    """Base class for all service integrations"""
    
    id: str                # Unique service identifier (e.g., "slack")
    name: str              # Display name
    
    @abstractmethod
    async def connect(self, credentials: dict) -> bool:
        """Initialize connection, return success"""
        pass
    
    @abstractmethod
    async def get_events(self, filter: WatchlistFilter) -> List[UnifiedEvent]:
        """Fetch events matching the filter"""
        pass
    
    @abstractmethod
    async def subscribe(self, filter: WatchlistFilter, callback: Callable) -> str:
        """Set up real-time event delivery, return subscription ID"""
        pass
    
    @abstractmethod
    async def unsubscribe(self, subscription_id: str) -> bool:
        """Cancel real-time subscription"""
        pass
    
    @abstractmethod
    def get_supported_filters(self) -> List[str]:
        """Return list of filter types this service supports"""
        pass
```

---

## Unified Event Model

All services translate their native events into a standard format:

```python
@dataclass
class UnifiedEvent:
    id: str                      # Unique event ID
    source: str                  # Service identifier (slack, reddit, etc.)
    type: str                    # message, post, mention, reaction, etc.
    timestamp: datetime
    
    # Actor info
    from_user: Optional[str]     # User ID
    from_name: str               # Display name
    from_avatar: Optional[str]   # Profile image URL
    
    # Destination info (if applicable)
    to_context: Optional[str]    # Channel, subreddit, etc.
    to_context_type: str         # channel, subreddit, direct_message, etc.
    
    # Content
    content: str                 # Main text/content
    content_type: str            # text, markdown, html, etc.
    attachments: List[Attachment]
    
    # Enriched data
    importance_score: float      # 0-1, calculated by router
    summary: Optional[str]       # LLM/generated summary
    keywords: List[str]          # Extracted topics/entities
    
    # Metadata
    raw_data: Optional[dict]     # Original event from the service
    links: List[str]             # URLs in the event
    mentions: List[str]          # Mentioned users/tags
```

---

## Watchlist / Subscription Model

Users configure what they want to watch:

```python
@dataclass
class WatchlistFilter:
    service_id: str              # slack, reddit, x, etc.
    filter_type: str             # channel, subreddit, user, hashtag, etc.
    filter_value: str            # #general, r/programming, @elon, etc.
    
    # Optional constraints
    keywords: List[str] = None   # Only events containing these
    importance_threshold: float = 0.0  # Minimum score
    time_window: Optional[timedelta] = None  # Only events after this time
    
    # Summary preferences
    summarize: bool = True
    summary_style: str = "concise"  # concise, detailed, bullets
```

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Dashboard (React)                    │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────────┐   │
│  │ Service │ │ Watchlist│ │  Event   │ │  Summary Panels    │   │
│  │ Status  │ │ Config   │ │  Feed    │ │  (Customizable)    │   │
│  └────┬────┘ └─────┬────┘ └────┬─────┘ └────────┬───────────┘   │
└───────┼────────────┼─────────────┼─────────────────┼────────────────┘
        │            │  WebSocket  │                 │
        ▼            ▼             ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Router Core                                  │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐              │
│  │ Dispatcher  │ │ Event Log    │ │ Watchlist    │              │
│  │ (Subscribes)│ │ (Store/Cache)│ │ Matcher      │              │
│  └──────┬──────┘ └──────┬───────┘ └──────┬───────┘              │
│         └──────────────┼───────────────┘                        │
└────────────────┼────────────────────────────────────────────────┘
                 │
    ┌────────────┼────────────┬────────────┬────────────┐
    ▼            ▼            ▼            ▼            ▼
┌───────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐
│ Slack │  │ Reddit   │  │ X/Twitter│  │ GChat    │  │ ...     │
│Provider│  │ Provider │  │ Provider │  │ Provider │  │ Provider│
└───────┘  └──────────┘  └──────────┘  └──────────┘  └─────────┘
     │          │            │            │            │
     ▼          ▼            ▼            ▼            ▼
  Slack API  Reddit API     X API       GChat API    External APIs
```

---

## Core Services

### 1. **Configuration Service**
- Stores user preferences
- Service credentials (encrypted)
- Watchlist definitions
- Summary templates
- Theme/display settings

### 2. **Router Core**
- Maintains active subscriptions to services
- Receives events via webhooks or polling
- Normalizes events to `UnifiedEvent`
- Matches events against user watchlists (tenant-ready, single-tenant behavior)
- Calculates importance scores
- Routes events to appropriate processors

### 3. **Summarization Service**
- LLM-based summarization (configurable)
- Keyword/entity extraction
- Deduplication across services
- Importance scoring algorithm

### 4. **Session Service**
- Real-time WebSocket delivery to dashboard
- Live updates
- Notification pushes

### 5. **Display Service** (in React)
- Component for rendering unified events
- Layout engine for summary panels
- Visualization options

### 6. **Notification Service**
- Push notifications
- Email digests
- Alert rules

---

## Event Flow

```
1. User adds watchlist: Slack + channel = "#general"
   └─ Router calls slack_provider.subscribe(filter)
   └─ Slack opens webhook or polling loop

2. New message arrives in #general
   └─ Slack provider webhook triggered
   └─ Provider translates to UnifiedEvent
   └─ Router receives UnifiedEvent
   
3. Event matching and enrichment
   └─ Check against all user watchlists
   └─ Calculate importance_score
   └─ Run through summarization pipeline
   └─ Extract keywords
   
4. Event routing
   └─ If matches user's watchlist
      └─ Store in event log
      └─ Push via WebSocket to dashboard
      └─ Trigger notification (if enabled)
```

---

## Configuration Examples

```yaml
# User config
watchlists:
  - service: slack
    filter_type: channel
    filter_value: "#general"
    importance_threshold: 0.5
    summarize: true
    
  - service: reddit
    filter_type: subreddit
    filter_value: "r/programming"
    keywords: ["AI", "LLM", "openai"]
    
  - service: x
    filter_type: user
    filter_value: "@elonmusk"
    importance_threshold: 0.8
    summary_style: "bullets"

summary_panels:
  - id: priority
    title: "Priority Feed"
    filters:
      - source: "*"
        importance_score: "> 0.8"
    display: "cards"
    
  - id: slack-activity
    title: "Slack Highlights"
    filters:
      - source: "slack"
    display: "threaded"
```

---

## Modular Integration Pattern

### Adding a New Service

Contributors only need to:

1. **Implement `ServiceProvider` interface**
2. **Add service to registry**:
   ```python
   # services/registry.py
   SERVICES = {
       "slack": SlackProvider,
       "reddit": RedditProvider,
       "x": TwitterProvider,
       "gchat": GChatProvider,
   }
   ```
3. **Add credential schema** (for config UI)

The core router and dashboard automatically support it.

### Example: Slack Provider Skeleton

```python
class SlackProvider(ServiceProvider):
    id = "slack"
    name = "Slack"
    
    async def connect(self, credentials):
        self.client = AsyncSlackClient(credentials["token"])
        self.authed_user = await self.client.auth_test()
        return True
    
    async def get_events(self, filter):
        if filter.filter_type == "channel":
            messages = await self.client.conversations_history(
                channel=filter.filter_value
            )
            return [self._to_unified(msg) for msg in messages]
    
    async def subscribe(self, filter, callback):
        # Set up Slack Event API webhook
        self.webhook_callbacks[filter.filter_value] = callback
        return f"slack-sub-{filter.filter_value}"
    
    def get_supported_filters(self):
        return ["channel", "user", "team"]
    
    def _to_unified(self, slack_msg):
        return UnifiedEvent(
            id=slack_msg["ts"],
            source="slack",
            type="message",
            timestamp=_parse_ts(slack_msg["ts"]),
            from_user=slack_msg["user"],
            content=slack_msg["text"],
            to_context=slack_msg["channel"],
            to_context_type="channel",
            # ... more fields
        )
```

---

## Database Schema (MVP, Tenant-Ready)

```sql
-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY,
    tenant_id TEXT DEFAULT 'default',
    email TEXT UNIQUE,
    config JSON,
    created_at TIMESTAMP
);

-- Service credentials (encrypted)
CREATE TABLE service_creds (
    user_id UUID REFERENCES users(id),
    tenant_id TEXT DEFAULT 'default',
    service_id TEXT,
    credentials_encrypted TEXT,
    PRIMARY KEY (user_id, service_id)
);

-- Watchlist configs
CREATE TABLE watchlists (
    user_id UUID REFERENCES users(id),
    id UUID PRIMARY KEY,
    tenant_id TEXT DEFAULT 'default',
    service_id TEXT,
    filter_type TEXT,
    filter_value TEXT,
    config JSON
);

-- Event log (for history/persistence)
CREATE TABLE events (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    tenant_id TEXT DEFAULT 'default',
    source TEXT,
    type TEXT,
    timestamp TIMESTAMP,
    from_user TEXT,
    to_context TEXT,
    content TEXT,
    importance_score FLOAT,
    summary TEXT,
    raw_data JSON
);
```

---

## Key Design Benefits

| Concern | Solution |
|---------|----------|
| **Scalability of integrations** | Plugin architecture—new services don't touch core |
| **Cross-service deduplication** | Unified event model + centralized routing |
| **Customizable summaries** | Pipeline approach with LLM integration |
| **Real-time vs batching** | Subscriptions for real-time, `get_events` for backfill/summary |
| **Tenant-ready** | `tenant_id` on all records (default `default` for desktop); easy future migration |
| **Contribution friendliness** | Clear interface + minimal boilerplate |
| **Failure isolation** | Provider errors don't crash router |

---

## Tech Stack Suggestion

| Layer | Tools |
|-------|-------|
| Frontend | React + TypeScript + WebSockets |
| Backend | Python (FastAPI/Starlette) + async/await |
| Database | PostgreSQL + pgvector (if we add semantic search) |
| Real-time | WebSockets (native or via Redis Pub/Sub) |
| LLM | OpenAI API / Claude API for summaries |
| Auth | OAuth flows per service (single-tenant behavior initially) |
| Deployment | Docker + Kubernetes |

---

## Project Structure

```
mage-social-hub/
├── frontend/                 # React + TypeScript
│   ├── src/
│   │   ├── components/       # UI components
│   │   ├── hooks/           # Custom React hooks
│   │   ├── services/        # WebSocket client, API client
│   │   └── types/           # TypeScript types
│   └── package.json
├── backend/
│   ├── core/                # Router core services
│   │   ├── router.py        # Main event router
│   │   ├── config.py        # Configuration service
│   │   ├── summary.py       # Summarization service
│   │   └── session.py       # WebSocket session manager
│   ├── services/            # Service providers
│   │   ├── base.py          # ServiceProvider base class
│   │   ├── slack/           # Slack implementation
│   │   ├── reddit/          # Reddit implementation
│   │   ├── twitter/         # X/Twitter implementation
│   │   └── registry.py      # Service registry
│   ├── models/              # Data models
│   ├── api/                 # FastAPI endpoints
│   ├── database/            # DB connection, migrations
│   └── main.py              # Application entry point
├── scripts/                 # Utility scripts
├── config/                  # Configuration files
└── docs/                    # Documentation
```

---

## Next Steps (Tenant-Ready, Single-Tenant Behavior)

### Phase 1: Core Foundation
- [ ] Set up project structure
- [ ] Implement `ServiceProvider` base class
- [ ] Create Router Core with WebSocket support
- [ ] Set up PostgreSQL database schema with `tenant_id` defaulted to `default`
- [ ] Build Configuration Service

### Phase 2: First Integration
- [ ] Implement Slack Provider
- [ ] Implement basic event normalization
- [ ] Set up Slack OAuth flow (single-tenant behavior)
- [ ] Test end-to-end with Slack

### Phase 3: Frontend Dashboard
- [ ] Build React dashboard layout
- [ ] Implement WebSocket client
- [ ] Create watchlist configuration UI
- [ ] Build event feed component

### Phase 4: Summarization
- [ ] Integrate LLM API for summaries
- [ ] Build importance scoring algorithm
- [ ] Add keyword extraction
- [ ] Create summary panel templates

---

## Service Integration Prioritization

### Top 5: Bang for Buck

| Rank | Service | Complexity | Reach | Why |
|------|---------|------------|-------|-----|
| 🥇 **1** | **Slack** | Low-Medium | Very High | Excellent API, webhooks, OAuth straightforward. Huge for tech/teams. |
| 🥈 **2** | **Discord** | Medium | Very High | Great API, bots, webhooks. Gaming/dev/communities. Rich features. |
| 🥉 **3** | **Reddit** | Low | High | Public read API requires no auth. Simple event model. Great for news/communities. |
| 4 | **X/Twitter** | High | Very High | API restrictions make this harder. Delay to 3rd priority at best. |
| 5 | **Telegram** | Low-Medium | High | Very simple bot API. Global reach. Good alternative. |

---

### Tier 1: Start Here **(First 3)**

#### 1. **Slack** 🔥
**Why first:** Proves the entire system works. Enterprise adoption, strong API, clear value prop.

- **Complexity:** Low-Medium
- **Auth:** OAuth 2.0 (well-documented)
- **Real-time:** Event API with webhooks ← perfect for this pattern
- **Event richness:** Channels, DMs, reactions, threads, attachments

**Implementation estimate:** 2-3 days for MVP provider

---

#### 2. **Discord** 🔥
**Why second:** Massive user base, APIs similar in spirit to Slack, but broader demographic.

- **Complexity:** Medium
- **Auth:** OAuth 2.0 or bot token
- **Real-time:** Gateway API (websockets) or HTTP endpoints
- **Event richness:** Channels, threads, DMs, reactions, voice states, emojis, embeds

**Implementation estimate:** 3-4 days for MVP provider

---

#### 3. **Reddit** 🔥
**Why third:** Instant breadth. No auth for public reads = fast to build and test.

- **Complexity:** Low
- **Auth:** Optional for public subreddits, OAuth for personal actions
- **Real-time:** Polling (no webhooks for public feeds) – but cheap and reliable
- **Event richness:** Posts, comments, upvotes, mod actions, crossposts

**Implementation estimate:** 1-2 days for MVP provider

---

### Tier 2: Phase 2 **(Next 2)**

#### 4. **Telegram**
- **Complexity:** Low-Medium
- **Why:** Simpler than Discord, huge in many regions, bot API is very developer-friendly
- **Caveat:** Less adoption in US tech circles vs Slack/Discord

#### 5. **X/Twitter** ⚠️
- **Complexity:** High
- **Why:** API restrictions, pricing tiers, rate limits. Valuable but early friction.
- **Better to:** Build once system is proven with easier integrations

---

### Why This Order Works

| Priority | Services | Value Delivered |
|----------|----------|-----------------|
| **Phase 1** | Slack + Discord + Reddit | Covers: **Work chat, community chat, news/forums** ← 80% of meaningful digital noise for most users |
| **Phase 2** | Telegram + X | Expands to **alternative chat + public news commentary** |
| **Phase 3** | GChat, LinkedIn, etc. | Enterprise/Professional verticals (harder auth, lower immediate impact) |

---

### Quick Comparison

| Service | API Quality | Auth Effort | Webhooks | First-Day Demo |
|---------|-------------|-------------|----------|----------------|
| Slack | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ✅ | ✅ |
| Discord | ⭐⭐⭐⭐ | ⭐⭐⭐ | ✅ | ✅ |
| Reddit | ⭐⭐⭐⭐ | ⭐⭐ | ❌ (polling) | ✅ (no auth) |
| Telegram | ⭐⭐⭐⭐ | ⭐ | ✅ | ✅ |
| X/Twitter | ⭐⭐ | ⭐⭐⭐⭐ | ✅ | ❌ (restricted) |
| GChat | ⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ | ⚠️ (Google Cloud setup) |

---

### Recommended Build Timeline

| Week | Focus | Deliverable |
|------|-------|-------------|
| **Week 1** | Slack Provider | End-to-end Slack integration working |
| **Week 2** | Discord Provider | Multi-service routing proven |
| **Week 3** | Reddit Provider | Polling + no-auth pattern validated |

After that you have a working system covering:
- Work messages (Slack)
- Community chats (Discord)
- News/forums (Reddit)

That's a compelling first release for most users. Then expand in any direction based on feedback.

---

## Notes

All service integrations can be added independently by contributors—only need to:
1. Implement the `ServiceProvider` interface
2. Register the service
3. Add credential schema for the config UI

The core router, event handling, and dashboard remain unchanged.
