// Floor plan editor of the house view: load a photo/PDF of the plan, draw the rooms over it
// (drag on the empty drawing), move and resize them, link each one to a Home Assistant area.
// "Proponi le stanze" asks Claude to read the plan and draws them for you to check.
// It lives over the page (not inside the house view), so live updates never interrupt a drag.

import { t } from "./i18n.js";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const round = (v) => Math.round(v * 10) / 10;
const boxOf = (points) => {
  const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
  return { x: Math.min(...xs), y: Math.min(...ys), w: round(Math.max(...xs) - Math.min(...xs)), h: round(Math.max(...ys) - Math.min(...ys)) };
};
const corners = (r) => r.points || [{ x: r.x, y: r.y }, { x: r.x + r.w, y: r.y }, { x: r.x + r.w, y: r.y + r.h }, { x: r.x, y: r.y + r.h }];
const localPoints = (r) => r.points.map((p) => ({ x: ((p.x - r.x) / (r.w || 1)) * 100, y: ((p.y - r.y) / (r.h || 1)) * 100 }));
export const shapeStyle = (r) => r.points ? `;clip-path:polygon(${localPoints(r).map((p) => `${p.x}% ${p.y}%`).join(",")})` : "";
export const shapeSVG = (r) => r.points ? `<svg class="plan-shape" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><polygon points="${localPoints(r).map((p) => `${p.x},${p.y}`).join(" ")}"/></svg>` : "";

export class PlanEditor {
  constructor({ api, token, onSaved, onText, toast }) {
    Object.assign(this, { api, token, onSaved, onText, toast });
    this.box = null;
  }

  async open() {
    const plan = await (await this.api("api/casa/plan")).json();
    this.areas = plan.areas || [];
    this.floors = (plan.floors || []).map((f) => ({ ...f, rooms: f.rooms.map((r) => ({ ...r })) }));
    if (!this.floors.length) this.floors.push({ name: t("Piano terra"), aspect: 1.4, rooms: [] });
    this.outside = [...(plan.outside || [])];
    this.energy = plan.energy || {};
    this.floor = 0;
    this.sel = null;
    this.tool = "rect";
    this.draft = null;
    this.point = null;
    this.msg = plan.error ? `${t("La piantina salvata ha un errore")}: ${plan.error}` : "";
    this.busy = false;
    this.box = document.createElement("div");
    this.box.className = "casa-modal casa-overlay ped";
    this.box.setAttribute("role", "dialog");
    this.box.setAttribute("aria-label", t("Editor della piantina"));
    document.body.appendChild(this.box);
    this.box.addEventListener("click", (e) => this.click(e));
    this.box.addEventListener("change", (e) => this.change(e));
    this.box.addEventListener("input", (e) => this.input(e));
    this.box.addEventListener("pointerdown", (e) => this.down(e));
    this.render();
  }

  close() {
    this.box?.remove();
    this.box = null;
  }

  get f() { return this.floors[this.floor]; }
  imageURL(name) {
    const tok = this.token();
    return `api/casa/plan-image/${name}?v=${this.f.v || 0}${tok ? "&token=" + encodeURIComponent(tok) : ""}`;
  }
  linked(r) { return this.areas.includes(r.area); }

