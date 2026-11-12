import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { Brain, TYPES } from "./brain.js";
import { Orb, describeTool } from "./orb.js";
import { CasaView } from "./casa.js";
import { CostsView, money } from "./costs.js";
import { AlertsView } from "./alerts.js";
import { t, LANG, LOCALE, setLang, translatePage } from "./i18n.js";

translatePage();

// ===================================================================== state
const S = {
  token: new URLSearchParams(location.search).get("token") || safeGet("hq_token") || "",
  data: null,              // last snapshot
  company: safeGet("hq_company"),
  selected: null,          // agent id
  speak: safeGet("hq_speak") === "1",
};
const STATUS_IT = { sleeping: t("dorme"), thinking: t("pensa"), writing: t("scrive"), working: t("lavora"), searching: t("cerca"), error: t("errore") };
const KIND_ICON = { task: "→", result: "✓", chat: "💬", ha: "⌂", memory: "◆", deadline: "⏰", notify: "📣", error: "⚠", system: "●" };

function safeGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function safeSet(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } }
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// URLs are relative to the page so the dashboard also works behind HA ingress
// (served under /api/hassio_ingress/<token>/).
async function api(path, opts = {}) {
  const res = await fetch(path.replace(/^\//, ""), {
    ...opts,
    headers: { "Content-Type": "application/json", "X-HubNEX-Lang": LANG, ...(S.token ? { Authorization: `Bearer ${S.token}` } : {}), ...(opts.headers || {}) },
  });
  if (res.status === 401) { showLogin(); throw new Error(t("non autorizzato")); }
  if (!res.ok) throw new Error(await res.text());
  return res;
}

const orb = new Orb($("orb"));
const costs = new CostsView(api);
const alerts = new AlertsView(api);

// ===================================================================== three.js scene
const container = $("scene");
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
container.appendChild(renderer.domElement);

const labelRenderer = new CSS2DRenderer();
labelRenderer.setSize(innerWidth, innerHeight);
Object.assign(labelRenderer.domElement.style, { position: "absolute", top: "0", pointerEvents: "none" });
labelRenderer.domElement.className = "labels";
container.appendChild(labelRenderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x03060d);
scene.fog = new THREE.FogExp2(0x03060d, 0.018);

const camera = new THREE.PerspectiveCamera(45, innerWidth / innerHeight, 0.1, 400);
// Portrait screens need the camera further back to fit the whole arena.
function fitCamera() {
  const k = Math.max(1, Math.sqrt(1.1 / camera.aspect));
  camera.position.setLength(Math.hypot(21, 27) * Math.min(k, 1.8));
}
camera.position.set(0, 21, 27);
fitCamera();

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI * 0.42;
controls.minDistance = 10;
controls.maxDistance = 90;
controls.autoRotate = true;
controls.autoRotateSpeed = 0.25;
controls.target.set(0, -1.5, 0);

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.75, 0.5, 0.4);
composer.addPass(bloom);
composer.addPass(new OutputPass());

scene.add(new THREE.AmbientLight(0x3355aa, 0.6));
const keyLight = new THREE.PointLight(0x4fd1ff, 40, 40);
keyLight.position.set(0, 8, 0);
scene.add(keyLight);

// Starfield
{
  const g = new THREE.BufferGeometry();
  const n = 1800, pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const r = 60 + Math.random() * 120, th = Math.random() * Math.PI * 2, ph = Math.random() * Math.PI * 0.5;
    pos.set([r * Math.cos(th) * Math.sin(ph), r * Math.cos(ph) - 20, r * Math.sin(th) * Math.sin(ph)], i * 3);
  }
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  scene.add(new THREE.Points(g, new THREE.PointsMaterial({ color: 0x6fa8ff, size: 0.35, transparent: true, opacity: 0.6 })));
}

// Floor grid
{
  const grid = new THREE.PolarGridHelper(40, 24, 16, 96, 0x0d2238, 0x0a1a2b);
  grid.position.y = -0.6;
  scene.add(grid);
}

let arena = new THREE.Group();
scene.add(arena);
const agentObjs = new Map();   // id -> {group, body, ring, halo, label, color, home}
const beams = new Map(); // agent id -> the beam from Jarvis, alive while that agent works
let hub = null;

const ARENA_R = 10, INNER_R = 3.2;

function clearArena() {
  scene.remove(arena);
  arena.traverse((o) => { if (o.element) o.element.remove(); });
  arena = new THREE.Group();
  scene.add(arena);
  agentObjs.clear();
  beams.clear(); // their meshes left with the old arena
}

function ring(r, color, opacity = 0.6, width = 0.04) {
  const m = new THREE.Mesh(
    new THREE.RingGeometry(r - width, r + width, 128),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity, side: THREE.DoubleSide }),
  );
  m.rotation.x = -Math.PI / 2;
  return m;
}

function label(html, cls) {
  const el = document.createElement("div");
  el.className = cls;
  el.innerHTML = html;
  return new CSS2DObject(el);
}

function buildArena() {
  clearArena();
  const d = S.data;
  const company = d.companies.find((c) => c.id === S.company) || d.companies[0];
  if (!company) return;
  S.company = company.id;

  // Platform
  const base = new THREE.Mesh(
    new THREE.CylinderGeometry(ARENA_R + 0.4, ARENA_R + 0.8, 0.5, 96, 1, true),
    new THREE.MeshStandardMaterial({ color: 0x07111f, emissive: 0x0a1a2e, metalness: 0.6, roughness: 0.5, side: THREE.DoubleSide }),
  );
  base.position.y = -0.3;
  arena.add(base);
  arena.add(ring(ARENA_R + 0.4, 0x4fd1ff, 0.9, 0.05));
  arena.add(ring(ARENA_R + 1.4, 0x4fd1ff, 0.25, 0.02));
  arena.add(ring(INNER_R, 0x4fd1ff, 0.7, 0.04));

  // Department wedges
  const depts = company.departments;
  const n = Math.max(depts.length, 1);
  const span = (Math.PI * 2) / n;
  depts.forEach((dept, i) => {
    const color = new THREE.Color(dept.color);
    const start = i * span + Math.PI / 2;
    const wedge = new THREE.Mesh(
      new THREE.RingGeometry(INNER_R + 0.15, ARENA_R + 0.3, 64, 1, start + 0.02, span - 0.04),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.06, side: THREE.DoubleSide }),
    );
    wedge.rotation.x = -Math.PI / 2;
    arena.add(wedge);
    const edge = new THREE.Mesh(
      new THREE.RingGeometry(ARENA_R + 0.18, ARENA_R + 0.32, 64, 1, start + 0.02, span - 0.04),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.85, side: THREE.DoubleSide }),
    );
    edge.rotation.x = -Math.PI / 2;
    edge.position.y = 0.01;
    arena.add(edge);

    const mid = start + span / 2;
    const dl = label(esc(dept.name), "dept-label");
    dl.element.style.color = dept.color;
    dl.position.set(Math.cos(mid) * (ARENA_R + 1.6), 0.3, -Math.sin(mid) * (ARENA_R + 1.6));
    arena.add(dl);

    // Agents of this department, spread inside the wedge
    const members = d.agents.filter((a) => a.company === company.id && a.department === dept.id);
    members.forEach((a, j) => {
      const t = (j + 1) / (members.length + 1);
      const ang = start + span * (0.18 + 0.64 * t);
      const r = INNER_R + (ARENA_R - INNER_R) * (members.length > 2 ? (j % 2 ? 0.42 : 0.7) : 0.58);
      addAgent(a, a.color || dept.color, new THREE.Vector3(Math.cos(ang) * r, 0, -Math.sin(ang) * r));
    });
  });

  // Hub: Jarvis core
  const boss = d.agents.find((a) => a.id === d.boss.id);
  hub = new THREE.Group();
  const pedestal = new THREE.Mesh(
    new THREE.CylinderGeometry(2.2, 2.6, 0.6, 64),
    new THREE.MeshStandardMaterial({ color: 0x081626, emissive: 0x0b2a44, metalness: 0.7, roughness: 0.35 }),
  );
  pedestal.position.y = 0;
  hub.add(pedestal);
  const core = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1.1, 1),
    new THREE.MeshBasicMaterial({ color: 0x4fd1ff, wireframe: true, transparent: true, opacity: 0.85 }),
  );
  core.position.y = 2.2;
  const inner = new THREE.Mesh(new THREE.SphereGeometry(0.45, 32, 16), new THREE.MeshBasicMaterial({ color: 0xbff0ff }));
  inner.position.y = 2.2;
  hub.add(core, inner);
  hub.userData = { core, inner };
  const hl = label(`${esc(company.logo)}<span class="hub-sub">${esc(company.name)}</span>`, "hub-label");
  hl.position.set(0, 4.6, 0);
  hub.add(hl);
  arena.add(hub);
  if (boss) {
    agentObjs.set(boss.id, { group: hub, body: inner, color: new THREE.Color(0x4fd1ff), home: new THREE.Vector3(0, 2.2, 0), isHub: true });
    const bl = label(agentLabelHtml(boss), `agent-label ${boss.status}`);
    bl.position.set(0, 0.6, 2.4);
    bl.element.addEventListener("click", () => selectAgent(boss.id));
    hub.add(bl);
    agentObjs.get(boss.id).label = bl;
  }

  renderCompanies();
  if (S.selected) renderCard();
  // Back on the HQ (or on another office) while someone works: their beam is there at once.
  for (const a of d.agents) if (a.id !== d.boss.id && a.status !== "sleeping" && a.status !== "error") fireBeam(a.id);
}

