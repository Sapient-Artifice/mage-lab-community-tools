# Mage Home Assistant Community Tool

Local-first Home Assistant integration for Mage Lab. This tool is designed to live in
`~/Mage/Tools` and be approved through the Mage Lab UI. Start with basic entity
query/control and expand to richer device-specific helpers later.

## Files
- `mage_home_assistant_tool.py` (tool functions)
- `home-assistant.sh` (Docker container helper)

## Setup
1) Copy `mage_home_assistant_tool.py` into `~/Mage/Tools` (or a subfolder).
2) Set environment variables:
   - `HA_URL` (default: `http://127.0.0.1:8123`)
   - `HA_TOKEN` (required: Home Assistant long-lived token)
   - Optional:
     - `HA_TIMEOUT` (default: `10` seconds)
     - `HA_ALLOWED_DOMAINS` (default: `light,switch`)
     - `HA_ALLOWED_SERVICES` (default: `turn_on,turn_off,toggle`)
3) In Mage Lab, approve the tool in the User Tools panel.

## Functions
- `ha_health_check()`
- `ha_list_entities(domain=None, name=None, area=None)`
- `ha_get_state(entity_id)`
- `ha_call_service(domain, service, entity_id=None, area=None, service_data=None)`
- `kasa_list_plugs(name=None, area=None)`

## Notes
- Kasa plugs are treated as standard HA `switch` entities. No device IPs needed
  if Home Assistant already has the devices configured.
- `kasa_list_plugs` uses best-effort name matching; refine as you standardize
  entity names or add device registry helpers later.

## Home Assistant Container Helper
Use `home-assistant.sh` to run Home Assistant in Docker without retyping the
full command each time.

```bash
cd mage-home-assistant
./home-assistant.sh start
```

Available actions:
- `./home-assistant.sh start`
- `./home-assistant.sh stop`
- `./home-assistant.sh restart`
- `./home-assistant.sh status`
- `./home-assistant.sh logs`
- `./home-assistant.sh update`
