# Slack Mage Community Tool

Slack Mage listens for Slack message events via Socket Mode and lets you define event rules inside a local dashboard. Rules can surface event metadata on the dashboard and notify the assistant via `ask_assistant` (without sharing message content).

## Files
- `slack_mage.py` — tool functions + Socket Mode listener + local API server.
- `slack_mage_dashboard.html` — dashboard UI served from a local server.

## Requirements
- mage lab desktop application.
- Slack app with Socket Mode enabled.
- Python dependency: `slack_sdk` (install in the mage lab environment if missing).

## Slack App Setup
1) Create a Slack app and enable **Socket Mode**.
2) Add bot scopes for public + private + DMs:
   - `channels:read`, `channels:history`
   - `groups:read`, `groups:history`
   - `im:read`, `im:history`
   - `mpim:read`, `mpim:history`
   - `users:read`
   - `connections:write` (Socket Mode)
3) Install the app to the workspace and copy:
   - Bot token (`xoxb-...`)
   - App-level token (`xapp-...`)

### Slack App Manifest (JSON)
Paste this into Slack's app manifest editor, then enable Socket Mode and install the app.
```json
{
  "display_information": {
    "name": "Slack Mage"
  },
  "features": {
    "bot_user": {
      "display_name": "Slack Mage",
      "always_online": false
    }
  },
  "oauth_config": {
    "redirect_urls": [],
    "scopes": {
      "bot": [
        "channels:read",
        "channels:history",
        "groups:read",
        "groups:history",
        "im:read",
        "im:history",
        "mpim:read",
        "mpim:history",
        "users:read"
      ],
      "user": []
    }
  },
  "settings": {
    "event_subscriptions": {
      "bot_events": [
        "message.channels",
        "message.groups",
        "message.im",
        "message.mpim"
      ]
    },
    "org_deploy_enabled": false,
    "socket_mode_enabled": true,
    "token_rotation_enabled": false
  }
}
```

Note: `connections:write` is required for the app-level token used by Socket Mode, but it is not a bot scope. Create the app token separately in Slack and assign `connections:write` there.

## Configuration (.env)
Add these lines to `~/.config/magelab/.env`:
```
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_MAGE_API_TOKEN=your-local-dashboard-token
```

`SLACK_MAGE_API_TOKEN` is used to access the local dashboard API. Keep it private.

### Getting the Tokens
1) Enable Socket Mode:
   - In the Slack app settings, open **Socket Mode** and toggle **Enable Socket Mode**.
2) Create the app-level token (`SLACK_APP_TOKEN`):
   - Go to **Basic Information** → **App-Level Tokens**.
   - Click **Generate Token and Scopes**, add `connections:write`, and create.
   - Copy the `xapp-...` token.
3) Install the app to your workspace (`SLACK_BOT_TOKEN`):
   - Go to **OAuth & Permissions** and click **Install to Workspace**.
   - Copy the **Bot User OAuth Token** (`xoxb-...`).
4) Create a local dashboard token:
   - Pick any long random string and set `SLACK_MAGE_API_TOKEN` in `.env`.

## Installation
1) Copy the `mage-Slack` folder into `~/Mage/Tools`.
2) Restart mage lab.
3) Toggle the tool on in **Settings -> Tools -> Community**.

## Usage
- Open the dashboard with:
  - `open_slack_mage_dashboard()`
- Start the listener (or use the dashboard button):
  - `slack_mage_start_listener()`
- Stop the listener:
  - `slack_mage_stop_listener()`

## Dashboard Guide
### Making Rules
1) Open the dashboard and keep the listener running.
2) Use the user/channel lookup buttons to fill IDs (recommended), or paste Slack IDs directly:
   - User IDs look like `U123...`
   - Channel IDs look like `C123...`
3) Leave User ID and/or Channel ID blank to match any user/channel.
4) Click **Save rule** to persist it.

### Event Types
- Current event type is **message_posted** (Slack message events only).
- The event type field is read-only in the dashboard.

### Rule Toggles
- **Show**: If on, matched events are recorded in dashboard state and shown in Recent Events and per-rule counts.
- **Notify**: If on, the assistant receives a notification when the rule matches (subject to throttling).
- **include message**: If on, the notification includes the message text. If off, only metadata is sent.
- **Enabled**: If off, the rule is ignored entirely.

### Visibility
- Dashboard shows recent events (metadata and message text if stored) and per-rule counts.
- The event log only includes events for rules with **Show** enabled.
- Message text is stored locally in the dashboard state file when surfaced.

### Mage Integration 
- Assistant notifications are sent via `ask_assistant` and are throttled per rule using the dashboard’s **Throttle seconds** setting.
- If **include message** is enabled, the full message text is sent to the assistant.
- If you want the assistant to know a rule matched without seeing content, keep **include message** off.

## Notes
- The dashboard runs on `127.0.0.1` with an auto-selected port. It avoids `127.0.0.1:11115`.
- Surfaced events store metadata plus message text in the local state file for dashboard display.
- Rule toggle "Notify + message" includes the message text in assistant notifications.

TODO:
- Integrate html page into mage tabs
- clean up dashboard to make more user friendly
- add responses and targeted assistant responses on behalf of user


## License
This tool inherits the MIT License from the mage lab Community Tools repository.