function agentLabelHtml(a) {
  return `<span class="dot"></span>${esc(a.name)}<span class="z">zZ</span>`;
}

function addAgent(a, colorHex, pos) {
  const color = new THREE.Color(colorHex);
  const group = new THREE.Group();
  group.position.copy(pos);

  const pad = ring(0.85, color, 0.8, 0.05);
  pad.position.y = 0.02;
  const halo = new THREE.Mesh(
    new THREE.CircleGeometry(0.8, 48),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.18 }),
  );
  halo.rotation.x = -Math.PI / 2;
  halo.position.y = 0.01;

  const body = new THREE.Mesh(
    new THREE.CapsuleGeometry(0.32, 0.55, 8, 16),
    new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.6, metalness: 0.2, roughness: 0.4 }),
  );
  body.position.y = 0.9;

  const spin = new THREE.Mesh(
    new THREE.TorusGeometry(0.62, 0.025, 8, 64, Math.PI * 1.3),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0 }),
  );
  spin.rotation.x = -Math.PI / 2;
  spin.position.y = 0.9;

  group.add(pad, halo, body, spin);
  const lbl = label(agentLabelHtml(a), `agent-label ${a.status}`);
  lbl.position.set(0, 1.9, 0);
  lbl.element.addEventListener("click", () => selectAgent(a.id));
  group.add(lbl);
  body.userData.agentId = a.id;
  arena.add(group);
  agentObjs.set(a.id, { group, body, ring: spin, halo, label: lbl, color, home: pos.clone() });
}

// A beam from Jarvis to an agent at work: it stays, pulsing, with dots running along it towards
// the agent, for as long as the agent works; when it is done the beam fades.
function fireBeam(agentId) {
  const target = agentObjs.get(agentId);
  if (!target || target.isHub) return;
  const old = beams.get(agentId);
  if (old) { old.dying = null; return; }
  const from = new THREE.Vector3(0, 2.2, 0);
  const to = target.group.position.clone().add(new THREE.Vector3(0, 0.9, 0));
  const mid = from.clone().lerp(to, 0.5).add(new THREE.Vector3(0, 3, 0));
  const curve = new THREE.QuadraticBezierCurve3(from, mid, to);
  const mesh = new THREE.Mesh(
    new THREE.TubeGeometry(curve, 40, 0.04, 6, false),
    new THREE.MeshBasicMaterial({ color: target.color, transparent: true, opacity: 1 }),
  );
  arena.add(mesh);
  const dots = [0, 1, 2].map(() => {
    const dot = new THREE.Mesh(new THREE.SphereGeometry(0.09, 12, 12), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9 }));
    arena.add(dot);
    return dot;
  });
  beams.set(agentId, { mesh, dots, curve, born: performance.now(), dying: null });
}

function stopBeam(agentId) {
  const b = beams.get(agentId);
  if (b && !b.dying) b.dying = performance.now();
}

// Click on 3D bodies
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
renderer.domElement.addEventListener("click", (e) => {
  if (S.view === "map") return pickNode(e);
  pointer.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1);
  raycaster.setFromCamera(pointer, camera);
  const bodies = [...agentObjs.values()].map((o) => o.body);
  const hit = raycaster.intersectObjects(bodies)[0];
  if (hit) selectAgent(hit.object.userData.agentId || S.data.boss.id);
});

const clock = new THREE.Clock();
function animate() {
  requestAnimationFrame(animate);
  const t = clock.getElapsedTime();
  if (S.data) {
    for (const [id, o] of agentObjs) {
      const a = S.data.agents.find((x) => x.id === id);
      if (!a) continue;
      const active = a.status !== "sleeping" && a.status !== "error";
      if (o.isHub) {
        hub.userData.core.rotation.y = t * (active ? 1.6 : 0.3);
        hub.userData.core.rotation.x = t * 0.2;
        const s = active ? 1 + Math.sin(t * 6) * 0.12 : 1 + Math.sin(t * 1.5) * 0.04;
        const v = orb.voiceLevel; // the hub breathes with Jarvis' voice
        hub.userData.inner.scale.setScalar(s + v * 0.7);
        keyLight.intensity = (active ? 70 : 40) + v * 140;
        continue;
      }
      const m = o.body.material;
      const target = a.status === "error" ? 0.2 : active ? 1.6 + Math.sin(t * 5) * 0.5 : 0.35;
      m.emissiveIntensity += (target - m.emissiveIntensity) * 0.1;
      m.emissive.copy(a.status === "error" ? new THREE.Color(0xff3355) : o.color);
      o.body.position.y = 0.9 + (active ? Math.sin(t * 3 + o.home.x) * 0.12 : Math.sin(t * 0.8 + o.home.x) * 0.03);
      o.ring.material.opacity += ((active ? 0.9 : 0) - o.ring.material.opacity) * 0.1;
      o.ring.rotation.z = t * (a.status === "working" ? 4 : 2);
      o.halo.material.opacity = active ? 0.25 + Math.sin(t * 4) * 0.1 : 0.12;
      o.group.scale.setScalar(S.selected === id ? 1.15 : 1);
    }
  }
  const now = performance.now();
  for (const [id, b] of beams) {
    const age = (now - b.born) / 1000;
    // a bright start, then a steady pulse; a fade of one second once the agent is done
    let o = age < 0.5 ? 1 : 0.55 + 0.3 * Math.sin(t * 4);
    if (b.dying) o *= Math.max(0, 1 - (now - b.dying) / 1000);
    b.mesh.material.opacity = o;
    b.dots.forEach((dot, k) => {
      dot.position.copy(b.curve.getPoint((t * 0.45 + k / 3) % 1));
      dot.material.opacity = Math.min(1, o * 1.4);
    });
    if (b.dying && now - b.dying > 1000) {
      for (const m of [b.mesh, ...b.dots]) { arena.remove(m); m.geometry.dispose(); m.material.dispose(); }
      beams.delete(id);
    }
  }
  if (S.view === "casa") return; // the house view is plain HTML: let the GPU rest
  if (S.view === "map") {
    brain.update(performance.now());
    brain.render();
    return;
  }
  controls.update();
  composer.render();
  labelRenderer.render(scene, camera);
}

addEventListener("resize", () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  fitCamera();
  renderer.setSize(innerWidth, innerHeight);
  composer.setSize(innerWidth, innerHeight);
  labelRenderer.setSize(innerWidth, innerHeight);
  brain.resize();
});

// ===================================================================== immersive mode
// Inside Home Assistant the dashboard is an add-on iframe. HA's ingress view listens for
// messages from it: "home-assistant/subscribe-properties" with kioskMode hides HA's sidebar
// and header (HA turns kiosk off by itself when you leave the panel), and unsubscribing
// brings them back. The ☰ button switches between the two.
const inHA = window.parent !== window;
let kiosk = false;

