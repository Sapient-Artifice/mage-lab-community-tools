from pathlib import Path
import requests
from ws_manager import open_tab
from utils.functions_metadata import function_schema

@function_schema(
    name="open_mage_maps",
    description=(
        "Open an interactive routing map. Optionally prefill start/end addresses and return routing info."
    ),
    required_params=[],
    optional_params=["start", "end"],
)
def open_mage_maps(start: str = None, end: str = None) -> str:
    """
    Opens the interactive_map2.html viewer in a new tab.
    If both start and end are provided, also returns a text summary of the route info.

    :param start: Start address (optional)
    :param end:   End address (optional)
    :return: Status message.
    """
    # Locate HTML viewer
    viewer_path = Path(__file__).parent / "mage_interactive_map.html"
    if not viewer_path.exists():
        return f"Error: Viewer HTML not found at {viewer_path}"

    # Generate and open the map page; bake-in start/end so the in-app map auto-routes
    if start or end:
        src = viewer_path.read_text(encoding="utf-8")
        js_script = '<script>(function(){'
        # Prefill input fields
        if start:
            js_start = requests.utils.requote_uri(start)
            js_script += f'document.getElementById("start").value=decodeURIComponent("{js_start}");'
        if end:
            js_end = requests.utils.requote_uri(end)
            js_script += f'document.getElementById("end").value=decodeURIComponent("{js_end}");'
        # Trigger map update: route if both, else center on single location
        if start and end:
            js_script += 'doRoute();'
        elif start:
            js_script += f'centerLocation(decodeURIComponent("{js_start}"),"start");'
        elif end:
            js_script += f'centerLocation(decodeURIComponent("{js_end}"),"end");'
        js_script += '})();</script>'

        baked = viewer_path.parent / "mage_interactive_map_current.html"
        baked.write_text(src.replace("</body>", js_script + "</body>"), encoding="utf-8")
        open_tab(str(baked))

        # Confirm back to the user: geocode and optionally fetch route info
        def geocode(addr: str):
            r = requests.get(
                'https://nominatim.openstreetmap.org/search',
                params={"format": "json", "q": addr},
                headers={"User-Agent": "mage-lab"}
            )
            r.raise_for_status()
            data = r.json()
            if not data:
                raise ValueError(f"Address not found: {addr}")
            return float(data[0]["lat"]), float(data[0]["lon"])

        # Single location case
        if not (start and end):
            loc = start or end
            lat, lon = geocode(loc)
            return f"Map opened. Location '{loc}' at (lat={lat:.5f}, lon={lon:.5f})."

        # Route case: compute distance & duration
        lat1, lon1 = geocode(start)
        lat2, lon2 = geocode(end)
        osrm_url = (
            f"https://router.project-osrm.org/route/v1/driving/"
            f"{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
        )
        r2 = requests.get(osrm_url)
        r2.raise_for_status()
        routes = r2.json().get("routes") or []
        if not routes:
            return f"Map opened. No route found between '{start}' and '{end}'."
        route = routes[0]
        dist_km = route.get("distance", 0) / 1000
        dur_min = route.get("duration", 0) / 60
        return (
            f"Map opened. Start '{start}' at (lat={lat1:.5f}, lon={lon1:.5f}), "
            f"end '{end}' at (lat={lat2:.5f}, lon={lon2:.5f}); "
            f"Distance {dist_km:.1f} km, duration {dur_min:.1f} min."
        )

    # No prefill: just open the blank map
    open_tab(str(viewer_path))
    return "Map opened."
