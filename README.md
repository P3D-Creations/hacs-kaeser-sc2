# Kaeser Sigma Control 2 — Home Assistant Integration

[![HACS Validation](https://github.com/P3D-Creations/hacs-kaeser-sc2/actions/workflows/validate.yml/badge.svg)](https://github.com/yourusername/hacs-kaeser-sc2/actions/workflows/validate.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A native Home Assistant integration for **Kaeser rotary screw air compressors** equipped with the **Sigma Control 2** controller. Communicates directly with the controller's built-in web server — no MQTT broker required.

Includes a **custom Lovelace card** that replicates the SC2 controller's front panel display.

![Screenshot placeholder — replace with actual screenshot](https://via.placeholder.com/600x300?text=Kaeser+SC2+Card)

## Features

- **Native HA integration** — no MQTT, no Docker, no add-ons needed
- **Config flow UI** — add compressors via Settings → Integrations → Add → "Kaeser Sigma Control 2"
- **Each compressor is its own device** with all sensors grouped under it
- **Custom Lovelace card** replicating the SC2 controller's physical display
- **Auto-discovery of sensor data** from the controller's HMI menu structure

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click **Integrations** → **⋮** menu → **Custom repositories**
3. Add `https://github.com/yourusername/hacs-kaeser-sc2` with category **Integration**
4. Click **Install**
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/kaeser_sc2` folder into your HA `config/custom_components/` directory
2. Copy the `js/kaeser-sc2-card.js` file into your HA `config/js/` directory (create `js/` if needed)
3. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **"Kaeser Sigma Control 2"**
3. Enter:
   - **Device name** — A friendly name (e.g. "Shop Air Compressor") — used for entity IDs
   - **Host** — IP address of the controller (e.g. `192.168.2.230`)
   - **Username** — Web interface login username
   - **Password** — Web interface login password
   - **Poll interval** — How often to read data (10–300 seconds, default 30)
4. Click **Submit**

Repeat for each compressor. Each one appears as a separate device.

## Entities Created

Each compressor creates the following entities:

### Sensors

| Entity | Description |
|--------|-------------|
| **Pressure** | Current system pressure (psi or bar) |
| **Temperature** | Discharge temperature |
| **State** | Operational state: off, load, idle, ready, standby, error |
| **Run Hours** | Total running hours |
| **Maintenance In** | Hours until next maintenance |
| **Key Switch** | Key switch position |
| **PA Status** | Pressure actuator / remote status |
| **Controller Time** | Time displayed on the controller |

### Binary Sensors (LED Indicators)

| Entity | Description |
|--------|-------------|
| **Error** | Error alarm active (red LED) |
| **Communication Error** | Comm error active (red LED) |
| **Maintenance Due** | Maintenance required (orange LED) |
| **Voltage OK** | Power supply OK (green LED) |
| **Load** | Compressor under load (green LED) |
| **Idle** | Compressor idling (green LED) |
| **Remote** | Remote control active (green LED) |
| **Clock** | Timer/clock function active (green LED) |
| **Power On** | Controller powered on (green LED) |

## Custom Lovelace Card

The integration includes a custom card that mimics the physical SC2 controller display:

- LCD-style status bar with pressure, time, and temperature
- Operational state badge
- Key switch and PA status
- Run hours and maintenance countdown
- LED indicator column matching the physical controller

### Card Configuration

Add to your Lovelace dashboard (YAML mode):

```yaml
type: custom:kaeser-sc2-card
entity_prefix: "shop_air_compressor"
title: "Shop Air Compressor"
```

The `entity_prefix` is the slugified version of the device name you entered during setup (lowercase, spaces → underscores). For example, "Shop Air Compressor" becomes `shop_air_compressor`. Check your entity IDs in **Settings → Devices → [your compressor] → Entities** to confirm.

### Card Editor

The card also supports the Lovelace visual editor — just add a "Custom: Kaeser Sigma Control 2" card from the card picker.

### Adding the card resource (if not auto-loaded)

The integration automatically registers the card JS. If it doesn't appear, manually add it:

1. Go to **Settings → Dashboards → ⋮ → Resources**
2. Add `/kaeser_sc2/kaeser-sc2-card.js` as a JavaScript Module

## How It Works

The Sigma Control 2 controller has an embedded web server that serves a JavaScript SPA. Instead of scraping HTML, this integration speaks the same **JSON-RPC protocol** that the original JavaScript frontend uses:

- **Endpoint:** `POST http://<ip>/json.json`
- **Authentication:** SHA256 challenge-response (handled automatically — just provide your username and password)
- **Data:** HMI objects (pressure, temperature, counters), LED states, I/O data, alarms

The integration discovers available sensors dynamically by parsing the controller's HMI menu tree, so it adapts to different Kaeser models and firmware versions.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Cannot connect" during setup | Verify IP is reachable. Try opening `http://<ip>/login.html` in a browser. |
| Login fails | Check username/password. Default credentials may be on a sticker on the controller. |
| Sensors showing "unavailable" | Set logging to debug: add `custom_components.kaeser_sc2: debug` to your `logger` config. Check for session timeout issues. |
| Pressure/temperature missing | The HMI object structure varies by firmware. File an issue with debug logs. |
| Card not appearing | Ensure the JS resource is registered (see above). Clear browser cache. |

### Debug Logging

```yaml
logger:
  default: info
  logs:
    custom_components.kaeser_sc2: debug
```

## Contributing

Issues and PRs welcome. If your Kaeser model has different HMI object types or LED configurations, please open an issue with debug logs so we can add support.

## License

MIT