function setKiosk(on) {
  kiosk = on;
  window.parent.postMessage(on ? { type: "home-assistant/subscribe-properties", kioskMode: true } : { type: "home-assistant/unsubscribe-properties" }, "*");
  safeSet("hq_immersive", on ? "1" : "0");
  $("ha-menu").classList.toggle("on", !on);
  $("ha-menu").title = on ? t("Mostra il menu di Home Assistant") : t("Nascondi il menu di Home Assistant");
}

if (inHA) {
  $("ha-menu").classList.remove("hidden");
  $("ha-menu").addEventListener("click", () => setKiosk(!kiosk));
  setKiosk(safeGet("hq_immersive") !== "0");
}

// ===================================================================== open Jarvis at start-up
// Home Assistant opens the page in the user's "core.default_panel" (falling back to the one set
// for everybody). Only the user themself can change theirs, and the HA settings only offer
// dashboards, so the switch lives here: the panel runs inside HA's page (same origin) and uses
// the logged-in user's own connection. Each person turns it on for their own account.
function haFrontend() {
  try {
    const hass = window.parent.document.querySelector("home-assistant")?.hass;
    if (!hass?.connection) return null;
    const parts = window.parent.location.pathname.split("/").filter(Boolean);
    // Sidebar panel: /<slug>; from the add-on page ("Apri interfaccia web"): /hassio/ingress/<slug>.
    const panel = parts[0] === "hassio" && parts[1] === "ingress" ? parts[2] : parts[0];
    return { hass, panel: hass.panels?.[panel] ? panel : null };
  } catch {
    return null; // not inside Home Assistant (or another origin)
  }
}

async function loadStartPref() {
  const ha = haFrontend();
  const sw = $("pref-start");
  if (!ha) {
    $("pref-start-row").classList.add("hidden");
    $("pref-start-note").classList.add("hidden");
    return;
  }
  const mine = (await ha.hass.connection.sendMessagePromise({ type: "frontend/get_user_data", key: "hubnex" })).value;
  if (mine) setUI(mine);
  $("pref-start-who").textContent = ha.hass.user?.name ? t("per {name}", { name: ha.hass.user.name }) : "";
  if (!ha.panel) {
    sw.disabled = true;
    $("pref-start-note").textContent = t("Per usarlo, attiva \"Mostra nella barra laterale\" nella pagina dell'add-on HubNEX e apri HubNEX da lì.");
    return;
  }
  const data = (await ha.hass.connection.sendMessagePromise({ type: "frontend/get_user_data", key: "core" })).value || {};
  setStartSwitch(data.default_panel === ha.panel);
}

function setSwitch(id, on) {
  $(id).classList.toggle("on", on);
  $(id).setAttribute("aria-checked", String(on));
}
const setStartSwitch = (on) => setSwitch("pref-start", on);

$("pref-start").addEventListener("click", async () => {
  const ha = haFrontend();
  if (!ha?.panel) return;
  const on = $("pref-start").getAttribute("aria-checked") !== "true";
  try {
    const conn = ha.hass.connection;
    const data = (await conn.sendMessagePromise({ type: "frontend/get_user_data", key: "core" })).value || {};
    const value = { ...data };
    if (on) value.default_panel = ha.panel;
    else if (value.default_panel === ha.panel) delete value.default_panel; // back to Home Assistant's default
    await conn.sendMessagePromise({ type: "frontend/set_user_data", key: "core", value });
    setStartSwitch(on);
    $("pref-start-note").textContent = on
      ? t("Fatto: aprendo Home Assistant con il tuo account arrivi su HubNEX. Gli altri utenti non cambiano.")
      : t("Spento: Home Assistant si apre di nuovo sulla tua plancia predefinita.");
  } catch (err) {
    $("pref-start-note").textContent = `⚠ ${t("Home Assistant non ha accettato la modifica")}: ${err.message || err.code || err}`;
  }
});
$("ha-prefs").addEventListener("click", () => {
  const open = $("prefs").classList.toggle("hidden") === false;
  $("ha-prefs").setAttribute("aria-expanded", String(open));
  if (open) loadStartPref().catch((err) => { $("pref-start-note").textContent = `⚠ ${err.message || err}`; });
});
$("prefs-close").addEventListener("click", () => { $("prefs").classList.add("hidden"); $("ha-prefs").setAttribute("aria-expanded", "false"); });
$("pref-costs").addEventListener("click", () => { $("prefs-close").click(); costs.open(); });
$("pref-alerts").addEventListener("click", () => { $("prefs-close").click(); alerts.open(); });
async function loadClaudeAuth() {
  const note = $("pref-claude-status");
  note.textContent = t("Verifico l'accesso Claude…");
  try {
    const data = await (await api("/api/claude/auth")).json();
    $("pref-claude-login").classList.toggle("hidden", data.mode === "api_key" || !data.subscription_enabled);
    const mode = { api_key: t("Chiave API"), subscription: t("Abbonamento"), hybrid: t("Abbonamento con riserva API") }[data.mode] || data.mode;
    const state = {
      ready: t("Collegato"), signed_out: t("Non collegato"), wrong_account: t("Account API, non abbonamento"),
      unavailable: t("Claude Code non disponibile"), off: t("Spento"),
    }[data.subscription.status] || data.subscription.status;
    note.textContent = `${mode} · ${state} · ${t("Chiave API")}: ${data.api_key_available ? t("presente") : t("assente")}`
      + (data.api_fallback ? ` · ${t("Riserva API attiva")}` : "")
      + (data.last_error ? ` · ${data.last_error}` : "")
      + (data.subscription.status === "signed_out" ? ` · ${t("Accedi nel terminale dell'add-on con claude auth login")}` : "");
  } catch (err) { note.textContent = `⚠ ${errorText(err)}`; }
}
$("pref-claude-refresh").addEventListener("click", loadClaudeAuth);
$("ha-prefs").addEventListener("click", () => { if (!$("prefs").classList.contains("hidden")) loadClaudeAuth(); });
let claudeLoginTimer;
async function pollClaudeLogin() {
  try {
    const data = await (await api("/api/claude/login")).json();
    $("pref-claude-output").textContent = data.output;
    if (data.running) claudeLoginTimer = setTimeout(pollClaudeLogin, 1200);
    else loadClaudeAuth();
  } catch (err) { $("pref-claude-output").textContent = `⚠ ${errorText(err)}`; }
}
$("pref-claude-start").addEventListener("click", async () => {
  clearTimeout(claudeLoginTimer);
  try {
    await api("/api/claude/login", { method: "POST" });
    pollClaudeLogin();
  } catch (err) { $("pref-claude-output").textContent = `⚠ ${errorText(err)}`; }
});
$("pref-claude-send").addEventListener("click", async () => {
  const input = $("pref-claude-code");
  try {
    await api("/api/claude/login/code", { method: "POST", body: JSON.stringify({ code: input.value }) });
    input.value = "";
  } catch (err) { $("pref-claude-output").textContent = `⚠ ${errorText(err)}`; }
});

// Backup and restore (administrators only; the add-on checks it too).
$("backup-get").addEventListener("click", async () => {
  const note = $("backup-note");
  note.textContent = t("Preparo il backup…");
  try {
    const res = await api("/api/backup");
    const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") || "")?.[1] || "hubnex-backup.zip";
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    note.textContent = t("Scaricato: {name}. Conservalo in un posto sicuro.", { name });
  } catch (err) { note.textContent = `⚠ ${errorText(err)}`; }
});
$("backup-put").addEventListener("click", () => $("backup-file").click());
$("backup-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  const note = $("backup-note");
  if (!confirm(t("Ripristinare \"{file}\"? Memoria, scadenze, Casa e configurazione di questa installazione vengono sostituite (le versioni attuali restano come copia di sicurezza).", { file: file.name }))) return;
  note.textContent = t("Carico il backup…");
  try {
    const res = await api("/api/backup/restore", { method: "POST", body: file, headers: { "Content-Type": "application/zip" } });
    const { restarting, manifest } = await res.json();
    note.textContent = restarting
      ? t("Backup del {date} caricato: HubNEX si riavvia, ricarica la pagina tra un minuto.", { date: manifest.created?.slice(0, 10) || "?" })
      : t("Backup caricato: riavvia HubNEX per applicarlo.");
  } catch (err) { note.textContent = `⚠ ${errorText(err)}`; }
});

