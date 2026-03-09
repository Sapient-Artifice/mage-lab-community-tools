# 🛠️ mage lab Community Tools

Welcome to the mage lab Community Tools repository! Here you'll find a collection of user-created tools designed to enhance your mage lab workflows, streamline tasks, and boost productivity within the mage lab environment.

---

## 🚀 Quick Installation

Getting started is straightforward:

1. Download or clone the repository.
2. Copy the desired Tools and associated files into your `~/Mage/Tools` directory.
3. Launch the mage lab app. You'll find a new toggle under the **Community** section, allowing you to enable or disable the installed tools with ease.

---

## Tools in this repo

### [mage_scheduler](./mage_scheduler/README.md)
A local task scheduling service built on FastAPI + Celery + Redis. Schedule one-shot commands, recurring cron jobs, and dependency-chained task pipelines. Includes a web dashboard, a structured LLM intent API, and completion notifications back to the assistant. **Pairs with [mage-scheduler-tool](./mage-scheduler-tool/README.md).**

### [mage-scheduler-tool](./mage-scheduler-tool/README.md)
The mage lab skill and Python tool that gives the assistant direct access to the scheduler — scheduling intents, previews, task management, and dashboard control — without constructing API calls by hand. **Requires the [mage_scheduler](./mage_scheduler/README.md) service.**

### [mage-Slack](./mage-Slack/README.md)
Listens for Slack message events via Socket Mode and lets you define rules that surface event metadata on a local dashboard or notify the assistant via `ask_assistant`.

### [mage-home-assistant](./mage-home-assistant/README.md)
Tool functions for managing a local Home Assistant instance, including Docker container helpers and entity state queries.

### [mage-Jira](./mage-Jira/)
Integration for Jira Cloud — create, edit, transition, assign, comment on issues, run JQL queries, and add attachments.

### [CommunityBraveSearch](./CommunityBraveSearch/BraveSearchCommunity_README.md)
Brave Search tool that calls Brave's REST API directly using your own API key, bypassing the mage lab gateway.

### [GrepGlob](./GrepGlob/GrepGlob_README.md)
Two file system search utilities: `GlobTool` for fast pattern-based file matching and `GrepTool` for content search across files.

### [mage-esp32-cam](./mage-esp32-cam/README.md)
Capture JPEG snapshots from ESP32-CAM modules over WiFi, save them to disk, and open them in a browser tab. Supports named cameras via env vars (`ESP32_CAM_<NAME>`) or direct URL per-request.

### [mageMap](./mageMap/MAGE_MAPS.md)
Interactive Leaflet-based routing map that opens in the browser (or embedded in mage lab), with address lookup and turn-by-turn routing.

---

## 🤝 Contributing

We welcome your creativity and expertise! Whether you're suggesting new tools or enhancing existing ones, your contributions help the community grow.

### How to Contribute:

1. Fork this repository.
2. Create a branch for your new feature or improvement (`git checkout -b feature/new-awesome-tool`).
3. Implement your feature or improvement.
4. Submit a Pull Request with clear descriptions of your changes.

For detailed guidance on creating and submitting new tools, visit the [official mage lab documentation](https://magelab.ai/en-usd/pages/docs).

---

## 📄 License

mage lab Community Tools are released under the **MIT License**. You're free to use, modify, and distribute these tools, provided you include the original license file.

---

🌟 **Happy coding, and thank you for contributing to the mage lab community!** 🌟
