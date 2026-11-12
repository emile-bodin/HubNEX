// Claude spend popup: per day, per agent, per model, this month against the budget.
// Opened from the "Spesa/Credito Claude" tile in HQ. The figures are HubNEX's own estimate
// (list prices × tokens of every call): the exact bill is on console.anthropic.com.
import { t, LOCALE } from "./i18n.js";

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const money = (v) => {
  if (v == null) return "—";
  if (v > 0 && v < 0.01) return "<$0.01";
  return "$" + Number(v).toLocaleString(LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};
const tokens = (n) => (n >= 1e6 ? (n / 1e6).toFixed(1) + "M" : n >= 1e3 ? Math.round(n / 1e3) + "k" : String(n));
const dayLabel = (d, opts = { day: "numeric", month: "short" }) => new Date(d + "T12:00").toLocaleDateString(LOCALE, opts);
const SPANS = [7, 30, 90];

export class CostsView {
  constructor(api) {
    this.api = api;
    this.days = 30;
    this.data = null;
    this.el = null;
    addEventListener("keydown", (e) => { if (e.key === "Escape" && this.el) { e.stopImmediatePropagation(); this.close(); } }, true);
  }

  async open() {
    if (!this.el) {
      this.el = document.createElement("div");
      this.el.className = "casa-modal costs-modal";
      this.el.setAttribute("role", "dialog");
      this.el.setAttribute("aria-label", t("Spesa Claude"));
      this.el.addEventListener("click", (e) => this.onClick(e));
      document.body.appendChild(this.el);
      document.body.classList.add("casa-modal-open");
    }
    this.render();
    await this.load();
  }

  close() {
    this.el?.remove();
    this.el = null;
    if (!document.querySelector(".casa-modal")) document.body.classList.remove("casa-modal-open");
  }

  async load() {
    try {
      this.data = await (await this.api(`/api/costs?days=${this.days}`)).json();
      this.error = null;
    } catch (e) {
      this.error = String(e.message || e);
    }
    this.render();
  }

  onClick(e) {
    if (e.target === this.el || e.target.closest("[data-costs-close]")) return this.close();
    const span = e.target.closest("[data-span]");
    if (span) { this.days = Number(span.dataset.span); this.load(); }
  }

  render() {
    if (!this.el) return;
    const d = this.data;
    const spans = SPANS.map((n) => `<button class="costs-span ${n === this.days ? "on" : ""}" data-span="${n}" aria-pressed="${n === this.days}">${t("{n} giorni", { n })}</button>`).join("");
    let body;
    if (this.error) body = `<p class="costs-note">${esc(this.error)}</p>`;
    else if (!d) body = `<p class="costs-note">${t("Carico…")}</p>`;
    else body = this.summaryHTML(d) + this.chartHTML(d) + this.breakdownHTML(t("Per agente"), d.by_agent, d.period) + this.breakdownHTML(t("Per modello"), d.by_model, d.period)
      + `<p class="costs-note">${t("Stima delle chiamate API. Le richieste tramite abbonamento Claude Code non hanno un costo API.")}</p>`;
    this.el.innerHTML = `<section class="panel casa-panel costs">
      <h3>${t("Spesa Claude")}<span class="costs-head"><span class="costs-spans">${spans}</span>
        <button class="casa-x" data-costs-close aria-label="${t("Chiudi")}">×</button></span></h3>
      ${body}
    </section>`;
  }

  summaryHTML(d) {
    const m = d.month;
    const cells = [
      [t("Oggi"), money(d.today)],
      [t("Questo mese"), money(m.spent)],
      [t("Stima a fine mese"), m.forecast == null ? "—" : money(m.forecast)],
      [t("Ultimi {n} giorni", { n: this.days }), money(d.period)],
    ];
    let budget = "";
    if (m.budget) {
      const used = m.spent / m.budget;
      const proj = m.forecast == null ? used : m.forecast / m.budget;
      const cls = used >= 1 ? "over" : used >= 0.8 ? "near" : "";
      budget = `<div class="costs-budget ${cls}">
        <div class="costs-budget-l"><span>${t("Budget del mese")}</span><span class="hc-num">${money(m.spent)} <small>/ ${money(m.budget)}</small></span></div>
        <div class="costs-track" role="img" aria-label="${t("{p}% del budget", { p: Math.round(used * 100) })}">
          <i class="proj" style="width:${Math.min(proj, 1) * 100}%"></i><i class="done" style="width:${Math.min(used, 1) * 100}%"></i><b style="left:80%"></b>
        </div>
        <small>${proj > 1 && used < 1 ? t("Di questo passo lo superi prima di fine mese") : used >= 1 ? t("Budget superato") : t("{p}% usato", { p: Math.round(used * 100) })}</small>
      </div>`;
    }
    return `<div class="costs-sum">${cells.map(([l, v]) => `<div><small>${l}</small><span class="hc-num">${v}</span></div>`).join("")}</div>${budget}`;
  }

  chartHTML(d) {
    const max = Math.max(...d.days.map((p) => p.cost), 0);
    if (!max) return `<div class="costs-chart empty">${t("Nessuna spesa in questo periodo")}</div>`;
    const today = d.days[d.days.length - 1].day;
    const bars = d.days.map((p) => {
      const h = p.cost ? Math.max(2, (p.cost / max) * 100) : 0;
      const tip = `${dayLabel(p.day, { weekday: "short", day: "numeric", month: "short" })} · ${money(p.cost)} · ${t("{n} chiamate", { n: p.calls })}`;
      return `<div class="costs-bar ${p.day === today ? "today" : ""}" title="${esc(tip)}"><i style="height:${h}%"></i></div>`;
    }).join("");
    return `<div class="costs-chart" role="img" aria-label="${t("Spesa per giorno")}">
      <span class="costs-max">${money(max)}</span>
      <div class="costs-bars ${d.days.length > 45 ? "dense" : ""}">${bars}</div>
      <div class="costs-axis"><span>${dayLabel(d.days[0].day)}</span><span>${t("oggi")}</span></div>
    </div>`;
  }

  breakdownHTML(title, rows, total) {
    if (!rows.length) return "";
    const top = rows[0].cost || 1;
    return `<div class="costs-block"><h4>${title}</h4>${rows.map((r) => `
      <div class="costs-row" title="${esc(t("{a} token in ingresso, {b} in uscita", { a: tokens(r.tokens_in), b: tokens(r.tokens_out) }))}">
        <span class="costs-name">${esc(r.name)}</span>
        <span class="costs-rbar"><i style="width:${(r.cost / top) * 100}%"></i></span>
        <span class="hc-num">${money(r.cost)}</span>
        <span class="costs-pct">${total ? Math.round((r.cost / total) * 100) : 0}%</span>
        <span class="costs-calls">${t("{n} chiamate", { n: r.calls })}</span>
      </div>`).join("")}</div>`;
  }
}