// ===================================================================== neural map
const brain = new Brain(renderer, container);
S.view = "hq";
let graphTimer = null, graphStale = true;

async function loadGraph() {
  graphStale = false;
  try {
    const g = await (await api("/api/graph")).json();
    brain.setData(g);
    S.graph = g;
    for (const a of S.data?.agents || []) brain.setActive(a.id, a.status);
    renderMapPanel();
  } catch (err) { console.warn("graph", err); graphStale = true; }
}

// Knowledge changed: refresh the map (debounced), or mark it stale while it isn't shown.
function graphChanged() {
  if (S.view !== "map") { graphStale = true; return; }
  clearTimeout(graphTimer);
  graphTimer = setTimeout(loadGraph, 1500);
}

const casa = new CasaView($("casa"), {
  api,
  token: () => S.token,
  deadlines: () => (S.data && S.data.role !== "casa" ? S.data.deadlines || [] : null),
});

function setView(view) {
  S.view = view;
  safeSet("hq_view", view);
  document.body.classList.toggle("map", view === "map");
  document.body.classList.toggle("casa", view === "casa");
  $("view-hq").classList.toggle("active", view === "hq");
  $("view-map").classList.toggle("active", view === "map");
  $("view-casa").classList.toggle("active", view === "casa");
  $("casa").classList.toggle("hidden", view !== "casa");
  if (view === "casa") casa.open(); else casa.close();
  $("map-panel").classList.toggle("hidden", view !== "map");
  $("node-card").classList.add("hidden");
  controls.enabled = view === "hq";
  labelRenderer.domElement.style.display = view === "hq" ? "" : "none";
  brain.show(view === "map");
  if (view === "map" && graphStale) loadGraph();
}
$("view-hq").addEventListener("click", () => setView("hq"));
$("view-map").addEventListener("click", () => setView("map"));
$("view-casa").addEventListener("click", () => setView("casa"));

// ===================================================================== what each person sees
// HQ/Mappa and the assistant can be switched off per person (e.g. who only turns the lights
// on). Inside Home Assistant the choice is saved with the account, so it follows them on every
// device; elsewhere it stays in this browser. The local copy applies it before HA answers.
const UI = { hq: true, ai: true };
try { setUI(JSON.parse(safeGet("hq_ui") || "{}")); } catch { /* ignore */ }

function setUI(value) {
  for (const k of ["hq", "ai"]) if (typeof value?.[k] === "boolean") UI[k] = value[k];
  safeSet("hq_ui", JSON.stringify(UI));
  applyUI();
}

function applyUI() {
  const hasCasa = !S.data || S.data.integrations.home_assistant; // without HA nothing can replace HQ
  const houseOnly = S.data?.role === "casa"; // HA user who is not an administrator (decided by the add-on)
  const onlyCasa = (!UI.hq || houseOnly) && hasCasa;
  document.body.classList.toggle("role-casa", houseOnly);
  document.body.classList.toggle("no-hq", onlyCasa);
  document.body.classList.toggle("no-ai", !UI.ai || houseOnly);
  setSwitch("pref-hq", UI.hq);
  setSwitch("pref-ai", UI.ai);
  $("pref-ui-note").textContent = houseOnly
    ? t("Il tuo account di Home Assistant non è amministratore: HubNEX mostra solo la Casa.")
    : !UI.hq && !hasCasa ? t("Senza Home Assistant collegato la Casa non c'è: HQ resta visibile.") : "";
  if (!onlyCasa && S.view !== "casa") document.body.classList.remove("casa");
  if (!onlyCasa || S.view === "casa") return;
  if (S.data) setView("casa");
  else document.body.classList.add("casa"); // until the snapshot opens the house: no HQ flash
}

for (const k of ["hq", "ai"]) {
  $(`pref-${k}`).addEventListener("click", async () => {
    setUI({ [k]: !UI[k] });
    if (k === "ai" && !UI.ai) closeChat();
    const ha = haFrontend();
    if (!ha) return;
    try {
      await ha.hass.connection.sendMessagePromise({ type: "frontend/set_user_data", key: "hubnex", value: { ...UI } });
    } catch (err) {
      $("pref-ui-note").textContent = `⚠ ${t("Salvata solo su questo dispositivo")}: ${err.message || err.code || err}`;
    }
  });
}
$("ha-prefs").classList.remove("hidden");
// Language: automatic (Home Assistant's) or chosen here; applied by reloading the page.
try { $("pref-lang").value = localStorage.getItem("hq_lang") || ""; } catch { /* private mode */ }
$("pref-lang").addEventListener("change", (e) => { setLang(e.target.value); location.reload(); });
// Theme: automatic (the device's), dark or light; applied at once, remembered on this device.
$("pref-theme").value = window.hqTheme?.() || "";
$("pref-theme").addEventListener("change", (e) => window.hqTheme?.(e.target.value));
if (inHA) loadStartPref().catch(() => {});

function renderMapPanel() {
  const g = S.graph;
  if (!g) return;
  const counts = {};
  for (const n of g.nodes) counts[n.type] = (counts[n.type] || 0) + 1;
  $("map-legend").innerHTML = Object.entries(TYPES)
    .filter(([type]) => counts[type])
    .map(([type, t]) => `<li data-type="${type}" class="${brain.hidden.has(type) ? "off" : ""}"><span class="sw" style="color:${t.color || "#9fc7ff"}"></span>${t.label}<span class="n">${counts[type]}</span></li>`)
    .join("");
  $("map-legend").querySelectorAll("li").forEach((li) => li.addEventListener("click", () => {
    const off = !brain.hidden.has(li.dataset.type);
    brain.setHidden(li.dataset.type, off);
    li.classList.toggle("off", off);
  }));
  renderMapCounters();
}

function renderMapCounters() {
  const g = S.graph;
  if (!g) return;
  const active = (S.data?.agents || []).filter((a) => a.status !== "sleeping" && a.status !== "error").length;
  $("map-counters").innerHTML = [
    [g.stats.nodes, t("Nodi")], [g.stats.links, t("Sinapsi")], [g.stats.memories, t("Memorie")],
    [g.stats.tasks, t("Compiti")], [g.stats.keywords, t("Concetti")], [active, t("Attivi"), active ? "hot" : ""],
  ].map(([v, l, cls]) => `<div><div class="v ${cls || ""}">${v.toLocaleString(LOCALE)}</div><div class="l">${l}</div></div>`).join("");
}

$("map-search").addEventListener("input", (e) => {
  const n = brain.search(e.target.value);
  $("map-search-info").textContent = e.target.value.trim() ? (n ? t("{n} nodi trovati", { n }) : t("Nessun risultato")) : "";
});

function pickNode(e) {
  const n = brain.pick(e);
  if (!n) return;
  if (n.type === "agent" || n.type === "core") {
    // Agents open their usual card, shown over the map.
    const id = n.type === "core" ? S.data.boss.id : n.id.slice(2);
    S.selected = id;
    renderCard();
    return;
  }
  const d = brain.describe(n);
  $("node-type").textContent = d.type;
  $("node-label").textContent = d.label;
  $("node-when").textContent = d.when;
  $("node-detail").textContent = d.detail || "";
  $("node-detail").parentElement.classList.toggle("hidden", !d.detail);
  $("node-links").innerHTML = d.neighbours.join(" · ");
  $("node-card").classList.remove("hidden");
}
$("node-close").addEventListener("click", () => { $("node-card").classList.add("hidden"); brain.selected = null; });

animate();

// ===================================================================== UI panels
function renderCompanies() {
  $("companies").innerHTML = S.data.companies
    .map((c) => `<button class="company ${c.id === S.company ? "active" : ""}" data-id="${esc(c.id)}"><span class="logo">${esc(c.logo)}</span>${esc(c.name)}</button>`)
    .join("");
  $("companies").querySelectorAll(".company").forEach((b) =>
    b.addEventListener("click", () => { S.company = b.dataset.id; safeSet("hq_company", S.company); buildArena(); }));
  const i = S.data.integrations;
  $("integrations").innerHTML = [["HA", i.home_assistant], ["TG", i.telegram], ["MAIL", i.mail], ["MCP", (i.connectors || []).length > 0], [t("VOCE"), i.voice]]
    .map(([n, on]) => `<span class="integration ${on ? "on" : ""}">${n}</span>`).join("");
}

