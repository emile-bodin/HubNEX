import { PlanEditor, shapeStyle, shapeSVG } from "./plan-editor.js";
import { Cards } from "./casa-cards.js";
import { Energy } from "./casa-energy.js";
import { t, num } from "./i18n.js";

// The house view: Home Assistant areas on the owner's floor plan, live.
// Tap a room for its quick card, "Apri stanza" for all its entities; buttons call Home
// Assistant directly (no AI, no credit). Rooms are HA areas: entities can be moved between
// areas (in HA) or just shown/hidden here.

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const ALERT = new Set(["door", "window", "opening", "garage_door", "smoke", "moisture", "gas", "safety", "problem", "carbon_monoxide"]);
const OPENING = new Set(["door", "window", "opening", "garage_door"]);
const PRESENCE = new Set(["motion", "occupancy", "presence"]);
const SECURITY_CLASSES = new Set([...ALERT, ...PRESENCE, "lock", "tamper", "vibration", "sound"]);
const APPLIANCE = /bollitor|kettle|boiler|caldai|scaldabagn|acqua|water|frigo|fridge|freezer|congelat|forno|oven|piastr|lavatric|lavastovigl|asciugatric|cpu|processor|chip|batter|intern|motor|esterna|outdoor|pompa|pump|vasca|piscina|pool/i;
const SHOW_AS = [["", t("Come in Home Assistant")], ["light", t("Luce")], ["switch", t("Presa / interruttore")], ["gate", t("Cancello / porta (impulso)")], ["siren", t("Sirena")], ["sensor", t("Solo stato")], ["stock", t("Scorta (pellet, sacchi…)")]];
// The free card's blocks: kind, name, a hint, its first size, the entities it suits.
const BLOCKS = [
  ["value", t("Valore grande"), t("un numero o uno stato in grande"), [2, 1], () => true],
  ["ring", t("Indicatore ad anello"), t("un valore su una scala"), [1, 1], (s) => s.k === "climate" || !isNaN(parseFloat(s.s))],
  ["toggle", t("Interruttore"), t("accendi e spegni"), [1, 1], (s) => ["light", "switch"].includes(s.k)],
  ["button", t("Pulsante"), t("scena, script o pulsante"), [1, 1], (s) => ["scene", "script", "button"].includes(s.k)],
  ["slider", t("Cursore"), t("luminosità o un numero"), [2, 1], (s) => ["light", "number", "stock"].includes(s.k)],
  ["chart", t("Grafico"), t("le ultime 24 ore"), [4, 1], (s) => s.k === "sensor" && !isNaN(parseFloat(s.s))],
  ["bar", t("Barra"), t("quanto è pieno"), [2, 1], (s) => !isNaN(parseFloat(s.s))],
  ["band", t("Fascia oraria"), t("da un orario a un altro"), [4, 1], (s) => s.k === "datetime"],
  ["select", t("Selettore"), t("scegli tra le opzioni"), [2, 1], (s) => s.k === "select"],
  ["state", t("Stato"), t("com'è e da quanto"), [1, 1], () => true],
  ["camera", t("Telecamera"), t("l'immagine, dal vivo"), [2, 2], (s) => s.k === "camera"],
  ["media", t("Media"), t("copertina e comandi"), [2, 1], (s) => s.k === "media"],
  ["ask", t("Domanda a Jarvis"), t("una domanda pronta, a un tocco"), [2, 1], () => false],
  ["text", t("Testo"), t("un titolo o una nota"), [4, 1], () => false],
];
const NO_ENTITY = new Set(["text", "ask"]);
// Ready-made cards: each block takes the first entity of the room (then of the house) that suits it.
const named = (re) => (s) => re.test(s.n || "");
const power = (s) => s.k === "sensor" && s.a.device_class === "power";
const TEMPLATES = [
  ["stufa", t("Stufa"), "warm", [
    ["value", (s) => s.k === "climate", 2, 2], ["toggle", (s) => ["switch", "light"].includes(s.k) && /stufa|stove|camino/i.test(s.n || ""), 1, 1],
    ["ring", (s) => s.k === "number" && /potenz|power/i.test(s.n || ""), 1, 1], ["bar", (s) => s.k === "stock", 2, 1],
    ["band", (s) => s.k === "datetime", 4, 1], ["select", (s) => s.k === "select", 4, 1]]],
  ["ingresso", t("Ingresso"), "cool", [
    ["camera", (s) => s.k === "camera", 4, 2], ["state", (s) => s.k === "lock", 2, 1],
    ["state", (s) => s.k === "binary" && ["door", "garage_door", "opening"].includes(s.a.device_class), 2, 1], ["button", (s) => ["scene", "script", "button"].includes(s.k), 4, 1]]],
  ["lavanderia", t("Lavanderia"), "cool", [
    ["state", (s) => s.k === "switch" && /lavatric|asciugatric|washing|dryer/i.test(s.n || ""), 2, 1], ["value", (s) => power(s) && /lavatric|asciugatric|washing|dryer/i.test(s.n || ""), 2, 1],
    ["chart", (s) => power(s) && /lavatric|asciugatric|washing|dryer/i.test(s.n || ""), 4, 1]]],
  ["clima", t("Clima stanza"), "cool", [
    ["value", (s) => s.k === "climate", 2, 2], ["ring", (s) => s.k === "sensor" && s.a.device_class === "humidity", 1, 1],
    ["state", (s) => s.k === "binary" && s.a.device_class === "window", 1, 1], ["chart", (s) => s.k === "sensor" && s.a.device_class === "temperature", 4, 1]]],
  ["energia", t("Energia"), "green", [
    ["value", power, 2, 1], ["value", (s) => s.k === "sensor" && s.a.device_class === "energy", 2, 1], ["chart", power, 4, 1]]],
  ["musica", t("Musica"), "violet", [
    ["media", (s) => s.k === "media", 4, 1], ["ask", null, 4, 1]]],
];
const BLOCK_SIZES = [[1, 1], [2, 1], [2, 2], [3, 1], [4, 1], [4, 2]];
const CARD_COLORS = [["", t("Nessuno")], ["warm", t("Arancio")], ["cool", t("Azzurro")], ["green", t("Verde")], ["violet", t("Viola")], ["red", t("Rosso")]];
function stateChoices(s) {
  if (!s) return [];
  const dc = s.a.device_class;
  const onoff = (on, off) => [["on", on], ["off", off]];
  if (s.a.options?.length) return s.a.options.map((o) => [o, o]);
  switch (s.k) {
    case "binary":
      if (["door", "window", "opening", "garage_door"].includes(dc)) return onoff(t("aperta"), t("chiusa"));
      if (["motion", "occupancy", "presence", "moving"].includes(dc)) return onoff(t("rileva"), t("libero"));
      return onoff(t("acceso"), t("spento"));
    case "light": case "switch": return onoff(t("acceso"), t("spento"));
    case "media": return [["playing", t("in riproduzione")], ["paused", t("in pausa")], ["idle", t("inattivo")], ["off", t("spento")], ["on", t("acceso")]];
    case "lock": return [["locked", t("bloccata")], ["unlocked", t("sbloccata")], ["open", t("aperta")]];
    case "cover": case "gate": return [["open", t("aperta")], ["closed", t("chiusa")], ["opening", t("in apertura")], ["closing", t("in chiusura")]];
    case "person": return [["home", t("a casa")], ["not_home", t("fuori")]];
    case "climate": return [["heat", t("Caldo")], ["cool", t("Freddo")], ["auto", "Auto"], ["off", t("Spento")]];
    case "alarm": return [["disarmed", t("disinserito")], ["armed_home", t("in casa")], ["armed_away", t("fuori casa")], ["armed_night", t("notte")], ["triggered", t("scattato")]];
    case "vacuum": return [["cleaning", t("pulisce")], ["docked", t("alla base")], ["returning", t("torna alla base")], ["paused", t("in pausa")]];
    default: return [];
  }
}
// The value of a condition or a rule: from a list when the entity's states are known, else typed.
function valueField(path, s, op, v) {
  const list = op === "=" || op === "!=" ? stateChoices(s) : [];
  if (!list.length) return `<input class="hc-input" data-fb="${path}" value="${esc(v)}" placeholder="${t("valore")}">`;
  const known = list.some(([x]) => x === v);
  return `<select class="hc-select" data-fb="${path}">${known ? "" : `<option value="${esc(v)}" selected>${esc(v || "—")}</option>`}${list.map(([x, l]) => `<option value="${esc(x)}" ${x === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
}
const COMPARES = [["<", t("sotto")], [">", t("sopra")], ["=", t("uguale a")], ["!=", t("diverso da")]];
const TAPS = [["", t("Niente")], ["toggle", t("Accendi / spegni")], ["run", t("Avvia scena o script")], ["ask", t("Chiedi a Jarvis")], ["room", t("Apri una stanza")]];
const SECTIONS = [
  ["light", t("Luci")], ["gate", t("Cancelli e porte")], ["climate", t("Clima")], ["stock", t("Scorte")], ["cover", t("Tapparelle e tende")], ["valve", t("Valvole e irrigazione")], ["media", t("Media")],
  ["switch", t("Prese e interruttori")], ["people", t("Persone")], ["security", t("Sicurezza")], ["camera", t("Telecamere")], ["sensor", t("Sensori")], ["settings", t("Orari e impostazioni")], ["vacuum", t("Pulizia")], ["action", t("Azioni")], ["other", t("Altro")],
];

// Home Assistant's own frontend, when Jarvis is open inside it (same origin): its connection
// gives the same camera streams HA's dashboards use.
function haParent() {
  try {
    const hass = window.parent !== window && window.parent.document.querySelector("home-assistant")?.hass;
    return hass?.connection ? hass : null;
  } catch {
    return null;
  }
}


const scripts = {};
function loadScript(src) {
  scripts[src] ||= new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = ok;
    s.onerror = () => fail(new Error(t("non riesco a caricare {src}", { src })));
    document.head.appendChild(s);
  });
  return scripts[src];
}

