/**
 * Kaeser Sigma Control 2 — Custom Lovelace Card
 *
 * Replicates the SC2 controller's front panel display, showing the
 * same data layout as the original web UI: status bar, LCD display
 * area, and LED indicator column.
 */

const CARD_VERSION = "1.0.0";

class KaeserSC2Card extends HTMLElement {
  // ── HA Lifecycle ──────────────────────────────────────────────
  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    this._updateCard();
  }

  setConfig(config) {
    if (!config.entity_prefix) {
      throw new Error("You must define an entity_prefix (e.g. sensor.192_168_2_230)");
    }
    this._config = config;
    this._entityPrefix = config.entity_prefix; // e.g. "192_168_2_230"
    this._title = config.title || "Kaeser SC2";
    this._rendered = false;
  }

  getCardSize() {
    return 8;
  }

  static getStubConfig() {
    return {
      entity_prefix: "shop_air_compressor",
      title: "Shop Air Compressor",
    };
  }

  // ── State helpers ────────────────────────────────────────────
  _state(suffix) {
    const id = `sensor.${this._entityPrefix}_${suffix}`;
    const s = this._hass?.states[id];
    return s ? s.state : "—";
  }

  _binaryState(suffix) {
    const id = `binary_sensor.${this._entityPrefix}_${suffix}`;
    const s = this._hass?.states[id];
    return s ? s.state === "on" : false;
  }

  _unit(suffix) {
    const id = `sensor.${this._entityPrefix}_${suffix}`;
    const s = this._hass?.states[id];
    return s?.attributes?.unit_of_measurement || "";
  }

  // ── Render ────────────────────────────────────────────────────
  _updateCard() {
    if (!this._rendered) {
      this.innerHTML = "";
      this.appendChild(this._buildCard());
      this._rendered = true;
    }
    this._refresh();
  }

  _buildCard() {
    const card = document.createElement("ha-card");

    const style = document.createElement("style");
    style.textContent = `
      :host {
        --kaeser-yellow: #FFCC00;
        --kaeser-dark: #1a1a1a;
        --lcd-bg: #2d3436;
        --lcd-text: #dfe6e9;
        --lcd-accent: #00b894;
        --led-off: #444;
        --led-red: #e74c3c;
        --led-orange: #f39c12;
        --led-green: #27ae60;
      }

      ha-card {
        background: #2c2c2c;
        border: 2px solid var(--kaeser-yellow);
        border-radius: 12px;
        overflow: hidden;
        font-family: 'Segoe UI', Arial, sans-serif;
      }

      .sc2-header {
        background: var(--kaeser-yellow);
        color: var(--kaeser-dark);
        padding: 8px 16px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        font-weight: 700;
        font-size: 14px;
      }
      .sc2-header .brand {
        font-size: 11px;
        font-weight: 400;
        opacity: 0.7;
      }

      .sc2-body {
        display: flex;
        padding: 12px;
        gap: 12px;
      }

      /* ── LCD Panel ─────────────────────────────────── */
      .lcd-panel {
        flex: 1;
        background: var(--lcd-bg);
        border: 2px solid #555;
        border-radius: 6px;
        padding: 0;
        min-height: 220px;
        display: flex;
        flex-direction: column;
      }

      .lcd-statusbar {
        display: flex;
        justify-content: space-between;
        padding: 6px 10px;
        background: #000;
        color: #fff;
        font-family: 'Courier New', monospace;
        font-size: 14px;
        border-radius: 4px 4px 0 0;
        border-bottom: 1px solid #555;
      }

      .lcd-content {
        padding: 8px 12px;
        font-family: 'Courier New', monospace;
        font-size: 13px;
        color: var(--lcd-text);
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 2px;
        line-height: 1.7;
      }

      .lcd-separator {
        border: none;
        border-top: 1px dashed #636e72;
        margin: 4px 0;
      }

      .lcd-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .lcd-row .label {
        color: #b2bec3;
      }
      .lcd-row .value {
        font-weight: 600;
        color: var(--lcd-text);
      }

      .state-badge {
        display: inline-block;
        padding: 2px 12px;
        border-radius: 4px;
        font-size: 14px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
      }
      .state-off      { background: #636e72; color: #fff; }
      .state-load     { background: var(--led-green); color: #fff; }
      .state-idle     { background: #2980b9; color: #fff; }
      .state-ready    { background: #00b894; color: #fff; }
      .state-standby  { background: #6c5ce7; color: #fff; }
      .state-error    { background: var(--led-red); color: #fff; }
      .state-unknown  { background: #636e72; color: #fff; }

      /* ── LED Column ────────────────────────────────── */
      .led-column {
        display: flex;
        flex-direction: column;
        gap: 6px;
        width: 90px;
        flex-shrink: 0;
      }

      .led {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 10px;
        color: #b2bec3;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }
      .led-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: var(--led-off);
        flex-shrink: 0;
        border: 1px solid #666;
        transition: background 0.3s, box-shadow 0.3s;
      }
      .led-dot.red    { background: var(--led-red);    box-shadow: 0 0 6px var(--led-red); }
      .led-dot.orange { background: var(--led-orange); box-shadow: 0 0 6px var(--led-orange); }
      .led-dot.green  { background: var(--led-green);  box-shadow: 0 0 6px var(--led-green); }
      .led-dot.flash  { animation: led-flash 0.8s infinite; }

      @keyframes led-flash {
        0%, 100% { opacity: 1; }
        50%      { opacity: 0.2; }
      }

      /* ── Footer ────────────────────────────────────── */
      .sc2-footer {
        padding: 6px 16px;
        font-size: 10px;
        color: #636e72;
        text-align: right;
        border-top: 1px solid #444;
      }
    `;
    card.appendChild(style);

    // Header
    const header = document.createElement("div");
    header.className = "sc2-header";
    header.innerHTML = `
      <span class="title">${this._title}</span>
      <span class="brand">KAESER SIGMA CONTROL 2</span>
    `;
    card.appendChild(header);

    // Body
    const body = document.createElement("div");
    body.className = "sc2-body";

    // LCD
    const lcd = document.createElement("div");
    lcd.className = "lcd-panel";
    lcd.innerHTML = `
      <div class="lcd-statusbar">
        <span id="sc2-pressure">—</span>
        <span id="sc2-time">—</span>
        <span id="sc2-temperature">—</span>
      </div>
      <div class="lcd-content">
        <hr class="lcd-separator">
        <div style="text-align:center;">
          <span id="sc2-state" class="state-badge state-unknown">—</span>
        </div>
        <hr class="lcd-separator">
        <div class="lcd-row">
          <span class="label">Key</span>
          <span class="value" id="sc2-key">—</span>
        </div>
        <div class="lcd-row">
          <span class="label">pA</span>
          <span class="value" id="sc2-pa">—</span>
        </div>
        <hr class="lcd-separator">
        <div class="lcd-row">
          <span class="label">Run</span>
          <span class="value" id="sc2-run">—</span>
        </div>
        <div class="lcd-row">
          <span class="label">Maintenance in</span>
          <span class="value" id="sc2-maint">—</span>
        </div>
      </div>
    `;
    body.appendChild(lcd);

    // LEDs
    const leds = document.createElement("div");
    leds.className = "led-column";
    const ledDefs = [
      { id: "led_error",       label: "Error",  color: "red" },
      { id: "led_com_error",   label: "Comm",   color: "red" },
      { id: "led_maintenance", label: "Maint",  color: "orange" },
      { id: "led_voltage",     label: "Volts",  color: "green" },
      { id: "led_load",        label: "Load",   color: "green" },
      { id: "led_idle",        label: "Idle",   color: "green" },
      { id: "led_remote",      label: "Remote", color: "green" },
      { id: "led_clock",       label: "Clock",  color: "green" },
      { id: "led_power_on",    label: "Power",  color: "green" },
    ];
    for (const led of ledDefs) {
      const el = document.createElement("div");
      el.className = "led";
      el.innerHTML = `<span class="led-dot" id="sc2-${led.id}"></span><span>${led.label}</span>`;
      leds.appendChild(el);
    }
    body.appendChild(leds);

    card.appendChild(body);

    // Footer
    const footer = document.createElement("div");
    footer.className = "sc2-footer";
    footer.innerHTML = `kaeser-sc2 v${CARD_VERSION}`;
    card.appendChild(footer);

    // Store references
    this._lcd = lcd;
    this._ledDefs = ledDefs;
    this._card = card;

    return card;
  }

  _refresh() {
    if (!this._card) return;

    const pressure = this._state("pressure");
    const pUnit = this._unit("pressure");
    const temp = this._state("temperature");
    const tUnit = this._unit("temperature");
    const time = this._state("controller_time");
    const state = this._state("state");
    const key = this._state("key_switch");
    const pa = this._state("pa_status");
    const run = this._state("run_hours");
    const maint = this._state("maintenance_in");

    // Status bar
    const el = (id) => this._card.querySelector(`#${id}`);
    el("sc2-pressure").textContent = pressure !== "—" ? `${pressure} ${pUnit}` : "—";
    el("sc2-time").textContent = time;
    el("sc2-temperature").textContent = temp !== "—" ? `${temp} ${tUnit}` : "—";

    // State badge
    const stateEl = el("sc2-state");
    stateEl.textContent = state;
    stateEl.className = `state-badge state-${state.replace(/\s+/g, "-")}`;

    // Key / PA
    el("sc2-key").textContent = key;
    el("sc2-pa").textContent = pa;

    // Counters
    el("sc2-run").textContent = run !== "—" ? `${run}h` : "—";
    el("sc2-maint").textContent = maint !== "—" ? `${maint}h` : "—";

    // LEDs
    for (const led of this._ledDefs) {
      const dot = el(`sc2-${led.id}`);
      if (!dot) continue;
      const isOn = this._binaryState(led.id);
      // Check if flashing (read raw state attribute)
      const rawId = `binary_sensor.${this._entityPrefix}_${led.id}`;
      const rawState = this._hass?.states[rawId];
      const rawLedVal = rawState?.attributes?.led_raw_state || "";
      const isFlash = rawLedVal === "flash" || rawState?.state === "on";

      dot.className = "led-dot";
      if (isOn) {
        dot.classList.add(led.color);
      }
    }
  }
}

// ── Card registration ──────────────────────────────────────────
customElements.define("kaeser-sc2-card", KaeserSC2Card);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "kaeser-sc2-card",
  name: "Kaeser Sigma Control 2",
  description: "Replicates the SC2 controller front panel with live data.",
  preview: true,
  documentationURL: "https://github.com/yourusername/hacs-kaeser-sc2",
});

// HACS frontend info
console.info(
  `%c KAESER-SC2-CARD %c v${CARD_VERSION} `,
  "color: #fff; background: #1a1a1a; font-weight: 700; padding: 2px 6px; border-radius: 4px 0 0 4px;",
  "color: #1a1a1a; background: #FFCC00; font-weight: 700; padding: 2px 6px; border-radius: 0 4px 4px 0;",
);