function renderStats() {
  const s = S.data.stats;
  const fmt = (n) => (n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? (n / 1e3).toFixed(1) + "k" : n);
  // Remaining Anthropic credit (estimated: credit entered in the add-on minus the cost of each call).
  const left = s.credit_usd - s.spent_usd;
  const claudeTile = s.credit_usd
    ? [t("Credito Claude"), money(Math.max(left, 0)), left < 1 ? "low" : "", true]
    : [t("Spesa Claude"), money(s.spent_usd), "", true];
  $("stats").innerHTML = [
    [t("Agenti attivi"), `${S.data.agents.filter((a) => a.status !== "sleeping" && a.status !== "error").length}/${S.data.agents.length}`, ""], [t("Compiti fatti"), s.tasks_done, ""],
    [t("Memorie"), s.memories, ""], claudeTile,
  ].map(([l, v, cls, claude]) => `<div class="stat ${cls}${claude ? " stat-costs" : ""}" ${claude ? `role="button" tabindex="0" data-costs title="${esc(t("Storico della spesa · {n} token dall'avvio", { n: fmt(s.tokens_in + s.tokens_out) }))}"` : ""}><div class="v">${esc(v)}</div><div class="l">${l}</div></div>`).join("");
}
$("stats").addEventListener("click", (e) => { if (e.target.closest("[data-costs]")) costs.open(); });
$("stats").addEventListener("keydown", (e) => { if ((e.key === "Enter" || e.key === " ") && e.target.closest("[data-costs]")) { e.preventDefault(); costs.open(); } });

function renderDeadlines() {
  const now = Date.now();
  $("deadlines").innerHTML = S.data.deadlines.map((d) => {
    const due = new Date(d.due.length <= 10 ? d.due + "T09:00" : d.due).getTime();
    const cls = due < now ? "late" : due - now < 3 * 864e5 ? "soon" : "";
    const label = new Date(due).toLocaleDateString(LOCALE, { day: "2-digit", month: "short" });
    return `<li class="${cls}"><span class="due">${label}</span><span class="t">${esc(d.title)}</span><button class="check" data-id="${d.id}" title="${t("Fatto")}" aria-label="${t("Segna come fatta")}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg></button></li>`;
  }).join("") || `<li><span class="t" style="color:var(--muted)">${t("Nessuna scadenza")}</span></li>`;
  $("deadlines").querySelectorAll(".check").forEach((b) =>
    b.addEventListener("click", () => api(`/api/deadlines/${b.dataset.id}/done`, { method: "POST" })));
}

// ---------------------------------------------------------------- drafts (same rules as Telegram:
// nothing is sent without two clicks)
function renderDrafts() {
  const drafts = S.data.drafts || [];
  const actions = S.data.actions || [];
  const total = drafts.length + actions.length;
  $("drafts-panel").classList.toggle("hidden", !total);
  $("drafts-badge").classList.toggle("hidden", !total);
  $("drafts-count").textContent = total;
  if (!total) $("drafts-sheet").classList.add("hidden");
  for (const box of [$("drafts"), $("drafts-mobile")]) {
    box.innerHTML = actions.map((a) => `
      <article class="draft action" data-action="${a.id}">
        <div class="draft-head">${t("Azione")} #${a.id}${a.agent_id && a.agent_id !== "jarvis" ? " · " + esc(agentName(a.agent_id)) : ""}</div>
        <div class="draft-body">${esc(a.summary)}</div>
        <div class="draft-actions">
          <button class="send" data-decide="ok">✅ ${t("Conferma")}</button>
          <button class="drop" data-decide="no">❌ ${t("Annulla")}</button>
        </div>
        <div class="draft-error hidden"></div>
      </article>`).join("") + drafts.map((d) => `
      <article class="draft" data-id="${d.id}">
        <div class="draft-head">#${d.id} · ${t("A")}: ${esc(d.to_addr)}</div>
        <div class="draft-subject">${esc(d.subject)}</div>
        <div class="draft-body">${esc(d.body)}</div>
        <div class="draft-actions">
          <button class="send" data-act="send">📤 ${t("Invia")}</button>
          <button data-act="save">💾 ${t("Salva")}</button>
          <button data-act="edit">✏️ ${t("Modifica")}</button>
          <button class="drop" data-act="drop">🗑 ${t("Scarta")}</button>
        </div>
        <form class="draft-edit hidden"><input placeholder="${t("Cosa cambio? es. più formale")}" required><button>↻</button></form>
        <div class="draft-error hidden"></div>
      </article>`).join("");
    box.querySelectorAll(".draft:not(.action)").forEach(bindDraft);
    box.querySelectorAll(".draft.action").forEach(bindAction);
  }
}

function bindDraft(card) {
  const id = card.dataset.id;
  const error = card.querySelector(".draft-error");
  const fail = (msg) => { card.classList.remove("busy"); error.textContent = "⚠ " + msg; error.classList.remove("hidden"); };
  const run = async (path, body) => {
    card.classList.add("busy");
    error.classList.add("hidden");
    try {
      await api(`/api/drafts/${id}/${path}`, { method: "POST", body: body ? JSON.stringify(body) : undefined });
    } catch (err) {
      fail(/non più attiva|no longer/.test(err.message) ? t("Bozza non più attiva") : err.message);
    }
  };
  card.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => {
    const act = b.dataset.act;
    if (act === "edit") return card.querySelector(".draft-edit").classList.toggle("hidden");
    if (act === "send" && !b.classList.contains("confirm")) {
      const d = S.data.drafts.find((x) => String(x.id) === id);
      b.classList.add("confirm");
      b.textContent = `✅ ${t("Conferma invio a {to}", { to: (d?.to_addr || "").slice(0, 28) })}`;
      setTimeout(() => { b.classList.remove("confirm"); b.textContent = `📤 ${t("Invia")}`; }, 6000);
      return;
    }
    run(act);
  }));
  card.querySelector(".draft-edit").addEventListener("submit", (e) => {
    e.preventDefault();
    const text = e.target.querySelector("input").value.trim();
    if (text) run("revise", { text });
  });
}

function bindAction(card) {
  const error = card.querySelector(".draft-error");
  card.querySelectorAll("[data-decide]").forEach((b) => b.addEventListener("click", async () => {
    card.classList.add("busy");
    error.classList.add("hidden");
    try {
      await api(`/api/actions/${card.dataset.action}/${b.dataset.decide}`, { method: "POST" });
    } catch (err) {
      card.classList.remove("busy");
      error.textContent = "⚠ " + (err.message.match(/"detail":"([^"]+)"/)?.[1] || err.message);
      error.classList.remove("hidden");
    }
  }));
}

$("drafts-badge").addEventListener("click", () => $("drafts-sheet").classList.remove("hidden"));
$("drafts-sheet-close").addEventListener("click", () => $("drafts-sheet").classList.add("hidden"));

function agentName(id) { return S.data?.agents.find((a) => a.id === id)?.name || ""; }

function feedItem(e) {
  const li = document.createElement("li");
  const time = new Date(e.ts * 1000).toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" });
  li.className = `kind-${e.kind}`;
  const text = e.text.length > 400 ? e.text.slice(0, 400) + "…" : e.text;
  li.innerHTML = `<span class="time">${time}</span><span class="who">${KIND_ICON[e.kind] || "·"}</span><span class="body">${esc(text)}</span>`;
  return li;
}

const FEED_PAGE = 25;
function renderFeed() {
  const ul = $("feed");
  ul.innerHTML = "";
  const recent = S.data.logs.slice(-FEED_PAGE);
  recent.reverse().forEach((e) => ul.appendChild(feedItem(e)));
  S.feedOldest = recent.length ? recent[recent.length - 1].id : null;
  $("feed-more").classList.toggle("hidden", S.data.logs.length < FEED_PAGE);
}

