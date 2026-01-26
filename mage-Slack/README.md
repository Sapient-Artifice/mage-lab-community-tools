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

## Notes
- The dashboard runs on `127.0.0.1` with an auto-selected port. It avoids `127.0.0.1:11115`.
- Events store metadata only (user ID, channel ID, timestamp). No message content is saved or sent.
- If `slack_sdk` is missing, install it in the mage lab Python environment.

## License
This tool inherits the MIT License from the mage lab Community Tools repository.