export class CasaView {
  constructor(root, { api, token, deadlines }) {
    this.root = root;
    this.api = api;
    this.deadlines = deadlines; // () => the owner's deadlines, or null for family members
    root.addEventListener("pointerdown", (e) => {
      const el = e.target.closest(".fe-prev .fb");
      if (!el || !this.freeEdit) return;
      this._drag = { i: Number(el.dataset.i), x: e.clientX, y: e.clientY, el, moved: false };
    });
    root.addEventListener("pointermove", (e) => {
      const d = this._drag;
      if (!d) return;
      if (!d.moved && Math.hypot(e.clientX - d.x, e.clientY - d.y) < 8) return;
      d.moved = true;
      d.el.classList.add("dragging");
      const over = document.elementFromPoint(e.clientX, e.clientY)?.closest(".fe-prev .fb");
      this.root.querySelectorAll(".fe-prev .fb.drop").forEach((x) => x !== over && x.classList.remove("drop"));
      if (over && over !== d.el) over.classList.add("drop");
      d.to = over ? Number(over.dataset.i) : null;
    });
    const drop = () => {
      const d = this._drag;
      this._drag = null;
      if (!d?.moved) return;
      this._dragged = true; // the click that follows is not a selection
      const f = this.freeEdit;
      if (f && d.to != null && d.to !== d.i) {
        const [m] = f.blocks.splice(d.i, 1);
        f.blocks.splice(d.to, 0, m);
        f.sel = d.to;
      }
      this.render(true);
      setTimeout(() => { this._dragged = false; }, 300);
    };
    root.addEventListener("pointerup", drop);
    root.addEventListener("pointercancel", drop);
    this.stockStats = {}; // stock entity -> its pace (per day, days left, last delivery)
    this.stockAt = {};
    this.token = token || (() => "");
    this.camTick = Date.now();
    this.camSrc = {}; // last frame loaded, per camera
    this.liveImgs = new Map(); // camera -> its live thumbnail (MJPEG), kept across redraws
    this.noLive = new Set(); // cameras whose stream gave no picture: still frames only
    this.noHLS = new Set(); // cameras whose HA video failed in a thumbnail: MJPEG for them
    // In the background no stream stays open; back in front, the thumbnails start again.
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) this.stopLive();
      else if (this.visible) this.render(true);
    });
    this.editor = new PlanEditor({
      api, token: this.token,
      onSaved: () => { this.toast(t("Piantina salvata")); this.reload(true); },
      onText: () => this.openLayout(),
      toast: (msg) => this.toast(msg),
    });
    this.live = null; // the camera (or camera grid) open over the view
    setInterval(() => this.refreshCameras(), 1000);
    addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      if (this.live) this.closeCamera();
      else if (this.toneOpen && this.visible) { this.toneOpen = null; this.render(true); }
      else if (this.weatherOpen && this.visible) { this.weatherOpen = false; this.render(true); }
      else if (this.freeEdit && this.visible) { this.freeEdit = null; this.render(true); }
      else if (this.energyOpen && !this.energyEdit && this.visible) { this.energyOpen = false; clearInterval(this._energyTimer); this.render(true); }
    });
    this.data = null;
    this.loading = null;
    this.selected = null; // area id of the quick card
    this.page = null; // area id of the full room page
    this.editing = false;
    this.mode = "ha";
    this.floor = 0;
    this.layout = null; // floor plan editor state
    this.dirty = false;
    root.addEventListener("click", (e) => this._click(e));
    root.addEventListener("change", (e) => this._change(e));
    root.addEventListener("input", (e) => this._input(e));
    root.addEventListener("focusout", () => { if (this.dirty) setTimeout(() => this.render(), 0); });
    root.addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === " ") && e.target.matches?.("[role=button][data-act]")) { e.preventDefault(); e.target.click(); }
    });
    root.addEventListener("pointerdown", (e) => this._dragStart(e));
    // Phone: the quick card is a sheet over the plan. Drag it down to close, up to open the room.
    root.addEventListener("touchstart", (e) => { this._touchY = e.target.closest(".hc-grab, .casa-quick > .hc-head") ? e.touches[0].clientY : null; }, { passive: true });
    root.addEventListener("touchend", (e) => {
      if (this._touchY == null || !this.selected) return;
      const dy = e.changedTouches[0].clientY - this._touchY;
      this._touchY = null;
      if (dy > 70) { this.selected = null; this.render(true); }
      else if (dy < -70) { this.page = this.selected; this.render(true); }
    }, { passive: true });
    addEventListener("keydown", (e) => {
      if (!this.pad || !this.visible || e.target.id === "pad-text") return;
      if (/^[0-9]$/.test(e.key)) this.padKey(e.key);
      else if (e.key === "Backspace") this.padKey("back");
      else if (e.key === "Enter") this.padKey("ok");
      else return;
      e.preventDefault();
    });
  }

  // ------------------------------------------------------------------ lifecycle
  async open() {
    this.visible = true;
    if (!this.data) await this.reload();
    else this.render();
    const e = this.data?.energy_panel;
    if (e && (e.power || Object.keys(e.bands || {}).length) && !this.energyLive) this.loadEnergy(); // the band now, for the dashboard
  }

  close() { this.visible = false; document.body.classList.remove("casa-sheet", "casa-modal-open"); }

  async reload(force = false) {
    this.loading ??= (async () => {
      try {
        this.data = await (await this.api("/api/casa")).json();
        this.error = null;
        this.loadForecast();
      } catch (err) {
        this.error = err.message;
      } finally {
        this.loading = null;
      }
    })();
    await this.loading;
    this.render(force);
  }

  // The weather forecast, from Home Assistant: every 30 minutes is plenty.
  async loadForecast() {
    if (!this.data?.weather || Date.now() - (this._fcAt || 0) < 18e5) return;
    this._fcAt = Date.now();
    try {
      const r = await this.api("/api/casa/forecast");
      this.forecast = (await r.json()).forecast || null;
      this.renderSoon();
    } catch {
      this.forecast = null;
    }
  }

  // A stock's pace, from Home Assistant's history: asked at most every 10 minutes.
  loadStock(eid) {
    if (Date.now() - (this.stockAt[eid] || 0) < 6e5) return;
    this.stockAt[eid] = Date.now();
    this.api(`/api/casa/stock/${encodeURIComponent(eid)}`).then((r) => r.json())
      .then((s) => { this.stockStats[eid] = s; this.renderSoon(); }).catch(() => {});
  }

  // Live events from the HQ WebSocket.
  handle(ev) {
    if (ev.type === "casa_changed") { if (this.visible) this.reload(); else this.data = null; return; }
    if (ev.type === "ha" && this.data) {
      if (ev.v) this.data.states[ev.e] = ev.v; else delete this.data.states[ev.e];
      if (this.visible) this.renderSoon();
    }
  }

  // What the chat should know: the room open on screen.
  context() {
    const a = this.page && this.area(this.page);
    return a ? `[${t("Sono nella stanza {room} della vista Casa", { room: a.name })}] ` : "";
  }

  renderSoon() {
    if (this._timer) return;
    this._timer = setTimeout(() => { this._timer = null; this.render(); }, 250);
  }

  // ------------------------------------------------------------------ helpers
  area(id) { return this.data?.areas.find((a) => a.id === id); }
  st(eid) { return this.data?.states[eid]; }
  dc(eid) { return this.st(eid)?.a?.device_class; }
  isOn(eid) { const s = this.st(eid); return !!s && ["on", "open", "opening", "playing", "unlocked", "heat", "cool", "auto", "heat_cool"].includes(s.s); }
  lightsOf(a) { return a.entities.filter((e) => this.st(e)?.k === "light"); }
  lit(a) { return this.lightsOf(a).some((e) => this.isOn(e)); }

  alerts(a) {
    return a.entities.filter((e) => { const s = this.st(e); return s?.s === "on" && ((s.k === "binary" && ALERT.has(s.a.device_class)) || s.k === "siren"); });
  }

  // Everything in the room that measures a temperature: thermostats and temperature sensors.
  tempSources(a) {
    return a.entities.filter((e) => {
      const s = this.st(e);
      return (s?.k === "climate" && s.a.current_temperature != null) || (s?.k === "sensor" && s.a.device_class === "temperature");
    });
  }

  readTemp(eid) {
    const s = this.st(eid);
    if (!s) return null;
    const v = s.k === "climate" ? Number(s.a.current_temperature) : parseFloat(s.s);
    return isNaN(v) ? null : v;
  }

  // The room's temperature: the source the owner picked, else a thermostat, else a sensor that
  // isn't measuring an appliance (kettle, fridge, boiler…).
  tempSource(a) {
    const sources = this.tempSources(a);
    if (a.temp && sources.includes(a.temp)) return a.temp;
    const ok = (e) => this.readTemp(e) != null;
    return sources.find((e) => this.st(e).k === "climate" && ok(e))
      || sources.find((e) => ok(e) && !APPLIANCE.test(`${e} ${this.st(e).n}`))
      || sources.find(ok) || null;
  }

  temp(a) {
    const e = this.tempSource(a);
    return e ? this.readTemp(e) : null;
  }

  value(eid) {
    const s = this.st(eid);
    if (!s) return "—";
    if (["unavailable", "unknown"].includes(s.s)) return s.s === "unknown" ? "—" : t("N/D");
    if (s.k === "binary") {
      const dc = s.a.device_class;
      if (OPENING.has(dc)) return s.s === "on" ? t("APERTA") : t("CHIUSA");
      if (PRESENCE.has(dc)) return s.s === "on" ? t("RILEVATO") : t("NESSUNO");
      if (dc === "moisture") return s.s === "on" ? t("ACQUA!") : t("ASCIUTTO");
      if (dc === "smoke" || dc === "gas" || dc === "carbon_monoxide") return s.s === "on" ? t("ALLARME!") : "OK";
      return s.s === "on" ? "ON" : "OFF";
    }
    if (s.k === "valve") return { open: t("APERTA"), closed: t("CHIUSA"), opening: t("APRE…"), closing: t("CHIUDE…") }[s.s] || s.s.toUpperCase();
    if (s.k === "person") return s.s === "home" ? t("A CASA") : s.s === "not_home" ? t("FUORI CASA") : s.s.toUpperCase(); // or the zone's name
    if (s.k === "lock") return { locked: t("BLOCCATA"), unlocked: t("SBLOCCATA"), locking: t("BLOCCO…"), unlocking: t("SBLOCCO…"), jammed: t("INCEPPATA"), open: t("APERTA") }[s.s] || s.s.toUpperCase();
    if (s.k === "alarm") return { disarmed: t("DISINSERITO"), armed_home: t("IN CASA"), armed_away: t("INSERITO"), armed_night: t("NOTTE"), triggered: t("SCATTATO!"), pending: t("IN ATTESA"), arming: t("INSERIMENTO") }[s.s] || s.s;
    if (s.k === "sensor") {
      const n = parseFloat(s.s);
      return isNaN(n) || /[^\d.,\-e]/i.test(s.s) ? s.s : `${num(n, Math.abs(n) < 10 && n % 1 ? 2 : 1)}${s.a.unit_of_measurement ? " " + s.a.unit_of_measurement : ""}`;
    }
    return s.s;
  }

  valueClass(eid) {
    const s = this.st(eid);
    if (!s) return "";
    if (s.k === "binary" && ALERT.has(s.a.device_class)) return s.s === "on" ? "bad" : "good";
    if (s.k === "lock") return s.s === "locked" ? "good" : "warn";
    if (s.k === "valve") return s.s === "open" || s.s === "opening" ? "warm" : "";
    if (s.k === "person") return s.s === "home" ? "good" : "";
    if (s.k === "alarm") return s.s === "triggered" ? "bad" : s.s === "disarmed" ? "" : "good";
    return "";
  }

  section(eid) {
    const s = this.st(eid);
    if (!s) return "other";
    if (["light", "gate", "climate", "cover", "valve", "media", "switch"].includes(s.k)) return s.k;
    if (s.k === "person") return "people";
    if (s.k === "lock" || s.k === "alarm" || s.k === "siren") return "security";
    if (s.k === "binary") return SECURITY_CLASSES.has(s.a.device_class) ? "security" : "sensor";
    if (s.k === "sensor") return "sensor";
    if (s.k === "scene" || s.k === "script" || s.k === "button") return "action";
    if (s.k === "camera") return "camera";
    if (s.k === "vacuum") return "vacuum";
    if (s.k === "stock") return "stock";
    if (["datetime", "number", "select", "text"].includes(s.k)) return "settings";
    return "other";
  }

  // A gate/door command: press a button, run a script, or give a relay a one-second impulse.
  gate(eid) {
    const domain = eid.split(".")[0];
    const s = this.st(eid);
    if (domain === "button" || domain === "input_button") this.call(domain, "press", { entity_id: eid });
    else if (domain === "script" || domain === "scene") this.call(domain, "turn_on", { entity_id: eid });
    else if (domain === "cover") this.call("cover", "toggle", { entity_id: eid });
    else if (domain === "lock") return this.lock(eid);
    else {
      this.call("homeassistant", "turn_on", { entity_id: eid });
      setTimeout(() => this.call("homeassistant", "turn_off", { entity_id: eid }), 1000);
    }
    this.toast(`▶ ${s?.n || eid}`);
  }

  // ---------------------------------------------------------------- cameras
  // Thumbnails are still frames through the add-on. A new frame replaces the old one only
  // once it has loaded, and redraws reuse the last loaded frame: they never go black.
  camURL(eid, tick = Date.now(), stream = false) {
    const tok = this.token();
    const q = [stream ? "" : `t=${tick}`, tok ? `token=${encodeURIComponent(tok)}` : ""].filter(Boolean).join("&");
    return `api/casa/camera/${encodeURIComponent(eid)}${stream ? "/stream" : ""}${q ? "?" + q : ""}`;
  }

  camHTML(eid) {
    const s = this.st(eid);
    const live = { streaming: t("IN DIRETTA"), recording: t("REGISTRA") }[s?.s] || "";
    this.camSrc[eid] ||= this.camURL(eid);
    return `<button class="casa-cam" data-act="cam" data-e="${eid}" aria-label="${t("Telecamera")} ${esc(s?.n || eid)}">
      <img data-cam="${eid}" src="${this.camSrc[eid]}" alt="">
      <span class="casa-cam-label">${esc(s?.n || eid)}${live ? ` · ${live}` : ""}</span></button>`;
  }

  refreshCameras() {
    if (!this.visible || document.hidden || Date.now() - this.camTick < 5000) return;
    this.camTick = Date.now();
    const eids = new Set([...document.querySelectorAll("img[data-cam]:not([data-live])")].map((i) => i.dataset.cam));
    for (const eid of eids) {
      const url = this.camURL(eid);
      const next = new Image();
      next.onload = () => {
        this.camSrc[eid] = url;
        document.querySelectorAll(`img[data-cam="${CSS.escape(eid)}"]`).forEach((i) => { i.src = url; });
      };
      next.src = url;
    }
  }

  // Live thumbnails: inside Home Assistant its own video (HLS, the same as the big view), else
  // the camera's MJPEG through the add-on. The element is moved, not rebuilt, when the view redraws (so the stream doesn't restart). At most MAX_LIVE at once:
  // a browser keeps only a few connections open to one address, and the rest of the
  // dashboard needs them too. The others stay still frames refreshed every 5 seconds.
  // The still frame stays on screen until the stream shows a picture, so a thumbnail is never
  // black; a stream with no picture after 10 seconds is dropped and the camera stays on stills.
  mountLive(root) {
    if (!root || document.hidden) return;
    const MAX_LIVE = 3;
    const placed = new Set();
    for (const img of root.querySelectorAll("img[data-cam]")) {
      const eid = img.dataset.cam;
      if (!eid.startsWith("camera.") || placed.has(eid) || this.noLive.has(eid)) continue;
      let live = this.liveImgs.get(eid);
      if (!live && this.liveImgs.size >= MAX_LIVE) continue;
      placed.add(eid);
      if (!live) live = this.startLive(img, eid);
      else if (!live.dataset.live) live.holder = img; // still waiting: it will take this place
      else if (live !== img) img.replaceWith(live);
    }
  }

  startLive(holder, eid) {
    const hass = haParent();
    if (hass && Number(this.st(eid)?.a.supported_features) & 2 && !this.noHLS.has(eid)) return this.startLiveHLS(holder, eid, hass);
    const live = document.createElement("img");
    live.className = holder.className;
    live.alt = "";
    live.dataset.cam = eid;
    live.holder = holder; // the still frame it will replace
    const t0 = Date.now();
    const drop = () => {
      if (this.liveImgs.get(eid) === live) this.liveImgs.delete(eid);
      this.noLive.add(eid);
      live.onerror = null;
      if (live.isConnected) { // it was playing: back to still frames in the same place
        live.removeAttribute("data-live");
        live.src = this.camSrc[eid] || this.camURL(eid);
      } else {
        live.src = "";
      }
    };
    const check = () => {
      if (this.liveImgs.get(eid) !== live) return; // stopped meanwhile
      if (live.naturalWidth) {
        live.dataset.live = "1";
        if (live.holder?.isConnected) live.holder.replaceWith(live);
        live.holder = null;
        return;
      }
      if (Date.now() - t0 > 10000) return drop();
      setTimeout(check, 250);
    };
    live.onerror = drop;
    live.src = this.camURL(eid, 0, true);
    this.liveImgs.set(eid, live);
    setTimeout(check, 250);
    return live;
  }

  // A muted <video> with Home Assistant's HLS: it takes the still frame's place once it plays.
  startLiveHLS(holder, eid, hass) {
    const video = document.createElement("video");
    Object.assign(video, { muted: true, autoplay: true, playsInline: true });
    video.className = holder.className;
    video.dataset.cam = eid;
    video.holder = holder;
    this.liveImgs.set(eid, video);
    (async () => {
      const { url } = await hass.connection.sendMessagePromise({ type: "camera/stream", entity_id: eid, format: "hls" });
      if (this.liveImgs.get(eid) !== video) return;
      await this.hlsPlay(video, url, 15);
      if (this.liveImgs.get(eid) !== video) return;
      video.dataset.live = "1";
      if (video.holder?.isConnected) video.holder.replaceWith(video);
      video.holder = null;
    })().catch(() => {
      if (this.liveImgs.get(eid) !== video) return; // stopped meanwhile
      this.liveImgs.delete(eid);
      this.noHLS.add(eid); // next redraw tries MJPEG
      const still = document.createElement("img");
      still.className = video.className;
      still.alt = "";
      still.dataset.cam = eid;
      still.src = this.camSrc[eid] || this.camURL(eid);
      if (video.isConnected) video.replaceWith(still);
      this.stopThumb(video);
    });
    return video;
  }

  // Closes a live thumbnail's connection (MJPEG image or HLS video).
  stopThumb(el) {
    el.dataset.stopped = "1";
    if (el.tagName === "VIDEO") {
      el._hls?.destroy();
      el._hls = null;
      el.pause();
      el.removeAttribute("src");
      el.load();
    } else {
      el.onerror = null; // closing it is not the camera's error
      el.src = "";
    }
  }

  // Close the streams of the thumbnails no longer on screen.
  pruneLive() {
    for (const [eid, el] of this.liveImgs) {
      if ((el.holder || el).isConnected) continue;
      this.stopThumb(el);
      this.liveImgs.delete(eid);
    }
  }

  stopLive() {
    for (const el of this.liveImgs.values()) this.stopThumb(el);
    this.liveImgs.clear();
  }

  // All cameras at a glance (the chip at the top of the house view).
  openCameraGrid() {
    const cams = this.data.areas.flatMap((a) => a.entities.filter((e) => this.st(e)?.k === "camera"));
    const box = this.overlay(t("Telecamere"), `<div class="casa-cams">${cams.map((e) => this.camHTML(e)).join("")}</div>`);
    this.mountLive(box); // the streams already open move into the grid, they don't restart
    box.addEventListener("click", (e) => {
      const cam = e.target.closest("[data-act='cam']");
      if (cam) this.openCamera(cam.dataset.e);
    });
  }

  // Live video: the player Home Assistant itself uses (HLS stream from HA) when Jarvis runs
  // inside Home Assistant, otherwise MJPEG through the add-on. It sits outside the view's
  // HTML, so the view's redraws never restart it.
  // HA's own HLS stream (inside Home Assistant) and MJPEG through the add-on start together;
  // as a last resort a still frame every second. The header says which one is running and,
  // if video failed, why.
  async openCamera(eid) {
    const s = this.st(eid);
    // The thumbnail already live moves into the big view: no new connection, live at once.
    const thumb = this.liveImgs.get(eid);
    const reuse = thumb?.dataset.live && (thumb.naturalWidth || thumb.tagName === "VIDEO") ? thumb : null;
    if (reuse) this.liveImgs.delete(eid);
    this.stopLive(); // the other thumbnails: their connections serve the big view now
    const box = this.overlay(s?.n || eid, `<div class="cam-mode">${t("Avvio video…")}</div><div class="cam-stage"><img class="cam-still" src="${this.camSrc[eid] || this.camURL(eid)}" alt=""></div>`, true);
    const stage = box.querySelector(".cam-stage");
    const mode = (text, on = false) => { const m = box.querySelector(".cam-mode"); m.textContent = text; m.classList.toggle("on", on); };
    const live = this.live;
    if (reuse?.tagName === "VIDEO") { // already Home Assistant's video: HD at once
      for (const a of ["data-cam", "data-live"]) reuse.removeAttribute(a);
      reuse.className = "cam-live";
      stage.querySelector(".cam-still")?.remove();
      stage.appendChild(reuse);
      live.video = reuse;
      reuse.play().catch(() => {});
      mode("● LIVE · HD", true);
      return;
    }
    const why = [];
    let mjpeg = false;
    let hd = false;
    // MJPEG through the add-on (the same as the thumbnail) and, inside Home Assistant, its own
    // HLS video (sharper) start together: whichever plays first is shown, HLS wins when it plays.
    const mjpegP = (async () => {
      if (reuse) {
        reuse.onerror = null;
        reuse.removeAttribute("data-cam");
        reuse.removeAttribute("data-live");
        reuse.className = "cam-live";
        stage.appendChild(reuse);
        live.img = reuse;
      } else {
        await this.playMJPEG(stage, eid, live);
      }
      if (this.live !== live || !live.img) return; // closed, or HLS already took over
      stage.querySelector(".cam-still")?.remove();
      if (!hd) mode("● LIVE", true);
      mjpeg = true;
    })().catch((err) => {
      why.push(`MJPEG: ${err.message}`);
      if (live.img) { live.img.src = ""; live.img.remove(); live.img = null; }
    });
    const hass = haParent();
    const hlsP = hass && Number(s?.a.supported_features) & 2 ? (async () => {
      const { url } = await hass.connection.sendMessagePromise({ type: "camera/stream", entity_id: eid, format: "hls" });
      if (this.live !== live) return;
      await this.playHLS(stage, url, live);
      if (this.live !== live) return;
      if (live.img) { live.img.src = ""; live.img.remove(); live.img = null; }
      hd = true;
      mode("● LIVE · HD", true);
    })().catch((err) => {
      why.push(`HLS: ${err.message || err.code || err}`);
      this.stopVideo(live);
    }) : null;
    await Promise.all([mjpegP, hlsP]);
    if (this.live !== live || mjpeg || hd) return;
    mode(`${t("Istantanee ogni secondo — video non disponibile")} (${why.join("; ")})`);
    const still = stage.querySelector(".cam-still");
    live.timer = setInterval(() => {
      const url = this.camURL(eid);
      const next = new Image();
      next.onload = () => { if (still) still.src = url; };
      next.src = url;
    }, 1000);
  }

  // Resolves once the video really plays; rejects on error or after 12 s of nothing.
  async playHLS(stage, url, live) {
    const video = document.createElement("video");
    Object.assign(video, { muted: true, autoplay: true, playsInline: true });
    video.className = "cam-live";
    if (live.img) video.style.display = "none"; // the MJPEG keeps playing until this one does
    stage.appendChild(video);
    live.video = video;
    await this.hlsPlay(video, url, 12);
    video.style.display = "";
    stage.querySelector(".cam-still")?.remove();
  }

  // Plays an HLS url in a <video>, like Home Assistant: hls.js wherever it works (Android, PC),
  // native HLS only otherwise (iPhone; some Android WebViews say they play HLS natively but
  // then don't). Resolves once it really plays; rejects on error or after `secs` of nothing.
  async hlsPlay(video, url, secs) {
    await loadScript("static/vendor/hls/hls.light.min.js").catch(() => {});
    if (video.dataset.stopped) throw new Error("stopped");
    await new Promise((ok, fail) => {
      const timer = setTimeout(() => fail(new Error(t("nessuna immagine dopo {n} secondi", { n: secs }))), secs * 1000);
      video.addEventListener("playing", () => { clearTimeout(timer); ok(); }, { once: true });
      video.addEventListener("error", () => { clearTimeout(timer); fail(new Error(`${t("errore del video")} (${video.error?.code})`)); }, { once: true });
      if (window.Hls?.isSupported()) {
        const hls = (video._hls = new window.Hls({ backBufferLength: 10, liveSyncDurationCount: 2 }));
        hls.on(window.Hls.Events.ERROR, (_, d) => { if (d.fatal) { clearTimeout(timer); fail(new Error(d.details || d.type)); } });
        hls.loadSource(url);
        hls.attachMedia(video);
      } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = url;
      } else {
        clearTimeout(timer);
        fail(new Error(t("il browser non riproduce HLS")));
      }
      video.play().catch(() => {});
    });
  }

  stopVideo(live) {
    if (live.video) { this.stopThumb(live.video); live.video.remove(); live.video = null; }
  }

  // MJPEG from the add-on: resolves at the first frame.
  async playMJPEG(stage, eid, live) {
    const img = document.createElement("img");
    img.className = "cam-live";
    img.alt = "";
    img.src = this.camURL(eid, 0, true);
    stage.appendChild(img);
    live.img = img;
    const start = Date.now();
    while (!img.naturalWidth) {
      if (this.live !== live || live.img !== img) return; // closed, or HLS took over
      if (Date.now() - start > 10000) throw new Error(t("nessuna immagine dopo {n} secondi", { n: 10 }));
      await new Promise((r) => setTimeout(r, 250));
    }
  }

  overlay(title, body, isLive = false) {
    this.closeCamera(false);
    const box = document.createElement("div");
    box.className = "casa-modal casa-overlay";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-label", title);
    box.innerHTML = `<section class="panel casa-panel ${isLive ? "casa-cam-modal" : "casa-cam-grid"}">
      <h3>${esc(title)} <button class="casa-x" aria-label="${t("Chiudi")}">×</button></h3>${body}</section>`;
    box.querySelector(".casa-x").addEventListener("click", () => this.closeCamera());
    box.addEventListener("click", (e) => { if (e.target === box) this.closeCamera(); });
    document.body.appendChild(box);
    this.live = { box };
    return box;
  }

  closeCamera(redraw = true) {
    const live = this.live;
    if (!live) return;
    this.live = null;
    clearInterval(live.timer);
    this.stopVideo(live);
    if (live.img) live.img.src = ""; // closes the MJPEG connection
    live.box.remove();
    if (redraw && this.visible) this.render(true); // the thumbnails go live again
  }

  // ---------------------------------------------------------------- alarm
  // Locks are not alarms: with a code in Home Assistant the keypad, otherwise a "Sì / No"
  // inside the card. Locking needs no confirmation.
  lock(eid) {
    const s = this.st(eid);
    if (!s) return;
    if (s.s !== "locked") { this.call("lock", "lock", { entity_id: eid }, eid); this.toast(t("Blocco {name}…", { name: s.n })); return; }
    if (s.a.code_format) this.pad = { eid, domain: "lock", service: "unlock", code: "", error: "", busy: false };
    else this.lockAsk = eid;
    this.render(true);
  }

  alarm(eid, service) {
    const s = this.st(eid);
    const disarm = service === "alarm_disarm";
    if (s.a.code_format && (disarm || s.a.code_arm_required !== false)) {
      // The keypad is the confirmation: nothing happens until the code is sent.
      this.pad = { eid, domain: "alarm_control_panel", service, code: "", error: "", busy: false };
      this.render(true);
      return;
    }
    if (disarm && !confirm(t("Disinserire {name}?", { name: s.n }))) return;
    this.call("alarm_control_panel", service, { entity_id: eid }, eid);
    this.toast(disarm ? t("Disinserisco l'allarme…") : t("Inserisco l'allarme…"));
  }

  padKey(key) {
    const p = this.pad;
    if (!p || p.busy) return;
    if (key === "back") p.code = p.code.slice(0, -1);
    else if (key === "ok") return this.padSend();
    else if (p.code.length < 12) p.code += key;
    p.error = "";
    const dots = this.root.querySelector(".pad-dots");
    if (dots) { dots.textContent = "●".repeat(p.code.length) || "—"; this.root.querySelector(".pad-error").textContent = ""; }
  }

  async padSend() {
    const p = this.pad;
    if (!p?.code) return;
    p.busy = true;
    const disarm = p.service === "alarm_disarm";
    try {
      await this.api("/api/casa/call", { method: "POST", body: JSON.stringify({ domain: p.domain, service: p.service, data: { entity_id: p.eid, code: p.code } }) });
      this.pad = null;
      this.toast(p.domain === "lock" ? t("Sblocco…") : disarm ? t("Disinserisco l'allarme…") : t("Inserisco l'allarme…"));
    } catch (err) {
      // Wrong code (or the alarm said no): stay on the keypad.
      Object.assign(p, { busy: false, code: "", error: /code|codice/i.test(err.message) ? t("Codice errato") : `⚠ ${err.message.replace(/^\{"detail":"|"\}$/g, "")}` });
    }
    this.render(true);
  }

  padHTML() {
    const p = this.pad, s = this.st(p.eid);
    const label = { unlock: t("Sblocca"), alarm_disarm: t("Disinserisci"), alarm_arm_home: t("Inserisci · In casa"), alarm_arm_away: t("Inserisci · Fuori"), alarm_arm_night: t("Inserisci · Notte"), alarm_arm_vacation: t("Inserisci · Vacanza") }[p.service] || p.service;
    const numeric = s?.a.code_format !== "text";
    const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "back", "0", "ok"];
    const body = numeric
      ? `<div class="pad-dots" aria-live="polite">${"●".repeat(p.code.length) || "—"}</div>
         <div class="pad-keys">${keys.map((k) => `<button data-act="pad" data-k="${k}" class="${k === "ok" ? "ok" : ""}" aria-label="${k === "back" ? t("Cancella") : k === "ok" ? t("Conferma") : k}">${k === "back" ? "⌫" : k === "ok" ? "✓" : k}</button>`).join("")}</div>`
      : `<input type="password" id="pad-text" autocomplete="off" aria-label="${t("Codice")}"><div class="casa-actions"><button class="casa-primary" data-act="pad-text">${t("Conferma")}</button></div>`;
    return `<div class="casa-modal" role="dialog" aria-label="${t("Codice")}"><section class="panel casa-panel casa-pad ${p.service === "alarm_disarm" || p.service === "unlock" ? "disarm" : ""}">
      <h3>${esc(label)} <button class="casa-x" data-act="pad-close" aria-label="${t("Annulla")}">×</button></h3>
      <div class="casa-sub">${esc(s?.n || p.eid)}</div>
      ${body}
      <div class="pad-error" role="alert">${esc(p.error || "")}</div>
    </section></div>`;
  }

  async call(domain, service, data, eid) {
    try {
      await this.api("/api/casa/call", { method: "POST", body: JSON.stringify({ domain, service, data }) });
    } catch (err) {
      this.toast(`⚠ ${err.message}`);
      if (eid) this.reload();
    }
  }

  toast(text) {
    // Outside the view's own HTML, or the next live redraw would wipe it.
    let box = document.querySelector(".casa-toast");
    if (!box) { box = document.createElement("div"); box.className = "casa-toast"; box.setAttribute("role", "status"); document.body.appendChild(box); }
    box.textContent = text;
    box.classList.add("on");
    clearTimeout(this._toast);
    this._toast = setTimeout(() => box.classList.remove("on"), 4000);
  }

  // ------------------------------------------------------------------ events
  async _click(e) {
    const el = e.target.closest("[data-act]");
    if (!el || !this.root.contains(el)) return;
    this._clickTarget = e.target;
    const { act, e: eid, area } = el.dataset;
    const domain = eid?.split(".")[0];
    if (this.editing && act === "toggle" && el.tagName === "ARTICLE") return; // arranging, not switching
    if (await this.energyClick(act, el)) return;
    switch (act) {
      case "room":
        this.selected = this.selected === area ? null : area;
        // On a phone the card sits under the plan: bring it up after drawing it.
        if (this.selected && innerWidth < 1100) setTimeout(() => this.root.querySelector(".casa-quick")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
        break;
      case "open": this.page = area; this.selected = area; this.editing = false; this.energyOpen = false; this.root.scrollTop = 0; break;
      case "home": this.page = null; this.editing = false; break;
      case "unselect": this.selected = null; break;
      case "floor": this.floor = Number(el.dataset.i); break;
      case "toggle": {
        const s = this.st(eid);
        if (s) s.s = s.s === "on" ? "off" : "on"; // optimistic: the live event confirms it
        this.call(domain === "media_player" ? "media_player" : domain, "toggle", { entity_id: eid }, eid);
        break;
      }
      case "tone": this.toneOpen = eid; break;
      case "tone-close": this.toneOpen = null; break;
      case "tone-bg": if (el !== this._clickTarget) return; this.toneOpen = null; break; // a tap outside the popup
      case "lcolor": this.call("light", "turn_on", { entity_id: eid, rgb_color: el.dataset.rgb.split(",").map(Number) }); return;
      case "lpick": return; // the colour picker: chosen in _change
      case "scene": this.call(domain, domain === "button" || domain === "input_button" ? "press" : "turn_on", { entity_id: eid }); this.toast(`▶ ${this.st(eid)?.n || eid}`); return;
      case "all-off": {
        const lights = this.lightsOf(this.area(area)).filter((x) => this.isOn(x));
        // homeassistant.turn_off: the "lights" may be relays shown as lights (switch.*)
        if (lights.length) this.call("homeassistant", "turn_off", { entity_id: lights });
        lights.forEach((x) => { this.st(x).s = "off"; });
        break;
      }
      case "temp": {
        const s = this.st(eid);
        const step = Number(s.a.target_temp_step) || 0.5;
        const temp = Math.round(((Number(s.a.temperature) || 20) + step * Number(el.dataset.d)) * 10) / 10;
        s.a.temperature = temp;
        this.call("climate", "set_temperature", { entity_id: eid, temperature: temp });
        break;
      }
      case "gate": this.gate(eid); return;
      case "alarm": this.alarm(eid, el.dataset.s); return;
      case "cam": this.openCamera(eid); return;
      case "cams": this.openCameraGrid(); return;
      case "pad": this.padKey(el.dataset.k); return;
      case "pad-text": this.pad.code = this.root.querySelector("#pad-text")?.value || ""; this.padSend(); return;
      case "pad-close": this.pad = null; break;
      case "alarm-panel": this.alarmOpen = true; break;
      case "weather": this.weatherOpen = true; break;
      case "weather-close": this.weatherOpen = false; break;
      case "ddone": this.api(`/api/deadlines/${el.dataset.id}/done`, { method: "POST" }).catch(() => {}); el.closest(".hc-today")?.classList.add("gone"); return;
      case "alarm-close": this.alarmOpen = false; break;
      case "kind": return;
      case "hvac": this.st(eid).s = el.dataset.m; this.call("climate", "set_hvac_mode", { entity_id: eid, hvac_mode: el.dataset.m }); break;
      case "cover": this.call(domain, el.dataset.s, { entity_id: eid }); return;
      case "valve": this.call("valve", el.dataset.s, { entity_id: eid }, eid); return;
      case "media": this.call("media_player", el.dataset.s, { entity_id: eid }, eid); return;
      case "mshuffle": this.call("media_player", "shuffle_set", { entity_id: eid, shuffle: el.dataset.v === "1" }); return;
      case "mrepeat": this.call("media_player", "repeat_set", { entity_id: eid, repeat: el.dataset.v }); return;
      case "mmute": this.call("media_player", "volume_mute", { entity_id: eid, is_volume_muted: el.dataset.v === "1" }); return;
      case "vac": this.call("vacuum", el.dataset.s, { entity_id: eid }); return;
      case "lock": this.lock(eid); return;
      case "lock-yes": this.lockAsk = null; this.call("lock", "unlock", { entity_id: eid }, eid); this.toast(t("Sblocco {name}…", { name: this.st(eid)?.n || eid })); break;
      case "lock-no": this.lockAsk = null; break;
      case "edit": this.editing = !this.editing; if (this.editing) this.search(""); break;
      // helpers (time of day, numbers, lists)
      case "pick": { const input = el.parentElement.querySelector("input[data-act='dt']"); try { input.showPicker(); } catch { input.focus(); } return; }
      case "nudge": {
        const st = this.st(eid), t = (String(st?.s).match(/\d{2}:\d{2}/) || ["00:00"])[0];
        const m = (((Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5)) + Number(el.dataset.d)) % 1440) + 1440) % 1440;
        this.setDateTime(eid, `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`);
        break;
      }
      case "stock-use": case "stock-add": {
        const st = this.st(eid), cfg = this.data.stock?.[eid] || {};
        const max = Number(st.a.max ?? st.a.maximum ?? Infinity), min = Number(st.a.min ?? st.a.minimum ?? 0);
        const v = (parseFloat(st.s) || 0) + (act === "stock-use" ? -1 : Number(cfg.delivery) || 1);
        this.setNumber(eid, Math.min(max, Math.max(min, v)));
        this.stockAt[eid] = 0; // the pace changes: ask again
        break;
      }
      case "stock-cfg": this.stockEdit = this.stockEdit === eid ? null : eid; break;
      case "stock-save": {
        const box = el.closest(".hc-stock");
        const body = { delivery: Number(box.querySelector("[name=delivery]").value), low: Number(box.querySelector("[name=low]").value) };
        this.stockEdit = null;
        this.api(`/api/casa/entities/${encodeURIComponent(eid)}/stock`, { method: "POST", body: JSON.stringify(body) })
          .then(() => this.reload(true)).catch((err) => this.toast(err.message));
        break;
      }
      case "numstep": {
        const st = this.st(eid), step = Number(st.a.step ?? 1);
        const v = Math.min(Number(st.a.max ?? Infinity), Math.max(Number(st.a.min ?? -Infinity), (parseFloat(st.s) || 0) + step * Number(el.dataset.d)));
        this.setNumber(eid, Math.round(v / step) * step);
        break;
      }
      case "selopt": if (el.tagName === "SELECT") return; this.setOption(eid, el.dataset.v); break;
      // the room's cards, arranged by the owner
      case "move": this.moveItem(el.dataset.id, Number(el.dataset.d)); return;
      case "size": {
        const id = el.dataset.id, w = el.dataset.w;
        if (id.startsWith("card:")) {
          const a = this.area(this.page), card = a.cards.find((c) => `card:${c.id}` === id);
          if (card) { card.size = w; this.api(`/api/casa/rooms/${encodeURIComponent(a.id)}/cards`, { method: "POST", body: JSON.stringify(card) }).catch((err) => this.toast(`⚠ ${err.message}`)); }
        } else {
          (this.data.sizes ||= {})[id] = w;
          if (w !== "wide") delete this.data.sizes[id];
          this.api(`/api/casa/entities/${encodeURIComponent(id)}/display`, { method: "POST", body: JSON.stringify({ size: w }) }).catch((err) => this.toast(`⚠ ${err.message}`));
        }
        break;
      }
      case "rename": this.renaming = { eid, name: this.st(eid)?.n || "" }; break;
      case "rename-close": this.renaming = null; break;
      case "rename-save": case "rename-reset": {
        const name = act === "rename-reset" ? null : this.root.querySelector("#casa-rename").value.trim() || null;
        const e = this.renaming.eid;
        this.renaming = null;
        await this.api(`/api/casa/entities/${encodeURIComponent(e)}/display`, { method: "POST", body: JSON.stringify({ name }) }).catch((err) => this.toast(`⚠ ${err.message}`));
        await this.reload(true);
        return;
      }
      case "order-reset": this.saveOrder([]); break;
      case "card-new": this.cardEdit = { area: this.page, id: null, name: "", entities: [], size: "wide", group: "", enable: null, nochart: [], q: "", cands: [] }; this.cardSearch(""); break;
      case "card-free": this.freeEdit = { area: this.page, id: null, name: "", color: "", style: "flat", group: "", blocks: [], sel: null, target: "entity", q: "", cands: [] }; break;
      case "card-edit": {
        const card = this.area(this.page).cards.find((c) => c.id === el.dataset.id);
        if (card.kind === "free") {
          this.freeEdit = { area: this.page, id: card.id, name: card.name, color: card.color || "", style: card.style || "", group: card.group || "", blocks: card.blocks.map((b) => ({ ...b })), sel: null, target: "entity", q: "", cands: [] };
          break;
        }
        this.cardEdit = { area: this.page, id: card.id, name: card.name, entities: [...card.entities], size: card.size, group: card.group || "", enable: card.enable ?? null, nochart: [...(card.nochart || [])], q: "", cands: [] };
        this.cardSearch("");
        break;
      }
      case "fb-close": this.freeEdit = null; break;
      case "fb-draft": {
        const f = this.freeEdit, text = (f.draft || "").trim();
        if (text.length < 3) { this.toast(t("Descrivi la card che vuoi")); return; }
        f.busy = true;
        this.render(true);
        try {
          const r = await (await this.api(`/api/casa/rooms/${encodeURIComponent(f.area)}/cards/draft`, { method: "POST", body: JSON.stringify({ text }) })).json();
          this.takeCard(f, r);
          if (!r.blocks.length) this.toast(t("Jarvis non ha trovato entità adatte: prova a descriverla in un altro modo."));
          else if (r.dropped) this.toast(r.dropped === 1 ? t("Un blocco scartato: un'entità che in casa non c'è.") : t("{n} blocchi scartati: entità che in casa non ci sono.", { n: r.dropped }));
        } catch (err) { this.toast(`⚠ ${err.message}`); }
        f.busy = false;
        break;
      }
      case "fb-export": {
        const f = this.freeEdit;
        f.exported = JSON.stringify({ hubnex_card: 1, name: f.name, color: f.color, style: f.style || "", blocks: f.blocks }, null, 1);
        navigator.clipboard?.writeText(f.exported).then(() => this.toast(t("Card copiata: incollala dove vuoi."))).catch(() => {});
        break;
      }
      case "card-import": this.freeEdit = { area: this.page, id: null, name: "", color: "", style: "flat", group: "", blocks: [], sel: null, target: "entity", q: "", cands: [], importing: true }; break;
      case "fb-import": {
        const f = this.freeEdit;
        let card;
        try { card = JSON.parse(f.paste || ""); } catch { this.toast(t("Il testo incollato non è una card di HubNEX.")); return; }
        try {
          const r = await (await this.api("/api/casa/cards/import", { method: "POST", body: JSON.stringify(card) })).json();
          f.importing = false;
          this.takeCard(f, r);
          if (r.missing) this.toast(r.missing === 1 ? t("Un blocco ha un'entità che qui non c'è: sceglila tu.") : t("{n} blocchi hanno entità che qui non ci sono: sceglile tu.", { n: r.missing }));
        } catch (err) { this.toast(`⚠ ${err.message}`); return; }
        break;
      }
      case "fb-tpl": {
        const [, name, color, list] = TEMPLATES.find(([k]) => k === el.dataset.t);
        const f = this.freeEdit, used = new Set();
        const pool = [...(this.area(f.area)?.entities || []), ...Object.keys(this.data.states)];
        const take = (fit) => {
          const e = fit && pool.find((x) => !used.has(x) && this.st(x) && fit(this.st(x)));
          if (e) used.add(e);
          return e || "";
        };
        const made = list.map(([kind, fit, w, h]) => {
          const b = { kind, entity: take(fit), entity2: "", label: "", w, h };
          if (kind === "band") b.entity2 = take((s) => s.k === "datetime");
          if (kind === "ring" && /humid|umid/i.test(this.st(b.entity)?.a.device_class || "")) Object.assign(b, { min: 0, max: 100 });
          if (kind === "ask") b.label = t("Cosa sta suonando in casa?");
          return b;
        });
        // only what the house has: a block without its entity is left out (and said)
        f.blocks = made.filter((b) => NO_ENTITY.has(b.kind) || (b.entity && (b.kind !== "band" || b.entity2)));
        const skipped = made.length - f.blocks.length;
        if (skipped) this.toast(skipped === 1 ? t("Un blocco del modello non ha trovato un'entità adatta: aggiungilo a mano.") : t("{n} blocchi del modello non hanno trovato un'entità adatta: aggiungili a mano.", { n: skipped }));
        f.name ||= name;
        f.color = color;
        f.sel = null;
        break;
      }
      case "fb-rule-add": (this.freeEdit.blocks[this.freeEdit.sel].rules ||= []).push({ op: ">", v: "", c: "red" }); break;
      case "fb-rule-del": this.freeEdit.blocks[this.freeEdit.sel].rules.splice(Number(el.dataset.i), 1); break;
      case "fb-show-add": this.freeEdit.blocks[this.freeEdit.sel].show = { e: "", op: "=", v: "on" }; this.freeEdit.target = "show"; this.freeSearch(""); break;
      case "fb-show-del": delete this.freeEdit.blocks[this.freeEdit.sel].show; this.freeEdit.target = "entity"; break;
      case "fb-ask": this.ask(el.dataset.q || ""); return;
      case "fb-tap": {
        const card = (this.area(this.page)?.cards || []).find((c) => c.id === el.dataset.card);
        const b = card?.blocks?.[Number(el.dataset.i)], tap = b?.tap;
        if (!tap) return;
        const target = tap.e || b.entity, dom = target?.split(".")[0];
        if (tap.do === "toggle" && target) { const s = this.st(target); if (s) s.s = s.s === "on" ? "off" : "on"; this.call(dom, "toggle", { entity_id: target }, target); }
        else if (tap.do === "run" && target) { this.call(dom, ["button", "input_button"].includes(dom) ? "press" : "turn_on", { entity_id: target }); this.toast(`▶ ${this.st(target)?.n || target}`); return; }
        else if (tap.do === "ask") { this.ask(tap.text); return; }
        else if (tap.do === "room" && this.area(tap.area)) { this.page = tap.area; this.selected = tap.area; this.root.scrollTop = 0; }
        break;
      }
      case "fb-add": {
        const [kind, , , [w, h]] = BLOCKS.find(([k]) => k === el.dataset.k);
        const f = this.freeEdit;
        f.blocks.push({ kind, entity: "", entity2: "", label: "", w, h });
        f.sel = f.blocks.length - 1;
        f.target = "entity";
        this.freeSearch("");
        break;
      }
      case "fb-sel":
        if (this._dragged) { this._dragged = false; return; } // the end of a drag, not a tap
        this.freeEdit.sel = Number(el.dataset.i); this.freeEdit.target = "entity"; this.freeSearch(""); break;
      case "fb-target": this.freeEdit.target = el.dataset.t; this.freeSearch(""); break;
      case "fb-pick": {
        const f = this.freeEdit, c = f.cands.find((x) => x.entity_id === eid);
        if (c?.state) this.data.states[eid] ||= c.state; // shown at once, before the card is saved
        const blk = f.blocks[f.sel];
        if (f.target === "show") (blk.show ||= { op: "=", v: "on" }).e = eid;
        else if (f.target === "tap") (blk.tap ||= { do: "toggle" }).e = eid;
        else blk[f.target] = eid;
        if (f.blocks[f.sel].kind === "band" && f.target === "entity") { f.target = "entity2"; this.freeSearch(""); }
        break;
      }
      case "fb-size": Object.assign(this.freeEdit.blocks[this.freeEdit.sel], { w: Number(el.dataset.w), h: Number(el.dataset.h) }); break;
      case "fb-move": {
        const f = this.freeEdit, i = f.sel, j = i + Number(el.dataset.d);
        if (j < 0 || j >= f.blocks.length) return;
        [f.blocks[i], f.blocks[j]] = [f.blocks[j], f.blocks[i]];
        f.sel = j;
        break;
      }
      case "fb-del": this.freeEdit.blocks.splice(this.freeEdit.sel, 1); this.freeEdit.sel = null; break;
      case "fb-color": this.freeEdit.color = el.dataset.c; break;
      case "fb-style": this.freeEdit.style = el.dataset.s; break;
      case "fb-save": {
        const f = this.freeEdit;
        if (!f.blocks.length) { this.toast(t("Aggiungi almeno un blocco")); return; }
        if (f.blocks.some((b) => !NO_ENTITY.has(b.kind) && !b.entity) || f.blocks.some((b) => b.kind === "band" && !b.entity2)) {
          this.toast(t("Scegli l'entità di ogni blocco")); return;
        }
        const blocks = f.blocks.map(({ kind, entity, entity2, label, w, h, min, max, rules, show, tap }) => ({
          kind, entity: entity || "", entity2: entity2 || "", label, w, h,
          ...(min != null && min !== "" ? { min: Number(min) } : {}), ...(max != null && max !== "" ? { max: Number(max) } : {}),
          ...(rules?.some((r) => r.v !== "") ? { rules: rules.filter((r) => r.v !== "") } : {}),
          ...(show?.e ? { show } : {}),
          ...(tap?.do ? { tap: { do: tap.do, e: tap.e || "", text: tap.text || "", area: tap.area || "" } } : {}),
        }));
        try {
          await this.api(`/api/casa/rooms/${encodeURIComponent(f.area)}/cards`, { method: "POST", body: JSON.stringify({ id: f.id, name: f.name || t("Card"), kind: "free", blocks, color: f.color, style: f.style || "", size: "wide", group: f.group || null }) });
          this.freeEdit = null;
          if (this.histAt) this.histAt[f.area] = 0; // its charts: ask for them now
          await this.reload(true);
        } catch (err) { this.toast(`⚠ ${err.message}`); }
        return;
      }
      case "card-del": {
        const card = this.area(this.page).cards.find((c) => c.id === el.dataset.id);
        if (!confirm(t("Togliere la card \"{name}\"? Le entità restano in Home Assistant.", { name: card?.name }))) return;
        await this.api(`/api/casa/rooms/${encodeURIComponent(this.page)}/cards/${encodeURIComponent(el.dataset.id)}/remove`, { method: "POST" }).catch((err) => this.toast(`⚠ ${err.message}`));
        await this.reload(true);
        return;
      }
      case "card-close": this.cardEdit = null; break;
      case "card-add": {
        const cand = this.cardEdit.cands.find((x) => x.entity_id === eid);
        if (cand?.state && !this.data.states[eid]) this.data.states[eid] = cand.state; // preview before saving
        if (!this.cardEdit.entities.includes(eid)) this.cardEdit.entities.push(eid);
        this.cardKeep();
        break;
      }
      case "card-rm": this.cardEdit.entities = this.cardEdit.entities.filter((x) => x !== eid); this.cardKeep(); break;
      case "card-up": case "card-down": {
        const list = this.cardEdit.entities, i = list.indexOf(eid), j = i + (act === "card-up" ? -1 : 1);
        if (j >= 0 && j < list.length) [list[i], list[j]] = [list[j], list[i]];
        this.cardKeep();
        break;
      }
      case "card-size": this.cardKeep(); this.cardEdit.size = el.dataset.w; break;
      case "card-chart": {
        this.cardKeep();
        const list = this.cardEdit.nochart;
        if (list.includes(eid)) list.splice(list.indexOf(eid), 1); else list.push(eid);
        break;
      }
      case "chart": {
        const off = (this.data.nochart ||= []).includes(eid);
        this.data.nochart = off ? this.data.nochart.filter((x) => x !== eid) : [...this.data.nochart, eid];
        this.api(`/api/casa/entities/${encodeURIComponent(eid)}/display`, { method: "POST", body: JSON.stringify({ chart: off }) }).catch((err) => this.toast(`⚠ ${err.message}`));
        break;
      }
      case "card-save": {
        this.cardKeep();
        const c = this.cardEdit;
        if (!c.entities.length) { this.toast(t("Aggiungi almeno un'entità")); return; }
        try {
          await this.api(`/api/casa/rooms/${encodeURIComponent(c.area)}/cards`, { method: "POST", body: JSON.stringify({ id: c.id, name: c.name || t("Card"), entities: c.entities, size: c.size, group: c.group || null, enable: c.enable && !c.entities.includes(c.enable) ? null : c.enable, nochart: c.nochart.filter((e) => c.entities.includes(e)) }) });
          this.cardEdit = null;
          this.toast(t("Card salvata"));
          await this.reload(true);
        } catch (err) { this.toast(`⚠ ${err.message.replace(/^\{"detail":"|"\}$/g, "")}`); }
        return;
      }
      case "hide": await this.api(`/api/casa/rooms/${encodeURIComponent(area)}/entities/${encodeURIComponent(eid)}/remove`, { method: "POST" }).catch((err) => this.toast(`⚠ ${err.message}`)); return;
      case "add": {
        try {
          await this.api(`/api/casa/rooms/${encodeURIComponent(area)}/entities`, { method: "POST", body: JSON.stringify({ entity_id: eid, mode: this.mode }) });
          this.toast(this.mode === "ha" ? t("Spostata anche in Home Assistant") : t("Aggiunta solo alla plancia"));
          this.search(this.query || "");
        } catch (err) {
          this.toast(`⚠ ${err.message.replace(/^\{"detail":"|"\}$/g, "")}`);
        }
        return;
      }
      case "layout": this.editor.open().catch((err) => this.toast(`⚠ ${err.message}`)); return;
      case "layout-close": this.layout = null; document.activeElement?.blur(); break;
      case "layout-save": await this.saveLayout(); return;
      default: return;
    }
    this.render(true);
  }

  _change(e) {
    const el = e.target;
    if (el.dataset.act === "bright") {
      this.call("light", "turn_on", { entity_id: el.dataset.e, brightness_pct: Number(el.value) });
    } else if (el.dataset.act === "ktemp") {
      this.call("light", "turn_on", { entity_id: el.dataset.e, color_temp_kelvin: Number(el.value) });
    } else if (el.dataset.act === "lpick") {
      const hex = el.value.replace("#", "");
      this.call("light", "turn_on", { entity_id: el.dataset.e, rgb_color: [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16)) });
    } else if (el.id === "card-enable" || el.id === "card-group") {
      this.cardKeep();
      this.render(true);
    } else if (el.dataset.act === "dt") {
      this.setDateTime(el.dataset.e, el.value);
    } else if (el.dataset.act === "numval") {
      this.setNumber(el.dataset.e, Number(el.value));
    } else if (el.dataset.act === "selopt" && el.tagName === "SELECT") {
      this.setOption(el.dataset.e, el.value);
      el.blur();
    } else if (el.dataset.act === "textval") {
      const domain = el.dataset.e.split(".")[0];
      this.call(domain, "set_value", { entity_id: el.dataset.e, value: el.value }, el.dataset.e);
      el.blur();
    } else if (el.dataset.act === "msrc" && el.value) {
      this.call("media_player", "select_source", { entity_id: el.dataset.e, source: el.value });
      el.blur();
    } else if (el.dataset.act === "vfan") {
      this.call("vacuum", "set_fan_speed", { entity_id: el.dataset.e, fan_speed: el.value });
      el.blur();
    } else if (el.dataset.act === "volume") {
      this.call("media_player", "volume_set", { entity_id: el.dataset.e, volume_level: Number(el.value) / 100 });
    } else if (el.name === "casa-mode") {
      this.mode = el.value;
    } else if (el.dataset.act === "kind") {
      const eid = el.dataset.e;
      this.api(`/api/casa/entities/${encodeURIComponent(eid)}/kind`, { method: "POST", body: JSON.stringify({ kind: el.value || null }) })
        .then(() => this.toast(el.value ? `${this.st(eid)?.n}: ${SHOW_AS.find(([k]) => k === el.value)[1].toLowerCase()}` : t("Tipo come in Home Assistant")))
        .catch((err) => this.toast(`⚠ ${err.message}`));
      if (this.st(eid)) this.st(eid).k = el.value || this.st(eid).nk || this.st(eid).k; // shown at once
      el.blur();
      this.render(true);
    } else if (el.dataset.act === "temp-src") {
      const area = this.area(el.dataset.area);
      if (area) area.temp = el.value || null; // shown at once; the server confirms with casa_changed
      this.api(`/api/casa/rooms/${encodeURIComponent(el.dataset.area)}/temperature`, { method: "POST", body: JSON.stringify({ entity_id: el.value || null }) })
        .then(() => this.toast(el.value ? t("Temperatura della stanza impostata") : t("Temperatura automatica")))
        .catch((err) => this.toast(`⚠ ${err.message}`));
      el.blur();
      this.render(true);
    }
  }

  _input(e) {
    const f = this.freeEdit;
    if (f && e.target.dataset.fb && f.blocks[f.sel]) {
      const path = e.target.dataset.fb.split("."), b = f.blocks[f.sel];
      let o = b;
      for (const k of path.slice(0, -1)) o = o[k] ??= {};
      o[path.at(-1)] = e.target.value;
      if (path.join(".") === "tap.do" && !e.target.value) delete b.tap;
      if (e.target.tagName === "SELECT" && path.at(-1) === "op") { this.render(true); return; }
      if (e.target.tagName === "SELECT" && path[0] === "tap") { if (b.tap?.do === "toggle" || b.tap?.do === "run") { f.target = "tap"; this.freeSearch(""); } this.render(true); return; }
      const box = this.root.querySelector("#fb-preview");
      if (box) box.innerHTML = this.freeCard(f, f);
      return;
    }
    if (f && (e.target.id === "fb-draft-text" || e.target.id === "fb-paste")) {
      f[e.target.id === "fb-paste" ? "paste" : "draft"] = e.target.value;
      return;
    }
    if (f && ["fb-name", "fb-label", "fb-min", "fb-max", "fb-find"].includes(e.target.id)) {
      const v = e.target.value;
      if (e.target.id === "fb-find") { clearTimeout(this._find); this._find = setTimeout(() => this.freeSearch(v), 250); return; }
      if (e.target.id === "fb-name") f.name = v;
      else f.blocks[f.sel][{ "fb-label": "label", "fb-min": "min", "fb-max": "max" }[e.target.id]] = e.target.id === "fb-label" ? v : v === "" ? null : Number(v);
      const box = this.root.querySelector("#fb-preview");
      if (box) box.innerHTML = this.freeCard(f, f);
      return;
    }
    if (e.target.id === "epick-find") {
      clearTimeout(this._find);
      this._find = setTimeout(() => this.ePickSearch(e.target.value), 250);
      return;
    }
    if (e.target.id === "card-find") {
      clearTimeout(this._find);
      this._find = setTimeout(() => this.cardSearch(e.target.value), 250);
      return;
    }
    if (e.target.id === "casa-find") {
      clearTimeout(this._find);
      this._find = setTimeout(() => this.search(e.target.value), 250);
    }
  }

  async search(q) {
    this.query = q;
    try {
      this.cands = await (await this.api(`/api/casa/entities?q=${encodeURIComponent(q)}&area=${encodeURIComponent(this.page || "")}`)).json();
    } catch { this.cands = []; }
    const box = this.root.querySelector("#casa-cands");
    if (box) box.innerHTML = this.candsHTML();
  }

  async openLayout() {
    try {
      this.layout = await (await this.api("/api/casa/layout")).json();
    } catch (err) { this.toast(`⚠ ${err.message}`); return; }
    this.render();
  }

  async saveLayout() {
    const text = this.root.querySelector("#casa-layout-text").value;
    try {
      await this.api("/api/casa/layout", { method: "POST", body: JSON.stringify({ text }) });
      this.layout = null;
      document.activeElement?.blur(); // a tap on Save can leave the keyboard on the text
      this.toast(t("Piantina salvata"));
      await this.reload(true);
    } catch (err) {
      const box = this.root.querySelector(".layout-error");
      box.textContent = err.message.replace(/^\{"detail":"|"\}$/g, "");
    }
  }

  // ------------------------------------------------------------------ rendering
  // `force`: drawn because of something the owner did; otherwise a live update, which waits
  // while a slider, the search or the floor plan text is in use.
  render(force = false) {
    if (!this.visible) return;
    const active = document.activeElement;
    if (!force && active && this.root.contains(active) && (active.type === "range" || active.type === "color" || active.tagName === "TEXTAREA" || active.tagName === "SELECT" || active.id === "casa-find" || active.closest(".casa-modal") || active.classList.contains("hc-input"))) {
      this.dirty = true; // don't yank the control from under the finger: redraw on blur
      return;
    }
    this.dirty = false;
    const scroll = this.root.scrollTop;
    const panelScroll = this.root.querySelector(".casa-modal .panel")?.scrollTop || 0; // a dialog keeps its place too
    let html;
    if (this.error) html = `<div class="casa-empty panel">⚠ ${esc(this.error)}</div>`;
    else if (!this.data) html = `<div class="casa-empty panel">${t("Collegamento a Home Assistant…")}</div>`;
    else if (!this.data.ready) html = `<div class="casa-empty panel">${t("Home Assistant non è ancora collegato: riprovo…")}</div>`;
    else html = this.page && this.area(this.page) ? this.roomHTML(this.area(this.page)) : this.homeHTML();
    // Dialogs live in their own layer: a live update of the house underneath doesn't touch an
    // open popup, and the popup itself is redrawn only when what it shows has changed.
    let layer = "";
    if (this.energyOpen && this.data?.ready) layer += this.energyHTML();
    if (this.layout) layer += this.layoutHTML();
    if (this.alarmOpen && this.data?.alarms?.length) {
      layer += `<div class="casa-modal" role="dialog" aria-label="${t("Allarme")}"><section class="panel casa-panel casa-alarm-modal">
        <h3>${t("Allarme")} <button class="casa-x" data-act="alarm-close" aria-label="${t("Chiudi")}">×</button></h3>
        <div class="hc-grid">${this.data.alarms.filter((e) => this.st(e)).map((e) => this.cardHTML(e)).join("")}</div></section></div>`;
    }
    if (this.toneOpen && this.st(this.toneOpen)) layer += this.toneHTML(this.toneOpen);
    if (this.weatherOpen && this.data?.weather && this.st(this.data.weather)) layer += this.weatherHTML();
    if (this.pad) layer += this.padHTML();
    if (this.cardEdit) layer += this.cardEditHTML();
    if (this.freeEdit) layer += this.freeEditHTML();
    if (this.renaming) layer += this.renameHTML();
    if (!this.pageEl || this.pageEl.parentNode !== this.root) {
      this.root.innerHTML = `<div class="casa-pagebox"></div><div class="casa-layer"></div>`;
      [this.pageEl, this.layerEl] = this.root.children;
      this._pageHTML = this._layerHTML = null;
    }
    if (force || html !== this._pageHTML) { this.pageEl.innerHTML = html; this._pageHTML = html; }
    if (force || layer !== this._layerHTML) {
      this.layerEl.innerHTML = layer;
      this._layerHTML = layer;
      const panel = this.layerEl.querySelector(".casa-modal .panel");
      if (panel) panel.scrollTop = panelScroll;
    }
    this.root.scrollTop = scroll;
    if (!this.live) {
      this.mountLive(this.pageEl);
      this.pruneLive();
    }
    document.body.classList.toggle("casa-sheet", !!(this.data && !this.page && this.selected && this.area(this.selected)));
    document.body.classList.toggle("casa-modal-open", !!(this.cardEdit || this.renaming || this.pad || this.layout || this.alarmOpen || this.energyOpen || this.toneOpen || this.weatherOpen || this.freeEdit));
    if (this.editing && this.cands) {
      const box = this.root.querySelector("#casa-cands");
      if (box) box.innerHTML = this.candsHTML();
    }
    if (this.data && !this.data.ready) setTimeout(() => this.visible && this.reload(), 5000);
  }

  homeHTML() {
    return `
      ${this.hudHTML()}
      <div class="casa-body">
        <aside class="casa-col casa-left">${this.climateHTML()}${this.activityHTML()}</aside>
        <main class="casa-center">${this.planHTML()}</main>
        <aside class="casa-col casa-right">${this.selected && this.area(this.selected) ? this.quickHTML(this.area(this.selected)) : this.overviewHTML()}</aside>
      </div>`;
  }

  climateHTML() {
    const rows = this.data.areas.filter((a) => !a.outside).map((a) => [a, this.temp(a)]).filter(([, v]) => v != null);
    const outside = this.data.weather && this.st(this.data.weather)?.a;
    if (!rows.length && !outside) return "";
    const avg = rows.length ? rows.reduce((s, [, v]) => s + v, 0) / rows.length : null;
    return `
      <section class="hc">
        <span class="hc-kick">${t("Temperatura delle stanze")}</span>
        ${rows.map(([a, v]) => `<button class="hc-temprow" data-act="room" data-area="${a.id}"><span>${esc(a.name)}</span><span class="hc-tbar"><i style="width:${Math.max(4, Math.min(100, ((v - 14) / 14) * 100))}%"></i></span><span class="mono">${num(v)}°</span></button>`).join("")}
        ${outside?.temperature != null ? `<div class="hc-temprow out"><span>${t("Esterno")}</span><span></span><span class="mono">${num(outside.temperature)}°</span></div>` : ""}
      </section>`;
  }

  planHTML() {
    const d = this.data;
    const floors = d.floors;
    const tiles = (list) => list.map((a) => {
      const cls = [this.lit(a) ? "lit" : "", this.alerts(a).length ? "alert" : "", this.selected === a.id ? "sel" : ""].join(" ");
      const temp = this.temp(a);
      return `<button class="casa-tile ${cls}" data-act="room" data-area="${a.id}"><b>${esc(a.name)}</b><span>${temp != null ? num(temp) + "°" : ""}${this.lit(a) ? ` · ${t("luce")}` : ""}${this.alerts(a).length ? ` · ${t("aperta")}` : ""}</span></button>`;
    }).join("");
    const outside = d.areas.filter((a) => a.outside);
    const others = d.areas.filter((a) => !a.placed);
    let plan = "";
    if (floors.length) {
      const f = floors[Math.min(this.floor, floors.length - 1)];
      const rooms = [...f.rooms].sort((a, b) => b.outline - a.outline).map((r) => {
        const a = r.area_id && this.area(r.area_id);
        const geo = `left:${r.x}%;top:${r.y}%;width:${r.w}%;height:${r.h}%${shapeStyle(r)}`;
        const small = r.w < 12 || r.h < 12;
        const tall = r.w < 12 && r.h > 30; // a narrow strip: the name runs along it
        if (!a) return `<div class="plan-room ${r.points ? "polygon" : ""} ${r.outline ? "outline" : "ghost"}" style="${geo}">${shapeSVG(r)}<b>${esc(r.name)}</b></div>`;
        const cls = [r.points ? "polygon" : "", r.outline ? "outline" : "", this.lit(a) ? "lit" : "", this.alerts(a).length ? "alert" : "", this.selected === a.id ? "sel" : "", small ? "small" : "", tall ? "tall" : ""].join(" ");
        const temp = this.temp(a);
        const tag = this.lit(a) ? t("LUCE") : this.alerts(a).length ? t("APERTA") : "";
        return `<button class="plan-room ${cls}" style="${geo}" data-act="room" data-area="${a.id}" aria-label="${esc(a.name)}">
          ${shapeSVG(r)}<b>${esc(a.name)}</b>${small ? "" : this.planIcons(a)}<span class="plan-meta"><span class="mono">${temp != null && !small ? num(temp) + "°" : ""}</span><span class="plan-tag">${small ? "" : tag}</span></span></button>`;
      }).join("");
      const tabs = floors.length > 1 ? `<div class="casa-floors">${floors.map((x, i) => `<button class="${i === this.floor ? "on" : ""}" data-act="floor" data-i="${i}">${esc(x.name)}</button>`).join("")}</div>` : `<div class="casa-floor-name">${esc(f.name)} · ${t("tocca una stanza")}</div>`;
      // The real drawing, faint under the hologram (light lines on the dark background).
      const tok = this.token();
      const img = f.image ? ` has-image" style="aspect-ratio:${f.aspect};--plan-img:url('api/casa/plan-image/${f.image}${tok ? "?token=" + encodeURIComponent(tok) : ""}')` : `" style="aspect-ratio:${f.aspect}`;
      plan = `${tabs}<div class="plan-wrap"><div class="plan${img}">${rooms}</div></div>`;
    } else if (!d.layout_error) {
      plan = `<div class="casa-hint panel">${t("Nessuna piantina ancora")} (<span class="mono">${esc(d.layout_file)}</span>): ${t("le stanze sono le aree di Home Assistant.")} <button data-act="layout">⚙ ${t("Disegna la piantina")}</button></div>`;
    }
    if (d.layout_error) {
      plan = `<div class="casa-hint panel bad">${t("La piantina ha un errore")} (<span class="mono">${esc(d.layout_file)}</span>): <b>${esc(d.layout_error)}</b> <button data-act="layout">⚙ ${t("Correggi")}</button></div>` + plan;
    }
    const alerts = d.areas.flatMap((a) => this.alerts(a).map((e) => `<button class="chip bad" data-act="room" data-area="${a.id}">${esc(this.st(e).n)} · ${esc(a.name)}</button>`)).join("");
    return `${plan}
      ${outside.length ? `<div class="casa-group"><span class="casa-lbl">${t("Fuori casa")}</span><div class="casa-tiles out">${tiles(outside)}</div></div>` : ""}
      ${others.length ? `<div class="casa-group"><span class="casa-lbl">${floors.length ? t("Altre aree") : t("Aree")}</span><div class="casa-tiles">${tiles(others)}</div></div>` : ""}
      ${alerts ? `<div class="casa-alerts">${alerts}</div>` : ""}`;
  }

  switchHTML(eid) {
    return `<button class="casa-switch ${this.isOn(eid) ? "on" : ""}" data-act="toggle" data-e="${eid}" aria-pressed="${this.isOn(eid)}" aria-label="${esc(this.st(eid)?.n)}"></button>`;
  }

  // What the room shows: the composed cards, then the entities not inside one of them; in the
  // owner's order when there is one.
  // The room's groups (Luci, Clima…), each with its cards in the owner's order. A composed card
  // sits in the group chosen for it, or in the group of its first entity.
  roomGroups(a) {
    const inCards = new Set((a.cards || []).flatMap((c) => c.entities));
    const groups = {};
    for (const c of a.cards || []) (groups[this.cardGroup(c)] ||= []).push(`card:${c.id}`);
    for (const e of a.entities) if (!inCards.has(e)) (groups[this.section(e)] ||= []).push(e);
    const rank = new Map((a.order || []).map((x, i) => [x, i]));
    const sort = (list) => list.map((x, i) => [x, rank.has(x) ? rank.get(x) : 1e6 + i]).sort((p, q) => p[1] - q[1]).map(([x]) => x);
    return SECTIONS.map(([k, title]) => [k, title, sort(groups[k] || [])]).filter(([, , ids]) => ids.length);
  }

  roomItems(a) { return this.roomGroups(a).flatMap(([, , ids]) => ids); }

  cardGroup(card) {
    if (card.group && SECTIONS.some(([k]) => k === card.group)) return card.group;
    const first = card.entities.find((e) => this.st(e));
    return first ? this.section(first) : "other";
  }

  itemHTML(id, a) {
    let html;
    if (id.startsWith("card:")) {
      const card = (a.cards || []).find((c) => `card:${c.id}` === id);
      if (!card) return "";
      html = this.composedCard(card);
    } else {
      html = this.cardHTML(id);
      if (!html) return "";
      if (this.data.sizes?.[id] === "wide") html = html.replace('class="hc ', 'class="hc wide ');
    }
    if (!this.editing) return html;
    const card = id.startsWith("card:");
    const wide = card ? (a.cards.find((c) => `card:${c.id}` === id)?.size === "wide") : this.data.sizes?.[id] === "wide" || /class="hc wide/.test(html);
    const bar = `<div class="hc-editbar">
        <button class="hc-handle" data-drag="${esc(id)}" aria-label="${t("Trascina per spostare")}">⋮⋮</button>
        <button data-act="move" data-d="-1" data-id="${esc(id)}" aria-label="${t("Sposta prima")}">‹</button><button data-act="move" data-d="1" data-id="${esc(id)}" aria-label="${t("Sposta dopo")}">›</button>
        ${card ? `<button data-act="card-edit" data-id="${esc(id.slice(5))}">${t("Modifica")}</button>` : `<button data-act="rename" data-e="${esc(id)}">${t("Rinomina")}</button>`}
        ${!card && this.st(id)?.k === "sensor" && !isNaN(parseFloat(this.st(id).s)) ? `<button data-act="chart" data-e="${esc(id)}">${(this.data.nochart || []).includes(id) ? t("Mostra grafico") : t("Togli grafico")}</button>` : ""}
        <button data-act="size" data-id="${esc(id)}" data-w="${wide ? "small" : "wide"}">${wide ? t("Piccola") : t("Larga")}</button>
        ${card ? `<button data-act="card-del" data-id="${esc(id.slice(5))}">${t("Togli")}</button>` : `<button data-act="hide" data-area="${a.id}" data-e="${esc(id)}">${t("Togli")}</button>`}
      </div>`;
    return html.replace(/<\/(article|div)>\s*$/, `${bar}</$1>`).replace(/^(\s*<(?:article|div) class="hc )/, `$1hc-edit `).replace(/^(\s*<(?:article|div) )/, `$1data-item="${esc(id)}" `);
  }

  roomHTML(a) {
    const groups = {};
    for (const e of a.entities) (groups[this.section(e)] ||= []).push(e);
    const lights = groups.light || [];
    const temp = this.temp(a);
    const presence = a.entities.find((e) => PRESENCE.has(this.dc(e)));
    const sources = this.tempSources(a);
    const chosen = this.tempSource(a);
    const tempLabel = sources.length > 1
      ? `<label class="casa-temp-src"><span>${t("temperatura da")}</span><select data-act="temp-src" data-area="${a.id}" aria-label="${t("Sensore della temperatura della stanza")}">
          <option value="" ${a.temp ? "" : "selected"}>${t("Automatico")}</option>
          ${sources.map((e) => `<option value="${e}" ${a.temp === e ? "selected" : ""}>${esc(this.st(e).n)} (${num(this.readTemp(e) ?? 0)}°)</option>`).join("")}
        </select></label>`
      : `<span>${t("temperatura")}</span>`;
    this.loadHistory(a);
    const watts = a.entities.map((e) => this.data.power?.[e]).filter(Boolean).reduce((sum, p) => sum + (parseFloat(this.st(p)?.s) || 0), 0);
    const stats = [
      temp != null || sources.length ? `<div><b>${temp != null ? num(temp) + "°" : "—"}</b>${tempLabel}</div>` : "",
      lights.length ? `<div><b class="warm">${lights.filter((e) => this.isOn(e)).length} / ${lights.length}</b><span>${t("luci accese")}</span></div>` : "",
      presence ? `<div><b>${this.isOn(presence) ? t("Sì") : t("No")}</b><span>${t("presenza")}</span></div>` : "",
      watts ? `<div><b>${num(watts, 0)} W</b><span>${t("consumo")}</span></div>` : "",
      `<div><b>${a.entities.length}</b><span>${t("entità")}</span></div>`,
    ].join("");
    const pills = this.data.areas.map((x) => `<button class="casa-pill ${x.id === a.id ? "on" : ""}" data-act="open" data-area="${x.id}">${esc(x.name)}</button>`).join("");
    const sections = this.roomGroups(a).map(([k, title, ids]) => this.sectionHTML(k, title, ids, a)).join("");
    return `
      <div class="casa-room">
        <header class="casa-room-head">
          <button class="casa-back" data-act="home">← ${t("Casa")}</button>
          <div><span class="casa-lbl">${a.outside ? t("Fuori casa") : esc(a.floor || t("Stanza"))}</span><h1>${esc(a.name)}</h1></div>
          <div class="casa-stats">${stats}</div>
          <button class="casa-edit ${this.editing ? "on" : ""}" data-act="edit" aria-pressed="${this.editing}">${this.editing ? t("Fine modifica") : t("Modifica stanza")}</button>
        </header>
        <nav class="casa-pills" aria-label="${t("Altre stanze")}">${pills}</nav>
        ${this.editing ? this.editHTML(a) : ""}
        <div class="casa-sections">${sections || `<p class="panel casa-panel casa-muted">${t("Nessuna entità: premi \"Modifica stanza\" per aggiungerne.")}</p>`}</div>
      </div>`;
  }

  sectionHTML(kind, title, ids, a) {
    const extra = kind === "light" && ids.some((e) => !e.startsWith("card:") && this.isOn(e)) ? `<button class="hc-link" data-act="all-off" data-area="${a.id}">${t("Spegni tutte")}</button>` : "";
    const body = kind === "action" && !this.editing && ids.every((e) => !e.startsWith("card:"))
      ? `<div class="hc-scenes">${ids.map((e) => `<button class="hc-scene" data-act="scene" data-e="${e}">${esc(this.st(e)?.n || e)}</button>`).join("")}</div>`
      : `<div class="hc-grid ${this.editing ? "editing" : ""}" data-group="${kind}">${ids.map((id) => this.itemHTML(id, a)).join("")}</div>`;
    return `<section class="hc-sec hc-sec-${kind}"><h3 class="hc-sectitle"><span>${title}</span>${extra}</h3>${body}</section>`;
  }

  // The last day of the room's sensors, for the little charts on their cards.
  async loadHistory(a) {
    this.hist ||= {};
    this.histAt ||= {};
    if (this.histAt[a.id] && Date.now() - this.histAt[a.id] < 300000) return;
    this.histAt[a.id] = Date.now();
    const eids = [...new Set([...a.entities, ...(a.cards || []).flatMap((c) => c.entities)])]
      .filter((e) => { const s = this.st(e); return s?.k === "sensor" && !isNaN(parseFloat(s.s)); });
    if (!eids.length) return;
    try {
      const data = await (await this.api(`/api/casa/history?e=${encodeURIComponent(eids.join(","))}`)).json();
      Object.assign(this.hist, data);
      if (this.page === a.id) this.renderSoon();
    } catch { /* no charts: the values are still there */ }
  }

  editHTML(a) {
    return `
      <section class="panel casa-panel casa-editor">
        <div class="casa-edit-col">
          <div class="hc-edit-actions"><button class="hc-btn primary" data-act="card-new">+ ${t("Nuova card")}</button><button class="hc-btn primary" data-act="card-free">+ ${t("Card libera")}</button><button class="hc-btn" data-act="card-import">${t("Importa card")}</button>
            ${(a.order || []).length ? `<button class="hc-link" data-act="order-reset">${t("Ordine automatico")}</button>` : ""}</div>
          <p class="casa-muted">${t("Sotto, ogni card ha i suoi comandi: trascinala (⋮⋮) o spostala con ‹ › dentro il suo gruppo, rinominala, rendila larga o piccola. Una card nuova raccoglie più entità, ad esempio la stufa con i suoi orari, e va nel gruppo che scegli.")}</p>
          <h3>${t("Entità in {room}", { room: esc(a.name) })}</h3>
          ${a.entities.map((e) => {
            const s = this.st(e);
            const cur = s?.nk ? s.k : "";
            const opts = SHOW_AS.map(([k, label]) => `<option value="${k}" ${k === cur ? "selected" : ""}>${label}</option>`).join("");
            return `<div class="casa-row casa-entity"><span>${esc(s?.n || e)} <small class="mono">${e}</small></span>
              <select data-act="kind" data-e="${e}" aria-label="${t("Mostra {name} come", { name: esc(s?.n || e) })}">${opts}</select>
              <button class="casa-mini" data-act="hide" data-area="${a.id}" data-e="${e}">${t("Togli")}</button></div>`;
          }).join("") || `<p class="casa-muted">${t("Ancora nessuna.")}</p>`}
          <p class="casa-muted">${t("Il tipo cambia solo come la vedi qui (es. un relè che accende una luce conta tra le luci; un cancello ha il pulsante a impulso). \"Togli\" la nasconde da questa plancia. In Home Assistant non cambia nulla.")}</p>
        </div>
        <div class="casa-edit-col">
          <h3>${t("Aggiungi entità")}</h3>
          <label class="casa-lbl" for="casa-find">${t("Cerca tra le entità di Home Assistant")}</label>
          <input id="casa-find" placeholder="${t("es. lampada, presa, sensore…")}" autocomplete="off" value="${esc(this.query || "")}">
          <div id="casa-cands"></div>
          <fieldset class="casa-mode">
            <legend class="casa-lbl">${t("Dove salvare")}</legend>
            <label><input type="radio" name="casa-mode" value="ha" ${this.mode === "ha" ? "checked" : ""}> ${t("Sposta l'area anche in Home Assistant (consigliato)")}</label>
            <label><input type="radio" name="casa-mode" value="local" ${this.mode === "local" ? "checked" : ""}> ${t("Solo nella plancia di HubNEX")}</label>
          </fieldset>
        </div>
      </section>`;
  }

  // ---------------------------------------------------------------- helpers: service calls
  setDateTime(eid, value) {
    const s = this.st(eid), domain = eid.split(".")[0];
    if (!s || !value) return;
    const { hasDate, hasTime } = this.dtParts(eid, s);
    const time = (value.match(/\d{2}:\d{2}/) || [""])[0], date = (value.match(/\d{4}-\d{2}-\d{2}/) || [""])[0];
    let service = "set_value", data = { entity_id: eid };
    if (domain === "input_datetime") {
      service = "set_datetime";
      if (hasDate && hasTime) data.datetime = `${date} ${time}:00`;
      else if (hasDate) data.date = date;
      else data.time = `${time}:00`;
    } else if (domain === "time") data.time = `${time}:00`;
    else if (domain === "date") data.date = date;
    else data.datetime = `${date} ${time}:00`;
    s.s = hasDate && hasTime ? `${date} ${time}:00` : hasDate ? date : `${time}:00`; // shown at once
    this.call(domain, service, data, eid);
    this.render(true);
  }

  setNumber(eid, value) {
    const s = this.st(eid);
    if (!s || isNaN(value)) return;
    s.s = String(value);
    this.call(eid.split(".")[0], "set_value", { entity_id: eid, value }, eid);
  }

  setOption(eid, option) {
    const s = this.st(eid);
    if (!s || option == null) return;
    s.s = option;
    this.call(eid.split(".")[0], "select_option", { entity_id: eid, option }, eid);
  }

  // ---------------------------------------------------------------- the room's arrangement
  saveOrder(items) {
    const a = this.area(this.page);
    if (!a) return;
    a.order = items;
    this.api(`/api/casa/rooms/${encodeURIComponent(a.id)}/order`, { method: "POST", body: JSON.stringify({ items }) }).catch((err) => this.toast(`⚠ ${err.message}`));
  }

  // Moving stays inside the card's group; the saved order is the whole room, group by group.
  moveItem(id, delta) {
    const a = this.area(this.page);
    const groups = this.roomGroups(a).map(([, , ids]) => ids);
    const list = groups.find((ids) => ids.includes(id));
    const i = list?.indexOf(id), j = i + delta;
    if (!list || j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j], list[i]];
    this.saveOrder(groups.flat());
    this.render(true);
  }

  // Drag a card by its handle (mouse or finger) and drop it on another one.
  _dragStart(e) {
    const handle = e.target.closest("[data-drag]");
    if (!handle || !this.editing) return;
    e.preventDefault();
    const id = handle.dataset.drag;
    const card = handle.closest("[data-item]");
    card?.classList.add("dragging");
    let over = null;
    const group = card?.closest("[data-group]");
    const move = (ev) => {
      let el = document.elementFromPoint(ev.clientX, ev.clientY)?.closest("[data-item]");
      if (el && el.closest("[data-group]") !== group) el = null; // only inside its own group
      if (over && over !== el) over.classList.remove("drop");
      over = el && el !== card ? el : null;
      over?.classList.add("drop");
    };
    const up = () => {
      removeEventListener("pointermove", move);
      removeEventListener("pointerup", up);
      card?.classList.remove("dragging");
      if (!over) return;
      const groups = this.roomGroups(this.area(this.page)).map(([, , ids]) => ids);
      const list = groups.find((ids) => ids.includes(id));
      list.splice(list.indexOf(id), 1);
      list.splice(list.indexOf(over.dataset.item), 0, id);
      this.saveOrder(groups.flat());
      this.render(true);
    };
    addEventListener("pointermove", move);
    addEventListener("pointerup", up);
  }

  renameHTML() {
    const r = this.renaming;
    return `<div class="casa-modal" role="dialog" aria-label="${t("Rinomina")}"><section class="panel casa-panel hc-dialog">
      <h3>${t("Rinomina")} <button class="casa-x" data-act="rename-close" aria-label="${t("Chiudi")}">×</button></h3>
      <p class="casa-muted">${t("Il nome cambia solo in HubNEX; in Home Assistant resta com'è")} (<span class="mono">${esc(r.eid)}</span>).</p>
      <input id="casa-rename" class="hc-input" value="${esc(r.name)}" maxlength="60" aria-label="${t("Nuovo nome")}">
      <div class="casa-actions"><button class="hc-btn primary" data-act="rename-save">${t("Salva")}</button><button class="hc-link" data-act="rename-reset">${t("Torna al nome di Home Assistant")}</button></div>
    </section></div>`;
  }

  // ---------------------------------------------------------------- composing a card
  cardKeep() {
    const n = this.root.querySelector("#card-name"), g = this.root.querySelector("#card-group"), en = this.root.querySelector("#card-enable");
    if (n && this.cardEdit) this.cardEdit.name = n.value;
    if (g && this.cardEdit) this.cardEdit.group = g.value;
    if (en && this.cardEdit) this.cardEdit.enable = en.value === "auto" ? null : en.value;
  }

  // A card from Claude's draft or an import into the editor, with its entities' states.
  takeCard(f, r) {
    Object.assign(this.data.states, Object.fromEntries(Object.entries(r.states || {}).filter(([, s]) => s)));
    f.blocks = r.blocks;
    f.name = r.name || f.name;
    f.color = r.color ?? f.color;
    if (r.style != null) f.style = r.style; // an imported card keeps its own; Jarvis's draft doesn't choose
    f.sel = r.blocks.findIndex((b) => !NO_ENTITY.has(b.kind) && !b.entity);
    if (f.sel < 0) f.sel = null;
    else this.freeSearch("");
  }

  // A question for Jarvis from a card: the chat at the bottom sends it (app.js listens).
  ask(text) {
    if (text?.trim()) window.dispatchEvent(new CustomEvent("hubnex-ask", { detail: text.trim() }));
  }

  // The free card editor: entities that suit the selected block, found as you type.
  async freeSearch(q) {
    const f = this.freeEdit;
    if (!f) return;
    f.q = q;
    try {
      f.cands = await (await this.api(`/api/casa/entities?all=1&q=${encodeURIComponent(q)}&area=${encodeURIComponent(f.area || "")}`)).json();
    } catch { f.cands = []; }
    const box = this.root.querySelector("#fb-cands");
    if (box) box.innerHTML = this.freeCandsHTML();
    else this.render(true);
  }

  freeCandsHTML() {
    const f = this.freeEdit, b = f.blocks[f.sel];
    if (!b) return "";
    const tapFit = b.tap?.do === "run" ? (s) => ["scene", "script", "button"].includes(s.k) : (s) => ["light", "switch", "media", "climate"].includes(s.k);
    const fits = f.target === "show" ? () => true : f.target === "tap" ? tapFit : BLOCKS.find(([k]) => k === b.kind)[4];
    const cur = f.target === "show" ? b.show?.e : f.target === "tap" ? b.tap?.e : b[f.target];
    const list = f.cands.filter((c) => c.state && fits(c.state)).slice(0, 40);
    return list.map((c) => `<button class="fe-cand ${cur === c.entity_id ? "on" : ""}" data-act="fb-pick" data-e="${esc(c.entity_id)}"><span>${esc(c.name)}</span><small>${esc(c.area || "")}${c.area ? " · " : ""}${esc(c.state.s ?? "")}</small></button>`).join("")
      || `<p class="casa-muted">${t("Nessuna entità adatta: prova a cercare.")}</p>`;
  }

  freeEditHTML() {
    const f = this.freeEdit, b = f.blocks[f.sel];
    const pal = BLOCKS.map(([k, name, hint]) => `<button class="fe-add" data-act="fb-add" data-k="${k}"><b>${name}</b><small>${hint}</small></button>`).join("")
      + `<span class="hc-kick fe-tpl-k">${t("Parti da un modello")}</span><div class="fe-tpls">${TEMPLATES.map(([k, name]) => `<button data-act="fb-tpl" data-t="${k}">${name}</button>`).join("")}</div>`;
    const colors = CARD_COLORS.map(([c, name]) => `<button class="fe-color ${c ? `fc-${c}` : ""} ${f.color === c ? "on" : ""}" data-act="fb-color" data-c="${c}" aria-label="${name}" title="${name}"></button>`).join("");
    let props = `<p class="casa-muted">${t("Tocca un blocco della card per modificarlo, o aggiungine uno.")}</p>`;
    if (b) {
      const [, name] = BLOCKS.find(([k]) => k === b.kind);
      const ent = (id, what) => {
        const s = this.st(id);
        return `<button class="fe-ent ${f.target === what ? "on" : ""}" data-act="fb-target" data-t="${what}"><span>${s ? esc(s.n) : t("da scegliere")}</span><small class="mono">${esc(id || "")}</small></button>`;
      };
      props = `<span class="hc-kick">${t("Blocco")}: ${name}</span>
        ${NO_ENTITY.has(b.kind) ? "" : b.kind === "band"
          ? `<label class="fe-lbl">${t("Inizio")}</label>${ent(b.entity, "entity")}<label class="fe-lbl">${t("Fine")}</label>${ent(b.entity2, "entity2")}`
          : `<label class="fe-lbl">${t("Entità")}</label>${ent(b.entity, "entity")}`}
        ${NO_ENTITY.has(b.kind) && !["show", "tap"].includes(f.target) ? "" : `<input id="fb-find" class="hc-input" placeholder="${t("Cerca…")}" value="${esc(f.q)}" autocomplete="off"><div class="fe-cands" id="fb-cands">${this.freeCandsHTML()}</div>`}
        <label class="fe-lbl" for="fb-label">${b.kind === "text" ? t("Testo") : b.kind === "ask" ? t("La domanda per Jarvis") : t("Etichetta (vuota: il nome dell'entità)")}</label>
        <input id="fb-label" class="hc-input" value="${esc(b.label || "")}" maxlength="60" autocomplete="off">
        ${["ring", "bar"].includes(b.kind) ? `<div class="fe-row"><label class="fe-lbl">${t("Minimo")}<input id="fb-min" class="hc-input" type="number" value="${b.min ?? ""}"></label><label class="fe-lbl">${t("Massimo")}<input id="fb-max" class="hc-input" type="number" value="${b.max ?? ""}"></label></div>` : ""}
        <label class="fe-lbl">${t("Dimensione")}</label>
        <div class="fe-sizes">${BLOCK_SIZES.map(([w, h]) => `<button class="${b.w === w && b.h === h ? "on" : ""}" data-act="fb-size" data-w="${w}" data-h="${h}">${w}×${h}</button>`).join("")}</div>
        ${NO_ENTITY.has(b.kind) ? "" : `<span class="hc-kick fe-sec">${t("Colore secondo il valore")}</span>
        ${(b.rules || []).map((r, i) => `<div class="fe-rule"><select data-fb="rules.${i}.op">${COMPARES.map(([o, l]) => `<option value="${o}" ${r.op === o ? "selected" : ""}>${l}</option>`).join("")}</select>
          ${valueField(`rules.${i}.v`, this.st(b.entity), r.op, r.v)}<select data-fb="rules.${i}.c">${CARD_COLORS.slice(1).map(([c, l]) => `<option value="${c}" ${r.c === c ? "selected" : ""}>${l}</option>`).join("")}</select>
          <button class="hc-link" data-act="fb-rule-del" data-i="${i}" aria-label="${t("Togli")}">×</button></div>`).join("")}
        ${(b.rules || []).length < 4 ? `<button class="hc-link" data-act="fb-rule-add">+ ${t("regola di colore")}</button>` : ""}`}
        <span class="hc-kick fe-sec">${t("Mostra solo se")}</span>
        ${b.show ? `${ent(b.show.e, "show")}<div class="fe-rule"><select data-fb="show.op">${COMPARES.map(([o, l]) => `<option value="${o}" ${b.show.op === o ? "selected" : ""}>${l}</option>`).join("")}</select>${valueField("show.v", this.st(b.show.e), b.show.op, b.show.v)}<button class="hc-link" data-act="fb-show-del" aria-label="${t("Togli")}">×</button></div>
          <small class="casa-muted">${t("Es. uguale a acceso: si vede solo quando è acceso o rileva qualcosa.")}</small>` : `<button class="hc-link" data-act="fb-show-add">+ ${t("condizione")}</button>`}
        <span class="hc-kick fe-sec">${t("Al tocco")}</span>
        <select class="hc-select" data-fb="tap.do">${TAPS.map(([d, l]) => `<option value="${d}" ${(b.tap?.do || "") === d ? "selected" : ""}>${l}</option>`).join("")}</select>
        ${["toggle", "run"].includes(b.tap?.do) ? `<label class="fe-lbl">${t("Su cosa (vuoto: l'entità del blocco)")}</label>${ent(b.tap.e, "tap")}` : ""}
        ${b.tap?.do === "ask" ? `<input class="hc-input" data-fb="tap.text" value="${esc(b.tap.text || "")}" placeholder="${t("La domanda per Jarvis")}">` : ""}
        ${b.tap?.do === "room" ? `<select class="hc-select" data-fb="tap.area">${this.data.areas.map((a) => `<option value="${a.id}" ${b.tap.area === a.id ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select>` : ""}
        <div class="fe-row fe-actions"><button class="hc-btn" data-act="fb-move" data-d="-1">‹ ${t("Prima")}</button><button class="hc-btn" data-act="fb-move" data-d="1">${t("Dopo")} ›</button><button class="hc-btn" data-act="fb-del">${t("Togli")}</button></div>`;
    }
    return `<div class="casa-modal fe-modal" role="dialog" aria-label="${t("Card libera")}"><section class="panel casa-panel fe-panel">
      <h3>${t("Card libera")} <button class="casa-x" data-act="fb-close" aria-label="${t("Chiudi")}">×</button></h3>
      ${f.importing ? `<div class="fe-import"><label class="fe-lbl" for="fb-paste">${t("Incolla qui una card esportata da HubNEX")}</label>
        <textarea id="fb-paste" class="hc-input" rows="6" spellcheck="false">${esc(f.paste || "")}</textarea>
        <button class="hc-btn primary" data-act="fb-import">${t("Importa")}</button></div>` : ""}
      <div class="fe-draft ${f.busy ? "busy" : ""}"><span class="fe-orb" aria-hidden="true"></span>
        <input id="fb-draft-text" class="hc-input" placeholder="${t("Descrivila a Jarvis: es. la stufa con temperatura, accensione, orari e pellet")}" value="${esc(f.draft || "")}" maxlength="1000" autocomplete="off" ${f.busy ? "disabled" : ""}>
        <button class="hc-btn" data-act="fb-draft" ${f.busy ? "disabled" : ""}>${f.busy ? t("Jarvis compone…") : t("Crea")}</button></div>
      <div class="fe-top"><input id="fb-name" class="hc-input" placeholder="${t("Nome della card")}" value="${esc(f.name)}" maxlength="60" autocomplete="off">
        <span class="fe-colors">${colors}</span>
        <span class="fe-style" role="group" aria-label="${t("Stile")}"><button class="${f.style ? "" : "on"}" data-act="fb-style" data-s="">${t("Riquadri")}</button><button class="${f.style === "flat" ? "on" : ""}" data-act="fb-style" data-s="flat">${t("Pulito")}</button></span>
        <button class="hc-btn" data-act="fb-export" ${f.blocks.length ? "" : "disabled"}>${t("Esporta")}</button><button class="hc-btn primary" data-act="fb-save">${t("Salva card")}</button></div>
      ${f.exported ? `<textarea class="hc-input fe-export" rows="4" readonly spellcheck="false">${esc(f.exported)}</textarea>` : ""}
      <div class="fe-cols">
        <div class="fe-pal"><span class="hc-kick">${t("Blocchi")}</span>${pal}</div>
        <div class="fe-prev"><span class="hc-kick">${t("Anteprima · griglia da 4 colonne, 2 sul telefono")}</span><div id="fb-preview">${this.freeCard(f, f)}</div></div>
        <div class="fe-props" id="fb-props">${props}</div>
      </div></section></div>`;
  }

  async cardSearch(q) {
    if (!this.cardEdit) return;
    this.cardEdit.q = q;
    try {
      this.cardEdit.cands = await (await this.api(`/api/casa/entities?all=1&q=${encodeURIComponent(q)}&area=${encodeURIComponent(this.cardEdit.area || "")}`)).json();
    } catch { this.cardEdit.cands = []; }
    const box = this.root.querySelector("#card-cands");
    if (box) box.innerHTML = this.cardCandsHTML();
    else this.render(true);
  }

  cardCandsHTML() {
    const c = this.cardEdit;
    return c.cands.filter((x) => !c.entities.includes(x.entity_id)).slice(0, 12).map((x) => `<button class="hc-cand" data-act="card-add" data-e="${esc(x.entity_id)}"><span>${esc(x.name)}</span><span class="mono">${esc(x.entity_id)}</span></button>`).join("") || `<p class="casa-muted">${t("Nessuna entità trovata.")}</p>`;
  }

  cardEditHTML() {
    const c = this.cardEdit;
    const preview = this.composedCard({ id: "preview", name: c.name || t("Card"), entities: c.entities, size: c.size, enable: c.enable, nochart: c.nochart }).replace(/data-act="[^"]*"/g, "");
    const numeric = (e) => { const s = this.st(e); return s?.k === "sensor" && !isNaN(parseFloat(s.s)); };
    const toggles = c.entities.filter((e) => ["input_boolean", "switch"].includes(e.split(".")[0]));
    const hasTimes = c.entities.filter((e) => this.st(e)?.k === "datetime").length >= 2;
    const guessed = this.cardEnable({ entities: c.entities });
    return `<div class="casa-modal" role="dialog" aria-label="${t("Card")}"><section class="panel casa-panel hc-dialog hc-cardedit">
      <h3>${c.id ? t("Modifica card") : t("Nuova card")} <button class="casa-x" data-act="card-close" aria-label="${t("Chiudi")}">×</button></h3>
      <div class="hc-cardedit-cols">
        <div>
          <label class="hc-kick" for="card-name">${t("Nome")}</label>
          <input id="card-name" class="hc-input" value="${esc(c.name)}" maxlength="60" placeholder="${t("es. Stufa")}">
          <span class="hc-kick" style="margin-top:12px">${t("Entità nella card")}</span>
          <div class="hc-chosen">${c.entities.map((e, i) => `<div class="hc-chosen-item"><span>${esc(this.st(e)?.n || e)}<small class="mono">${esc(e)}</small></span>
            <span class="hc-chosen-ctl">${numeric(e) ? `<label class="hc-chart-tg">${t("grafico")}<button class="casa-switch ${c.nochart.includes(e) ? "" : "on"}" data-act="card-chart" data-e="${esc(e)}" role="switch" aria-checked="${!c.nochart.includes(e)}" aria-label="${t("Grafico di {name}", { name: esc(this.st(e)?.n || e) })}"></button></label>` : ""}<button data-act="card-up" data-e="${esc(e)}" aria-label="${t("Su")}" ${i ? "" : "disabled"}>↑</button><button data-act="card-down" data-e="${esc(e)}" aria-label="${t("Giù")}" ${i < c.entities.length - 1 ? "" : "disabled"}>↓</button><button data-act="card-rm" data-e="${esc(e)}" aria-label="${t("Togli")}">×</button></span></div>`).join("") || `<p class="casa-muted">${t("Ancora nessuna: cercale qui sotto.")}</p>`}</div>
          <label class="hc-kick" for="card-find" style="margin-top:12px">${t("Aggiungi entità")}</label>
          <input id="card-find" class="hc-input" value="${esc(c.q)}" placeholder="${t("cerca per nome o entity_id…")}" autocomplete="off">
          <div id="card-cands" class="hc-cands">${this.cardCandsHTML()}</div>
        </div>
        <div>
          <label class="hc-kick" for="card-group">${t("Gruppo")}</label>
          <select id="card-group" class="hc-select" style="margin-bottom:14px">
            <option value="">${t("Automatico")}${c.entities.length ? ` (${esc((SECTIONS.find(([k]) => k === this.cardGroup({ entities: c.entities })) || ["", t("Altro")])[1])})` : ""}</option>
            ${SECTIONS.map(([k, title]) => `<option value="${k}" ${c.group === k ? "selected" : ""}>${title}</option>`).join("")}
          </select>
          ${hasTimes && toggles.length ? `<label class="hc-kick" for="card-enable">${t("Gli orari valgono quando è acceso")}</label>
          <select id="card-enable" class="hc-select" style="margin-bottom:14px">
            <option value="auto" ${c.enable == null ? "selected" : ""}>${t("Automatico")}${guessed ? ` (${esc(this.st(guessed)?.n || guessed)})` : ` (${t("nessuno")})`}</option>
            ${toggles.map((e) => `<option value="${esc(e)}" ${c.enable === e ? "selected" : ""}>${esc(this.st(e)?.n || e)}</option>`).join("")}
            <option value="" ${c.enable === "" ? "selected" : ""}>${t("Nessuno: gli orari valgono sempre")}</option>
          </select>` : ""}
          <span class="hc-kick">${t("Dimensione")}</span>
          <div class="hc-tabs" style="margin:6px 0 16px"><button class="hc-tab ${c.size === "small" ? "sel" : ""}" data-act="card-size" data-w="small">${t("Piccola")}</button><button class="hc-tab ${c.size === "wide" ? "sel" : ""}" data-act="card-size" data-w="wide">${t("Larga")}</button></div>
          <span class="hc-kick">${t("Anteprima")}</span>
          <div class="hc-preview">${c.entities.length ? preview : `<p class="casa-muted">${t("La card compare qui mentre la componi.")}</p>`}</div>
          <div class="casa-actions"><button class="hc-btn primary" data-act="card-save">${t("Salva card")}</button><button class="hc-link" data-act="card-close">${t("Annulla")}</button></div>
        </div>
      </div>
    </section></div>`;
  }

  candsHTML() {
    const area = this.page;
    return (this.cands || []).map((c) => `
      <div class="casa-row"><span>${esc(c.name)}<small class="${c.area ? "warm" : ""}">${c.area ? t("ora in: {area}", { area: esc(c.area) }) : t("senza area")}${c.hidden ? ` · ${t("nascosta in HA")}` : ""}</small><small class="mono">${esc(c.entity_id)}</small></span>
      <button class="casa-mini add" data-act="add" data-area="${area}" data-e="${c.entity_id}">+ ${t("Aggiungi")}</button></div>`).join("") || `<p class="casa-muted">${t("Nessuna entità trovata.")}</p>`;
  }

  layoutHTML() {
    const l = this.layout;
    return `
      <div class="casa-modal" role="dialog" aria-label="${t("Piantina")}">
        <section class="panel casa-panel">
          <h3>${t("Piantina")} <button class="casa-x" data-act="layout-close" aria-label="${t("Chiudi")}">×</button></h3>
          <p class="casa-muted">${t("Incolla qui la piantina (YAML) e premi Salva: viene scritta in {file}. Le stanze vanno chiamate come le aree di Home Assistant:", { file: `<span class="mono">${esc(l.file)}</span>` })}</p>
          <div class="casa-area-names">${l.areas.map((n) => `<span class="chip">${esc(n)}</span>`).join("")}</div>
          <textarea id="casa-layout-text" spellcheck="false">${esc(l.text)}</textarea>
          <div class="layout-error">${esc(l.error || "")}</div>
          <div class="casa-actions"><button class="casa-primary" data-act="layout-save">${t("Salva piantina")}</button><button data-act="layout-close">${t("Annulla")}</button></div>
        </section>
      </div>`;
  }
}

Object.assign(CasaView.prototype, Cards, Energy);