  // ------------------------------------------------------------------ drawing
  render() {
    if (!this.box) return;
    const f = this.f;
    const tabs = this.floors.map((x, i) => `<button class="${i === this.floor ? "on" : ""}" data-ed="floor" data-i="${i}">${esc(x.name)}</button>`).join("")
      + `<button data-ed="add-floor" title="${t("Aggiungi un piano")}">+ ${t("Piano")}</button>`;
    const rooms = f.rooms.map((r, i) => `
      <div class="ped-room ${r.points ? "polygon" : ""} ${i === this.sel ? "sel" : ""} ${this.linked(r) ? "" : "unlinked"} ${r.outline ? "outline" : ""}"
           data-room="${i}" style="left:${r.x}%;top:${r.y}%;width:${r.w}%;height:${r.h}%${shapeStyle(r)}">
        ${shapeSVG(r)}<span>${esc(r.area)}</span>${r.points ? "" : `<i class="ped-handle" data-handle="${i}" aria-hidden="true"></i>`}
      </div>`).join("");
    const r = this.sel != null ? f.rooms[this.sel] : null;
    const vertices = r?.points?.map((p, j) => `<button class="ped-vertex ${j === this.point ? "on" : ""}" data-point="${j}" style="left:${p.x}%;top:${p.y}%" aria-label="${t("Angolo")} ${j + 1}"></button>`).join("") || "";
    const edges = r?.points?.map((p, j) => { const next = r.points[(j + 1) % r.points.length]; return `<button class="ped-edge" data-edge="${j}" style="left:${(p.x + next.x) / 2}%;top:${(p.y + next.y) / 2}%" aria-label="${t("Aggiungi angolo")}"></button>`; }).join("") || "";
    const draft = this.draft ? `<svg class="ped-draft" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><polyline points="${this.draft.map((p) => `${p.x},${p.y}`).join(" ")}"/></svg>${this.draft.map((p, j) => `<button class="ped-vertex ${j === 0 ? "first" : ""}" data-draft-point="${j}" style="left:${p.x}%;top:${p.y}%" aria-label="${j === 0 ? t("Chiudi forma") : `${t("Angolo")} ${j + 1}`}"></button>`).join("")}` : "";
    const areaOpts = (cur) => `<option value="" ${this.linked({ area: cur }) ? "" : "selected"}>— ${t("solo disegno (nome libero)")} —</option>`
      + this.areas.map((a) => `<option ${a === cur ? "selected" : ""}>${esc(a)}</option>`).join("");
    const side = r ? `
        <h4>${t("Stanza")}</h4>
        <label class="ped-field">${t("Area di Home Assistant")}<select data-ed="area">${areaOpts(r.area)}</select></label>
        ${this.linked(r) ? "" : `<label class="ped-field">${t("Nome sul disegno")}<input data-ed="label" value="${esc(r.area)}" maxlength="60"></label>
          <p class="casa-muted">${t("Senza area si vede ma non si tocca: scegli l'area per comandarla.")}</p>`}
        <label class="ped-check"><input type="checkbox" data-ed="outline" ${r.outline ? "checked" : ""}> ${t("Solo contorno (balcone, giardino…)")}</label>
        <div class="casa-actions">${r.points ? `<button data-ed="delete-point" ${this.point == null || r.points.length <= 3 ? "disabled" : ""}>${t("Elimina angolo")}</button>` : `<button data-ed="edit-points">${t("Modifica angoli")}</button>`}</div>
        <div class="casa-actions"><button data-ed="delete" class="ped-danger">${t("Elimina stanza")}</button><button data-ed="unselect">${t("Fatto")}</button></div>`
      : `<p class="casa-muted">${this.tool === "polygon" ? t("Tocca gli angoli in ordine; chiudi sul primo punto o premi Completa forma.") : f.image ? t("Trascina sul disegno per aggiungere una stanza; toccane una per spostarla, ridimensionarla (angolo in basso a destra) o sceglierne l'area.") : t("Carica la planimetria (foto, immagine o PDF), poi disegna le stanze o fai la proposta automatica.")}</p>`;
    const unplaced = this.areas.filter((a) => !this.floors.some((x) => x.rooms.some((q) => q.area === a)));
    this.box.innerHTML = `
      <section class="panel casa-panel ped-panel">
        <h3>${t("Piantina")} <button class="casa-x" data-ed="close" aria-label="${t("Chiudi")}">×</button></h3>
        <div class="ped-bar">
          <div class="casa-floors ped-tabs">${tabs}</div>
          <label class="ped-btn">${t("Carica planimetria")}<input type="file" data-ed="file" accept="image/*,application/pdf" hidden></label>
          <button data-ed="suggest" ${f.image && !this.busy ? "" : "disabled"} title="${t("Claude legge la planimetria e propone le stanze")}">${t("Proponi le stanze")}</button>
          <button data-ed="add-room">+ ${t("Stanza")}</button>
          <button data-ed="tool-rect" class="${this.tool === "rect" ? "on" : ""}">${t("Rettangolo")}</button>
          <button data-ed="tool-polygon" class="${this.tool === "polygon" ? "on" : ""}">${t("Disegna angoli")}</button>
          ${this.draft ? `<button data-ed="finish-polygon">${t("Completa forma")}</button><button data-ed="cancel-polygon">${t("Annulla")}</button>` : ""}
          <button data-ed="text">${t("Testo")}</button>
          <button class="casa-primary ped-save" data-ed="save" ${this.busy ? "disabled" : ""}>${t("Salva piantina")}</button>
        </div>
        <div class="ped-msg ${this.msgBad ? "bad" : ""}" role="status">${esc(this.msg)}</div>
        <div class="ped-body">
          <div class="ped-stage-wrap">
            <div class="ped-stage" style="aspect-ratio:${f.aspect}">
              ${f.image ? `<img src="${this.imageURL(f.image)}" alt="" draggable="false">` : ""}
              ${rooms}
              ${this.draft ? draft : vertices + edges}
            </div>
          </div>
          <aside class="ped-side">
            <label class="ped-field">${t("Nome del piano")}<input data-ed="floor-name" value="${esc(f.name)}" maxlength="60"></label>
            ${side}
            <h4>${t("Fuori casa")}</h4>
            <div class="ped-outside">${this.areas.map((a) => `<label class="ped-check"><input type="checkbox" data-ed="outside" value="${esc(a)}" ${this.outside.includes(a) ? "checked" : ""}> ${esc(a)}</label>`).join("") || `<p class="casa-muted">${t("Nessuna area in Home Assistant.")}</p>`}</div>
            ${unplaced.length ? `<p class="casa-muted">${t("Aree non ancora disegnate (compariranno sotto la piantina)")}: ${unplaced.map(esc).join(", ")}</p>` : ""}
          </aside>
        </div>
      </section>`;
  }

