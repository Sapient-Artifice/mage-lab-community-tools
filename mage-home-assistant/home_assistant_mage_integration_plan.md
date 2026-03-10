# Home Assistant → Mage Integration Plan

## Document Info
- **Created:** February 3, 2026
- **Status:** Planning Phase
- **Primary Focus:** Kasa (TP-Link) Smart Devices

---

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Kasa Smart Devices Primer](#kasa-smart-devices-primer)
4. [Phase 1: Core Connection Layer](#phase-1-core-connection-layer)
5. [Phase 2: Mage Tool Functions](#phase-2-mage-tool-functions)
6. [Phase 3: User Permission System](#phase-3-user-permission-system)
7. [Phase 4: Kasa-Specific Integration](#phase-4-kasa-specific-integration)
8. [Phase 5: Security & Safety](#phase-5-security--safety)
9. [Development Roadmap](#development-roadmap)
10. [Key Design Decisions](#key-design-decisions)

---

## Overview

This plan details how to integrate **Home Assistant** into Mage, enabling AI-driven control of home automation devices. The initial focus will be on **Kasa (TP-Link) Smart Devices** due to their:

- Wide adoption and affordability
- Excellent Home Assistant native support (TP-Link Smart Home integration)
- Local connectivity (no cloud dependency in most cases)
- Variety of device types (plugs, switches, bulbs, strips, hubs)

### Goals
1. **Query device states** - Read entity information from Home Assistant
2. **Control devices** - Execute service calls to modify device states
3. **Natural language commands** - Parse conversational requests into HA actions
4. **Permission-based control** - User defines what AI can do
5. **Safety layer** - Prevent dangerous or unintended actions
6. **Audit logging** - Track all AI-initiated actions

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          Mage Environment                        │
│                                                                  │
│  ┌─────────────┐    REST/WebSocket    ┌──────────────────┐     │
│  │   Mage AI   │ ◄─────────────────► │ Home Assistant   │     │
│  │   (LTM/Tools)│  Port 8123          │   (Core + API)   │     │
│  └─────────────┘                      └──────────────────┘     │
│         │                                         │            │
│         │                                         │            │
│  ┌──────▼─────────┐                    ┌─────────▼──────────┐ │
│  │ Permission     │◄───────────────────│ TP-Link (Kasa)     │ │
│  │   Config       │    Local Network   │   Devices          │ │
│  │                │                    │                    │ │
│  │ • Entity ACL   │                    │ • Plugs & Strips   │ │
│  │ • Domain Rules │                    │ • Light Bulbs      │ │
│  │ • Approval     │                    │ • Wall Switches    │ │
│  │   Queue        │                    │ • Light Strips     │ │
│  └────────────────┘                    │ • Hubs             │ │
│                                        └────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Communication Flow

```
User Query → Mage AI → Parse Intent → Permission Check → Home Assistant API
                                                        │
                                                        ▼
                                              ┌───────────────────┐
                                              │ TP-Link (Kasa)    │
                                              │ Local Discovery   │
                                              │ & Control         │
                                              └───────────────────┘
```

---

## Kasa Smart Devices Primer

### What is Kasa?

**Kasa** is TP-Link's smart home ecosystem, consisting of WiFi-connected devices that can be controlled locally without cloud dependency. Devices communicate using TP-Link's proprietary Smart Home protocol.

### Home Assistant Integration

Home Assistant includes the **TP-Link Smart Home** integration (native, built-in) which supports both Kasa and Tapo devices.

**Integration Stats:**
- Used by 14.2% of active Home Assistant installations
- Platinum quality rating
- IoT Class: Local Polling
- Updates devices every 5 seconds
- Local connectivity (no cloud required for most operations)

### Supported Kasa Devices

| Device Type | Supported Models | Entity Type in HA |
|-------------|------------------|-------------------|
| **Smart Plugs** | HS100, HS103, HS105, HS110, KP100, KP105, KP115, KP125, KP125M, KP401, EP10, EP25 | `switch.*` |
| **Power Strips** | HS107, HS300, KP200, KP303, KP400, EP40, EP40M | `switch.*` (multiple) |
| **Wall Switches** | HS200, HS210, HS220, ES20M, KS200, KS200M, KS205, KS220, KS220M, KS225, KS230, KS240, KP405 | `switch.*` |
| **Smart Bulbs** | KL110, KL120, KL125, KL130, KL135, KL50, KL60, LB110 | `light.*` |
| **Light Strips** | KL400L5, KL420L5, KL430 | `light.*` |
| **Hubs** | KH100 | `hub.*` |
| **Hub Sensors** | KE100 (temperature) | `sensor.*` |

### Entity Types & Capabilities

#### Switch Entities (Plugs, Strips, Basic Switches)
```yaml
entity_id: switch.kasa_plug_kitchen
state: "on" | "off"
attributes:
  friendly_name: "Kitchen Kasa Plug"
  device_class: "outlet"
```

**Available Services:**
| Service | Description | Parameters |
|---------|-------------|------------|
| `turn_on` | Turn device on | `brightness` (for dimmers) |
| `turn_off` | Turn device off | none |
| `toggle` | Flip state | none |

#### Light Entities (Bulbs, Strips, Dimmer Switches)
```yaml
entity_id: light.kasa_bulb_living_room
state: "on" | "off"
attributes:
  friendly_name: "Living Room Kasa Bulb"
  supported_color_modes: ["brightness", "color_temp", "hs"]
  brightness: 255
  color_mode: "hs"
  hs_color: [30.5, 100.0]
  min_mireds: 153
  max_mireds: 500
```

**Available Services:**
| Service | Description | Parameters |
|---------|-------------|------------|
| `turn_on` | Turn light on | `brightness`, `color_name`, `color_temp`, `hs_color`, `transition` |
| `turn_off` | Turn light off | `transition` |
| `toggle` | Flip state | - |
| `tplink.random_effect` | Random light effect | See docs (strips only) |
| `tplink.sequence_effect` | Sequence light effect | See docs (strips only) |

#### Sensor Entities (Energy Monitoring, Hub Sensors)
```yaml
entity_id: sensor.kasa_plug_energy_current
state: "0.45"
attributes:
  friendly_name: "Kitchen Plug Current"
  unit_of_measurement: "A"

energy_today: "2.34 kWh"
energy_total: "156.78 kWh"
voltage: "121.3 V"
power: "54.6 W"
```

### Kasa-Specific HA Services

The TP-Link integration exposes additional services:

```yaml
# Random light effect (light strips)
service: tplink.random_effect
target:
  entity_id: light.kasa_strip
data:
  brightness: 90
  transition: 2000
  hue_range: [340, 360]
  # ... more parameters

# Sequence light effect (light strips)
service: tplink.sequence_effect
target:
  entity_id: light.kasa_strip
data:
  sequence:
    - [340, 20, 50]
    - [20, 50, 50]
  brightness: 80
  transition: 2000
```

### Setup in Home Assistant

1. **Device Provisioning** - Add Kasa device to the Kasa app first
2. **Add Integration:**
   ```
   Settings → Devices & services → Add Integration → TP-Link Smart Home
   ```
3. **Configuration:**
   - Host (hostname/IP address)
   - Username (TP-Link cloud email, required for newer devices)
   - Password (TP-Link cloud password, required for newer devices)
4. **Auto-discovery** works for devices on same subnet

### Known Limitations

| Limitation | Impact |
|------------|--------|
| Different subnet | Auto-discovery doesn't work - must add by IP |
| Light effects | Not supported on Kasa bulbs (only strips) |
| Power strip child plugs | Energy monitoring updates every 60 seconds |
| Newer devices | Require cloud credentials for local auth |

### Example Entity Names (Kasa)

| Physical Device | HA Entity ID | Type |
|-----------------|--------------|------|
| Living Room Kasa Plug | `switch.living_room_plug` | Switch |
| Kitchen Strip Outlet 1 | `switch.kitchen_strip_outlet_1` | Switch |
| Kitchen Strip Outlet 2 | `switch.kitchen_strip_outlet_2` | Switch |
| Bedroom Bulb | `light.bedroom_bulb` | Light |
| Living Room Strip | `light.living_room_strip` | Light |
| Office Strip Power | `sensor.office_strip_power` | Sensor |
| Kitchen Plug Energy Today | `sensor.kitchen_plug_energy_today` | Sensor |

---

## Phase 1: Core Connection Layer

### 1.1 WebSocket Client (Recommended)

WebSocket is preferred over REST for real-time state updates and lower latency.

**File:** `/tools/home_assistant/websocket_client.py`

```python
"""
Home Assistant WebSocket Client for Mage
Provides bidirectional, real-time communication with Home Assistant.
"""

import websockets
import json
import asyncio
from typing import Optional, Dict, Any, Callable, List

class HomeAssistantWSClient:
    """WebSocket client for Home Assistant API."""
    
    def __init__(self, url: str, token: str):
        """
        Initialize the WebSocket client.
        
        Args:
            url: WebSocket URL (e.g., ws://192.168.1.100:8123/api/websocket)
            token: Home Assistant long-lived access token
        """
        self.url = url
        self.token = token
        self.id_counter = 1
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self.subscriptions: Dict[int, List[Callable]] = {}
        self.event_handlers: Dict[str, List[Callable]] = {}
    
    async def connect(self) -> bool:
        """
        Connect to Home Assistant WebSocket API.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.ws = await websockets.connect(self.url)
            
            # Handle auth_required
            msg = await self.ws.recv()
            auth_msg = json.loads(msg)
            
            if auth_msg.get("type") != "auth_required":
                raise Exception(f"Expected auth_required, got: {auth_msg}")
            
            # Send auth
            await self.ws.send(json.dumps({
                "type": "auth",
                "access_token": self.token
            }))
            
            # Verify auth_ok
            response = await self.ws.recv()
            response_data = json.loads(response)
            
            if response_data.get("type") != "auth_ok":
                raise Exception(f"Authentication failed: {response_data}")
            
            self.connected = True
            
            # Start event listener
            asyncio.create_task(self._listen_for_messages())
            
            return True
            
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            self.connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from Home Assistant."""
        if self.ws:
            await self.ws.close()
            self.connected = False
    
    async def _listen_for_messages(self):
        """Background task to listen for incoming messages."""
        while self.connected and self.ws:
            try:
                message = await self.ws.recv()
                data = json.loads(message)
                msg_type = data.get("type")
                
                # Handle event messages
                if msg_type == "event":
                    subscription_id = data.get("id")
                    event = data.get("event", {})
                    
                    # Call subscription callbacks
                    if subscription_id in self.subscriptions:
                        for callback in self.subscriptions[subscription_id]:
                            await callback(event)
                
                # Handle result messages (responses to commands)
                # These are handled by the request methods
            
            except websockets.exceptions.ConnectionClosed:
                self.connected = False
                break
            except Exception as e:
                print(f"Error in message listener: {e}")
    
    async def _send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a command and wait for response.
        
        Args:
            command: Command dictionary with 'type' and other required fields
            
        Returns:
            Response dictionary
        """
        if not self.connected:
            raise Exception("Not connected to Home Assistant")
        
        msg_id = self.id_counter
        self.id_counter += 1
        
        command["id"] = msg_id
        await self.ws.send(json.dumps(command))
        
        # Wait for response with matching ID
        # (In production, use a proper response queue)
        while True:
            response = await self.ws.recv()
            response_data = json.loads(response)
            if response_data.get("id") == msg_id:
                return response_data
    
    async def get_states(self) -> List[Dict[str, Any]]:
        """
        Get all entity states from Home Assistant.
        
        Returns:
            List of entity state dictionaries
        """
        response = await self._send_command({"type": "get_states"})
        if response.get("success"):
            return response.get("result", [])
        raise Exception(f"Failed to get states: {response}")
    
    async def get_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Get state of a specific entity.
        
        Args:
            entity_id: Entity ID (e.g., 'light.bedroom_bulb')
            
        Returns:
            Entity state dictionary or None if not found
        """
        states = await self.get_states()
        for state in states:
            if state.get("entity_id") == entity_id:
                return state
        return None
    
    async def call_service(
        self, 
        domain: str, 
        service: str, 
        service_data: Dict[str, Any] = None,
        target: Dict[str, Any] = None,
        return_response: bool = False
    ) -> Dict[str, Any]:
        """
        Call a Home Assistant service.
        
        Args:
            domain: Service domain (e.g., 'light', 'switch')
            service: Service name (e.g., 'turn_on', 'turn_off')
            service_data: Service parameters
            target: Target specification (e.g., {'entity_id': 'light.bedroom'})
            return_response: Whether to request response data
            
        Returns:
            Response dictionary
        """
        command = {
            "type": "call_service",
            "domain": domain,
            "service": service
        }
        
        if service_data:
            command["service_data"] = service_data
        
        if target:
            command["target"] = target
        
        if return_response:
            command["return_response"] = True
        
        response = await self._send_command(command)
        
        if response.get("success"):
            return response.get("result", {})
        raise Exception(f"Service call failed: {response}")
    
    async def subscribe_events(
        self, 
        event_type: str = "state_changed",
        callback: Callable = None
    ) -> int:
        """
        Subscribe to Home Assistant events.
        
        Args:
            event_type: Type of event to subscribe to
            callback: Callback function to call when event occurs
            
        Returns:
            Subscription ID
        """
        response = await self._send_command({
            "type": "subscribe_events",
            "event_type": event_type
        })
        
        if response.get("success"):
            sub_id = response.get("id")
            if callback:
                if sub_id not in self.subscriptions:
                    self.subscriptions[sub_id] = []
                self.subscriptions[sub_id].append(callback)
            return sub_id
        
        raise Exception(f"Failed to subscribe to events: {response}")
    
    async def unsubscribe_events(self, subscription_id: int):
        """
        Unsubscribe from events.
        
        Args:
            subscription_id: Subscription ID returned by subscribe_events
        """
        await self._send_command({
            "type": "unsubscribe_events",
            "subscription": subscription_id
        })
        
        if subscription_id in self.subscriptions:
            del self.subscriptions[subscription_id]
```

### 1.2 REST Fallback Client

For compatibility and fallback scenarios:

**File:** `/tools/home_assistant/rest_client.py`

```python
"""
Home Assistant REST Client for Mage
Provides HTTP-based communication with Home Assistant API.
Used as fallback when WebSocket is unavailable.
"""

import requests
from typing import Dict, Any, List, Optional

class HomeAssistantRESTClient:
    """REST client for Home Assistant API."""
    
    def __init__(self, base_url: str, token: str):
        """
        Initialize the REST client.
        
        Args:
            base_url: Base URL (e.g., 'http://192.168.1.100:8123')
            token: Home Assistant long-lived access token
        """
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    def get_states(self) -> List[Dict[str, Any]]:
        """Get all entity states."""
        response = requests.get(
            f"{self.base_url}/api/states",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()
    
    def get_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get state of a specific entity."""
        response = requests.get(
            f"{self.base_url}/api/states/{entity_id}",
            headers=self.headers
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    
    def call_service(
        self,
        domain: str,
        service: str,
        service_data: Dict[str, Any] = None,
        target: Dict[str, Any] = None,
        return_response: bool = False
    ) -> Dict[str, Any]:
        """Call a Home Assistant service."""
        url = f"{self.base_url}/api/services/{domain}/{service}"
        
        if return_response:
            url += "?return_response"
        
        payload = {}
        if service_data:
            payload = service_data
        if target:
            payload.update(target)
        
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_config(self) -> Dict[str, Any]:
        """Get Home Assistant configuration."""
        response = requests.get(
            f"{self.base_url}/api/config",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()
    
    def get_services(self) -> Dict[str, Any]:
        """Get all available services."""
        response = requests.get(
            f"{self.base_url}/api/services",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()
```

### 1.3 Client Factory

**File:** `/tools/home_assistant/client_factory.py`

```python
"""
Factory for creating Home Assistant clients.
Automatically chooses WebSocket for real-time, falls back to REST.
"""

from typing import Optional
from .websocket_client import HomeAssistantWSClient
from .rest_client import HomeAssistantRESTClient

def create_ha_client(
    host: str,
    port: int,
    token: str,
    use_websocket: bool = True
) -> Optional[object]:
    """
    Create a Home Assistant client.
    
    Args:
        host: Home Assistant hostname or IP
        port: Home Assistant port (usually 8123)
        token: Long-lived access token
        use_websocket: Prefer WebSocket if True
        
    Returns:
        HA client instance (WSClient or RESTClient)
    """
    if use_websocket:
        ws_url = f"ws://{host}:{port}/api/websocket"
        client = HomeAssistantWSClient(ws_url, token)
        # Note: In async context, need to await connect()
        return client
    
    rest_url = f"http://{host}:{port}"
    return HomeAssistantRESTClient(rest_url, token)

# Singleton pattern for the active client
_active_ha_client = None

def get_ha_client():
    """Get the active Home Assistant client."""
    global _active_ha_client
    return _active_ha_client

def set_ha_client(client):
    """Set the active Home Assistant client."""
    global _active_ha_client
    _active_ha_client = client
```

---

## Phase 2: Mage Tool Functions

### 2.1 Entity Query Tool

**Tool Name:** `ha_query_states`

```python
"""
Mage Tool: Query Home Assistant Entity States
"""

from typing import List, Dict, Any, Optional
from .client_factory import get_ha_client

def ha_query_states(
    category: str = None,
    room: str = None,
    entity_id: str = None,
    state: str = None,
    attribute_filter: Dict[str, Any] = None
) -> List[Dict[str, Any]]:
    """
    Query Home Assistant entities with flexible filtering.
    
    Args:
        category: Filter by entity domain (light, switch, sensor, etc.)
        room: Filter by area/room from attributes
        entity_id: Specific entity ID to query
        state: Filter by current state value
        attribute_filter: Dict of attribute key-value pairs to match
        
    Returns:
        List of matching entity state dictionaries
        
    Examples:
        >>> ha_query_states(category="light")
        Returns all lights
        
        >>> ha_query_states(room="kitchen")
        Returns all devices in kitchen area
        
        >>> ha_query_states(entity_id="switch.kasa_plug")
        Returns specific plug state
        
        >>> ha_query_states(state="on", category="light")
        Returns all lights that are currently on
    """
    client = get_ha_client()
    if not client:
        return {"error": "No Home Assistant client configured"}
    
    # Get all states
    if entity_id:
        entity = client.get_state(entity_id)
        return [entity] if entity else []
    
    all_states = client.get_states()
    results = []
    
    for state in all_states:
        entity_id = state.get("entity_id", "")
        domain = entity_id.split(".")[0] if "." in entity_id else entity_id
        attributes = state.get("attributes", {})
        
        # Category filter (domain)
        if category and domain != category.lower():
            continue
            
        # Room/Area filter
        if room:
            room_attr = (attributes.get("room") or 
                        attributes.get("area") or
                        attributes.get("friendly_name", "").lower())
            if room.lower() not in room_attr.lower():
                continue
            
        # State filter
        if state and state.get("state") != state:
            continue
            
        # Attribute filter
        if attribute_filter:
            match = True
            for key, value in attribute_filter.items():
                if attributes.get(key) != value:
                    match = False
                    break
            if not match:
                continue
        
        results.append(state)
    
    return results
```

### 2.2 Service Call Tool

**Tool Name:** `ha_call_service`

```python
"""
Mage Tool: Execute Home Assistant Services
"""

from typing import Dict, Any, Optional

def ha_call_service(
    domain: str,
    service: str,
    entity_id: str = None,
    device_id: str = None,
    area_id: str = None,
    service_data: Dict[str, Any] = None,
    require_approval: bool = None,
    reason: str = None
) -> Dict[str, Any]:
    """
    Execute a Home Assistant service with permission checking.
    
    Args:
        domain: Service domain (light, switch, switch, automation, etc.)
        service: Service name (turn_on, turn_off, toggle, etc.)
        entity_id: Target entity ID
        device_id: Target device ID
        area_id: Target area ID
        service_data: Additional service parameters
        require_approval: Override default permission setting
        reason: Human-readable reason for the action (for audit log)
        
    Returns:
        Service execution result
        
    Examples:
        >>> ha_call_service("light", "turn_on", entity_id="light.bedroom_bulb")
        Turn on bedroom light
        
        >>> ha_call_service("switch", "turn_off", entity_id="switch.kasa_plug")
        Turn off Kasa plug
        
        >>> ha_call_service(
        ...     "light", "turn_on",
        ...     entity_id="light.kasa_bulb",
        ...     service_data={"brightness": 200, "color_name": "red"}
        ... )
        Turn on Kasa bulb at specific brightness and color
    """
    from .client_factory import get_ha_client
    from .permissions import PermissionEngine
    
    client = get_ha_client()
    if not client:
        return {"success": False, "error": "No Home Assistant client configured"}
    
    permissions = PermissionEngine()
    
    # Build target
    target = {}
    if entity_id:
        target["entity_id"] = entity_id
    if device_id:
        target["device_id"] = device_id
    if area_id:
        target["area_id"] = area_id
    
    # Determine if approval needed
    can_execute, needs_approval = permissions.can_execute(
        domain, service, entity_id, require_approval
    )
    
    if not can_execute:
        return {
            "success": False,
            "error": f"Permission denied: cannot execute {domain}.{service}"
        }
    
    if needs_approval:
        approved = permissions.request_approval({
            "action": f"{domain}.{service}",
            "target": target,
            "service_data": service_data,
            "reason": reason
        })
        
        if not approved:
            return {
                "success": False,
                "error": "Action requires approval and was not approved"
            }
    
    # Execute service
    try:
        result = client.call_service(
            domain=domain,
            service=service,
            service_data=service_data,
            target=target
        )
        
        # Log action
        from .audit import log_ha_action
        log_ha_action({
            "domain": domain,
            "service": service,
            "target": target,
            "service_data": service_data,
            "reason": reason,
            "approved_by": "user" if needs_approval else "auto",
            "result": result
        })
        
        return {
            "success": True,
            "result": result,
            "message": f"Successfully executed {domain}.{service}"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
```

### 2.3 Natural Language Controller

**Tool Name:** `ha_natural_command`

```python
"""
Mage Tool: Natural Language Home Assistant Control
"""

from typing import Dict, Any

def ha_natural_command(query: str, context: Dict[str, Any] = None) -> str:
    """
    Parse natural language and execute Home Assistant commands.
    
    Args:
        query: Natural language command
        context: Additional context (time, user, location, etc.)
        
    Returns:
        Human-readable response
        
    Examples:
        >>> ha_natural_command("Turn on the kitchen lights")
        "Done! Turned on 2 lights in the kitchen."
        
        >>> ha_natural_command("What's the temperature in the bedroom?")
        "The bedroom temperature is 22.5°C"
        
        >>> ha_natural_command("Set the living room light to blue")
        "Done! Living room light is now blue."
    """
    # This would use LLM to parse intent
    # For now, we'll outline the structure
    
    parsed_intent = parse_ha_intent(query)
    
    # Intent structure:
    # {
    #     "action": "turn_on",  # or query, toggle, set, etc.
    #     "domain": "light",
    #     "service": "turn_on",
    #     "entities": ["light.kitchen_main", "light.kitchen_under_cabinet"],
    #     "parameters": {"brightness": 255, "color_name": "warm white"},
    #     "room": "kitchen",
    #     "confidence": 0.95
    # }
    
    if not parsed_intent:
        return "I couldn't understand that command. Please try rephrasing."
    
    # Handle queries vs actions
    if parsed_intent.get("action") == "query":
        return handle_query(parsed_intent)
    
    # Handle actions
    return handle_action(parsed_intent)

def parse_ha_intent(query: str) -> Dict[str, Any]:
    """
    Parse natural language into structured HA intent.
    
    Uses LLM to extract:
    - Intent type (control, query, automation creation)
    - Domain (light, switch, sensor, etc.)
    - Service (turn_on, turn_off, etc.)
    - Entities (matched by name/room)
    - Parameters (brightness, color, temperature, etc.)
    """
    # Implementation would use LLM
    # Placeholder structure
    return {
        "action": "control",
        "domain": "light",
        "service": "turn_on",
        "entities": ["light.kitchen_main"],
        "parameters": {}
    }

def handle_action(intent: Dict[str, Any]) -> str:
    """Execute a control action intent."""
    from .ha_call_service import ha_call_service
    
    results = []
    success_count = 0
    
    for entity_id in intent.get("entities", []):
        result = ha_call_service(
            domain=intent["domain"],
            service=intent["service"],
            entity_id=entity_id,
            service_data=intent.get("parameters")
        )
        
        if result.get("success"):
            success_count += 1
            results.append(f"✓ {entity_id}")
        else:
            results.append(f"✗ {entity_id}: {result.get('error')}")
    
    total = len(intent.get("entities", []))
    if success_count == total:
        return f"Done! {' '.join(results)}"
    else:
        return f"Partial success ({success_count}/{total}): {' '.join(results)}"

def handle_query(intent: Dict[str, Any]) -> str:
    """Handle a query intent."""
    from .ha_query_states import ha_query_states
    
    entity_id = intent.get("entities", [None])[0]
    results = ha_query_states(entity_id=entity_id)
    
    if not results:
        return "No matching entities found."
    
    # Format results for human reading
    response_parts = []
    for result in results:
        entity_id = result.get("entity_id", "")
        state = result.get("state", "")
        attrs = result.get("attributes", {})
        friendly = attrs.get("friendly_name", entity_id)
        unit = attrs.get("unit_of_measurement", "")
        response_parts.append(f"{friendly}: {state}{unit}")
    
    return "\n".join(response_parts)
```

### 2.4 State Subscription Tool

**Tool Name:** `ha_subscribe_events`

```python
"""
Mage Tool: Subscribe to Home Assistant Events
"""

import asyncio
from typing import Callable, Optional

async def ha_subscribe_events(
    entity_id: str = None,
    event_type: str = "state_changed",
    callback: Callable = None,
    duration_seconds: int = None
):
    """
    Subscribe to Home Assistant events for real-time monitoring.
    
    Args:
        entity_id: Filter events to specific entity
        event_type: Event type to subscribe to (default: state_changed)
        callback: Async function to call on each event
        duration_seconds: Auto-unsubscribe after this duration
        
    Examples:
        >>> # Monitor a light for changes
        >>> async def on_change(event):
        ...     print(f"Changed: {event}")
        >>> await ha_subscribe_events(
        ...     entity_id="light.kitchen",
        ...     callback=on_change
        ... )
        
        >>> # Monitor all state changes for 60 seconds
        >>> await ha_subscribe_events(duration_seconds=60)
    """
    from .client_factory import get_ha_client
    
    client = get_ha_client()
    if not client or not hasattr(client, 'subscribe_events'):
        print("No Home Assistant client or client doesn't support subscriptions")
        return
    
    # Subscribe
    subscription_id = await client.subscribe_events(
        event_type=event_type,
        callback=callback
    )
    
    print(f"Subscribed to {event_type} events (ID: {subscription_id})")
    
    # Auto-unsubscribe
    if duration_seconds:
        await asyncio.sleep(duration_seconds)
        await client.unsubscribe_events(subscription_id)
        print(f"Unsubscribed from {subscription_id}")
```

### 2.5 Tool Summary

| Tool | Description | Primary Use |
|------|-------------|-------------|
| `ha_query_states` | Query entity states with filters | Read device states |
| `ha_call_service` | Execute services with permission check | Control devices |
| `ha_natural_command` | Natural language HA control | Conversational interface |
| `ha_subscribe_events` | Real-time event monitoring | Detect state changes |

---

## Phase 3: User Permission System

### 3.1 Permission Configuration File

**File:** `/config/home_assistant_permissions.yaml`

```yaml
# Home Assistant Permission Configuration for Mage
# Defines what the AI can and cannot do with your devices

# Entity-level permissions (wildcards supported)
entities:
  # Kasa plugs - full control, no approval needed
  "switch.kasa_*":
    read: true
    write: true
    require_approval: false
    description: "Kasa smart plugs"
  
  # Light entities - can read and write
  "light.*":
    read: true
    write: true
    require_approval: false
    description: "All lights"
  
  # Camera entities - read only (can view, not control)
  "camera.*":
    read: true
    write: false
    require_approval: true
    description: "Cameras (view only)"
  
  # Lock entities - always require approval
  "lock.*":
    read: true
    write: true
    require_approval: true
    description: "Smart locks"
  
  # Alarm system - extra restrictions
  "alarm_control_panel.*":
    read: true
    write: true
    require_approval: true
    description: "Alarm system"

# Domain-level permissions for services
domains:
  light:
    description: "Lighting control"
    services:
      turn_on:
        require_approval: false
        allow_params: ["brightness", "color_name", "color_temp", "transition"]
      turn_off:
        require_approval: false
        allow_params: ["transition"]
      toggle:
        require_approval: false
  
  switch:
    description: "Switch control"
    services:
      turn_on:
        require_approval: false
      turn_off:
        require_approval: false
      toggle:
        require_approval: false
  
  automation:
    description: "Automations"
    services:
      trigger:
        require_approval: true
      turn_on:
        require_approval: true
      turn_off:
        require_approval: true
  
  climate:
    description: "Thermostat/Climate control"
    services:
      set_temperature:
        require_approval: false
        allow_params: ["temperature"]
        # Safety: reject extreme temperature changes
        param_limits:
          temperature:
            min: 55
            max: 85
            max_delta: 5  # Max change from current
  
  sensor:
    description: "Sensors (read only)"
    read_only: true
    can_write: false

# Global safety settings
global_settings:
  # Always require approval for these domain actions
  require_approval_for:
    - domain: alarm_control_panel
      service: "*"
    - domain: lock
      service: "*"
    - domain: camera
      service: "*"
    - domain: automation
      service: trigger
  
  # Auto-approve these (consider safe)
  auto_approve:
    - domain: light
      service: turn_on
    - domain: light
      service: turn_off
    - domain: switch
      service: turn_on
    - domain: switch
      service: turn_off
    - queries_only  # All read-only operations
  
  # Rate limiting to prevent rapid repeated actions
  rate_limits:
    default:
      max_per_minute: 10
    light:
      max_per_minute: 30
    switch:
      max_per_minute: 20
  
  # Audit logging settings
  audit:
    log_all_actions: true
    log_queries: false
    retention_days: 90

# Approval queue settings
approval:
  # How long to wait for approval before timing out (seconds)
  timeout_seconds: 60
  
  # Maximum pending approvals
  max_pending: 5
  
  # Approval methods (in order of preference)
  methods:
    - slack        # Request via Slack
    - web_ui       # Show in web dashboard
    - console      # Command-line prompt
```

### 3.2 Permission Engine

**File:** `/tools/home_assistant/permissions.py`

```python
"""
Permission Engine for Home Assistant Integration
Provides permission checking, approval requests, and safety validation.
"""

import yaml
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta

class PermissionEngine:
    """
    Manages permissions for Home Assistant actions.
    Reads config from permissions.yaml and evaluates each action.
    """
    
    def __init__(self, config_path: str = "/config/home_assistant_permissions.yaml"):
        self.config = self._load_config(config_path)
        self.approval_queue: List[Dict] = []
        self.rate_limit_tracker: Dict[str, List[datetime]] = {}
    
    def _load_config(self, path: str) -> Dict[str, Any]:
        """Load permission configuration from YAML file."""
        try:
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            # Return default config if file not found
            return self._default_config()
    
    def _default_config(self) -> Dict[str, Any]:
        """Return default conservative permissions."""
        return {
            "entities": {
                "light.*": {"read": True, "write": True, "require_approval": False},
                "switch.*": {"read": True, "write": True, "require_approval": False},
                "sensor.*": {"read": True, "write": False},
                "*.default": {"read": True, "write": True, "require_approval": True}
            },
            "domains": {},
            "global_settings": {
                "require_approval_for": [],
                "rate_limits": {"default": {"max_per_minute": 10}}
            }
        }
    
    def can_read(self, entity_id: str) -> bool:
        """
        Check if AI can read entity state.
        
        Args:
            entity_id: Entity ID (e.g., 'light.bedroom_bulb')
            
        Returns:
            True if reading is allowed
        """
        entity_rule = self._find_entity_rule(entity_id)
        if entity_rule:
            return entity_rule.get("read", False)
        
        # Default: can read unless explicitly denied
        domain = entity_id.split(".")[0]
        domain_config = self.config.get("domains", {}).get(domain, {})
        if domain_config.get("read_only") or not domain_config.get("can_write", True):
            return domain_config.get("read_only", False)
        
        return True  # Default allow
    
    def can_execute(
        self,
        domain: str,
        service: str,
        entity_id: str = None,
        require_approval: bool = None
    ) -> Tuple[bool, bool]:
        """
        Check if AI can execute a service.
        
        Args:
            domain: Service domain (light, switch, etc.)
            service: Service name (turn_on, turn_off, etc.)
            entity_id: Target entity ID
            require_approval: Override default approval setting
            
        Returns:
            Tuple of (allowed: bool, needs_approval: bool)
        """
        # Check entity-specific rules first
        if entity_id:
            entity_rule = self._find_entity_rule(entity_id)
            if entity_rule:
                if not entity_rule.get("write", True):
                    return False, False
                need_approval = entity_rule.get("require_approval", False)
                if require_approval is None:
                    return True, need_approval
        
        # Check domain/service rules
        domain_config = self.config.get("domains", {}).get(domain, {})
        service_config = domain_config.get("services", {}).get(service, {})
        
        need_approval = require_approval or service_config.get("require_approval", False)
        
        # Check global requirements
        for req in self.config.get("global_settings", {}).get("require_approval_for", []):
            if req.get("domain") == domain and req.get("service") in ["*", service]:
                need_approval = True
        
        # Check rate limits
        action_key = f"{domain}.{service}"
        if not self._check_rate_limit(action_key):
            return False, True
        
        return True, need_approval
    
    def _find_entity_rule(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Find matching entity rule, supporting wildcards."""
        entity_rules = self.config.get("entities", {})
        
        # Direct match
        if entity_id in entity_rules:
            return entity_rules[entity_id]
        
        # Wildcard match
        domain = entity_id.split(".")[0]
        wildcard_key = f"{domain}.*"
        if wildcard_key in entity_rules:
            return entity_rules[wildcard_key]
        
        # Default wildcard
        if "*.*" in entity_rules or "*.default" in entity_rules:
            return entity_rules.get("*.*") or entity_rules.get("*.default")
        
        return None
    
    def _check_rate_limit(self, action_key: str) -> bool:
        """
        Check if action respects rate limits.
        
        Args:
            action_key: Action identifier (e.g., 'light.turn_on')
            
        Returns:
            True if action is allowed under rate limits
        """
        rate_limits = self.config.get("global_settings", {}).get("rate_limits", {})
        
        # Get limit for this action
        limit = rate_limits.get(action_key, rate_limits.get("default", {"max_per_minute": 10}))
        max_per_minute = limit.get("max_per_minute", 10)
        
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        # Clean old entries
        if action_key in self.rate_limit_tracker:
            self.rate_limit_tracker[action_key] = [
                t for t in self.rate_limit_tracker[action_key] if t > minute_ago
            ]
        else:
            self.rate_limit_tracker[action_key] = []
        
        # Check limit
        if len(self.rate_limit_tracker[action_key]) >= max_per_minute:
            return False
        
        # Record this action
        self.rate_limit_tracker[action_key].append(now)
        return True
    
    def request_approval(self, action: Dict[str, Any]) -> bool:
        """
        Request user approval for a pending action.
        
        Args:
            action: Action specification
            
        Returns:
            True if approved, False if denied or timed out
        """
        # Add to approval queue
        action["requested_at"] = datetime.now().isoformat()
        action["status"] = "pending"
        self.approval_queue.append(action)
        
        # In production, this would:
        # 1. Send notification via app/Slack/UI
        # 2. Wait for response (blocking or async)
        # 3. Timeout if no response
        
        # Placeholder: auto-approve for non-critical, deny for critical
        approval_settings = self.config.get("approval", {})
        
        # Check auto-approve settings
        for auto_rule in self.config.get("global_settings", {}).get("auto_approve", []):
            domain = auto_rule.get("domain")
            service = auto_rule.get("service")
            
            if (action.get("domain") == domain and 
                action.get("action") == service and
                auto_rule != "queries_only"):
                action["status"] = "approved"
                action["approved_by"] = "auto-policy"
                return True
        
        # Critical actions require explicit approval
        action["status"] = "requires_user_approval"
        
        # Send notification (placeholder)
        print(f"[PENDING APPROVAL] {action}")
        
        # In production, block and wait for response
        # For now, return False (require explicit user action)
        return False
    
    def approve_action(self, action_id: int, approved_by: str = "user") -> bool:
        """
        Approve a pending action.
        
        Args:
            action_id: Index of action in approval queue
            approved_by: Who approved the action
            
        Returns:
            True if approval was successful
        """
        if action_id < len(self.approval_queue):
            self.approval_queue[action_id]["status"] = "approved"
            self.approval_queue[action_id]["approved_by"] = approved_by
            self.approval_queue[action_id]["approved_at"] = datetime.now().isoformat()
            return True
        return False
    
    def deny_action(self, action_id: int, denied_by: str = "user") -> bool:
        """Deny a pending action."""
        if action_id < len(self.approval_queue):
            self.approval_queue[action_id]["status"] = "denied"
            self.approval_queue[action_id]["denied_by"] = denied_by
            self.approval_queue[action_id]["denied_at"] = datetime.now().isoformat()
            return True
        return False
    
    def validate_service_parameters(
        self,
        domain: str,
        service: str,
        service_data: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate service parameters against safety limits.
        
        Args:
            domain: Service domain
            service: Service name
            service_data: Parameters to validate
            
        Returns:
            Tuple of (valid: bool, error_message: Optional[str])
        """
        domain_config = self.config.get("domains", {}).get(domain, {})
        service_config = domain_config.get("services", {}).get(service, {})
        
        # Check allowed parameters
        allowed_params = service_config.get("allow_params")
        if allowed_params:
            for param in service_data.keys():
                if param not in allowed_params:
                    return False, f"Parameter '{param}' is not allowed"
        
        # Check parameter limits
        param_limits = service_config.get("param_limits", {})
        for param, limits in param_limits.items():
            if param in service_data:
                value = service_data[param]
                
                if "min" in limits and value < limits["min"]:
                    return False, f"{param} below minimum of {limits['min']}"
                
                if "max" in limits and value > limits["max"]:
                    return False, f"{param} above maximum of {limits['max']}"
                
                # Max delta from current (would need to fetch current state)
                if "max_delta" in limits:
                    # Placeholder: would need current state comparison
                    pass
        
        return True, None
```

### 3.3 Audit Logging

**File:** `/tools/home_assistant/audit.py`

```python
"""
Audit Logging for Home Assistant Actions
Logs all AI-initiated actions for accountability and debugging.
"""

import json
from datetime import datetime
from typing import Dict, Any
from pathlib import Path

def log_ha_action(action: Dict[str, Any], result: Dict[str, Any] = None):
    """
    Log a Home Assistant action to the audit log.
    
    Args:
        action: Action specification
        result: Execution result
        
    Example action format:
        {
            "domain": "light",
            "service": "turn_on",
            "target": {"entity_id": "light.bedroom"},
            "service_data": {"brightness": 200},
            "reason": "User requested turning on bedroom light",
            "source": "ha_natural_command"
        }
    """
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "result": result,
        "session_id": getattr(log_ha_action, "session_id", "unknown")
    }
    
    # Determine log file
    log_dir = Path("/logs/home_assistant")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Use date-based log file
    log_file = log_dir / f"actions_{datetime.now().strftime('%Y%m%d')}.jsonl"
    
    # Append to log
    with open(log_file, 'a') as f:
        f.write(json.dumps(log_entry) + "\n")

def set_audit_session(session_id: str):
    """Set the current audit session ID."""
    log_ha_action.session_id = session_id

def get_audit_logs(
    start_date: str = None,
    end_date: str = None,
    entity_id: str = None,
    limit: int = 100
) -> list:
    """
    Retrieve audit log entries.
    
    Args:
        start_date: Start date (YYYYMMDD format)
        end_date: End date (YYYYMMDD format)
        entity_id: Filter by entity ID
        limit: Maximum number of entries to return
        
    Returns:
        List of log entries
    """
    log_dir = Path("/logs/home_assistant")
    entries = []
    
    # Scan log files
    for log_file in sorted(log_dir.glob("actions_*.jsonl")):
        file_date = log_file.stem.split("_")[1]
        
        # Date filtering
        if start_date and file_date < start_date:
            continue
        if end_date and file_date > end_date:
            continue
        
        # Read entries
        with open(log_file, 'r') as f:
            for line in f:
                if len(entries) >= limit:
                    break
                entry = json.loads(line.strip())
                
                # Entity filtering
                if entity_id:
                    target = entry.get("action", {}).get("target", {})
                    if target.get("entity_id") != entity_id:
                        continue
                
                entries.append(entry)
        
        if len(entries) >= limit:
            break
    
    return entries
```

---

## Phase 4: Kasa-Specific Integration

### 4.1 Kasa Entity Recognizer

**File:** `/tools/home_assistant/kasa_tools.py`

```python
"""
Kasa-specific tools and helpers for Mage Integration.
"""

from typing import Dict, Any, List, Optional

# Kasa device patterns for entity name recognition
KASA_PATTERNS = {
    "plugs": ["plug", "outlet", "kp", "hs", "ep", "power"],
    "bulbs": ["bulb", "kl", "light", "lamp"],
    "strips": ["strip", "multi", "hs300", "kp400"],
    "switches": ["switch", "wall", "ks", "es"],
    "strips_light": ["strip", "light", "kl", "lightstrip"]
}

def recognize_kasa_entity(entity_id: str, attributes: Dict[str, Any]) -> str:
    """
    Recognize Kasa device type from entity ID and attributes.
    
    Args:
        entity_id: Home Assistant entity ID
        attributes: Entity attributes
        
    Returns:
        Device type: 'plug', 'bulb', 'strip', 'switch', 'strip_light', or 'unknown'
    """
    entity_lower = entity_id.lower()
    friendly_name = attributes.get("friendly_name", "").lower()
    
    combined = entity_lower + " " + friendly_name
    
    for device_type, patterns in KASA_PATTERNS.items():
        if any(p in combined for p in patterns):
            # Further disambiguate plug vs strip
            if device_type == "plugs" and "strip" in combined:
                return "strip"
            return device_type
    
    # Check supported features
    supported_features = attributes.get("supported_features", 0)
    
    # Light features suggest bulb or strip_light
    if attributes.get("supported_color_modes"):
        if "strip" in combined:
            return "strip_light"
        return "bulb"
    
    return "light" if "light" in entity_lower else "switch"

def get_kasa_capabilities(entity_id: str, attributes: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get capabilities of a Kasa device.
    
    Args:
        entity_id: Entity ID
        attributes: Entity attributes
        
    Returns:
        Dictionary of device capabilities
    """
    device_type = recognize_kasa_entity(entity_id, attributes)
    
    capabilities = {
        "device_type": device_type,
        "has_energy_monitoring": False,
        "has_brightness": False,
        "has_color": False,
        "has_color_temp": False,
        "has_effects": False,
        "is_dimmable": False
    }
    
    # Check for energy monitoring sensors (common for newer plugs)
    friendly_name = attributes.get("friendly_name", "")
    if "voltage" in attributes or "current" in attributes or "power" in attributes:
        capabilities["has_energy_monitoring"] = True
        capabilities["has_power"] = True
    
    # Light capabilities
    color_modes = attributes.get("supported_color_modes", [])
    
    if brightness in attributes or "brightness" in color_modes:
        capabilities["has_brightness"] = True
        capabilities["is_dimmable"] = True
    
    if "color_temp" in color_modes or "color_temp" in attributes:
        capabilities["has_color_temp"] = True
    
    if "hs" in color_modes or "xy" in color_modes or "rgb" in color_modes:
        capabilities["has_color"] = True
    
    # Effects (light strips)
    if device_type == "strip" and attributes.get("effect_list"):
        capabilities["has_effects"] = True
    
    return capabilities

def query_kasa_entities(
    category: str = None,
    room: str = None,
    device_type: str = None
) -> List[Dict[str, Any]]:
    """
    Query only Kasa-branded entities.
    
    Args:
        category: HA entity category (light, switch, sensor)
        room: Filter by room/area
        device_type: Kasa device type (plug, bulb, strip, switch)
        
    Returns:
        List of matching Kasa entities with capabilities
    """
    from .ha_query_states import ha_query_states
    
    all_entities = ha_query_states()
    results = []
    
    for entity in all_entities:
        entity_id = entity.get("entity_id", "")
        attributes = entity.get("attributes", {})
        
        # Check if it's a Kasa device
        entity_lower = entity_id.lower() + " " + attributes.get("friendly_name", "").lower()
        is_kasa = "kasa" in entity_lower or any(
            p in entity_lower for patterns in KASA_PATTERNS.values() for p in patterns
        )
        
        if not is_kasa:
            continue
        
        # Category filter
        domain = entity_id.split(".")[0]
        if category and domain != category:
            continue
        
        # Room filter
        if room:
            room_match = (room.lower() in attributes.get("room", "").lower() or
                         room.lower() in attributes.get("area", "").lower() or
                         room.lower() in attributes.get("friendly_name", "").lower())
            if not room_match:
                continue
        
        # Device type filter
        kasa_type = recognize_kasa_entity(entity_id, attributes)
        if device_type and kasa_type != device_type:
            continue
        
        # Add capabilities
        entity["kasa_type"] = kasa_type
        entity["kasa_capabilities"] = get_kasa_capabilities(entity_id, attributes)
        
        results.append(entity)
    
    return results

def get_kasa_power_consumption(plug_entity_id: str) -> Dict[str, Any]:
    """
    Get current power consumption from a Kasa plug.
    
    Args:
        plug_entity_id: Entity ID of the plug
        
    Returns:
        Dictionary with power metrics
    """
    from .ha_query_states import ha_query_states
    
    # Look for power sensors associated with this plug
    base_name = plug_entity_id.replace("switch.", "").replace("light.", "")
    power_sensors = ha_query_states(category="sensor")
    
    power_data = {}
    
    for sensor in power_sensors:
        entity_id = sensor.get("entity_id", "")
        attributes = sensor.get("attributes", {})
        
        if base_name in entity_id.lower():
            friendly = attributes.get("friendly_name", "").lower()
            state = sensor.get("state")
            unit = attributes.get("unit_of_measurement", "")
            
            if "power" in friendly:
                power_data["current_power"] = f"{state}{unit}"
            elif "energy" in friendly and "today" in friendly:
                power_data["energy_today"] = f"{state}{unit}"
            elif "energy" in friendly and "total" in friendly:
                power_data["energy_total"] = f"{state}{unit}"
            elif "current" in friendly:
                power_data["current"] = f"{state}{unit}"
            elif "voltage" in friendly:
                power_data["voltage"] = f"{state}{unit}"
    
    return power_data if power_data else {"error": "No power data found"}
```

### 4.2 Kasa Control Tools

```python
"""
Kasa-specific control functions.
"""

def kasa_turn_on(
    device_id: str,
    brightness: int = None,
    color_name: str = None,
    color_temp: int = None
) -> Dict[str, Any]:
    """
    Turn on a Kasa device with optional parameters.
    
    Args:
        device_id: Entity ID of the Kasa device
        brightness: Brightness (0-255) for bulbs/dimmers
        color_name: Color name for color-capable bulbs
        color_temp: Color temperature for bulbs
    """
    from .ha_call_service import ha_call_service
    
    domain = "light" if device_id.startswith("light.") else "switch"
    service_data = {}
    
    if brightness is not None:
        service_data["brightness"] = brightness
    if color_name is not None:
        service_data["color_name"] = color_name
    if color_temp is not None:
        service_data["color_temp"] = color_temp
    
    return ha_call_service(
        domain=domain,
        service="turn_on",
        entity_id=device_id,
        service_data=service_data if service_data else None
    )

def kasa_effect_random(
    strip_entity_id: str,
    brightness: int = 90,
    hue_range: tuple = (0, 360),
    saturation_range: tuple = (40, 100),
    transition: int = 2000
) -> Dict[str, Any]:
    """
    Set random effect on Kasa light strip.
    """
    from .ha_call_service import ha_call_service
    
    return ha_call_service(
        domain="light",
        service="tplink.random_effect",
        entity_id=strip_entity_id,
        service_data={
            "brightness": brightness,
            "hue_range": list(hue_range),
            "saturation_range": list(saturation_range),
            "transition": transition
        }
    )

def kasa_sequence_effect(
    strip_entity_id: str,
    sequence: List[tuple],
    brightness: int = 80,
    transition: int = 2000
) -> Dict[str, Any]:
    """
    Set sequence effect on Kasa light strip.
    
    sequence: List of HSV tuples [(hue, saturation, value), ...]
    """
    from .ha_call_service import ha_call_service
    
    # Convert tuples to lists for JSON serialization
    sequence_lists = [[h, s, v] for h, s, v in sequence]
    
    return ha_call_service(
        domain="light",
        service="tplink.sequence_effect",
        entity_id=strip_entity_id,
        service_data={
            "sequence": sequence_lists,
            "brightness": brightness,
            "transition": transition
        }
    )
```

### 4.3 Kasa Natural Language Patterns

Common commands mapped to Kasa actions:

| Natural Language | Mapped Action | Parameters |
|------------------|---------------|------------|
| "Turn on the kitchen plug" | `switch.turn_on` | entity_id=switch.kitchen_plug |
| "Turn off all lights in the living room" | `light.turn_off` | area=living_room |
| "Set the bedroom light to 50%" | `light.turn_on` | entity_id=light.bedroom, brightness=128 |
| "Make the living room light warm white" | `light.turn_on` | entity_id=..., color_temp=400 |
| "Set the desk lamp to blue" | `light.turn_on` | entity_id=..., color_name=blue |
| "Party mode on the strip lights" | `tplink.random_effect` | hue_range=(0,360), saturation_range=(50,100) |
| "Rainbow effect on the strip" | `tplink.sequence_effect` | sequence=[(0,100,100), (60,100,100), ...] |
| "What's the power usage of the kitchen plug?" | Query power sensor | - |
| "Turn off everything in the office" | `switch.turn_off` + `light.turn_off` | area=office |

---

## Phase 5: Security & Safety

### 5.1 Safety Layer

**File:** `/tools/home_assistant/safety.py`

```python
"""
Safety Layer for Home Assistant Integration
Prevents dangerous or unintended actions.
"""

from typing import Dict, Any, Tuple, Optional, List

class SafetyLayer:
    """
    Validates actions against safety rules before execution.
    """
    
    # Domain classifications by risk level
    SAFE_DOMAINS = {"light", "switch", "sensor", "binary_sensor", "button"}
    MODERATE_RISK_DOMAINS = {"climate", "cover", "fan", "input_boolean", "scene", "script"}
    HIGH_RISK_DOMAINS = {"alarm_control_panel", "lock", "camera", "automation"}
    
    # Danger thresholds
    SAFE_ACTIONS = ["turn_on", "turn_off", "toggle"]
    MODERATE_ACTIONS = ["set_temperature", "open_cover", "close_cover", "set_percentage"]
    DANGER_ACTIONS = ["trigger", "arm_away", "arm_home", "arm_night", "disarm", "unlock", "lock"]
    
    # Predefined safety checks
    def preflight_check(
        self,
        domain: str,
        service: str,
        service_data: Dict[str, Any],
        entity_id: str = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Perform safety validation before executing action.
        
        Returns:
            Tuple of (safe: bool, warning_message: Optional[str])
        """
        # 1. Domain restrictions
        if domain in self.HIGH_RISK_DOMAINS:
            return False, f"High risk domain '{domain}' requires explicit approval"
        
        # 2. Action assessment
        action_risk = self._assess_action_risk(domain, service)
        if action_risk == "DANGER":
            return False, f"Action '{service}' on '{domain}' requires explicit approval"
        
        # 3. Parameter safety checks
        param_safe, param_error = self._validate_parameters(domain, service, service_data)
        if not param_safe:
            return False, f"Parameter validation failed: {param_error}"
        
        # 4. State-based safety (would need current state)
        state_safe, state_warning = self._check_state_safety(domain, service, entity_id, service_data)
        if not state_safe:
            return False, state_warning
        
        return True, None
    
    def _assess_action_risk(self, domain: str, service: str) -> str:
        """Assess risk level of an action."""
        if service in self.DANGER_ACTIONS:
            return "DANGER"
        if service in self.MODERATE_ACTIONS:
            return "MODERATE"
        if service in self.SAFE_ACTIONS:
            return "SAFE"
        return "UNKNOWN"  # Default to moderate
    
    def _validate_parameters(
        self,
        domain: str,
        service: str,
        service_data: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Validate action parameters against safety limits."""
        
        # Temperature thresholds
        if domain == "climate" and service == "set_temperature":
            temp = service_data.get("temperature") or service_data.get("temp")
            if temp:
                if temp < 50:
                    return False, f"Temperature {temp}°F is dangerously low"
                if temp > 90:
                    return False, f"Temperature {temp}°F is dangerously high"
        
        # Cover/Blind limits
        if domain == "cover" and service == "set_cover_position":
            position = service_data.get("position")
            if position and (position < 0 or position > 100):
                return False, f"Position must be 0-100, got {position}"
        
        # Brightness limits
        if "brightness" in service_data:
            brightness = service_data["brightness"]
            if brightness < 0 or brightness > 255:
                return False, f"Brightness must be 0-255, got {brightness}"
        
        return True, None
    
    def _check_state_safety(
        self,
        domain: str,
        service: str,
        entity_id: str,
        service_data: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Check current state and warn of potentially harmful changes.
        
        This would require fetching current state and comparing.
        """
        # Placeholder for state-based checks
        # Examples:
        # - Don't set temp to near-freezing if currently comfortable
        # - Warn if turning off security devices at night
        # - Warn if opening covers during storm
        return True, None
    
    def check_for_unintended_consequences(
        self,
        domain: str,
        service: str,
        entity_id: str
    ) -> List[str]:
        """
        Check for potential unintended consequences of an action.
        Returns list of warning messages.
        """
        warnings = []
        
        # Security devices at strange hours
        if domain in {"alarm", "lock", "camera"}:
            # Would need current time
            warnings.append("Modifying security devices - confirm intentionally")
        
        # All lights off at night
        if domain == "light" and service == "turn_off":
            # Would check if it's evening and no other lights requested
            warnings.append("Turning off all lights may affect visibility")
        
        return warnings
```

### 5.2 Emergency Stop

```python
"""
Emergency stop functionality for Home Assistant integration.
"""

def emergency_stop_all_lights():
    """Immediately turn off all light entities."""
    from .ha_query_states import ha_query_states
    from .ha_call_service import ha_call_service
    
    lights = ha_query_states(category="light", state="on")
    
    for light in lights:
        ha_call_service(
            domain="light",
            service="turn_off",
            entity_id=light["entity_id"],
            reason="Emergency stop"
        )
    
    return {"stopped": len(lights), "message": f"Turned off {len(lights)} lights"}

def emergency_stop_switches(area: str = None, exclude_patterns: List[str] = None):
    """
    Turn off switches, optionally filtering by area and excluding certain patterns.
    
    Args:
        area: Specific area to target (None = all areas)
        exclude_patterns: List of entity ID patterns to exclude
    """
    from .ha_query_states import ha_query_states
    from .ha_call_service import ha_call_service
    
    exclude_patterns = exclude_patterns or []
    
    switches = ha_query_states(category="switch", state="on", area=area)
    
    stopped = 0
    for switch in switches:
        entity_id = switch["entity_id"]
        
        # Check exclusions
        if any(pattern in entity_id for pattern in exclude_patterns):
            continue
        
        ha_call_service(
            domain="switch",
            service="turn_off",
            entity_id=entity_id,
            reason="Emergency stop"
        )
        stopped += 1
    
    return {"stopped": stopped, "message": f"Turned off {stopped} switches"}
```

---

## Development Roadmap

| Phase | Duration | Focus | Deliverables |
|-------|----------|-------|--------------|
| **Phase 0** | 1 week | Setup | Home Assistant instance, test Kasa devices |
| **Phase 1** | 1-2 weeks | Core Connection | WS/REST clients, configuration handling |
| **Phase 2** | 1-2 weeks | Basic Tools | `ha_query_states`, `ha_call_service`, testing |
| **Phase 3** | 1 week | Permissions | Permission system, config file, approval queue |
| **Phase 4** | 1 week | Kasa Integration | Kasa-specific tools, entity recognition |
| **Phase 5** | 1 week | Safety Layer | Safety validations, audit logging |
| **Phase 6** | 1 week | Natural Language | `ha_natural_command`, intent parsing |
| **Phase 7** | 1 week | Advanced Features | Event subscriptions, automation creation |
| **Phase 8** | 1 week | Testing & Documentation | End-to-end testing, docs |
| **Total** | ~8-9 weeks | | Production-ready integration |

### Milestones

1. **Week 2:** Successfully query Kasa device states from Mage
2. **Week 4:** Control Kasa devices (turn on/off) with permission checks
3. **Week 6:** Natural language commands working for common Kasa actions
4. **Week 8:** Full integration with safety layer and audit logging

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **WebSocket over REST** | Real-time updates, lower latency, bidirectional communication |
| **Permission-based control** | User retains control; AI acts as assistant, not autonomous agent |
| **Approval queue** | Critical actions require explicit consent |
| **Entity-level permissions** | Granular control per device type |
| **Safety presets** | Default protections for dangerous operations |
| **Audit trail** | Full accountability for all AI actions |
| **Rate limiting** | Prevent rapid repeated actions |
| **Kasa-first approach** | Start with simple, well-supported devices |
| **Modular architecture** | Easy to extend to other device types |
| **Config-driven policy** | Permissions defined in YAML, not code |

---

## Appendix A: Testing Checklist

### Basic Functionality
- [ ] Can query all Kasa device states
- [ ] Can query specific Kasa device by entity ID
- [ ] Can turn on a Kasa plug
- [ ] Can turn off a Kasa plug
- [ ] Can toggle a Kasa light
- [ ] Can change brightness on Kasa bulb
- [ ] Can change color on Kasa bulb

### Permissions
- [ ] Permission denied for restricted entities
- [ ] Approval requested for moderate-risk actions
- [ ] Auto-approval works for safe actions
- [ ] Rate limiting prevents excessive actions

### Safety
- [ ] Validation rejects out-of-range temperatures
- [ ] Validation rejects out-of-range positions
- [ ] Emergency stop function works

### Natural Language
- [ ] "Turn on the kitchen light" works
- [ ] "Turn off all lights" works
- [ ] "Set temperature to 72" works
- [ ] "What's the power usage?" returns data

---

## Appendix B: Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "No Home Assistant client configured" | Client not initialized | Run `set_ha_client()` or check config |
| "Authentication failed" | Invalid token | Verify long-lived access token |
| "Permission denied" | Entity not allowed | Check permissions.yaml |
| "Device not discovered" | Different subnet | Add device by IP address |
| WebSocket connection drops | Network instability | Implement reconnection logic |

---

*End of Document*