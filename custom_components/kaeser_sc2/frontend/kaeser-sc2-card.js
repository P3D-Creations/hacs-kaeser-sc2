/**
 * Kaeser Sigma Control 2 — Custom Lovelace Card  v3.0.0
 *
 * Pixel-accurate replica of the SC2 controller front panel with:
 *  - Visual config editor for entity assignment
 *  - Fine-tuning controls for position, size, and font of every element
 *
 * Configuration (YAML or visual editor):
 *   type: custom:kaeser-sc2-card
 *   entity_prefix: shop_air_compressor
 *   title: Shop Air Compressor
 */

const CARD_VERSION = "3.0.0";
const IMG_BASE = "/kaeser_sc2/images";

/* ═══════════════════════════════════════════════════════════════
 * Default layout constants (all in px at 750×493 native)
 * These become the base values; user offsets are added on top.
 * ═══════════════════════════════════════════════════════════════ */
const DEFAULTS = {
  /* Status bar */
  sb_left: 198,  sb_top: 88,  sb_width: 345, sb_height: 20,
  sb_font: 16,

  /* LCD content area */
  lcd_left: 198, lcd_top: 110, lcd_width: 345, lcd_height: 155,
  lcd_font: 16,

  /* LED dot size */
  led_size: 13,

  /* Individual LED positions */
  led_error_x: 43,       led_error_y: 44,
  led_com_error_x: 43,   led_com_error_y: 107,
  led_maintenance_x: 43, led_maintenance_y: 169,
  led_voltage_x: 43,     led_voltage_y: 256,
  led_load_x: 43,        led_load_y: 388,
  led_idle_x: 43,        led_idle_y: 424,
  led_remote_x: 225,     led_remote_y: 389,
  led_clock_x: 300,      led_clock_y: 389,
  led_power_on_x: 643,   led_power_on_y: 321,
};

const SC2_W = 750;
const SC2_H = 493;

const LED_NAMES = [
  "led_error","led_com_error","led_maintenance","led_voltage",
  "led_load","led_idle","led_remote","led_clock","led_power_on"
];
const LED_COLOURS = {
  led_error:"red", led_com_error:"red", led_maintenance:"orange",
  led_voltage:"green", led_load:"green", led_idle:"green",
  led_remote:"green", led_clock:"green", led_power_on:"green",
};
const LED_LABELS = {
  led_error:"Error", led_com_error:"Comm Error", led_maintenance:"Maintenance",
  led_voltage:"Voltage", led_load:"Load", led_idle:"Idle",
  led_remote:"Remote", led_clock:"Clock", led_power_on:"Power On",
};

/* helpers */
function _v(cfg, key) {
  /* return config value or default */
  if (cfg && cfg[key] !== undefined && cfg[key] !== null && cfg[key] !== "") {
    return Number(cfg[key]);
  }
  return DEFAULTS[key] !== undefined ? DEFAULTS[key] : 0;
}
function _pctX(px) { return (px / SC2_W * 100).toFixed(3) + "%"; }
function _pctY(px) { return (px / SC2_H * 100).toFixed(3) + "%"; }
function _clean(val) {
  return (!val || val === "—" || val === "unknown" || val === "unavailable") ? "" : val;
}
function _hVal(val) {
  return (!val || val === "—" || val === "unknown" || val === "unavailable") ? "" : val + "h";
}


/* ╔═══════════════════════════════════════════════════════════════╗
 * ║                     MAIN CARD CLASS                          ║
 * ╚═══════════════════════════════════════════════════════════════╝ */
class KaeserSC2Card extends HTMLElement {

  static getConfigElement() {
    return document.createElement("kaeser-sc2-card-editor");
  }
  static getStubConfig() {
    return { entity_prefix: "", title: "Kaeser SC2" };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    this._ensureRendered();
    this._refresh();
  }

  setConfig(config) {
    this._config = config;
    this._rendered = false;   /* force re-render when config changes */
  }

  getCardSize() { return 9; }

