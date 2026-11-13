// Every Italian text of the dashboard (t("…") and data-i18n) has its English and Dutch.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const path = require("node:path");

test("il dizionario inglese è completo", () => {
  const out = execFileSync(process.env.PYTHON || "python3", ["dev/i18n_keys.py", "--missing"], { cwd: path.resolve(__dirname, "../..") });
  assert.deepEqual(JSON.parse(out), [], "testi senza traduzione inglese (aggiungili in web/i18n-en.js)");
});

test("il dizionario olandese è completo", () => {
  const out = execFileSync(process.env.PYTHON || "python3", ["dev/i18n_keys.py", "--missing", "--lang", "nl"], { cwd: path.resolve(__dirname, "../..") });
  assert.deepEqual(JSON.parse(out), [], "testi senza traduzione olandese (aggiungili in web/i18n-nl.js)");
});
