# Slack Mage Integration Tool Plan

## Goals
- Provide a Slack integration tool that reads credentials from `.env`.
- Offer an HTML dashboard inside the mage lab UI to configure event rules and view surfaced events.
- Allow rules to:
  1) surface events on the dashboard (counts/logs), and
  2) watch for events and notify the assistant via the `ask_assistant` endpoint.
- Do not pass message content to the assistant; only metadata about the event.

## Non-goals
- Full Slack message retrieval or display.
- Long-term storage of message content.
- Advanced analytics or historical exports.

## Assumptions
- It is acceptable (though not formally documented) to run a lightweight local HTTP server for the dashboard APIs.
- Slack Socket Mode is the initial integration path (no public webhooks).
- mage lab tools can call internal endpoints like `ask_assistant`.

## User Experience
- User opens a Slack Mage dashboard (HTML) within the mage lab interface.
- User sets rules:
  - Events to surface on the dashboard (e.g., any message in channel X).
  - Events to watch/notify the assistant (e.g., specified user posts in channel Y).
- User sees counters and a small event log (metadata only).

## Configuration (.env)
- `SLACK_BOT_TOKEN`: bot token (starts with `xoxb-`).
- `SLACK_APP_TOKEN`: Socket Mode token (starts with `xapp-`).
- `SLACK_MAGE_API_TOKEN`: shared secret for local dashboard API auth.
- Optional: `SLACK_SIGNING_SECRET` (only needed if we later add HTTP events).
- Optional: `SLACK_DEFAULT_WORKSPACE` (if multi-workspace support is added).

## Data Model
Store config/state as JSON in the workspace.

- `slack_mage_config.json`
  - `rules`: list of rule objects with `surface` and `notify_assistant` flags
  - `notification_settings`: throttling / quiet hours / duplicates
- `slack_mage_state.json`
  - `event_counts`: per-rule or per-type counters
  - `recent_events`: ring buffer of metadata-only events

Example rule:
```json
{
  "id": "rule-123",
  "name": "Sam in #general",
  "type": "message_posted",
  "channel_id": "C123456",
  "user_id": "U234567",
  "match": {
    "user_only": true,
    "channel_only": true
  },
  "surface": true,
  "notify_assistant": true
}
```

## Event Handling
- Use Slack Socket Mode (websocket) to receive events.
- Filter events locally based on configured rules.
- Update `slack_mage_state.json` with metadata-only events:
  - `event_type`, `channel_id`, `user_id`, `timestamp`, `rule_id`
- If `notify_assistant` is true, call `ask_assistant` with a short payload:
  - Example: `"sam_event": {"rule_id":"rule-123","event_type":"message_posted","channel_id":"C...","user_id":"U...","timestamp":"..."}`.
  - No message content.

## Assistant Notification
- The Slack tool calls `ask_assistant` with a structured payload and a short instruction.
- The assistant can follow-up by calling `notify_me` (or other tools).
- Include a deduplication or rate-limit mechanism to avoid spam (e.g., 1 per rule per N seconds).

## Dashboard (HTML)
- Single HTML file loaded by a tool function, similar to other mage lab HTML tools.
- JS UI provides:
  - List of existing rules (surface/watch toggles).
  - Form to add/edit rules.
  - Live counters and recent metadata events.
- UI communicates with a local API (localhost-only):
  - `GET /config` / `POST /config`
  - `GET /state` / `POST /state/reset`
  - `POST /listener/start` / `POST /listener/stop`

## Tool Functions (Python)
- `open_slack_mage_dashboard()`: open the HTML dashboard in mage lab.
- `slack_mage_start_listener()`: start Socket Mode listener.
- `slack_mage_stop_listener()`: stop listener.
- `slack_mage_status()`: return current state (listener running, counts).

## Security & Privacy
- Never store or forward message content.
- Store only IDs and timestamps.
- Do not log raw event payloads.
- Respect Slack rate limits and retry behavior.
- Local HTTP server must bind to `127.0.0.1`, avoid port `11115`, and include a simple auth token + tight CORS.
- Avoid blocking the mage lab backend process; run the listener/server in a background thread or subprocess.

## Decisions
- Socket Mode will be used for the initial release.
- Persist config/state in the workspace.
- Dashboard should map usernames/channel names to IDs using the Slack Web API.
- `ask_assistant` uses `POST http://127.0.0.1:11115/ask_assistant` with `{ "message": "..." }`.
- Support both public channels and private/DM scopes.

## Open Questions
1) Any constraints on Slack scopes or app setup beyond standard Socket Mode + events?
2) Should we add a minimal WebSocket listener to capture assistant responses, or rely on the UI only?

## Milestones
1) Confirm API approach (Socket Mode vs HTTP) and `ask_assistant` integration details.
2) Implement Python listener and config/state storage.
3) Implement local API server + HTML dashboard.
4) Wire assistant notification + dedup/throttle.
5) Quick manual test with a real Slack workspace.
