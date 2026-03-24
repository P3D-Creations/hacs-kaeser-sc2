/**
 * Kaeser Sigma Control 2 — Custom Lovelace Card  v4.0.1
 *
 * Pixel-accurate replica of the SC2 controller front panel.
 *  - Device picker dropdown in editor (auto-discovers Kaeser entities)
 *  - Editor uses change events to prevent focus loss on keypress
 *  - LED positions hardcoded from real hardware calibration
 *  - Pressure displayed as integer (no decimals, max 3 digits)
 *  - Wrapped in IIFE to prevent global scope collisions
 */
(function () {
  "use strict";

  var CARD_VERSION = "4.0.1";

  /* ── Card-picker registration — MUST run before the guard ──────
   * If the browser has a cached old version that already called
   * customElements.define(), the guard below would exit the IIFE
   * and skip window.customCards.push(), causing "card does not exist".
   * Registering FIRST guarantees the picker always knows about us.
   * ─────────────────────────────────────────────────────────────── */
  window.customCards = window.customCards || [];
  if (!window.customCards.some(function(c) { return c.type === "kaeser-sc2-card"; })) {
    window.customCards.push({
      type: "kaeser-sc2-card",
      name: "Kaeser Sigma Control 2",
      description: "Pixel-accurate replica of the SC2 controller front panel with live data and LEDs.",
      preview: false,
      documentationURL: "https://github.com/P3D-Creations/hacs-kaeser-sc2"
    });
  }

  console.info(
    "%c KAESER-SC2-CARD %c v" + CARD_VERSION + " ",
    "color:#fff;background:#1a1a1a;font-weight:700;padding:2px 6px;border-radius:4px 0 0 4px",
    "color:#1a1a1a;background:#FFCC00;font-weight:700;padding:2px 6px;border-radius:0 4px 4px 0"
  );

  /* Guard against double customElements.define (throws if called twice) */
  if (customElements.get("kaeser-sc2-card")) return;

  var IMG_BASE = "/kaeser_sc2/images";

  /* ═══════════════════════════════════════════════════════════════
   * Layout constants (px at 750×493 native)
   * ═══════════════════════════════════════════════════════════════ */
  var DEFAULTS = {
    sb_left: 198,  sb_top: 88,  sb_width: 345, sb_height: 20,
    sb_font: 16,
    lcd_left: 198, lcd_top: 110, lcd_width: 345, lcd_height: 155,
    lcd_font: 16
  };

  /* LED positions — calibrated to real hardware, not configurable */
  var LED_SIZE = 13;
  var LED_POS = {
    led_error:       { x: 43,  y: 44  },
    led_com_error:   { x: 43,  y: 107 },
    led_maintenance: { x: 43,  y: 165 },
    led_voltage:     { x: 43,  y: 250 },
    led_load:        { x: 43,  y: 378 },
    led_idle:        { x: 43,  y: 412 },
    led_remote:      { x: 225, y: 376 },
    led_clock:       { x: 300, y: 376 },
    led_power_on:    { x: 643, y: 311 }
  };

  var SC2_W = 750;
  var SC2_H = 493;

  var LED_NAMES = [
    "led_error","led_com_error","led_maintenance","led_voltage",
    "led_load","led_idle","led_remote","led_clock","led_power_on"
  ];
  var LED_COLOURS = {
    led_error:"red", led_com_error:"red", led_maintenance:"orange",
    led_voltage:"green", led_load:"green", led_idle:"green",
    led_remote:"green", led_clock:"green", led_power_on:"green"
  };

  /* helpers */
  function _v(cfg, key) {
    if (cfg && cfg[key] !== undefined && cfg[key] !== null && cfg[key] !== "") {
      return Number(cfg[key]);
    }
    return DEFAULTS[key] !== undefined ? DEFAULTS[key] : 0;
  }
  function _pctX(px) { return (px / SC2_W * 100).toFixed(3) + "%"; }
  function _pctY(px) { return (px / SC2_H * 100).toFixed(3) + "%"; }
  function _clean(val) {
    return (!val || val === "\u2014" || val === "unknown" || val === "unavailable") ? "" : val;
  }
  function _hVal(val) {
    return (!val || val === "\u2014" || val === "unknown" || val === "unavailable") ? "" : val + "h";
  }
  function _intPressure(val) {
    if (!_clean(val)) return "";
    var n = parseFloat(val);
    return isNaN(n) ? val : String(Math.round(n));
  }

  /* ╔═══════════════════════════════════════════════════════════════╗
   * ║                     MAIN CARD CLASS                          ║
   * ╚═══════════════════════════════════════════════════════════════╝ */
  class KaeserSC2Card extends HTMLElement {

    constructor() {
      super();
      this._config = null;
      this._hass = null;
      this._rendered = false;
      this.attachShadow({ mode: "open" });
    }

    static getConfigElement() {
      return document.createElement("kaeser-sc2-card-editor");
    }
    static getStubConfig() {
      return { entity_prefix: "", title: "Kaeser SC2" };
    }

    set hass(hass) {
      this._hass = hass;
      if (!this._config) return;
      try {
        this._ensureRendered();
        this._refresh();
      } catch (e) {
        console.error("[kaeser-sc2-card] render error:", e);
      }
    }

    setConfig(config) {
      if (!config) throw new Error("Invalid configuration");
      this._config = config;
      this._rendered = false;
    }

    getCardSize() { return 9; }

    /* ── entity helpers ── */
    _entity(domain, suffix) {
      var prefix = this._config.entity_prefix || "";
      if (!prefix) return null;
      var id = domain + "." + prefix + "_" + suffix;
      return (this._hass && this._hass.states) ? this._hass.states[id] || null : null;
    }
    _state(suffix) {
      var e = this._entity("sensor", suffix);
      return e ? e.state : "\u2014";
    }
    _binaryState(suffix) {
      var e = this._entity("binary_sensor", suffix);
      return e ? e.state : "off";
    }
    _unit(suffix) {
      var e = this._entity("sensor", suffix);
      return (e && e.attributes && e.attributes.unit_of_measurement) || "";
    }

    /* ── render ── */
    _ensureRendered() {
      if (this._rendered) return;
      this.shadowRoot.innerHTML = "";
      this._buildCard();
      this._rendered = true;
    }

    _buildCard() {
      var c = this._config;
      var shadow = this.shadowRoot;

      var sb_l = _v(c,"sb_left"),  sb_t = _v(c,"sb_top"),  sb_w = _v(c,"sb_width"),  sb_h = _v(c,"sb_height"), sb_f = _v(c,"sb_font");
      var lcd_l= _v(c,"lcd_left"), lcd_t= _v(c,"lcd_top"), lcd_w= _v(c,"lcd_width"), lcd_h= _v(c,"lcd_height"),lcd_f= _v(c,"lcd_font");

      var style = document.createElement("style");
      style.textContent =
        ":host{display:block}" +
        "ha-card{overflow:hidden;border-radius:12px;background:#2c2c2c}" +
        ".hdr{display:flex;align-items:center;justify-content:space-between;background:#FFCC00;color:#1a1a1a;padding:6px 14px;font:700 14px/1.2 'Segoe UI',Arial,sans-serif}" +
        ".hdr .b{font-size:11px;font-weight:400;opacity:.7}" +
        ".panel{position:relative;width:100%;padding-bottom:" + (SC2_H/SC2_W*100).toFixed(4) + "%;background:url('" + IMG_BASE + "/sc2.jpg') center/100% 100% no-repeat;overflow:hidden}" +
        ".inner{position:absolute;inset:0}" +
        ".sb{position:absolute;left:" + _pctX(sb_l) + ";top:" + _pctY(sb_t) + ";width:" + _pctX(sb_w) + ";height:" + _pctY(sb_h) + ";background:#000;overflow:hidden}" +
        ".sb span{position:absolute;top:0;height:100%;display:flex;align-items:center;font:normal " + sb_f + "px/1 'Courier New','Arial Unicode MS',monospace;color:#fff;white-space:nowrap}" +
        ".lcd{position:absolute;left:" + _pctX(lcd_l) + ";top:" + _pctY(lcd_t) + ";width:" + _pctX(lcd_w) + ";height:" + _pctY(lcd_h) + ";overflow:hidden}" +
        ".ln{position:relative;box-sizing:border-box}" +
        ".ln span{position:absolute;top:0;height:100%;display:flex;align-items:center;font:normal " + lcd_f + "px/1 'Courier New','Arial Unicode MS',monospace;color:#454545;white-space:nowrap;overflow:hidden}" +
        ".sb span,.ln span{font-size:clamp(6px,2.13vw," + Math.max(sb_f,lcd_f) + "px)}" +
        ".led{position:absolute;width:" + _pctX(LED_SIZE) + ";height:" + _pctY(LED_SIZE) + "}" +
        ".led.flash{animation:blink .6s infinite}" +
        "@keyframes blink{0%,100%{opacity:1}50%{opacity:.12}}" +
        ".ft{padding:4px 14px;font:400 10px/1.4 'Segoe UI',Arial,sans-serif;color:#636e72;text-align:right}";
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

      /* Status bar — pressure (left) | clock (center) | temperature (right) */
      var sb = document.createElement("div"); sb.className = "sb";
      var sbW = sb_w;
      function sp(left, width, id, align) {
        return "<span id='" + id + "' style='left:" + (left/sbW*100).toFixed(2) + "%;width:" + (width/sbW*100).toFixed(2) + "%;justify-content:" + (align||"flex-end") + "'></span>";
      }
      sb.innerHTML =
        sp(4, 115, "sb-p", "flex-start") +
        sp(120, 100, "sb-t", "center") +
        sp(245, 100, "sb-d", "flex-end");
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
        lp(5, lW - 5, "lcd-st", "flex-start"),
        sep,
        lp(5,60,null,null,"Key") + lp(65,15,null,null,"-") + lp(80,55,"lcd-key","flex-start") +
          lp(140,10,null,null,"\u00a6") +
          lp(155,25,null,"flex-start","pA") + lp(180,15,null,null,"-") + lp(200,140,"lcd-pa","flex-start"),
        sep,
        lp(160,60,null,null,"Run") + lp(230,115,"lcd-run","flex-end"),
        lp(160,60,null,null,"Load") + lp(230,115,"lcd-load","flex-end"),
        lp(5,220,null,null,"Maintenance in") + lp(230,115,"lcd-mt","flex-end")
      ];
      var lineH = (100 / lines.length).toFixed(3) + "%";
      for (var i = 0; i < lines.length; i++) {
        var d = document.createElement("div"); d.className = "ln";
        d.style.height = lineH;
        d.innerHTML = lines[i];
        if (i === 6) d.id = "ln-load";
        lcd.appendChild(d);
      }
      inner.appendChild(lcd);

      /* LEDs — hardcoded positions */
      for (var li = 0; li < LED_NAMES.length; li++) {
        var name = LED_NAMES[li];
        var pos = LED_POS[name];
        if (!pos) continue;
        var img = document.createElement("img");
        img.className = "led";
        img.id = "led-" + name;
        img.src = IMG_BASE + "/led_off.png";
        img.style.left = _pctX(pos.x);
        img.style.top  = _pctY(pos.y);
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

    /* ── refresh ── */
    _refresh() {
      if (!this.shadowRoot) return;
      var self = this;
      function $(id) { return self.shadowRoot.getElementById(id); }

      /* Pressure — integer, no decimals, max 3 digits */
      var p  = this._state("pressure"), pU = this._unit("pressure") || "psi";
      var pFmt = _intPressure(p);

      var t  = this._state("temperature"), tU = this._unit("temperature") || "\u00b0F";
      var tm = this._state("controller_time");

      var sbP = $("sb-p"), sbT = $("sb-t"), sbD = $("sb-d");
      if (sbP) sbP.textContent = pFmt ? pFmt + " " + pU : "";
      if (sbT) sbT.textContent = _clean(tm) || "";
      if (sbD) sbD.textContent = _clean(t)  ? t + tU : "";

      var lcdSt = $("lcd-st"); if (lcdSt) lcdSt.textContent = _clean(this._state("state"));
      var lcdKy = $("lcd-key"); if (lcdKy) lcdKy.textContent = _clean(this._state("key_switch"));
      var lcdPa = $("lcd-pa"); if (lcdPa) lcdPa.textContent = _clean(this._state("pa_status"));
      var lcdRn = $("lcd-run"); if (lcdRn) lcdRn.textContent = _hVal(this._state("run_hours"));
      var loadRaw = this._state("load_hours");
      var lcdLd = $("lcd-load"); if (lcdLd) lcdLd.textContent = _hVal(loadRaw);
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

    constructor() {
      super();
      this._config = {};
      this._hass = null;
      this._rendered = false;
      this._internalChange = false;
    }

    set hass(hass) {
      var hadHass = !!this._hass;
      this._hass = hass;
      /* First time we get hass — (re)render to populate device list */
      if (!hadHass && this._config) {
        this._render();
        this._rendered = true;
      }
    }

    setConfig(config) {
      this._config = Object.assign({}, config);
      /* Skip re-render when we triggered the change ourselves */
      if (this._internalChange) {
        this._internalChange = false;
        return;
      }
      this._render();
      this._rendered = true;
    }

    _fire() {
      this._internalChange = true;
      this.dispatchEvent(new CustomEvent("config-changed", {
        detail: { config: Object.assign({}, this._config) },
        bubbles: true, composed: true
      }));
    }

    /* ── Auto-discover Kaeser devices from hass.states ── */
    _findKaeserDevices() {
      var devices = {};
      if (!this._hass || !this._hass.states) return [];
      var suffixes = ["_pressure", "_temperature", "_state", "_run_hours", "_controller_time"];
      var labelSuffixes = [" Pressure", " Temperature", " State", " Run Hours", " Controller Time"];

      for (var entityId in this._hass.states) {
        if (!entityId.startsWith("sensor.")) continue;
        var name = entityId.substring(7); /* strip "sensor." */
        for (var i = 0; i < suffixes.length; i++) {
          if (name.endsWith(suffixes[i])) {
            var prefix = name.substring(0, name.length - suffixes[i].length);
            if (!devices[prefix]) devices[prefix] = { count: 0, friendlyName: "" };
            devices[prefix].count++;
            /* Extract friendly device name from entity attributes */
            if (!devices[prefix].friendlyName) {
              var ent = this._hass.states[entityId];
              if (ent && ent.attributes && ent.attributes.friendly_name) {
                var fn = ent.attributes.friendly_name;
                for (var j = 0; j < labelSuffixes.length; j++) {
                  if (fn.endsWith(labelSuffixes[j])) {
                    devices[prefix].friendlyName = fn.substring(0, fn.length - labelSuffixes[j].length);
                    break;
                  }
                }
              }
            }
            break;
          }
        }
      }

      /* Keep only prefixes that match at least 3 of our known suffixes */
      var result = [];
      for (var p in devices) {
        if (devices[p].count >= 3) {
          result.push({
            prefix: p,
            name: devices[p].friendlyName || p.replace(/_/g, " ")
          });
        }
      }
      return result.sort(function(a, b) { return a.prefix.localeCompare(b.prefix); });
    }

    _render() {
      this.innerHTML = "";
      var self = this;

      var root = document.createElement("div");
      root.style.cssText = "padding:16px;font-family:'Segoe UI',Arial,sans-serif;font-size:14px;color:var(--primary-text-color,#333)";

      /* ── General ─────────────────────────────────────────── */
      root.appendChild(this._heading("General"));
      root.appendChild(this._textField("title", "Card Title", "Kaeser SC2"));

      /* ── Device Picker ───────────────────────────────────── */
      var devWrap = document.createElement("div");
      devWrap.style.cssText = "margin-bottom:12px";
      var devLabel = document.createElement("label");
      devLabel.textContent = "Compressor";
      devLabel.style.cssText = "display:block;font-size:12px;font-weight:600;margin-bottom:4px;color:var(--primary-text-color,#333)";
      devWrap.appendChild(devLabel);

      var devices = this._findKaeserDevices();
      var currentPrefix = this._config.entity_prefix || "";
      var isCustom = true;

      var select = document.createElement("select");
      select.style.cssText = "width:100%;max-width:400px;padding:8px 10px;border:1px solid var(--divider-color,#ccc);border-radius:6px;font-size:14px;background:var(--card-background-color,#fff);color:var(--primary-text-color,#333);box-sizing:border-box";

      var optBlank = document.createElement("option");
      optBlank.value = "";
      optBlank.textContent = "-- Select a compressor --";
      select.appendChild(optBlank);

      for (var i = 0; i < devices.length; i++) {
        var opt = document.createElement("option");
        opt.value = devices[i].prefix;
        opt.textContent = devices[i].name + "  (" + devices[i].prefix + ")";
        if (currentPrefix === devices[i].prefix) { opt.selected = true; isCustom = false; }
        select.appendChild(opt);
      }

      var optCustom = document.createElement("option");
      optCustom.value = "__custom__";
      optCustom.textContent = "Custom prefix\u2026";
      if (isCustom && currentPrefix) optCustom.selected = true;
      select.appendChild(optCustom);

      /* Manual prefix input — hidden unless "Custom" is chosen */
      var manualInput = document.createElement("input");
      manualInput.type = "text";
      manualInput.value = (isCustom && currentPrefix) ? currentPrefix : "";
      manualInput.placeholder = "my_compressor";
      manualInput.style.cssText = "width:100%;max-width:400px;padding:8px 10px;border:1px solid var(--divider-color,#ccc);border-radius:6px;font-size:14px;background:var(--card-background-color,#fff);color:var(--primary-text-color,#333);box-sizing:border-box;margin-top:6px;display:" + ((isCustom && currentPrefix) ? "block" : "none");

      select.addEventListener("change", function() {
        if (this.value === "__custom__") {
          manualInput.style.display = "block";
          manualInput.focus();
        } else {
          manualInput.style.display = "none";
          self._config.entity_prefix = this.value;
          self._fire();
        }
      });

      /* change event fires on blur — does NOT steal focus mid-typing */
      manualInput.addEventListener("change", function() {
        self._config.entity_prefix = this.value;
        self._fire();
      });

      devWrap.appendChild(select);
      devWrap.appendChild(manualInput);

      var devHelp = document.createElement("div");
      devHelp.textContent = "The prefix shared by all entities for this compressor (e.g. sensor.PREFIX_pressure).";
      devHelp.style.cssText = "font-size:11px;color:var(--secondary-text-color,#888);margin-top:3px";
      devWrap.appendChild(devHelp);
      root.appendChild(devWrap);

      /* ── Advanced layout (collapsible) ───────────────────── */
      var details = document.createElement("details");
      details.style.cssText = "margin-top:12px";
      var summary = document.createElement("summary");
      summary.textContent = "Advanced Layout";
      summary.style.cssText = "cursor:pointer;font-weight:700;font-size:15px;padding-bottom:4px;border-bottom:1px solid var(--divider-color,#ddd);user-select:none";
      details.appendChild(summary);

      var advInner = document.createElement("div");
      advInner.style.cssText = "padding-top:10px";

      advInner.appendChild(this._subHeading("Status Bar Position & Size"));
      advInner.appendChild(this._row([
        this._numField("sb_left","Left",DEFAULTS.sb_left),
        this._numField("sb_top","Top",DEFAULTS.sb_top),
        this._numField("sb_width","Width",DEFAULTS.sb_width),
        this._numField("sb_height","Height",DEFAULTS.sb_height)
      ]));
      advInner.appendChild(this._row([
        this._numField("sb_font","Font (px)",DEFAULTS.sb_font)
      ]));

      advInner.appendChild(this._subHeading("LCD Content Position & Size"));
      advInner.appendChild(this._row([
        this._numField("lcd_left","Left",DEFAULTS.lcd_left),
        this._numField("lcd_top","Top",DEFAULTS.lcd_top),
        this._numField("lcd_width","Width",DEFAULTS.lcd_width),
        this._numField("lcd_height","Height",DEFAULTS.lcd_height)
      ]));
      advInner.appendChild(this._row([
        this._numField("lcd_font","Font (px)",DEFAULTS.lcd_font)
      ]));

      var hint = document.createElement("div");
      hint.style.cssText = "margin-top:10px;padding:10px;background:var(--secondary-background-color,#f5f5f5);border-radius:8px;font-size:12px;line-height:1.5;color:var(--secondary-text-color,#666)";
      hint.textContent = "All coordinates are in pixels within the 750\u00d7493 SC2 background image. The card scales proportionally to fit the dashboard column width.";
      advInner.appendChild(hint);

      details.appendChild(advInner);
      root.appendChild(details);

      this.appendChild(root);
    }

    _heading(text) {
      var h = document.createElement("div");
      h.textContent = text;
      h.style.cssText = "font-weight:700;font-size:15px;margin:18px 0 8px 0;padding-bottom:4px;border-bottom:1px solid var(--divider-color,#ddd)";
      return h;
    }

    _subHeading(text) {
      var h = document.createElement("div");
      h.textContent = text;
      h.style.cssText = "font-weight:600;font-size:13px;margin:12px 0 6px 0;color:var(--secondary-text-color,#666)";
      return h;
    }

    _row(children) {
      var r = document.createElement("div");
      r.style.cssText = "display:flex;gap:10px;margin-bottom:8px;align-items:flex-end;flex-wrap:wrap";
      for (var i = 0; i < children.length; i++) r.appendChild(children[i]);
      return r;
    }

    _textField(key, label, placeholder) {
      var self = this;
      var wrap = document.createElement("div");
      wrap.style.cssText = "margin-bottom:10px";

      var lbl = document.createElement("label");
      lbl.textContent = label;
      lbl.style.cssText = "display:block;font-size:12px;font-weight:600;margin-bottom:4px;color:var(--primary-text-color,#333)";
      wrap.appendChild(lbl);

      var inp = document.createElement("input");
      inp.type = "text";
      inp.value = this._config[key] || "";
      inp.placeholder = placeholder || "";
      inp.style.cssText = "width:100%;max-width:400px;padding:8px 10px;border:1px solid var(--divider-color,#ccc);border-radius:6px;font-size:14px;background:var(--card-background-color,#fff);color:var(--primary-text-color,#333);box-sizing:border-box";
      /* change fires on blur — preserves focus while typing */
      inp.addEventListener("change", function() {
        self._config[key] = this.value;
        self._fire();
      });
      wrap.appendChild(inp);
      return wrap;
    }

    _numField(key, label, defaultVal) {
      var self = this;
      var wrap = document.createElement("div");
      wrap.style.cssText = "display:flex;flex-direction:column;min-width:70px;max-width:100px";

      var lbl = document.createElement("label");
      lbl.textContent = label;
      lbl.style.cssText = "font-size:11px;font-weight:600;margin-bottom:3px;color:var(--secondary-text-color,#666)";
      wrap.appendChild(lbl);

      var inp = document.createElement("input");
      inp.type = "number";
      inp.step = "1";
      var current = this._config[key];
      inp.value = (current !== undefined && current !== null && current !== "") ? current : "";
      inp.placeholder = String(defaultVal);
      inp.style.cssText = "width:100%;padding:6px 8px;border:1px solid var(--divider-color,#ccc);border-radius:6px;font-size:13px;background:var(--card-background-color,#fff);color:var(--primary-text-color,#333);box-sizing:border-box";
      /* change fires on blur — preserves focus while typing */
      inp.addEventListener("change", function() {
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

})();