  say(text, bad = false) {
    this.msg = text;
    this.msgBad = bad;
    const m = this.box?.querySelector(".ped-msg");
    if (m) { m.textContent = text; m.classList.toggle("bad", bad); }
  }

  // ------------------------------------------------------------------ actions
  async click(e) {
    if (e.target === this.box) return this.close();
    if (e.target.closest("[data-draft-point]")) {
      if (Number(e.target.closest("[data-draft-point]").dataset.draftPoint) === 0) this.finishPolygon();
      return;
    }
    if (this.tool === "polygon" && e.target.closest(".ped-stage")) {
      const stage = e.target.closest(".ped-stage"), rect = stage.getBoundingClientRect();
      (this.draft ||= []).push({ x: round(clamp((e.clientX - rect.left) / rect.width * 100, 0, 100)), y: round(clamp((e.clientY - rect.top) / rect.height * 100, 0, 100)) });
      this.render();
      return;
    }
    const el = e.target.closest("[data-ed]");
    if (!el) return;
    const f = this.f;
    switch (el.dataset.ed) {
      case "close": return this.close();
      case "floor": this.floor = Number(el.dataset.i); this.sel = null; this.point = null; this.draft = null; break;
      case "add-floor": this.floors.push({ name: `${t("Piano")} ${this.floors.length + 1}`, aspect: 1.4, rooms: [] }); this.floor = this.floors.length - 1; this.sel = null; this.point = null; this.draft = null; break;
      case "add-room": {
        const area = this.areas.find((a) => !this.floors.some((x) => x.rooms.some((q) => q.area === a))) || t("Nuova stanza");
        f.rooms.push({ area, x: 40, y: 40, w: 20, h: 20, outline: false });
        this.sel = f.rooms.length - 1;
        this.point = null;
        break;
      }
      case "delete": f.rooms.splice(this.sel, 1); this.sel = null; this.point = null; break;
      case "unselect": this.sel = null; this.point = null; break;
      case "tool-rect": this.tool = "rect"; this.draft = null; break;
      case "tool-polygon": this.tool = "polygon"; this.sel = null; this.point = null; break;
      case "finish-polygon": return this.finishPolygon();
      case "cancel-polygon": this.draft = null; break;
      case "edit-points": {
        const r = f.rooms[this.sel];
        r.points = corners(r).map((p) => ({ x: round(p.x), y: round(p.y) }));
        this.point = null;
        break;
      }
      case "delete-point": {
        const r = f.rooms[this.sel];
        if (r?.points?.length > 3 && this.point != null) { r.points.splice(this.point, 1); Object.assign(r, boxOf(r.points)); this.point = null; }
        break;
      }
      case "suggest": return this.suggest();
      case "save": return this.save();
      case "text": this.close(); return this.onText();
      default: return;
    }
    this.render();
  }

  finishPolygon() {
    if (!this.draft || this.draft.length < 3) { this.say(t("Servono almeno tre angoli"), true); return; }
    const points = this.draft;
    const box = boxOf(points);
    if (box.w < 2 || box.h < 2 || points.length > 32) { this.say(t("Forma non valida"), true); return; }
    const area = this.areas.find((a) => !this.floors.some((x) => x.rooms.some((q) => q.area === a))) || t("Nuova stanza");
    this.f.rooms.push({ area, ...box, points, outline: false });
    this.sel = this.f.rooms.length - 1;
    this.draft = null;
    this.tool = "rect";
    this.render();
  }