$("feed-more").addEventListener("click", async () => {
  if (!S.feedOldest) return;
  const older = await (await api(`/api/logs?before=${S.feedOldest}&limit=${FEED_PAGE}`)).json();
  older.reverse().forEach((e) => $("feed").appendChild(feedItem(e)));
  if (older.length) S.feedOldest = older[older.length - 1].id;
  if (older.length < FEED_PAGE) $("feed-more").classList.add("hidden");
});

function selectAgent(id) {
  S.selected = id;
  for (const [aid, o] of agentObjs) o.label?.element.classList.toggle("selected", aid === id);
  controls.autoRotate = false;
  renderCard();
}

function renderCard() {
  const a = S.data.agents.find((x) => x.id === S.selected);
  if (!a) return $("agent-card").classList.add("hidden");
  const company = S.data.companies.find((c) => c.id === a.company);
  const dept = company?.departments.find((d) => d.id === a.department);
  $("agent-card").classList.remove("hidden");
  $("card-avatar").style.color = a.color || dept?.color || "#4fd1ff";
  $("card-company").textContent = company ? `${company.name} · ${dept?.name || ""}` : "Headquarter";
  $("card-name").textContent = a.name;
  $("card-role").textContent = a.role;
  $("card-status").className = `badge ${a.status}`;
  $("card-status").textContent = STATUS_IT[a.status] || a.status;
  $("card-detail").textContent = a.detail || (a.done ? t("{n} compiti completati", { n: a.done }) : "");
  const show = (id, v) => { $(id + "-wrap").classList.toggle("hidden", !v); if (v) $(id).textContent = v; };
  show("card-task", a.task);
  show("card-thought", a.status !== "sleeping" ? a.thought : null);
  show("card-result", a.last_result);
  const routines = S.data.routines[a.id] || [];
  $("card-routines-wrap").classList.toggle("hidden", !routines.length);
  $("card-routines").innerHTML = routines.map((r) =>
    `<li class="${r.enabled ? "" : "off"}">${r.enabled ? "" : `[${t("spenta")}] `}${r.at ? `${t("ore")} ${esc(r.at)}${r.days ? " (" + r.days.join(", ") + ")" : ""}` : `${t("ogni")} ${esc(r.every)}`}: ${esc(r.task.slice(0, 90))}…</li>`).join("");
  $("assign-form").classList.toggle("hidden", a.id === S.data.boss.id);
}

$("card-close").addEventListener("click", () => {
  S.selected = null;
  for (const o of agentObjs.values()) o.label?.element.classList.remove("selected");
  $("agent-card").classList.add("hidden");
});

$("assign-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const task = $("assign-input").value.trim();
  if (!task || !S.selected) return;
  $("assign-input").value = "";
  await api(`/api/agents/${S.selected}/task`, { method: "POST", body: JSON.stringify({ task, wait: false }) });
});

$("add-deadline").addEventListener("click", () => $("deadline-form").classList.toggle("hidden"));
$("deadline-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  await api("/api/deadlines", { method: "POST", body: JSON.stringify({ title: f.get("title"), due: f.get("due"), company: S.company }) });
  e.target.reset();
  e.target.classList.add("hidden");
});

setInterval(() => {
  const time = new Date().toLocaleString(LOCALE, { weekday: "short", hour: "2-digit", minute: "2-digit" }).toUpperCase();
  $("clock").textContent = S.data?.version ? `${time} · v${S.data.version}` : time;
}, 1000);

// ===================================================================== chat + voice
// While you talk to Jarvis from here his orb takes the stage: it listens to you, shows what
// he is doing (thinking, using a tool, involving the team) and pulses with his voice.
const talk = { on: false, audio: null, ctx: null, analyser: null, typing: 0, thought: null, hearing: false, player: null, routed: false };
const SPEAKER_ON = `<svg class="ui-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/></svg>`;
const SPEAKER_OFF = `<svg class="ui-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="m16 9.5 5 5M21 9.5l-5 5"/></svg>`;
const SILENCE_WAV = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQAAAAA=";

// Phones (and the HA app) only let a page play sound it started during a tap. The answer
// arrives seconds later, so on the tap we start (silently) the player that will speak it.
function unlockAudio() {
  audioContext();
  if (!talk.player) talk.player = new Audio();
  if (!talk.player.src || talk.player.src === SILENCE_WAV || talk.player.ended || talk.player.paused) {
    talk.player.src = SILENCE_WAV;
    talk.player.play().catch(() => {});
  }
}

// The player for an answer: wired to the analyser (orb pulsing with the voice) when Web Audio
// runs; a wired player is silent if Web Audio is suspended, so then a plain one is used.
async function answerPlayer() {
  if (talk.ctx && talk.ctx.state !== "running") await talk.ctx.resume().catch(() => {});
  const running = talk.ctx?.state === "running";
  talk.player ||= new Audio();
  if (running && !talk.routed) {
    try { talk.ctx.createMediaElementSource(talk.player).connect(talk.analyser); talk.routed = true; } catch { /* already wired */ }
  }
  if (talk.routed && !running) { orb.useAnalyser(null); return new Audio(); }
  orb.useAnalyser(talk.routed ? talk.analyser : null);
  return talk.player;
}

function errorText(err) {
  try { return JSON.parse(err.message).detail || err.message; } catch { return err.message || String(err); }
}

// Under an answer that could not be spoken: why, and (if the phone blocked it) a tap to listen.
function voiceNote(el, note) {
  const div = document.createElement("div");
  div.className = "voice-note";
  div.textContent = note.error.charAt(0).toUpperCase() + note.error.slice(1);
  if (note.replay) {
    const b = document.createElement("button");
    b.textContent = `▶ ${t("Ascolta")}`;
    b.addEventListener("click", () => new Audio(note.replay).play());
    div.appendChild(b);
  }
  el.appendChild(div);
}
const orbThought = $("orb").querySelector(".orb-thought");

// Created on a click: browsers only play Web Audio after a user gesture.
function audioContext() {
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return null;
  if (!talk.ctx) {
    talk.ctx = new AC();
    talk.analyser = talk.ctx.createAnalyser();
    talk.analyser.fftSize = 256;
    talk.analyser.smoothingTimeConstant = 0.6;
    talk.analyser.connect(talk.ctx.destination);
  }
  if (talk.ctx.state === "suspended") talk.ctx.resume().catch(() => {});
  return talk.ctx;
}

function stopTalk() {
  talk.on = false;
  talk.typing++; // cancels a running typewriter
  if (talk.audio) { talk.audio.pause(); talk.audio = null; }
  orbThought.textContent = "";
}

function closeChat() {
  stopTalk();
  orb.done(0);
  $("chat-log").innerHTML = "";
  $("chat-close").classList.add("hidden");
}
$("chat-close").addEventListener("click", closeChat);
addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!$("agent-card").classList.contains("hidden")) return $("card-close").click();
  closeChat();
});

function addMsg(text, who, pending = false, files = []) {
  $("chat-close").classList.remove("hidden");
  const div = document.createElement("div");
  div.className = `msg ${who}${pending ? " pending" : ""}`;
  div.textContent = text;
  if (files.length) {
    const box = document.createElement("div");
    box.className = "msg-files";
    for (const f of files) box.appendChild(fileChip(f));
    div.prepend(box);
  }
  $("chat-log").appendChild(div);
  $("chat-log").scrollTop = $("chat-log").scrollHeight;
  return div;
}

// Reveals the text letter by letter; progress() goes from 0 to 1 (elapsed time, or the audio).
function typewrite(el, text, progress, onFrame) {
  const run = ++talk.typing;
  el.classList.add("typing");
  return new Promise((resolve) => {
    const step = () => {
      const p = run === talk.typing ? Math.min(1, progress()) : 1;
      el.textContent = text.slice(0, Math.ceil(text.length * p));
      $("chat-log").scrollTop = $("chat-log").scrollHeight;
      if (p >= 1) { el.classList.remove("typing"); return resolve(); }
      onFrame?.();
      requestAnimationFrame(step);
    };
    step();
  });
}

