# Mage Maps (Interactive Routing Map)

Interactive routing map for Mage Lab. Provides a Leaflet-based map viewer and routing tool that opens directly in your web browser (embedded in Mage Lab).

## Files

- `mage_interactive_map.html` &mdash; Core HTML/JavaScript viewer (version 2) with controls for start/end addresses and routing logic.
- `mage_interactive_map_current.html` &mdash; Auto-generated "baked" HTML when pre-filling start/end parameters; overwritten on each run.
- `mage_maps.py` &mdash; Python wrapper exposing the `open_mage_maps` function as a Mage CLI tool, including optional `start` and `end` parameters.

## Installation

Copy all three files into your `~/Mage/Tools` directory. Make sure it is toggled on in the **Community** section of Mage Lab.

## Usage

You can ask Mage to use the Mage Maps tool to show you one location or a route between two locations!
```python
# Mage will open the interactive map automatically and pass in paramters based on your request.

# Route between two locations
open_mage_maps(start="New York, NY", end="Boston, MA")

# Show one location
open_mage_maps(start="San Francisco, CA")
```

## License

This tool inherits the MIT License from the Mage Lab Community Tools repository.