  change(e) {
    const el = e.target, f = this.f, r = this.sel != null ? f.rooms[this.sel] : null;
    switch (el.dataset.ed) {
      case "file": if (el.files[0]) this.upload(el.files[0]); return;
      case "area": if (r) { r.area = el.value || (this.linked(r) ? t("Nuova stanza") : r.area); this.render(); } return;
      case "outline": if (r) r.outline = el.checked; this.render(); return;
      case "outside": this.outside = el.checked ? [...new Set([...this.outside, el.value])] : this.outside.filter((a) => a !== el.value); return;
    }
  }

  input(e) {
    const el = e.target, f = this.f;
    if (el.dataset.ed === "floor-name") {
      f.name = el.value;
      const tab = this.box.querySelector(`.ped-tabs [data-i="${this.floor}"]`);
      if (tab) tab.textContent = el.value;
    } else if (el.dataset.ed === "label" && this.sel != null) {
      f.rooms[this.sel].area = el.value;
      const span = this.box.querySelector(`[data-room="${this.sel}"] span`);
      if (span) span.textContent = el.value;
    }
  }

  async upload(file) {
    this.busy = true;
    this.say(t("Carico la planimetria…"));
    try {
      const res = await this.api(`api/casa/plan-image?floor=${this.floor + 1}`, {
        method: "POST", body: file, headers: { "Content-Type": file.type || "application/octet-stream" },
      });
      const { image, aspect } = await res.json();
      Object.assign(this.f, { image, aspect, v: Date.now() });
      this.busy = false;
      this.render();
      this.say(this.f.rooms.length ? t("Planimetria caricata.") : t("Planimetria caricata: disegna le stanze o premi «Proponi le stanze»."));
    } catch (err) {
      this.busy = false;
      this.render();
      this.say(`${t("Non riesco a caricarla")}: ${detail(err)}`, true);
    }
  }

  async suggest() {
    const f = this.f;
    if (f.rooms.length && !confirm(t("Sostituire le stanze di questo piano con la proposta?"))) return;
    this.busy = true;
    this.render();
    this.say(t("Sto guardando la planimetria… (qualche secondo)"));
    try {
      const { rooms, skipped = 0 } = await (await this.api("api/casa/plan-suggest", { method: "POST", body: JSON.stringify({ image: f.image }) })).json();
      f.rooms = rooms.map(({ linked, ...r }) => r);
      const free = rooms.filter((r) => !r.linked).length;
      this.busy = false;
      this.sel = null;
      this.point = null;
      this.render();
      this.say(free ? t("Proposte {n} stanze. Controllale: {free} senza area di Home Assistant (bordo arancione), sposta o ridimensiona dove serve, poi salva.", { n: rooms.length, free }) : t("Proposte {n} stanze. Controllale: sposta o ridimensiona dove serve, poi salva.", { n: rooms.length }));
      if (skipped) this.say(`${t("Proposte {n} stanze. Controllale: sposta o ridimensiona dove serve, poi salva.", { n: rooms.length })} ${t("Forme non valide ignorate: {n}.", { n: skipped })}`);
    } catch (err) {
      this.busy = false;
      this.render();
      this.say(`${t("Proposta non riuscita")}: ${detail(err)}`, true);
    }
  }

  async save() {
    if (this.draft) { this.say(t("Completa o annulla prima la forma"), true); return; }
    const floors = this.floors.map(({ v, ...f }) => ({ ...f, name: (f.name || "").trim() || t("Piano"), rooms: f.rooms.filter((r) => (r.area || "").trim()) }));
    this.busy = true;
    this.say(t("Salvo…"));
    try {
      await this.api("api/casa/plan", { method: "POST", body: JSON.stringify({ floors, outside: this.outside, energy: this.energy }) });
      this.close();
      this.onSaved();
    } catch (err) {
      this.busy = false;
      this.say(`${t("Non salvata")}: ${detail(err)}`, true);
    }
  }

