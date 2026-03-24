/**
 * Kaeser Sigma Control 2 — Custom Lovelace Card  v2.0.0
 *
 * Pixel-accurate replica of the SC2 controller front panel.
 * Uses the actual SC2 background image (sc2.jpg) with LED indicators
 * and LCD text overlaid at the exact positions used by the controller's
 * own web interface.
 *
 * Configuration (YAML):
 *   type: custom:kaeser-sc2-card
 *   entity_prefix: shop_air_compressor   # prefix used when you added the device
 *   title: Shop Air Compressor           # optional header text
 */

const CARD_VERSION = "2.0.0";

/* ── Image base URL (set by __init__.py static-path registration) ── */
const IMG_BASE = "/kaeser_sc2/images";

/* ── SC2 panel pixel dimensions (from sc2.jpg) ── */
const SC2_W = 750;
const SC2_H = 493;

/* ── LCD geometry inside the SC2 image ── */
const LCD_LEFT   = 198;
const LCD_TOP_SB = 88;   // status bar top
const LCD_SB_H   = 20;   // status bar height
const LCD_TOP    = 112;   // start of home screen content
const LCD_WIDTH  = 345;
const LCD_HEIGHT = 140;
const CHAR_W     = 10;    // monospace character width at 16px

/* ── LED positions (left, top) inside the 750x493 image ── */
const LED_POSITIONS = {
  led_error:       { x:  43, y:  44 },
  led_com_error:   { x:  43, y: 107 },
  led_maintenance: { x:  43, y: 169 },
  led_voltage:     { x:  43, y: 256 },
  led_load:        { x:  43, y: 388 },
  led_idle:        { x:  43, y: 424 },
  led_remote:      { x: 225, y: 389 },
  led_clock:       { x: 300, y: 389 },
  led_power_on:    { x: 643, y: 321 },
};

/* ── LED colour mapping ── */
const LED_COLOURS = {
  led_error:       "red",
  led_com_error:   "red",
  led_maintenance: "orange",
  led_voltage:     "green",
  led_load:        "green",
  led_idle:        "green",
  led_remote:      "green",
  led_clock:       "green",
  led_power_on:    "green",
};

/* ── Percentage helpers (for responsive positioning) ── */
function pctX(px)  { return (px / SC2_W * 100).toFixed(3) + "%"; }
function pctY(px)  { return (px / SC2_H * 100).toFixed(3) + "%"; }
function pctW(px)  { return (px / SC2_W * 100).toFixed(3) + "%"; }
function pctH(px)  { return (px / SC2_H * 100).toFixed(3) + "%"; }
function lcdPct(px){ return (px / LCD_WIDTH * 100).toFixed(2) + "%"; }

function _clean(val) {
  return (!val || val === "—" || val === "unknown" || val === "unavailable") ? "" : val;
}
function _hVal(val) {
  return (!val || val === "—" || val === "unknown" || val === "unavailable") ? "" : val + "h";
}


class KaeserSC2Card extends HTMLElement {