  /* ── entity helpers ─────────────────────────────────────── */
  _entity(domain, suffix) {
    var prefix = this._config.entity_prefix || "";
    if (!prefix) return null;
    var id = domain + "." + prefix + "_" + suffix;
    return (this._hass && this._hass.states) ? this._hass.states[id] || null : null;
  }
  _state(suffix) {
    var e = this._entity("sensor", suffix);
    return e ? e.state : "—";
  }
  _binaryState(suffix) {
    var e = this._entity("binary_sensor", suffix);
    return e ? e.state : "off";
  }
  _unit(suffix) {
    var e = this._entity("sensor", suffix);
    return (e && e.attributes && e.attributes.unit_of_measurement) || "";
  }

  /* ── render ────────────────────────────────────────────── */
  _ensureRendered() {
    if (this._rendered) return;
    /* Tear down previous shadow */
    if (this.shadowRoot) {
      this.shadowRoot.innerHTML = "";
    } else {
      this.attachShadow({ mode: "open" });
    }
    this._buildCard();
    this._rendered = true;
  }

  _buildCard() {
    var c = this._config;
    var shadow = this.shadowRoot;

    /* Resolve all layout values from config (with defaults) */
    var sb_l = _v(c,"sb_left"),  sb_t = _v(c,"sb_top"),  sb_w = _v(c,"sb_width"),  sb_h = _v(c,"sb_height"), sb_f = _v(c,"sb_font");
    var lcd_l= _v(c,"lcd_left"), lcd_t= _v(c,"lcd_top"), lcd_w= _v(c,"lcd_width"), lcd_h= _v(c,"lcd_height"),lcd_f= _v(c,"lcd_font");
    var led_sz = _v(c,"led_size");

    /* ── CSS ── */
    var style = document.createElement("style");
    style.textContent = `
:host { display:block; }
ha-card { overflow:hidden; border-radius:12px; background:#2c2c2c; }
.hdr { display:flex; align-items:center; justify-content:space-between; background:#FFCC00; color:#1a1a1a; padding:6px 14px; font:700 14px/1.2 'Segoe UI',Arial,sans-serif; }
.hdr .b { font-size:11px; font-weight:400; opacity:.7; }
.panel { position:relative; width:100%; padding-bottom:${(SC2_H/SC2_W*100).toFixed(4)}%; background:url('${IMG_BASE}/sc2.jpg') center/100% 100% no-repeat; overflow:hidden; }
.inner { position:absolute; inset:0; }
.sb { position:absolute; left:${_pctX(sb_l)}; top:${_pctY(sb_t)}; width:${_pctX(sb_w)}; height:${_pctY(sb_h)}; background:#000; overflow:hidden; }
.sb span { position:absolute; top:0; height:100%; display:flex; align-items:center; font:normal ${sb_f}px/1 'Courier New','Arial Unicode MS',monospace; color:#fff; white-space:nowrap; }
.lcd { position:absolute; left:${_pctX(lcd_l)}; top:${_pctY(lcd_t)}; width:${_pctX(lcd_w)}; height:${_pctY(lcd_h)}; overflow:hidden; }
.ln { position:relative; box-sizing:border-box; }
.ln span { position:absolute; top:0; height:100%; display:flex; align-items:center; font:normal ${lcd_f}px/1 'Courier New','Arial Unicode MS',monospace; color:#454545; white-space:nowrap; overflow:hidden; }
.sb span, .ln span { font-size:clamp(6px, 2.13cqw, ${Math.max(sb_f,lcd_f)}px); }
@supports not (font-size:1cqw) { .sb span, .ln span { font-size:clamp(6px, 2.13vw, ${Math.max(sb_f,lcd_f)}px); } }
.led { position:absolute; width:${_pctX(led_sz)}; height:${_pctY(led_sz)}; }
.led.flash { animation:blink .6s infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.12} }
.ft { padding:4px 14px; font:400 10px/1.4 'Segoe UI',Arial,sans-serif; color:#636e72; text-align:right; }
`;
    shadow.appendChild(style);

    var card = document.createElement("ha-card");

    /* Header */
    var title = c.title || "Kaeser SC2";
    var hdr = document.createElement("div"); hdr.className = "hdr";
    hdr.innerHTML = "<span>" + this._esc(title) + "</span><span class='b'>KAESER SIGMA CONTROL 2</span>";
    card.appendChild(hdr);

    /* Panel */
    var panel = document.createElement("div"); panel.className = "panel";
    var inner = document.createElement("div"); inner.className = "inner";

    /* Status bar */
    var sb = document.createElement("div"); sb.className = "sb";
    var sbW = sb_w;
    function sp(left, width, id, align) {
      return "<span id='" + id + "' style='left:" + (left/sbW*100).toFixed(2) + "%;width:" + (width/sbW*100).toFixed(2) + "%;justify-content:" + (align||"flex-end") + "'></span>";
    }
    sb.innerHTML = sp(0,80,"sb-p") + sp(120,70,"sb-t") + sp(250,95,"sb-d");
    inner.appendChild(sb);

    /* LCD content — 8 lines */
    var lcd = document.createElement("div"); lcd.className = "lcd";
    var lW = lcd_w;
    function lp(left,width,id,align,text) {
      var s = "left:" + (left/lW*100).toFixed(2) + "%;width:" + (width/lW*100).toFixed(2) + "%";
      if (align) s += ";justify-content:" + align;
      var inner = text || "";
      return "<span " + (id ? "id='"+id+"'" : "") + " style='" + s + "'>" + inner + "</span>";
    }
    var sep = "<span style='left:0;width:100%'>------------------------------</span>";

    var lines = [
      sep,
      lp(0, lW, "lcd-st", "flex-start"),
      sep,
      lp(0,70,null,null,"Key") + lp(80,10,null,null,"-") + lp(100,40,"lcd-key") + lp(150,10,null,null,"¦") + lp(160,20,null,"flex-end","pA") + lp(190,10,null,null,"-") + lp(210,135,"lcd-pa"),
      sep,
      lp(160,60,null,null,"Run") + lp(230,115,"lcd-run","flex-end"),
      lp(160,60,null,null,"Load") + lp(230,115,"lcd-load","flex-end"),
      lp(0,220,null,null,"Maintenance in") + lp(230,115,"lcd-mt","flex-end"),
    ];
    var lineH = (100 / lines.length).toFixed(3) + "%";
    for (var i = 0; i < lines.length; i++) {
      var d = document.createElement("div"); d.className = "ln";
      d.style.height = lineH;
      d.innerHTML = lines[i];
      /* Tag the Load line so we can hide it when load_hours is unavailable */
      if (i === 6) d.id = "ln-load";
      lcd.appendChild(d);
    }
    inner.appendChild(lcd);

    /* LEDs */
    for (var li = 0; li < LED_NAMES.length; li++) {
      var name = LED_NAMES[li];
      var lx = _v(c, name + "_x");
      var ly = _v(c, name + "_y");
      var img = document.createElement("img");
      img.className = "led";
      img.id = "led-" + name;
      img.src = IMG_BASE + "/led_off.png";
      img.style.left = _pctX(lx);
      img.style.top  = _pctY(ly);
      inner.appendChild(img);
    }

    panel.appendChild(inner);
    card.appendChild(panel);

    /* Footer */
    var ft = document.createElement("div"); ft.className = "ft";
    ft.textContent = "kaeser-sc2-card v" + CARD_VERSION;
    card.appendChild(ft);

    shadow.appendChild(card);
  }