  // ------------------------------------------------------------------ dragging (mouse and touch)
  down(e) {
    if (!e.target.closest(".ped-stage") || e.button > 0) return;
    if (this.tool === "polygon" || e.target.closest("[data-draft-point]")) return;
    const rect = e.target.closest(".ped-stage").getBoundingClientRect();
    const pt = (ev) => ({ x: clamp(((ev.clientX - rect.left) / rect.width) * 100, 0, 100), y: clamp(((ev.clientY - rect.top) / rect.height) * 100, 0, 100) });
    const start = pt(e);
    const f = this.f;
    const handle = e.target.closest("[data-handle]");
    const roomEl = e.target.closest("[data-room]");
    const vertex = e.target.closest("[data-point]");
    const edge = e.target.closest("[data-edge]");
    let mode, i, orig;
    if (handle) { mode = "resize"; i = Number(handle.dataset.handle); }
    else if (vertex || edge) { mode = "vertex"; i = this.sel; }
    else if (roomEl) { mode = "move"; i = Number(roomEl.dataset.room); }
    else { mode = "draw"; }
    if (mode === "vertex") {
      const r = f.rooms[i];
      if (edge && r.points.length < 32) {
        this.point = Number(edge.dataset.edge) + 1;
        const a = r.points[this.point - 1], b = r.points[this.point % r.points.length];
        r.points.splice(this.point, 0, { x: round((a.x + b.x) / 2), y: round((a.y + b.y) / 2) });
      } else if (vertex) this.point = Number(vertex.dataset.point);
      this.render();
    }
    if (mode === "draw") {
      f.rooms.push({ area: t("Nuova stanza"), x: start.x, y: start.y, w: 0, h: 0, outline: false });
      i = f.rooms.length - 1;
      this.sel = i;
      this.point = null;
      this.render();
    } else if (this.sel !== i) {
      this.sel = i;
      this.point = null;
      this.render();
    }
    // render() may have rebuilt the drawing: follow the pointer on the window, not on an element.
    orig = { ...f.rooms[i], points: f.rooms[i].points?.map((p) => ({ ...p })) };
    e.preventDefault();
    const move = (ev) => {
      const p = pt(ev), r = f.rooms[i];
      if (mode === "move") {
        r.x = round(clamp(orig.x + p.x - start.x, 0, 100 - r.w));
        r.y = round(clamp(orig.y + p.y - start.y, 0, 100 - r.h));
        if (r.points) r.points = orig.points.map((q) => ({ x: round(q.x + r.x - orig.x), y: round(q.y + r.y - orig.y) }));
      } else if (mode === "vertex") {
        r.points[this.point] = { x: round(p.x), y: round(p.y) };
        Object.assign(r, boxOf(r.points));
      } else if (mode === "resize") {
        r.w = round(clamp(orig.w + p.x - start.x, 2, 100 - r.x));
        r.h = round(clamp(orig.h + p.y - start.y, 2, 100 - r.y));
      } else {
        r.x = round(Math.min(start.x, p.x)); r.y = round(Math.min(start.y, p.y));
        r.w = round(Math.abs(p.x - start.x)); r.h = round(Math.abs(p.y - start.y));
      }
      const el = this.box.querySelector(`[data-room="${i}"]`);
      Object.assign(el.style, { left: `${r.x}%`, top: `${r.y}%`, width: `${r.w}%`, height: `${r.h}%` });
      if (r.points && r.w && r.h) {
        el.style.clipPath = `polygon(${localPoints(r).map((q) => `${q.x}% ${q.y}%`).join(",")})`;
        el.querySelector("polygon").setAttribute("points", localPoints(r).map((q) => `${q.x},${q.y}`).join(" "));
        this.box.querySelectorAll("[data-point]").forEach((node) => { const q = r.points[Number(node.dataset.point)]; node.style.left = `${q.x}%`; node.style.top = `${q.y}%`; });
        this.box.querySelectorAll("[data-edge]").forEach((node) => { const j = Number(node.dataset.edge), a = r.points[j], b = r.points[(j + 1) % r.points.length]; node.style.left = `${(a.x + b.x) / 2}%`; node.style.top = `${(a.y + b.y) / 2}%`; });
      }
    };
    const up = () => {
      removeEventListener("pointermove", move);
      removeEventListener("pointerup", up);
      removeEventListener("pointercancel", up);
      const r = f.rooms[i];
      if (mode === "draw") {
        if (r.w < 2 || r.h < 2) { f.rooms.splice(i, 1); this.sel = null; }
        else {
          // A new room gets the first area of Home Assistant not drawn yet.
          const area = this.areas.find((a) => !this.floors.some((x) => x.rooms.some((q) => q.area === a)));
          if (area) r.area = area;
        }
      }
      this.render();
    };
    addEventListener("pointermove", move);
    addEventListener("pointerup", up);
    addEventListener("pointercancel", up);
  }
}

function detail(err) {
  try { return JSON.parse(err.message).detail || err.message; } catch { return err.message || String(err); }
}