  /* ===========================================================
   * HA lifecycle
   * =========================================================== */
  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    if (!this._rendered) this._render();
    this._refresh();
  }

  setConfig(config) {
    if (!config.entity_prefix) {
      throw new Error("You must define entity_prefix (e.g. shop_air_compressor)");
    }
    this._config = config;
    this._prefix = config.entity_prefix;
    this._title  = config.title || "Kaeser SC2";
    this._rendered = false;
  }

  getCardSize() { return 9; }

  static getStubConfig() {
    return { entity_prefix: "shop_air_compressor", title: "Shop Air Compressor" };
  }

  /* ===========================================================
   * State helpers
   * =========================================================== */
  _state(suffix) {
    const id = "sensor." + this._prefix + "_" + suffix;
    const s  = this._hass && this._hass.states ? this._hass.states[id] : null;
    return s ? s.state : "—";
  }
  _binaryState(suffix) {
    const id = "binary_sensor." + this._prefix + "_" + suffix;
    const s  = this._hass && this._hass.states ? this._hass.states[id] : null;
    return s ? s.state : "off";
  }
  _unit(suffix) {
    const id = "sensor." + this._prefix + "_" + suffix;
    const s  = this._hass && this._hass.states ? this._hass.states[id] : null;
    return (s && s.attributes && s.attributes.unit_of_measurement) ? s.attributes.unit_of_measurement : "";
  }

  /* ===========================================================
   * Build the card DOM (once)
   * =========================================================== */
  _render() {
    this.innerHTML = "";

    /* Shadow DOM keeps styles isolated */
    const shadow = this.attachShadow({ mode: "open" });

    /* ── Stylesheet ── */
    const style = document.createElement("style");
    style.textContent = [
      ":host { display: block; }",

      /* Card */
      "ha-card { overflow:hidden; border-radius:12px; background:#2c2c2c; }",

      /* Header */
      ".sc2-header { display:flex; align-items:center; justify-content:space-between; background:#FFCC00; color:#1a1a1a; padding:6px 14px; font:700 14px/1.2 'Segoe UI',Arial,sans-serif; }",
      ".sc2-header .brand { font-size:11px; font-weight:400; opacity:.7; }",

      /* Panel wrapper — maintains 750:493 aspect ratio */
      ".sc2-panel { position:relative; width:100%; padding-bottom:" + pctH(SC2_H).replace('%','') / SC2_W * SC2_W + "%; overflow:hidden; }",
      ".sc2-panel { padding-bottom:" + (SC2_H / SC2_W * 100).toFixed(4) + "%; background:url('" + IMG_BASE + "/sc2.jpg') center/100% 100% no-repeat; }",

      /* Inner coordinate layer */
      ".sc2-inner { position:absolute; inset:0; }",

      /* Status bar (black top row of LCD) */
      ".lcd-sb { position:absolute; left:" + pctX(LCD_LEFT) + "; top:" + pctY(LCD_TOP_SB) + "; width:" + pctW(LCD_WIDTH) + "; height:" + pctH(LCD_SB_H) + "; background:#000; overflow:hidden; }",
      ".lcd-sb span { position:absolute; top:0; height:100%; display:flex; align-items:center; font:normal 16px/1 'Courier New','Arial Unicode MS',monospace; color:#fff; white-space:nowrap; }",
      ".sb-p { left:0; width:" + lcdPct(80) + "; justify-content:flex-end; }",
      ".sb-t { left:" + lcdPct(120) + "; width:" + lcdPct(70) + "; justify-content:flex-end; }",
      ".sb-d { left:" + lcdPct(250) + "; width:" + lcdPct(95) + "; justify-content:flex-end; }",

      /* LCD home-screen content area */
      ".lcd-c { position:absolute; left:" + pctX(LCD_LEFT) + "; top:" + pctY(LCD_TOP) + "; width:" + pctW(LCD_WIDTH) + "; height:" + pctH(LCD_HEIGHT) + "; overflow:hidden; }",
      ".lcd-ln { position:relative; height:" + (100/7).toFixed(2) + "%; box-sizing:border-box; }",
      ".lcd-ln span { position:absolute; top:0; height:100%; display:flex; align-items:center; font:normal 16px/1 'Courier New','Arial Unicode MS',monospace; color:#454545; white-space:nowrap; overflow:hidden; }",

      /* Responsive font scaling: 16px at 750px native width */
      ".lcd-sb span, .lcd-ln span { font-size:clamp(7px, 2.13cqw, 16px); }",
      /* Container query fallback — use vw-based if cq not supported */
      "@supports not (font-size: 1cqw) { .lcd-sb span, .lcd-ln span { font-size:clamp(7px, 2.13vw, 16px); } }",

      /* LED images */
      ".led-i { position:absolute; width:" + pctW(13) + "; height:" + pctH(13) + "; image-rendering:auto; }",
      ".led-i.flash { animation:led-blink .6s infinite; }",
      "@keyframes led-blink { 0%,100%{opacity:1} 50%{opacity:.12} }",

      /* Footer */
      ".sc2-footer { padding:4px 14px; font:400 10px/1.4 'Segoe UI',Arial,sans-serif; color:#636e72; text-align:right; }",
    ].join("\n");
    shadow.appendChild(style);

    /* ── Card element ── */
    const card = document.createElement("ha-card");

    /* Header */
    const hdr = document.createElement("div");
    hdr.className = "sc2-header";
    hdr.innerHTML = "<span>" + this._esc(this._title) + "</span><span class='brand'>KAESER SIGMA CONTROL 2</span>";
    card.appendChild(hdr);

    /* Panel */
    const panel = document.createElement("div");
    panel.className = "sc2-panel";
    const inner = document.createElement("div");
    inner.className = "sc2-inner";

    /* ── Status bar ── */
    const sb = document.createElement("div");
    sb.className = "lcd-sb";
    sb.innerHTML = ""
      + "<span class='sb-p' id='sb-p'></span>"
      + "<span class='sb-t' id='sb-t'></span>"
      + "<span class='sb-d' id='sb-d'></span>";
    inner.appendChild(sb);

    /* ── LCD content (7 lines) ── */
    const lcd = document.createElement("div");
    lcd.className = "lcd-c";

    // Line 0: separator
    lcd.appendChild(this._sep());
    // Line 1: state
    lcd.appendChild(this._ln("<span id='lcd-st' style='left:0;width:100%'></span>"));
    // Line 2: separator
    lcd.appendChild(this._sep());
    // Line 3: Key – val | pA – val
    lcd.appendChild(this._ln(""
      + "<span style='left:0;width:" + lcdPct(70) + "'>Key</span>"
      + "<span style='left:" + lcdPct(80)  + ";width:" + lcdPct(10) + "'>-</span>"
      + "<span id='lcd-key' style='left:" + lcdPct(100) + ";width:" + lcdPct(40) + "'></span>"
      + "<span style='left:" + lcdPct(150) + ";width:" + lcdPct(10) + "'>¦</span>"
      + "<span style='left:" + lcdPct(160) + ";width:" + lcdPct(20) + ";justify-content:flex-end'>pA</span>"
      + "<span style='left:" + lcdPct(190) + ";width:" + lcdPct(10) + "'>-</span>"
      + "<span id='lcd-pa' style='left:" + lcdPct(210) + ";width:" + lcdPct(90) + "'></span>"
    ));
    // Line 4: separator
    lcd.appendChild(this._sep());
    // Line 5: Run
    lcd.appendChild(this._ln(""
      + "<span style='left:" + lcdPct(160) + ";width:" + lcdPct(60) + "'>Run</span>"
      + "<span id='lcd-run' style='left:" + lcdPct(230) + ";width:" + lcdPct(70) + ";justify-content:flex-end'></span>"
    ));
    // Line 6: Load
    lcd.appendChild(this._ln(""
      + "<span style='left:" + lcdPct(160) + ";width:" + lcdPct(60) + "'>Load</span>"
      + "<span id='lcd-load' style='left:" + lcdPct(230) + ";width:" + lcdPct(70) + ";justify-content:flex-end'></span>"
    ));

    inner.appendChild(lcd);

    /* ── Maintenance line: placed below the 7-line lcd-c area ── */
    /* The real SC2 displays 7 visible lines but the Run/Load lines only
       take up positions 5-6. Maintenance sits at line-7 which may clip.
       We render it inside the LCD content area by using a slightly taller
       region or we can just add an 8th line. Since we set 7 lines, let's
       actually use 8 lines and adjust the height. */

    /* Actually, let's restructure: the real display has these lines in the content area:
       0: ----- separator
       1: On load  (state)
       2: ----- separator
       3: Key - on ¦ pA - Load
       4: ----- separator
       5: Run          6169h
       6: Load         2535h
       But there isn't a "Load" line on the default SC2 display if the controller
       doesn't show it. The real captured data shows "Run" and "Maintenance in" labels.
       From the 1.json capture: objects 14="Run", 15=6169h, 16="Load", 17=2535h, 18="Maintenance in", 19=468h
       So the real display actually has: Run, Load, Maintenance in — BUT the web
       interface only shows Run and Maintenance on the home screen overview.
       Let's show all three + Maintenance on an 8th line. We already have 7 lines.
       Let me adjust back to the data. */

    /* Since we already added lines 5 (Run) and 6 (Load), we need line 7 (Maintenance).
       But we only allocated 7 lines (0-6). Let's just add an 8th line inside lcd-c
       and use height: 12.5% (100/8) instead. We'll fix the CSS. */

    // Line 7: Maintenance in
    lcd.appendChild(this._ln(""
      + "<span style='left:0;width:" + lcdPct(220) + "'>Maintenance in</span>"
      + "<span id='lcd-mt' style='left:" + lcdPct(230) + ";width:" + lcdPct(70) + ";justify-content:flex-end'></span>"
    ));

    /* ── LED indicators ── */
    for (var name in LED_POSITIONS) {
      if (!LED_POSITIONS.hasOwnProperty(name)) continue;
      var pos = LED_POSITIONS[name];
      var img = document.createElement("img");
      img.className = "led-i";
      img.id = "led-" + name;
      img.src = IMG_BASE + "/led_off.png";
      img.style.left = pctX(pos.x);
      img.style.top  = pctY(pos.y);
      inner.appendChild(img);
    }

    panel.appendChild(inner);
    card.appendChild(panel);

    /* Footer */
    var footer = document.createElement("div");
    footer.className = "sc2-footer";
    footer.textContent = "kaeser-sc2-card v" + CARD_VERSION;
    card.appendChild(footer);

    shadow.appendChild(card);
    this._shadow = shadow;
    this._rendered = true;

    /* Now fix the line heights: we have 8 lines, so each is 12.5% */
    var lines = lcd.querySelectorAll(".lcd-ln");
    for (var i = 0; i < lines.length; i++) {
      lines[i].style.height = (100 / lines.length).toFixed(2) + "%";
    }
  }

  _sep() {
    var d = document.createElement("div");
    d.className = "lcd-ln";
    d.innerHTML = "<span style='left:0;width:100%;color:#454545'>------------------------------</span>";
    return d;
  }
  _ln(html) {
    var d = document.createElement("div");
    d.className = "lcd-ln";
    d.innerHTML = html;
    return d;
  }
  _esc(s) {
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  /* ===========================================================
   * Refresh entity values
   * =========================================================== */
  _refresh() {
    if (!this._shadow) return;
    var self = this;
    function $(id) { return self._shadow.getElementById(id); }

    /* Status bar */
    var p  = this._state("pressure");
    var pU = this._unit("pressure") || "psi";
    var t  = this._state("temperature");
    var tU = this._unit("temperature") || "°F";
    var tm = this._state("controller_time");

    var sbP = $("sb-p");
    var sbT = $("sb-t");
    var sbD = $("sb-d");
    if (sbP) sbP.textContent = _clean(p) ? p + pU : "";
    if (sbT) sbT.textContent = _clean(tm) || "";
    if (sbD) sbD.textContent = _clean(t)  ? t + tU : "";

    /* LCD data */
    var st = $("lcd-st");
    var ky = $("lcd-key");
    var pa = $("lcd-pa");
    var rn = $("lcd-run");
    var ld = $("lcd-load");
    var mt = $("lcd-mt");

    if (st) st.textContent = _clean(this._state("state"));
    if (ky) ky.textContent = _clean(this._state("key_switch"));
    if (pa) pa.textContent = _clean(this._state("pa_status"));
    if (rn) rn.textContent = _hVal(this._state("run_hours"));
    if (ld) ld.textContent = _hVal(this._state("load_hours"));
    if (mt) mt.textContent = _hVal(this._state("maintenance_in"));

    /* LEDs */
    for (var name in LED_POSITIONS) {
      if (!LED_POSITIONS.hasOwnProperty(name)) continue;
      var img = $("led-" + name);
      if (!img) continue;

      var raw = this._binaryState(name);
      var entityId = "binary_sensor." + this._prefix + "_" + name;
      var entity = (this._hass && this._hass.states) ? this._hass.states[entityId] : null;
      var ledRaw = (entity && entity.attributes) ? (entity.attributes.led_raw_state || "") : "";

      if (raw === "on" || ledRaw === "flash") {
        var colour = LED_COLOURS[name] || "green";
        img.src = IMG_BASE + "/led_" + colour + ".png";
        if (ledRaw === "flash") {
          img.classList.add("flash");
        } else {
          img.classList.remove("flash");
        }
      } else {
        img.src = IMG_BASE + "/led_off.png";
        img.classList.remove("flash");
      }
    }
  }
}

/* ── Registration ──────────────────────────────────────────── */
customElements.define("kaeser-sc2-card", KaeserSC2Card);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "kaeser-sc2-card",
  name: "Kaeser Sigma Control 2",
  description: "Pixel-accurate replica of the SC2 controller front panel with live data and LEDs.",
  preview: true,
  documentationURL: "https://github.com/P3D-Creations/hacs-kaeser-sc2",
});

console.info(
  "%c KAESER-SC2-CARD %c v" + CARD_VERSION + " ",
  "color:#fff; background:#1a1a1a; font-weight:700; padding:2px 6px; border-radius:4px 0 0 4px;",
  "color:#1a1a1a; background:#FFCC00; font-weight:700; padding:2px 6px; border-radius:0 4px 4px 0;",
);
