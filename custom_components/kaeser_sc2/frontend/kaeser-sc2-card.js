/**
 * Kaeser Sigma Control 2 — Custom Lovelace Card
 *
 * Pixel-accurate replica of the SC2 controller front panel.
 *  - Editor built on HA's ha-form with native device/entity selectors
 *  - LED positions calibrated from real hardware (native 750x513 px)
 *  - Text scales with card width via CSS container queries (cqw units)
 *  - Active-message popup + hamburger button (dismiss / recent-list view)
 *  - Renders full skeleton on setConfig without waiting for hass
 *  - Wrapped in IIFE to prevent global scope collisions
 */
(function () {
  "use strict";

  var CARD_VERSION = "5.3.0";

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

  /* ── Deferred definition ─────────────────────────────────────────
   * HA's app bundle installs the scoped custom-element-registry
   * polyfill, which replaces window.customElements with a fresh
   * registry that ignores anything defined natively before it. This
   * module is small and often runs before app.js; defining then makes
   * HA report "Custom element doesn't exist" (shown as "Configuration
   * error") until a lucky reload. So the classes are created and
   * defined only once the polyfill is in place, or once HA's root
   * element exists (frontends without the polyfill).
   * ─────────────────────────────────────────────────────────────── */
  var nativeRegistry = window.customElements;
  var booted = false;
  function boot() {
    if (booted) return;
    booted = true;
    if (window.customElements.get("kaeser-sc2-card")) return;
    defineCard();
  }
  if (window.CustomElementRegistryPolyfill) {
    boot();
  } else {
    nativeRegistry.whenDefined("home-assistant").then(boot);
    nativeRegistry.whenDefined("hc-main").then(boot);  /* cast receiver */
  }

  function defineCard() {
    var IMG_BASE = "/kaeser_sc2/images";

    /* ═══════════════════════════════════════════════════════════════
     * Layout constants — px at 750x513 native (measured, pixel-tight)
     *   display screen (LCD glass): x197 y90 w348 h179
     *   status bar occupies top 20px of the glass; content the rest.
     * ═══════════════════════════════════════════════════════════════ */
    var DEFAULTS = {
      sb_left: 197,  sb_top: 90,   sb_width: 348, sb_height: 20,
      sb_font: 16,
      lcd_left: 197, lcd_top: 110, lcd_width: 348, lcd_height: 159,
      lcd_font: 16
    };

    var SC2_W = 750;
    var SC2_H = 513;

    /* LED render size (native px) and measured centres */
    var LED_SIZE = 13;
    var LED_POS = {
      led_error:       { cx: 49,  cy: 53  },
      led_com_error:   { cx: 49,  cy: 116 },
      led_maintenance: { cx: 49,  cy: 179 },
      led_voltage:     { cx: 49,  cy: 266 },
      led_load:        { cx: 49,  cy: 398 },
      led_idle:        { cx: 49,  cy: 434 },
      led_remote:      { cx: 231, cy: 398 },
      led_clock:       { cx: 306, cy: 398 },
      led_power_on:    { cx: 649, cy: 331 }
    };

    /* Hamburger / acknowledge button region (native px) */
    var HAMBURGER = { x: 107, y: 48, w: 51, h: 51 };

    /* Green I / red O button regions (native px, measured) — clickable when
     * power_switch_entity is configured (switch wired to remote-control input) */
    var BTN_ON  = { x: 642, y: 324, w: 66, h: 63 };
    var BTN_OFF = { x: 642, y: 395, w: 66, h: 63 };
    /* switch-state indicator (LED + caption) below the red O button */
    var PWR_LED = { cx: 649, cy: 472 };
    var PWR_LBL = { x: 659, y: 466, w: 60, h: 13 };

    var LED_NAMES = [
      "led_error","led_com_error","led_maintenance","led_voltage",
      "led_load","led_idle","led_remote","led_clock","led_power_on"
    ];
    var LED_COLOURS = {
      led_error:"red", led_com_error:"red", led_maintenance:"orange",
      led_voltage:"green", led_load:"green", led_idle:"green",
      led_remote:"green", led_clock:"green", led_power_on:"green"
    };
    /* Preferred entity-suffix per LED (translated names); fall back to led_* */
    var LED_ENTITY_SUFFIX = {
      led_error:        "error",
      led_com_error:    "communication_error",
      led_maintenance:  "maintenance_due",
      led_voltage:      "voltage_ok",
      led_load:         "load",
      led_idle:         "idle",
      led_remote:       "remote",
      led_clock:        "clock",
      led_power_on:     "power_on"
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
    function _cqw(px)  { return (px / SC2_W * 100).toFixed(3) + "cqw"; }
    function _clean(val) {
      return (!val || val === "—" || val === "unknown" || val === "unavailable") ? "" : val;
    }
    function _hVal(val) {
      return (!val || val === "—" || val === "unknown" || val === "unavailable") ? "" : val + "h";
    }
    function _intPressure(val) {
      if (!_clean(val)) return "";
      var n = parseFloat(val);
      return isNaN(n) ? val : String(Math.round(n));
    }

    var TYPE_LABELS = { "0":"Info", "1":"Warning", "2":"Fault", "3":"System", "4":"Diagnose",
                        "I":"Info", "W":"Warning", "F":"Fault", "S":"System", "D":"Diagnose" };
    function _typeLabel(msg) {
      if (!msg) return "";
      if (msg.type_text) return String(msg.type_text);
      var t = msg.type;
      if (t === undefined || t === null || t === "") return "";
      var key = String(t);
      return TYPE_LABELS[key] || key;
    }
    function _msgId(msg) {
      if (!msg) return "";
      /* Compound key: id alone could be reused by the controller when the same
       * fault recurs later — including the event time makes a recurrence pop
       * the message up again instead of staying silently dismissed. */
      var base = "";
      if (msg.id !== undefined && msg.id !== null && msg.id !== "") base = String(msg.id);
      else if (msg.report_id !== undefined && msg.report_id !== null && msg.report_id !== "") base = String(msg.report_id);
      var when = msg.datetime || ((msg.date || "") + " " + (msg.time || "")).trim();
      if (base) return base + "|" + when;
      return String(when + "|" + (msg.message || ""));
    }
    function _msgCode(msg) {
      if (!msg) return "";
      if (msg.report_id !== undefined && msg.report_id !== null && msg.report_id !== "") return String(msg.report_id);
      if (msg.id !== undefined && msg.id !== null && msg.id !== "") return String(msg.id);
      return "";
    }
    /* Routine operational events (type 0, e.g. "Controller on") never raise
     * the popup — filtered backend-side too, but keep the card safe when it
     * runs against an older integration version. */
    function _isOperationalMsg(msg) {
      if (!msg) return false;
      var t = msg.type;
      if (t === 0 || t === "0") return true;
      return String(msg.type_text || "").toLowerCase().indexOf("operation") === 0;
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
        this._view = "normal";        /* "normal" | "history" */
        this._dismissed = null;        /* Set of dismissed active-message ids */
        this.attachShadow({ mode: "open" });
      }

      static getConfigElement() {
        return document.createElement("kaeser-sc2-card-editor");
      }
      static getStubConfig(hass) {
        /* pre-select the first compressor so the preview renders immediately */
        var prefix = "";
        var ents = (hass && hass.entities) || {};
        for (var id in ents) {
          var e = ents[id];
          if (e.platform === "kaeser_sc2" && e.translation_key === "pressure" && id.indexOf("sensor.") === 0) {
            prefix = id.slice(7, id.length - "_pressure".length);
            break;
          }
        }
        return { entity_prefix: prefix, title: "Kaeser SC2" };
      }

      set hass(hass) {
        this._hass = hass;
        if (!this._config) return;
        this._tryRender();
      }

      setConfig(config) {
        if (!config) throw new Error("Invalid configuration");
        this._config = config;
        this._rendered = false;
        this._dismissed = null;
        /* Paint the full panel skeleton IMMEDIATELY, before hass arrives */
        this._tryRender();
      }

      _tryRender() {
        try {
          this._ensureRendered();
          this._refresh();
        } catch (e) {
          console.error("[kaeser-sc2-card] render error:", e);
          this.shadowRoot.innerHTML =
            "<ha-card><div style='padding:16px;color:red;font-family:monospace'>" +
            "<b>kaeser-sc2-card error:</b><br>" + this._esc(String(e)) +
            "</div></ha-card>";
        }
      }

      getCardSize() { return 9; }
      getGridOptions() { return { columns: 12, rows: "auto" }; }

      /* ── dismissal persistence (per entity_prefix, survives refresh) ── */
      _dismissKey() {
        return "kaeser-sc2-dismissed:" + (this._config && this._config.entity_prefix || "");
      }
      _loadDismissed() {
        if (this._dismissed) return this._dismissed;
        var set = {};
        try {
          var raw = window.localStorage.getItem(this._dismissKey());
          if (raw) {
            var arr = JSON.parse(raw);
            if (arr && arr.length) for (var i = 0; i < arr.length; i++) set[String(arr[i])] = true;
          }
        } catch (e) { /* localStorage unavailable — degrade gracefully */ }
        this._dismissed = set;
        return set;
      }
      _saveDismissed() {
        try {
          var arr = [];
          for (var k in this._dismissed) if (this._dismissed.hasOwnProperty(k)) arr.push(k);
          /* cap stored ids so localStorage never grows unboundedly */
          if (arr.length > 50) arr = arr.slice(arr.length - 50);
          window.localStorage.setItem(this._dismissKey(), JSON.stringify(arr));
        } catch (e) { /* ignore */ }
      }

      /* ── entity helpers ── */
      _entity(domain, suffix) {
        var prefix = this._config.entity_prefix || "";
        if (!prefix) return null;
        var id = domain + "." + prefix + "_" + suffix;
        return (this._hass && this._hass.states) ? this._hass.states[id] || null : null;
      }
      _ledEntity(name) {
        /* prefer translated-name suffix, fall back to led_* (older installs) */
        var mapped = LED_ENTITY_SUFFIX[name];
        var e = mapped ? this._entity("binary_sensor", mapped) : null;
        if (e) return e;
        return this._entity("binary_sensor", name);
      }
      _state(suffix) {
        var e = this._entity("sensor", suffix);
        return e ? e.state : "—";
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
        var self = this;

        var sb_l = _v(c,"sb_left"),  sb_t = _v(c,"sb_top"),  sb_w = _v(c,"sb_width"),  sb_h = _v(c,"sb_height"), sb_f = _v(c,"sb_font");
        var lcd_l= _v(c,"lcd_left"), lcd_t= _v(c,"lcd_top"), lcd_w= _v(c,"lcd_width"), lcd_h= _v(c,"lcd_height"),lcd_f= _v(c,"lcd_font");

        var style = document.createElement("style");
        style.textContent =
          ":host{display:block}" +
          "ha-card{overflow:hidden;border-radius:12px;background:#2c2c2c}" +
          ".hdr{display:flex;align-items:center;justify-content:space-between;background:#FFCC00;color:#1a1a1a;padding:6px 14px;font:700 14px/1.2 'Segoe UI',Arial,sans-serif}" +
          ".hdr .b{font-size:11px;font-weight:400;opacity:.7}" +
          /* container-type establishes the cqw reference = panel inline width */
          ".panel{position:relative;width:100%;padding-bottom:" + (SC2_H/SC2_W*100).toFixed(4) + "%;background:url('" + IMG_BASE + "/sc2.jpg') center/100% 100% no-repeat;overflow:hidden;container-type:inline-size}" +
          ".inner{position:absolute;inset:0}" +
          ".sb{position:absolute;left:" + _pctX(sb_l) + ";top:" + _pctY(sb_t) + ";width:" + _pctX(sb_w) + ";height:" + _pctY(sb_h) + ";background:#000;overflow:hidden}" +
          ".sb span{position:absolute;top:0;height:100%;display:flex;align-items:center;font:normal " + _cqw(sb_f) + "/1 'Courier New','Arial Unicode MS',monospace;color:#fff;white-space:nowrap}" +
          ".lcd{position:absolute;left:" + _pctX(lcd_l) + ";top:" + _pctY(lcd_t) + ";width:" + _pctX(lcd_w) + ";height:" + _pctY(lcd_h) + ";box-sizing:border-box;padding:" + _cqw(6) + ";overflow:hidden}" +
          ".lines{position:relative;width:100%;height:100%}" +
          ".ln{position:relative;box-sizing:border-box}" +
          ".ln span{position:absolute;top:0;height:100%;display:flex;align-items:center;font:normal " + _cqw(lcd_f) + "/1 'Courier New','Arial Unicode MS',monospace;color:#454545;white-space:nowrap;overflow:hidden}" +
          /* popup — inverse-video alert box over the content region */
          ".popup{position:absolute;inset:0;background:#000;color:#fff;box-sizing:border-box;padding:" + _cqw(4) + ";display:none;flex-direction:column;justify-content:center;font:normal " + _cqw(lcd_f) + "/1.25 'Courier New','Arial Unicode MS',monospace;overflow:hidden}" +
          ".popup .prow{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" +
          ".popup .pttl{font-weight:700}" +
          ".popup .pmsg{margin:" + _cqw(2) + " 0}" +
          ".popup .pdim{opacity:.85}" +
          ".popup .phint{margin-top:" + _cqw(3) + ";opacity:.7;font-size:" + _cqw(lcd_f * 0.8) + "}" +
          ".popup .pmore+.pmore{border-top:1px solid #555;margin-top:" + _cqw(3) + ";padding-top:" + _cqw(3) + "}" +
          /* history — recent messages list over the content region */
          ".hist{position:absolute;inset:0;box-sizing:border-box;padding:" + _cqw(2) + ";display:none;flex-direction:column;color:#333;font:normal " + _cqw(lcd_f * 0.82) + "/1.25 'Courier New','Arial Unicode MS',monospace;overflow:hidden}" +
          ".hist .htitle{font-weight:700;color:#222;border-bottom:1px solid #7a7a7a;padding-bottom:" + _cqw(1) + ";margin-bottom:" + _cqw(1) + "}" +
          ".hist .hrow{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" +
          ".hist .hempty{opacity:.7}" +
          ".led{position:absolute;width:" + _pctX(LED_SIZE) + ";height:" + _pctY(LED_SIZE) + "}" +
          ".led.flash{animation:blink .6s infinite}" +
          "@keyframes blink{0%,100%{opacity:1}50%{opacity:.12}}" +
          /* hamburger / acknowledge clickable region */
          ".ack{position:absolute;left:" + _pctX(HAMBURGER.x) + ";top:" + _pctY(HAMBURGER.y) + ";width:" + _pctX(HAMBURGER.w) + ";height:" + _pctY(HAMBURGER.h) + ";cursor:pointer;border-radius:50%;background:rgba(255,255,255,0);transition:background .1s}" +
          ".ack:hover{background:rgba(255,255,255,0.12)}" +
          ".ack:active{background:rgba(0,0,0,0.18)}" +
          /* power buttons — clickable only when power_switch_entity is set */
          ".pwr{position:absolute;cursor:pointer;border-radius:4px;background:rgba(255,255,255,0);transition:background .1s}" +
          ".pwr:hover{background:rgba(255,255,255,0.18)}" +
          ".pwr:active{background:rgba(0,0,0,0.3)}" +
          /* switch-state caption — same style as the panel's printed labels */
          ".pwrlbl{position:absolute;display:flex;align-items:center;font:700 " + _cqw(10) + "/1 'Segoe UI',Arial,sans-serif;color:rgba(255,255,255,0.75);letter-spacing:" + _cqw(1) + ";white-space:nowrap}" +
          ".pwrlbl.offline{color:rgba(255,255,255,0.45)}" +
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

        /* LCD content region */
        var lcd = document.createElement("div"); lcd.className = "lcd";

        /* normal line stack */
        var lines = document.createElement("div"); lines.className = "lines";
        var lW = lcd_w;
        function lp(left,width,id,align,text) {
          var s = "left:" + (left/lW*100).toFixed(2) + "%;width:" + (width/lW*100).toFixed(2) + "%";
          if (align) s += ";justify-content:" + align;
          var innerTxt = text || "";
          return "<span " + (id ? "id='"+id+"'" : "") + " style='" + s + "'>" + innerTxt + "</span>";
        }
        var sep = "<span style='left:0;width:100%'>------------------------------</span>";
        var lineDefs = [
          sep,
          lp(5, lW - 5, "lcd-st", "flex-start"),
          sep,
          lp(5,60,null,null,"Key") + lp(65,15,null,null,"-") + lp(80,55,"lcd-key","flex-start") +
            lp(140,10,null,null,"¦") +
            lp(155,25,null,"flex-start","pA") + lp(180,15,null,null,"-") + lp(200,140,"lcd-pa","flex-start"),
          sep,
          lp(160,60,null,null,"Run") + lp(230,115,"lcd-run","flex-end"),
          lp(160,60,null,null,"Load") + lp(230,115,"lcd-load","flex-end"),
          lp(5,220,null,null,"Maintenance in") + lp(230,115,"lcd-mt","flex-end")
        ];
        var lineH = (100 / lineDefs.length).toFixed(3) + "%";
        for (var i = 0; i < lineDefs.length; i++) {
          var d = document.createElement("div"); d.className = "ln";
          d.style.height = lineH;
          d.innerHTML = lineDefs[i];
          if (i === 6) d.id = "ln-load";
          lines.appendChild(d);
        }
        lcd.appendChild(lines);

        /* popup + history overlays */
        var popup = document.createElement("div"); popup.className = "popup"; popup.id = "lcd-popup";
        lcd.appendChild(popup);
        var hist = document.createElement("div"); hist.className = "hist"; hist.id = "lcd-hist";
        lcd.appendChild(hist);

        inner.appendChild(lcd);

        /* LEDs — positioned by measured centres */
        for (var li = 0; li < LED_NAMES.length; li++) {
          var name = LED_NAMES[li];
          var pos = LED_POS[name];
          if (!pos) continue;
          var img = document.createElement("img");
          img.className = "led";
          img.id = "led-" + name;
          img.src = IMG_BASE + "/led_off.png";
          img.style.left = _pctX(pos.cx - LED_SIZE / 2);
          img.style.top  = _pctY(pos.cy - LED_SIZE / 2);
          inner.appendChild(img);
        }

        /* Hamburger / acknowledge button */
        var ack = document.createElement("div");
        ack.className = "ack";
        ack.id = "ack-btn";
        ack.title = "Acknowledge / messages";
        ack.addEventListener("click", function () { self._onHamburger(); });
        inner.appendChild(ack);

        /* Power buttons — active only when a switch entity is configured */
        if (c.power_switch_entity) {
          function pwrBtn(id, rect, on, title) {
            var b = document.createElement("div");
            b.className = "pwr";
            b.id = id;
            b.title = title;
            b.style.left = _pctX(rect.x); b.style.top = _pctY(rect.y);
            b.style.width = _pctX(rect.w); b.style.height = _pctY(rect.h);
            b.addEventListener("click", function () { self._powerAction(on); });
            inner.appendChild(b);
          }
          pwrBtn("pwr-on",  BTN_ON,  true,  "Turn on " + c.power_switch_entity);
          pwrBtn("pwr-off", BTN_OFF, false, "Turn off " + c.power_switch_entity);

          /* switch-state LED + caption */
          var pled = document.createElement("img");
          pled.className = "led";
          pled.id = "pwr-led";
          pled.src = IMG_BASE + "/led_off.png";
          pled.style.left = _pctX(PWR_LED.cx - LED_SIZE / 2);
          pled.style.top  = _pctY(PWR_LED.cy - LED_SIZE / 2);
          pled.title = c.power_switch_entity;
          inner.appendChild(pled);
          var plbl = document.createElement("div");
          plbl.className = "pwrlbl";
          plbl.id = "pwr-lbl";
          plbl.style.left = _pctX(PWR_LBL.x); plbl.style.top = _pctY(PWR_LBL.y);
          plbl.style.width = _pctX(PWR_LBL.w); plbl.style.height = _pctY(PWR_LBL.h);
          plbl.textContent = "SWITCH";
          inner.appendChild(plbl);
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

      /* ── active-message helpers ── */
      _activeMsgEntity() { return this._entity("sensor", "active_message"); }
      _activeMessages() {
        var e = this._activeMsgEntity();
        if (!e || !e.attributes) return [];
        var am = e.attributes.active_messages || [];
        var out = [];
        for (var i = 0; i < am.length; i++) {
          if (!_isOperationalMsg(am[i])) out.push(am[i]);
        }
        return out;
      }
      _allMessages() {
        var e = this._activeMsgEntity();
        if (!e || !e.attributes) return [];
        return e.attributes.messages || [];
      }
      /* popup should show when there are active messages not all dismissed */
      _popupPending() {
        var active = this._activeMessages();
        if (!active.length) return false;
        var dis = this._loadDismissed();
        for (var i = 0; i < active.length; i++) {
          if (!dis[_msgId(active[i])]) return true;
        }
        return false;
      }

      _powerAction(on) {
        var entity = this._config && this._config.power_switch_entity;
        if (!entity || !this._hass || !this._hass.callService) return;
        /* homeassistant.turn_on/off works for switch, input_boolean, etc. */
        this._hass.callService("homeassistant", on ? "turn_on" : "turn_off", {
          entity_id: entity
        });
      }

      _onHamburger() {
        /* popup visible → dismiss it; otherwise toggle history view */
        var popupVisible = (this._view === "normal") && this._popupPending();
        if (popupVisible) {
          var active = this._activeMessages();
          var dis = this._loadDismissed();
          for (var i = 0; i < active.length; i++) dis[_msgId(active[i])] = true;
          this._saveDismissed();
        } else {
          this._view = (this._view === "history") ? "normal" : "history";
        }
        this._refresh();
      }

      /* ── refresh ── */
      _refresh() {
        if (!this.shadowRoot) return;
        var self = this;
        function $(id) { return self.shadowRoot.getElementById(id); }

        /* Pressure — integer, no decimals, max 3 digits */
        var p  = this._state("pressure"), pU = this._unit("pressure") || "psi";
        var pFmt = _intPressure(p);

        var t  = this._state("temperature"), tU = this._unit("temperature") || "°F";
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

        /* ── LEDs ── */
        for (var li = 0; li < LED_NAMES.length; li++) {
          var name = LED_NAMES[li];
          var img = $("led-" + name);
          if (!img) continue;
          var ent = this._ledEntity(name);
          var raw = ent ? ent.state : "off";
          var offline = (raw === "unavailable" || raw === "unknown");
          var ledRaw = (ent && ent.attributes && !offline) ? (ent.attributes.led_raw_state || "") : "";
          var ledColor = (ent && ent.attributes) ? (ent.attributes.led_color || LED_COLOURS[name] || "green") : (LED_COLOURS[name] || "green");
          if (!offline && (raw === "on" || ledRaw === "on" || ledRaw === "flash")) {
            img.src = IMG_BASE + "/led_" + ledColor + ".png";
            img.classList.toggle("flash", ledRaw === "flash");
          } else {
            img.src = IMG_BASE + "/led_off.png";
            img.classList.remove("flash");
          }
        }

        /* ── switch-state indicator ── */
        var pwrEntity = this._config && this._config.power_switch_entity;
        if (pwrEntity) {
          var pled = $("pwr-led"), plbl = $("pwr-lbl");
          if (pled && plbl) {
            var pst = (this._hass && this._hass.states && this._hass.states[pwrEntity])
              ? this._hass.states[pwrEntity].state : null;
            if (pst === "on") {
              pled.src = IMG_BASE + "/led_green.png";
              plbl.textContent = "SWITCH";
              plbl.classList.remove("offline");
            } else if (pst === "off") {
              pled.src = IMG_BASE + "/led_off.png";
              plbl.textContent = "SWITCH";
              plbl.classList.remove("offline");
            } else {
              /* unavailable / unknown / entity missing */
              pled.src = IMG_BASE + "/led_orange.png";
              plbl.textContent = "OFFLINE";
              plbl.classList.add("offline");
            }
          }
        }

        /* ── popup / history overlays ── */
        this._refreshOverlays();
      }

      _refreshOverlays() {
        var self = this;
        function $(id) { return self.shadowRoot.getElementById(id); }
        var popup = $("lcd-popup");
        var hist  = $("lcd-hist");
        var lines = this.shadowRoot.querySelector(".lines");
        if (!popup || !hist) return;

        var showPopup = (this._view === "normal") && this._popupPending();
        var showHist  = (this._view === "history");

        /* history view ─────────────────────────────────────────── */
        if (showHist) {
          hist.innerHTML = this._buildHistoryHtml();
          hist.style.display = "flex";
        } else {
          hist.style.display = "none";
        }

        /* popup view ────────────────────────────────────────────── */
        if (showPopup) {
          popup.innerHTML = this._buildPopupHtml();
          popup.style.display = "flex";
        } else {
          popup.style.display = "none";
        }

        /* normal lines hidden whenever an overlay covers them */
        if (lines) lines.style.visibility = (showPopup || showHist) ? "hidden" : "visible";
      }

      _buildPopupHtml() {
        var active = this._activeMessages();
        var dis = this._loadDismissed();
        /* only show the not-yet-dismissed active messages, newest first */
        var show = [];
        for (var i = 0; i < active.length && show.length < 2; i++) {
          if (!dis[_msgId(active[i])]) show.push(active[i]);
        }
        if (!show.length) show = active.slice(0, 1);
        var html = "";
        for (var j = 0; j < show.length; j++) {
          var m = show[j];
          var label = _typeLabel(m);
          var code = _msgCode(m);
          var ttl = this._esc((label ? label : "Message") + (code ? "  " + code : ""));
          var body = this._esc(_clean(m.message) || m.state_text || "");
          var when = this._esc(((m.date || "") + " " + (m.time || "")).trim() || _clean(m.datetime) || "");
          html += "<div class='pmore'>" +
                    "<div class='prow pttl'>" + ttl + "</div>" +
                    "<div class='prow pmsg'>" + body + "</div>" +
                    "<div class='prow pdim'>" + when + "</div>" +
                  "</div>";
        }
        html += "<div class='phint'>Press ≡ to acknowledge</div>";
        return html;
      }

      _buildHistoryHtml() {
        var msgs = this._allMessages();
        var html = "<div class='htitle'>Recent messages</div>";
        if (!msgs.length) {
          html += "<div class='hrow hempty'>No messages</div>";
          return html;
        }
        var n = Math.min(msgs.length, 6);
        for (var i = 0; i < n; i++) {
          var m = msgs[i];
          var when = ((m.date || "") + " " + (m.time || "")).trim() || _clean(m.datetime) || "";
          var st = m.state || "";
          var arrow = (st.indexOf("coming") === 0) ? "▶" : (st.indexOf("going") === 0) ? "◁" : "•";
          var code = _msgCode(m);
          var msg = _clean(m.message) || m.state_text || "";
          var row = when + "  " + arrow + "  " + (code ? code + " " : "") + msg;
          html += "<div class='hrow'>" + this._esc(row) + "</div>";
        }
        return html;
      }
    }

    /* ╔═══════════════════════════════════════════════════════════════╗
     * ║                   VISUAL CONFIG EDITOR                       ║
     * ╚═══════════════════════════════════════════════════════════════╝
     * Built on HA's own <ha-form> with native selectors (device picker
     * filtered to this integration, entity picker for the power switch),
     * so it looks and behaves like built-in card editors and tracks
     * frontend changes without custom widget code.
     */
    var INTEGRATION = "kaeser_sc2";
    var PRESSURE_SUFFIX = "_pressure";

    var EDITOR_SCHEMA = [
      { name: "title", selector: { text: {} } },
      { name: "device", selector: { device: { filter: { integration: INTEGRATION } } } },
      { name: "power_switch_entity",
        selector: { entity: { filter: { domain: ["switch", "input_boolean"] } } } },
      { type: "expandable", name: "", title: "Advanced", schema: [
        { name: "entity_prefix", selector: { text: {} } },
        { type: "grid", name: "", schema: [
          { name: "sb_left",   selector: { number: { mode: "box", step: 1 } } },
          { name: "sb_top",    selector: { number: { mode: "box", step: 1 } } },
          { name: "sb_width",  selector: { number: { mode: "box", step: 1 } } },
          { name: "sb_height", selector: { number: { mode: "box", step: 1 } } },
          { name: "sb_font",   selector: { number: { mode: "box", step: 1 } } }
        ]},
        { type: "grid", name: "", schema: [
          { name: "lcd_left",   selector: { number: { mode: "box", step: 1 } } },
          { name: "lcd_top",    selector: { number: { mode: "box", step: 1 } } },
          { name: "lcd_width",  selector: { number: { mode: "box", step: 1 } } },
          { name: "lcd_height", selector: { number: { mode: "box", step: 1 } } },
          { name: "lcd_font",   selector: { number: { mode: "box", step: 1 } } }
        ]}
      ]}
    ];

    var EDITOR_LABELS = {
      title: "Title",
      device: "Compressor",
      power_switch_entity: "Power switch (optional)",
      entity_prefix: "Entity prefix",
      sb_left: "Status bar left", sb_top: "Status bar top", sb_width: "Status bar width",
      sb_height: "Status bar height", sb_font: "Status bar font",
      lcd_left: "LCD left", lcd_top: "LCD top", lcd_width: "LCD width",
      lcd_height: "LCD height", lcd_font: "LCD font"
    };
    var EDITOR_HELPERS = {
      power_switch_entity: "Green I turns it on, red O turns it off, e.g. a switch wired to the remote-control input.",
      entity_prefix: "Set automatically from the compressor. Override only for renamed entities (sensor.PREFIX_pressure)."
    };

    class KaeserSC2CardEditor extends HTMLElement {

      constructor() {
        super();
        this._config = {};
        this._hass = null;
        this._form = null;
      }

      set hass(hass) {
        this._hass = hass;
        this._update();
      }

      setConfig(config) {
        this._config = Object.assign({}, config);
        this._update();
      }

      connectedCallback() {
        this._ensureForm();
      }

      /* ha-form is lazy-loaded by HA; loading a built-in card's editor
       * pulls it (and the selectors) in when no other editor has yet. */
      _ensureForm() {
        if (this._form) return;
        var self = this;
        if (!customElements.get("ha-form") && window.loadCardHelpers) {
          window.loadCardHelpers()
            .then(function (h) { return h.createCardElement({ type: "entities", entities: [] }); })
            .then(function (c) { return c && c.constructor.getConfigElement && c.constructor.getConfigElement(); })
            .catch(function () {});
        }
        customElements.whenDefined("ha-form").then(function () {
          if (self._form) return;
          var form = document.createElement("ha-form");
          form.schema = EDITOR_SCHEMA;
          form.computeLabel = function (s) { return EDITOR_LABELS[s.name] || s.name; };
          form.computeHelper = function (s) {
            if (EDITOR_HELPERS[s.name]) return EDITOR_HELPERS[s.name];
            return DEFAULTS[s.name] !== undefined ? "Default " + DEFAULTS[s.name] : "";
          };
          form.addEventListener("value-changed", function (ev) { self._valueChanged(ev); });
          self._form = form;
          self.appendChild(form);
          self._update();
        });
      }

      _update() {
        if (!this._form) return;
        this._form.hass = this._hass;
        var data = Object.assign({}, this._config);
        var dev = this._deviceForPrefix(this._config.entity_prefix);
        if (dev) data.device = dev;
        this._form.data = data;
      }

      /* compressor device <-> entity_prefix, via the entity registry */
      _deviceForPrefix(prefix) {
        if (!prefix || !this._hass || !this._hass.entities) return undefined;
        var ent = this._hass.entities["sensor." + prefix + PRESSURE_SUFFIX];
        return (ent && ent.device_id) || undefined;
      }
      _prefixForDevice(deviceId) {
        if (!deviceId || !this._hass || !this._hass.entities) return "";
        var ents = this._hass.entities;
        for (var id in ents) {
          var e = ents[id];
          if (e.device_id !== deviceId || id.indexOf("sensor.") !== 0) continue;
          if (e.translation_key === "pressure" ||
              id.slice(-PRESSURE_SUFFIX.length) === PRESSURE_SUFFIX) {
            return id.slice(7, id.length - PRESSURE_SUFFIX.length);
          }
        }
        return "";
      }

      _valueChanged(ev) {
        ev.stopPropagation();
        var value = Object.assign({}, ev.detail.value);
        var oldDev = this._deviceForPrefix(this._config.entity_prefix);
        if (value.device !== oldDev) {
          var prefix = this._prefixForDevice(value.device);
          if (prefix) value.entity_prefix = prefix;
          else if (!value.device) delete value.entity_prefix;
        }
        delete value.device;
        for (var k in value) {
          if (value[k] === undefined || value[k] === null || value[k] === "") delete value[k];
        }
        this._config = value;
        this.dispatchEvent(new CustomEvent("config-changed", {
          detail: { config: Object.assign({}, value) },
          bubbles: true, composed: true
        }));
      }
    }

    customElements.define("kaeser-sc2-card", KaeserSC2Card);
    customElements.define("kaeser-sc2-card-editor", KaeserSC2CardEditor);
  }

})();