  _esc(s) { var d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

  /* ── refresh ───────────────────────────────────────────── */
  _refresh() {
    if (!this.shadowRoot) return;
    var self = this;
    function $(id) { return self.shadowRoot.getElementById(id); }

    var p  = this._state("pressure"), pU = this._unit("pressure") || "psi";
    var t  = this._state("temperature"), tU = this._unit("temperature") || "°F";
    var tm = this._state("controller_time");

    var sbP = $("sb-p"), sbT = $("sb-t"), sbD = $("sb-d");
    if (sbP) sbP.textContent = _clean(p)  ? p + pU : "";
    if (sbT) sbT.textContent = _clean(tm) || "";
    if (sbD) sbD.textContent = _clean(t)  ? t + tU : "";

    var lcdSt = $("lcd-st"); if (lcdSt) lcdSt.textContent = _clean(this._state("state"));
    var lcdKy = $("lcd-key"); if (lcdKy) lcdKy.textContent = _clean(this._state("key_switch"));
    var lcdPa = $("lcd-pa"); if (lcdPa) lcdPa.textContent = _clean(this._state("pa_status"));
    var lcdRn = $("lcd-run"); if (lcdRn) lcdRn.textContent = _hVal(this._state("run_hours"));
    var loadRaw = this._state("load_hours");
    var lcdLd = $("lcd-load"); if (lcdLd) lcdLd.textContent = _hVal(loadRaw);
    /* Hide the entire Load line when load_hours is unavailable */
    var lnLoad = $("ln-load");
    if (lnLoad) lnLoad.style.display = _clean(loadRaw) ? "" : "none";
    var lcdMt = $("lcd-mt"); if (lcdMt) lcdMt.textContent = _hVal(this._state("maintenance_in"));

    for (var li = 0; li < LED_NAMES.length; li++) {
      var name = LED_NAMES[li];
      var img = $("led-" + name);
      if (!img) continue;
      var raw = this._binaryState(name);
      var ent = this._entity("binary_sensor", name);
      var ledRaw = (ent && ent.attributes) ? (ent.attributes.led_raw_state || "") : "";
      if (raw === "on" || ledRaw === "flash") {
        img.src = IMG_BASE + "/led_" + (LED_COLOURS[name]||"green") + ".png";
        img.classList.toggle("flash", ledRaw === "flash");
      } else {
        img.src = IMG_BASE + "/led_off.png";
        img.classList.remove("flash");
      }
    }
  }
}


/* ╔═══════════════════════════════════════════════════════════════╗
 * ║                   VISUAL CONFIG EDITOR                       ║
 * ╚═══════════════════════════════════════════════════════════════╝ */
class KaeserSC2CardEditor extends HTMLElement {