// Written answer: the orb "speaks" in step with the text.
async function reveal(el, text) {
  orb.useAnalyser(null);
  orb.show("speaking", "");
  const start = performance.now(), ms = Math.min(6000, Math.max(700, text.length * 22));
  await typewrite(el, text, () => (performance.now() - start) / ms, () => {
    const t = performance.now();
    orb.synthetic = 0.2 + 0.45 * Math.abs(Math.sin(t / 70) * Math.sin(t / 190));
  });
  if (talk.on) { talk.on = false; orb.done(); }
}

// Spoken answer: real loudness from the audio drives the orb, the text follows the voice.
// Returns true when spoken, else { error, replay? } to show under the written answer.
async function speak(text, el, written = text) {
  orb.caption(t("Preparo la voce…"));
  let src;
  try {
    const res = await api("/api/tts", { method: "POST", body: JSON.stringify({ text: text.replace(/[*_`#]/g, "").slice(0, 2500) }) });
    src = URL.createObjectURL(await res.blob());
  } catch (err) {
    return { error: `${t("Voce non disponibile")}: ${errorText(err)}` };
  }
  try {
    if (!talk.on) return true;
    const audio = await answerPlayer();
    talk.audio = audio;
    audio.src = src;
    const ended = new Promise((r) => { audio.onended = r; audio.onpause = r; audio.onerror = r; });
    try {
      await audio.play();
    } catch (err) {
      talk.audio = null;
      return err.name === "NotAllowedError"
        ? { error: t("il telefono ha bloccato l'audio automatico."), replay: src }
        : { error: `${t("audio non riproducibile")} (${err.message})`, replay: src };
    }
    orb.show("speaking", "");
    const start = performance.now();
    await typewrite(el, written, () => {
      if (audio.ended) return 1;
      if (Number.isFinite(audio.duration) && audio.duration > 0) return (audio.currentTime / audio.duration) * 1.08;
      return (performance.now() - start) / (text.length * 60);
    }, () => { orb.synthetic = 0.35; });
    await ended;
    if (talk.audio === audio) { talk.audio = null; talk.on = false; orb.done(); }
    return true;
  } catch (err) {
    console.warn("tts", err);
    return { error: `${t("voce non riprodotta")} (${err.message})`, replay: src };
  }
}

// ===================================================================== attachments
// Photos (from the camera too, on a phone), PDFs and text files for the next message.
// Big photos are scaled down here first: less to upload from a building site.
const files = { list: [] };
const SHRINK_OVER = 1.5 * 1024 * 1024;

function fileChip(f, onRemove) {
  const chip = document.createElement(f.url ? "a" : "span");
  chip.className = `file-chip ${f.kind || ""}${f.status ? " " + f.status : ""}`;
  if (f.url) { chip.href = f.url; chip.target = "_blank"; chip.rel = "noopener"; }
  if (f.kind === "image" && f.preview) {
    const img = document.createElement("img");
    img.src = f.preview; img.alt = "";
    chip.appendChild(img);
  } else {
    const tag = document.createElement("b");
    tag.textContent = f.kind === "pdf" ? "PDF" : f.kind === "text" ? "TXT" : "…";
    chip.appendChild(tag);
  }
  const name = document.createElement("span");
  name.textContent = f.status === "uploading" ? t("caricamento…") : f.name;
  chip.appendChild(name);
  if (onRemove) {
    const x = document.createElement("button");
    x.type = "button"; x.className = "mini"; x.textContent = "×";
    x.title = t("Rimuovi allegato"); x.setAttribute("aria-label", x.title);
    x.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); onRemove(); });
    chip.appendChild(x);
  }
  return chip;
}

function renderFiles() {
  const box = $("chat-files");
  box.replaceChildren(...files.list.map((f) => fileChip(f, () => {
    files.list = files.list.filter((g) => g !== f);
    renderFiles();
  })));
  box.classList.toggle("hidden", !files.list.length);
  $("attach").classList.toggle("on", files.list.length > 0);
}

async function shrink(file) {
  if (!file.type.startsWith("image/") || file.size < SHRINK_OVER || file.type === "image/gif") return file;
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const k = Math.min(1, 2000 / Math.max(bmp.width, bmp.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * k); canvas.height = Math.round(bmp.height * k);
    canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((r) => canvas.toBlob(r, "image/jpeg", 0.85));
    return blob && blob.size < file.size ? blob : file;
  } catch {
    return file; // a format the browser cannot draw: the add-on tries itself
  }
}

function addFiles(list) {
  for (const file of list) {
    if (files.list.length >= 10) break;
    const f = { name: file.name, kind: file.type.startsWith("image/") ? "image" : "", status: "uploading" };
    if (f.kind === "image") f.preview = URL.createObjectURL(file);
    f.ready = (async () => {
      try {
        const body = await shrink(file);
        const res = await api(`/api/attachments?name=${encodeURIComponent(file.name)}`, {
          method: "POST", body, headers: { "Content-Type": body.type || file.type || "application/octet-stream" },
        });
        Object.assign(f, await res.json(), { status: "" });
      } catch (err) {
        files.list = files.list.filter((g) => g !== f);
        addMsg(`⚠ ${t("Allegato non caricato")} (${file.name}): ${errorText(err)}`, "jarvis");
      }
      renderFiles();
    })();
    files.list.push(f);
  }
  renderFiles();
}

$("attach").addEventListener("click", () => $("attach-input").click());
$("attach-input").addEventListener("change", (e) => { addFiles([...e.target.files]); e.target.value = ""; });
// Pasting a screenshot or dropping files on the chat attaches them too.
$("chat-input").addEventListener("paste", (e) => {
  const pasted = [...(e.clipboardData?.files || [])];
  if (pasted.length) { e.preventDefault(); addFiles(pasted); }
});
$("chat").addEventListener("dragover", (e) => { if (e.dataTransfer?.types.includes("Files")) e.preventDefault(); });
$("chat").addEventListener("drop", (e) => {
  if (!e.dataTransfer?.files.length) return;
  e.preventDefault();
  addFiles([...e.dataTransfer.files]);
});

// The answer of a chat job: short requests every 1.5 s, so no proxy cuts a long wait. A
// dropped connection on the way (phone changing network…) is retried, not reported.
async function chatAnswer(job) {
  let misses = 0;
  for (;;) {
    await new Promise((r) => setTimeout(r, 1500));
    let res;
    try {
      res = await api(`/api/chat/${job}`);
    } catch (err) {
      if (err instanceof TypeError && ++misses < 40) continue; // network: try again
      throw err;
    }
    misses = 0;
    const out = await res.json();
    if (out.done) return out;
  }
}

// A question from a card of the house ("Domanda a Jarvis"): as if typed in the chat.
window.addEventListener("hubnex-ask", (e) => sendChat(e.detail));

async function sendChat(text, sent = []) {
  stopTalk();
  const voice = S.speak && S.data?.integrations?.voice;
  talk.on = true;
  talk.thought = S.data?.agents.find((a) => a.id === S.data.boss.id)?.thought ?? null;
  orb.show("thinking");
  addMsg(text, "me", false, sent.map((f) => ({ ...f, url: `api/attachments/${f.id}${S.token ? `?token=${encodeURIComponent(S.token)}` : ""}` })));
  const wait = addMsg(t("{name} sta pensando…", { name: S.data?.boss?.name || t("L'assistente") }), "jarvis", true);
  try {
    // In a room of the house view Jarvis knows where you are ("spegni qui").
    const context = S.view === "casa" ? casa.context() : "";
    const res = await api("/api/chat", { method: "POST", body: JSON.stringify({ text: context + text, speak: !!voice, attachments: sent.map((f) => f.id), background: true }) });
    const { reply, spoken: said, by } = await chatAnswer((await res.json()).job);
    wait.classList.remove("pending");
    if (by === "ha" || by === "quick") { // a small note: who answered
      wait.dataset.by = by;
      wait.dataset.byLabel = by === "ha" ? "Home Assistant" : t("Risposta rapida");
    }
    if (!talk.on) { wait.textContent = reply; return; } // conversation closed meanwhile
    wait.textContent = "";
    orbThought.textContent = "";
    // "Risposte a voce: riassunto": the voice says the gist, the text is the whole answer
    const spoken = voice ? await speak(said || reply, wait, reply) : null;
    if (spoken === true) return;
    await reveal(wait, reply);
    if (spoken?.error) voiceNote(wait, spoken);
  } catch (err) {
    wait.classList.remove("pending");
    wait.textContent = "⚠ " + err.message;
    talk.on = false;
    orb.done(800);
  }
}

// Live HQ events tell the orb what Jarvis (and whoever he involves) is doing right now.
function orbFollow(a) {
  if (!talk.on || orb.state === "speaking" || orb.state === "listening" || !S.data) return;
  if (a.id === S.data.boss.id) {
    if (a.status === "thinking") orb.show("thinking");
    else if (a.status === "writing") orb.show("thinking", t("Formulo la risposta…"));
    else if (a.status === "working" || a.status === "searching") orb.show("working", describeTool(a.detail, a.name));
    if (a.thought && a.thought !== talk.thought) orbThought.textContent = lastSentences(a.thought);
  } else if (a.status !== "sleeping" && a.status !== "error") {
    orb.show("working", t("{name} al lavoro…", { name: a.name }));
  }
}

function lastSentences(text) {
  const parts = text.replace(/\s+/g, " ").trim().split(/(?<=[.!?])\s/);
  let out = parts.pop() || "";
  if (out.length < 40 && parts.length) out = parts.pop() + " " + out;
  return out.length > 160 ? "…" + out.slice(-160) : out;
}

// The request wraps and grows with the text (up to about 6 lines, then it scrolls).
function fitChatInput() {
  const el = $("chat-input");
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight + 2, el.offsetParent ? parseFloat(getComputedStyle(el).maxHeight) || 999 : 999) + "px";
  el.style.overflowY = el.scrollHeight > el.clientHeight + 2 ? "auto" : "hidden";
}
$("chat-input").addEventListener("input", fitChatInput);
// Enter sends, Shift+Enter goes to a new line (on phones the keyboard's key sends too).
$("chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    $("chat-form").requestSubmit();
  }
});
$("chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("chat-input").value.trim();
  if (!text && !files.list.length) return;
  $("chat-input").value = "";
  fitChatInput();
  unlockAudio();
  const pending = files.list;
  files.list = [];
  renderFiles();
  await Promise.all(pending.map((f) => f.ready)); // photos still uploading
  const sent = pending.filter((f) => f.id);
  if (!text && !sent.length) return;
  sendChat(text, sent);
});

$("speaker").classList.toggle("on", S.speak);
$("speaker").addEventListener("click", () => {
  S.speak = !S.speak;
  safeSet("hq_speak", S.speak ? "1" : "0");
  $("speaker").classList.toggle("on", S.speak);
  setSpeakerIcon();
  if (!S.speak && talk.audio) talk.audio.pause();
});
function setSpeakerIcon() {
  $("speaker").innerHTML = S.speak ? SPEAKER_ON : SPEAKER_OFF;
  $("speaker").classList.toggle("on", S.speak);
  $("speaker").setAttribute("aria-pressed", String(S.speak));
  $("speaker").title = S.speak ? t("Risposte vocali attive") : t("Risposte vocali spente");
}
setSpeakerIcon();

// Browser speech recognition (Chrome/Edge/Safari). Hidden where unsupported.
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (!SR) $("mic").classList.add("hidden");
else {
  const rec = new SR();
  rec.lang = LANG === "it" ? "it-IT" : (navigator.language || "en-GB");
  rec.interimResults = true; // your words appear under the orb while you speak
  let heard = "";
  const pulse = () => {
    if (orb.state !== "listening") return;
    const t = performance.now();
    orb.synthetic = talk.hearing ? 0.3 + 0.45 * Math.abs(Math.sin(t / 60) * Math.sin(t / 170)) : 0.06 + 0.04 * Math.sin(t / 300);
    requestAnimationFrame(pulse);
  };
  rec.onstart = () => { stopTalk(); talk.on = true; orb.show("listening"); pulse(); };
  rec.onspeechstart = () => { talk.hearing = true; };
  rec.onspeechend = () => { talk.hearing = false; };
  rec.onresult = (e) => {
    let final = "", interim = "";
    for (const r of e.results) (r.isFinal ? (final += r[0].transcript) : (interim += r[0].transcript));
    if (final) heard = final;
    orbThought.textContent = `“${(final || interim).trim()}”`;
  };
  rec.onend = () => {
    $("mic").classList.remove("rec");
    talk.hearing = false;
    const text = heard.trim();
    heard = "";
    if (text) { S.speak = true; setSpeakerIcon(); sendChat(text); } else { talk.on = false; orbThought.textContent = ""; orb.done(300); }
  };
  $("mic").addEventListener("click", () => {
    unlockAudio();
    $("mic").classList.add("rec");
    try { rec.start(); } catch { /* already listening */ }
  });
}

// ===================================================================== live connection
function showLogin() { $("login").classList.remove("hidden"); $("login-token").focus(); }
$("login-form").addEventListener("submit", (e) => {
  e.preventDefault();
  S.token = $("login-token").value.trim();
  safeSet("hq_token", S.token);
  $("login").classList.add("hidden");
  connect();
});

let ws, retry = 1000;
function connect() {
  const url = new URL("ws", location.href);
  url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
  url.search = `?token=${encodeURIComponent(S.token)}`;
  ws = new WebSocket(url);
  ws.onopen = () => { retry = 1000; document.querySelector(".live-dot").classList.remove("off"); };
  ws.onclose = (e) => {
    document.querySelector(".live-dot").classList.add("off");
    if (e.code === 4401) return showLogin();
    setTimeout(connect, retry);
    retry = Math.min(retry * 2, 15000);
  };
  ws.onmessage = (m) => handle(JSON.parse(m.data));
}

function handle(ev) {
  switch (ev.type) {
    case "snapshot":
      if (S.token) safeSet("hq_token", S.token);
      S.data = ev.state;
      $("chat-input").placeholder = t("Parla con {name}…", { name: S.data.boss.name });
      buildArena(); renderStats(); renderDeadlines(); renderFeed(); renderDrafts();
      $("view-casa").classList.toggle("hidden", !S.data.integrations.home_assistant);
      if ((!UI.hq || S.data.role === "casa") && S.data.integrations.home_assistant) { if (S.view !== "casa") setView("casa"); }
      else if (safeGet("hq_view") === "map" && S.view !== "map") setView("map");
      else if (safeGet("hq_view") === "casa" && S.view !== "casa" && S.data.integrations.home_assistant) setView("casa");
      applyUI();
      break;
    case "agent": {
      if (!S.data) return;
      const i = S.data.agents.findIndex((a) => a.id === ev.agent.id);
      const prev = S.data.agents[i];
      const busy = ev.agent.status !== "sleeping" && ev.agent.status !== "error";
      if (busy) fireBeam(ev.agent.id);
      else if (prev && prev.status !== ev.agent.status) stopBeam(ev.agent.id);
      S.data.agents[i] = ev.agent;
      const o = agentObjs.get(ev.agent.id);
      if (o?.label) o.label.element.className = `agent-label ${ev.agent.status}${S.selected === ev.agent.id ? " selected" : ""}`;
      if (S.selected === ev.agent.id) renderCard();
      renderStats();
      brain.setActive(ev.agent.id, ev.agent.status);
      orbFollow(ev.agent);
      renderMapCounters();
      break;
    }
    case "log":
      if (["memory", "result", "deadline", "mail"].includes(ev.entry.kind)) graphChanged();
      S.data.logs.push(ev.entry);
      $("feed").prepend(feedItem(ev.entry));
      if ($("feed").children.length > 300) $("feed").lastChild.remove(); // long-open dashboards
      break;
    case "deadlines": S.data.deadlines = ev.deadlines; renderDeadlines(); if (casa.visible) casa.render(); break;
    case "drafts": S.data.drafts = ev.drafts; renderDrafts(); break;
    case "actions": S.data.actions = ev.actions; renderDrafts(); break;
    case "stats": S.data.stats = ev.stats; renderStats(); break;
    case "ha": case "casa_changed": casa.handle(ev); break;
  }
}

connect();
