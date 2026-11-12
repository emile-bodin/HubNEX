// Legacy Italian keys map to the English text shown throughout the dashboard.
import { EN } from "./i18n-en.js";

export const LANG = "en";
export const LOCALE = "en-GB";
document.documentElement.lang = LANG;

export function t(text, vars) {
  let out = EN[text] ?? text;
  if (EN[text] === undefined) (window.__i18nMissing ||= new Set()).add(text);
  if (vars) out = out.replace(/\{(\w+)\}/g, (m, k) => (vars[k] ?? m));
  return out;
}

// Static texts of index.html: data-i18n (the element's text) and data-i18n-attr="placeholder,title".
export function translatePage(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => {
    // Only the element's own text, before any child element (e.g. <small> or <button>).
    const node = [...el.childNodes].find((n) => n.nodeType === 3 && n.textContent.trim());
    if (node) node.textContent = node.textContent.replace(node.textContent.trim(), t(node.textContent.trim()));
  });
  root.querySelectorAll("[data-i18n-attr]").forEach((el) => {
    for (const a of el.dataset.i18nAttr.split(",")) if (el.getAttribute(a)) el.setAttribute(a, t(el.getAttribute(a)));
  });
}

export const num = (v, d = 1) => Number(v).toLocaleString(LOCALE, { maximumFractionDigits: d });