  set hass(hass) { this._hass = hass; }

  setConfig(config) {
    this._config = Object.assign({}, config);
    this._render();
  }

  /* ── fire config-changed ── */
  _fire() {
    var ev = new CustomEvent("config-changed", {
      detail: { config: Object.assign({}, this._config) },
      bubbles: true, composed: true,
    });
    this.dispatchEvent(ev);
  }

  /* ── build editor UI ── */
  _render() {
    this.innerHTML = "";

    var root = document.createElement("div");
    root.style.cssText = "padding:16px; font-family:'Segoe UI',Arial,sans-serif; font-size:14px; color:var(--primary-text-color,#333);";

    /* ── Section: General ── */
    root.appendChild(this._heading("General"));
    root.appendChild(this._textField("title", "Card Title", "Kaeser SC2"));
    root.appendChild(this._textField("entity_prefix", "Entity Prefix", "shop_air_compressor",
      "The prefix used for all entities (e.g. if your sensor is sensor.my_comp_pressure, enter my_comp)"));

    /* ── Section: Status Bar ── */
    root.appendChild(this._heading("Status Bar Position & Size"));
    root.appendChild(this._row([
      this._numField("sb_left","Left",DEFAULTS.sb_left),
      this._numField("sb_top","Top",DEFAULTS.sb_top),
      this._numField("sb_width","Width",DEFAULTS.sb_width),
      this._numField("sb_height","Height",DEFAULTS.sb_height),
    ]));
    root.appendChild(this._row([
      this._numField("sb_font","Font Size (px)",DEFAULTS.sb_font),
    ]));

    /* ── Section: LCD Content ── */
    root.appendChild(this._heading("LCD Content Position & Size"));
    root.appendChild(this._row([
      this._numField("lcd_left","Left",DEFAULTS.lcd_left),
      this._numField("lcd_top","Top",DEFAULTS.lcd_top),
      this._numField("lcd_width","Width",DEFAULTS.lcd_width),
      this._numField("lcd_height","Height",DEFAULTS.lcd_height),
    ]));
    root.appendChild(this._row([
      this._numField("lcd_font","Font Size (px)",DEFAULTS.lcd_font),
    ]));

    /* ── Section: LED Size ── */
    root.appendChild(this._heading("LED Indicators"));
    root.appendChild(this._row([
      this._numField("led_size","LED Size (px)",DEFAULTS.led_size),
    ]));

    /* ── Section: Individual LED Positions ── */
    root.appendChild(this._heading("LED Positions (px in 750×493 image)"));
    for (var i = 0; i < LED_NAMES.length; i++) {
      var name = LED_NAMES[i];
      var label = LED_LABELS[name] || name;
      root.appendChild(this._row([
        this._labelEl(label),
        this._numField(name + "_x", "X", DEFAULTS[name + "_x"]),
        this._numField(name + "_y", "Y", DEFAULTS[name + "_y"]),
      ]));
    }

    /* ── Hint ── */
    var hint = document.createElement("div");
    hint.style.cssText = "margin-top:16px; padding:10px; background:var(--secondary-background-color,#f5f5f5); border-radius:8px; font-size:12px; line-height:1.5; color:var(--secondary-text-color,#666);";
    hint.innerHTML = "<b>Position guide:</b> All coordinates are in pixels within the 750×493 SC2 background image. "
      + "The card scales proportionally to fit the dashboard column width. "
      + "Adjust values in small increments (5–10px) and the card preview will update live.";
    root.appendChild(hint);

    this.appendChild(root);
  }

