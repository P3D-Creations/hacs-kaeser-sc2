# Kaeser Sigma Control 2 for Home Assistant

[![HACS Validation](https://github.com/P3D-Creations/hacs-kaeser-sc2/actions/workflows/validate.yml/badge.svg)](https://github.com/P3D-Creations/hacs-kaeser-sc2/actions/workflows/validate.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Native Home Assistant integration for Kaeser rotary screw compressors with the Sigma Control 2 controller. Talks JSON-RPC directly to the controller's embedded web server; no MQTT or add-ons. Includes a Lovelace card that replicates the SC2 front panel.

## Installation

HACS: add `https://github.com/P3D-Creations/hacs-kaeser-sc2` as a custom repository (category: Integration), install, restart Home Assistant.

Manual: copy `custom_components/kaeser_sc2/` into `config/custom_components/` and restart. The card JS ships inside the integration and registers itself.

## Configuration

Settings > Devices & Services > Add Integration > "Kaeser Sigma Control 2". Fields:

| Field | Notes |
|-------|-------|
| Device name | Used to build entity IDs (slugified) |
| Host | Controller IP, e.g. `192.168.2.230` |
| Username / Password | Web interface login |
| Poll interval | 10-300 s, default 30; changeable later via Configure |

Each compressor is a separate device with its own entities.

## Entities

Sensors: Pressure, Temperature, State, Run Hours, Load Hours, Maintenance In, Key Switch, PA Status, Controller Time, Active Message.

Active Message state is the text of the most recent active fault/warning, or `none`. Attributes: `messages` (recent history, newest first), `active_messages` (currently active subset), `active_count`.

Binary sensors mirror the nine panel LEDs: Error (red), Communication Error (red), Maintenance Due (orange), Voltage OK, Load, Idle, Remote, Clock, Power On (green). Each exposes `led_raw_state` (`off`/`on`/`flash`) and `led_color` attributes.

## Lovelace card

```yaml
type: custom:kaeser-sc2-card
entity_prefix: shop_air_compressor
title: Shop Air Compressor
```

`entity_prefix` is the slugified device name (`Shop Air Compressor` -> `shop_air_compressor`); confirm against your entity IDs. The card is also available in the visual card picker ("Kaeser Sigma Control 2") with a compressor dropdown.

Behavior:

- Live status bar (pressure, controller time, temperature) and LCD lines matching the physical display
- LED indicators with correct colors and blinking for flash states
- Text and layout scale with card width (CSS container queries)
- Active fault/warning pops up on the LCD. The acknowledge button (circle with bars, top-left cluster) dismisses it; dismissal is browser-side only and the LED keeps tracking the compressor. Pressing it again shows the recent-message history; once more returns to the live display. New messages reappear automatically.

If the card does not load, add `/kaeser_sc2/kaeser-sc2-card.js` as a JavaScript Module under Settings > Dashboards > Resources, and hard-refresh the browser after updates.

## Protocol

The integration authenticates with the controller's SHA256 challenge-response login and polls `POST http://<ip>/json.json` for HMI objects (pressure, temperature, counters, enums), LED states, I/O data, and the report list (messages). Sensor discovery walks the controller's HMI menu tree, so it adapts to different models and firmware.

## Troubleshooting

| Problem | Check |
|---------|-------|
| Cannot connect during setup | `http://<ip>/login.html` reachable in a browser |
| Login fails | Credentials; defaults may be printed on the controller |
| Entities unavailable | Enable debug logging (below); look for auth/session errors |
| Missing values | HMI layout varies by firmware; open an issue with debug logs |
| Card not appearing | Resource registered (see above); clear browser cache |

```yaml
logger:
  logs:
    custom_components.kaeser_sc2: debug
```

## License

MIT