  /* ── UI builder helpers ── */
  _heading(text) {
    var h = document.createElement("div");
    h.textContent = text;
    h.style.cssText = "font-weight:700; font-size:15px; margin:18px 0 8px 0; padding-bottom:4px; border-bottom:1px solid var(--divider-color,#ddd);";
    return h;
  }

  _row(children) {
    var r = document.createElement("div");
    r.style.cssText = "display:flex; gap:10px; margin-bottom:8px; align-items:flex-end; flex-wrap:wrap;";
    for (var i = 0; i < children.length; i++) r.appendChild(children[i]);
    return r;
  }

  _labelEl(text) {
    var d = document.createElement("div");
    d.textContent = text;
    d.style.cssText = "min-width:90px; font-size:13px; padding-bottom:6px;";
    return d;
  }

  _textField(key, label, placeholder, helpText) {
    var self = this;
    var wrap = document.createElement("div");
    wrap.style.cssText = "margin-bottom:10px;";

    var lbl = document.createElement("label");
    lbl.textContent = label;
    lbl.style.cssText = "display:block; font-size:12px; font-weight:600; margin-bottom:4px; color:var(--primary-text-color,#333);";
    wrap.appendChild(lbl);

    var inp = document.createElement("input");
    inp.type = "text";
    inp.value = this._config[key] || "";
    inp.placeholder = placeholder || "";
    inp.style.cssText = "width:100%; max-width:400px; padding:8px 10px; border:1px solid var(--divider-color,#ccc); border-radius:6px; font-size:14px; background:var(--card-background-color,#fff); color:var(--primary-text-color,#333); box-sizing:border-box;";
    inp.addEventListener("input", function() {
      self._config[key] = this.value;
      self._fire();
    });
    wrap.appendChild(inp);

    if (helpText) {
      var ht = document.createElement("div");
      ht.textContent = helpText;
      ht.style.cssText = "font-size:11px; color:var(--secondary-text-color,#888); margin-top:3px;";
      wrap.appendChild(ht);
    }
    return wrap;
  }

  _numField(key, label, defaultVal) {
    var self = this;
    var wrap = document.createElement("div");
    wrap.style.cssText = "display:flex; flex-direction:column; min-width:70px; max-width:100px;";

    var lbl = document.createElement("label");
    lbl.textContent = label;
    lbl.style.cssText = "font-size:11px; font-weight:600; margin-bottom:3px; color:var(--secondary-text-color,#666);";
    wrap.appendChild(lbl);

    var inp = document.createElement("input");
    inp.type = "number";
    inp.step = "1";
    var current = this._config[key];
    inp.value = (current !== undefined && current !== null && current !== "") ? current : "";
    inp.placeholder = String(defaultVal);
    inp.style.cssText = "width:100%; padding:6px 8px; border:1px solid var(--divider-color,#ccc); border-radius:6px; font-size:13px; background:var(--card-background-color,#fff); color:var(--primary-text-color,#333); box-sizing:border-box;";
    inp.addEventListener("input", function() {
      if (this.value === "" || this.value === String(defaultVal)) {
        delete self._config[key];
      } else {
        self._config[key] = Number(this.value);
      }
      self._fire();
    });
    wrap.appendChild(inp);
    return wrap;
  }
}


/* ╔═══════════════════════════════════════════════════════════════╗
 * ║                     REGISTRATION                             ║
 * ╚═══════════════════════════════════════════════════════════════╝ */
customElements.define("kaeser-sc2-card", KaeserSC2Card);
customElements.define("kaeser-sc2-card-editor", KaeserSC2CardEditor);

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
