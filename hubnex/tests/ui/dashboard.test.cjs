// Browser tests of the dashboard, against dev/demo.py (pretend Home Assistant and Claude).
// Run from the add-on folder:  node --test tests/ui/
const { test, before, after } = require("node:test");
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const path = require("node:path");
const { chromium } = require("playwright");

const PORT = 18000 + Math.floor(Math.random() * 1000);
const URL = `http://127.0.0.1:${PORT}/`;
let server, browser;

async function waitForServer() {
  for (let i = 0; i < 250; i++) {
    try { if ((await fetch(URL)).ok) return; } catch {}
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error("la demo non parte");
}

before(async () => {
  server = spawn(process.env.PYTHON || "python3", ["dev/demo.py", String(PORT)], {
    cwd: path.resolve(__dirname, "../.."), stdio: ["ignore", "inherit", "inherit"],
  });
  await waitForServer();
  browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
});

after(async () => {
  await browser?.close();
  server?.kill("SIGKILL"); // no graceful shutdown needed: it is a throwaway demo
});

// A page that fails the test on any JavaScript error.
async function open(viewport = { width: 1440, height: 900 }, lang = "it") {
  const page = await browser.newPage({ viewport });
  await page.addInitScript((l) => localStorage.setItem("hq_lang", l), lang);
  page.errors = [];
  page.on("pageerror", (e) => page.errors.push(e.message));
  await page.goto(URL);
  await page.waitForSelector("#view-casa");
  return page;
}

async function casa(page) {
  await page.click("#view-casa");
  await page.waitForSelector(".plan-room[data-area='soggiorno']");
}

async function done(page) {
  assert.deepEqual(page.errors, [], "errori JavaScript nella pagina");
  await page.close();
}

test("vista Casa: piantina, scheda della stanza, pagina della stanza", { timeout: 30000 }, async () => {
  const page = await open();
  await casa(page);
  assert.equal(await page.locator(".plan-room").count(), 7, "le stanze della piantina");
  assert.match(await page.textContent("#casa"), /Giardino/, "le aree fuori casa sotto la piantina");
  await page.click(".plan-room[data-area='cucina']");
  await page.waitForSelector(".casa-quick");
  assert.match(await page.textContent(".casa-quick"), /Cucina/);
  await page.click(".casa-quick [data-act='open']");
  await page.waitForSelector(".casa-room");
  assert.match(await page.textContent(".casa-room"), /Soffitto cucina/);
  await page.click("[data-act='home']");
  await page.waitForSelector(".plan-room[data-area='cucina']");
  await done(page);
});

test("comando dalla scheda: la luce cambia stato", { timeout: 30000 }, async () => {
  const page = await open();
  await casa(page);
  await page.click(".plan-room[data-area='soggiorno']");
  const card = page.locator(".casa-quick [data-act='toggle'][data-e='light.striscia']").first();
  await card.waitFor();
  const before = await card.textContent();
  await card.click();
  await page.waitForFunction(
    (b) => document.querySelector(".casa-quick [data-act='toggle'][data-e='light.striscia']")?.textContent !== b, before,
  );
  await done(page);
});

test("popup Energia: si apre, resta dov'è con gli aggiornamenti dal vivo, si chiude", { timeout: 30000 }, async () => {
  const page = await open();
  await casa(page);
  await page.click("[data-act='energy']");
  const panel = page.locator(".casa-energy-modal .panel");
  await panel.waitFor();
  // the day's chart arrives a moment after the popup: wait until its height stops changing
  let last = -1;
  for (let i = 0; i < 20; i++) {
    const h = await panel.evaluate((el) => el.scrollHeight);
    if (h === last) break;
    last = h;
    await page.waitForTimeout(300);
  }
  // halfway down: a few pixels more or less at the bottom don't move it
  await panel.evaluate((el) => { el.scrollTop = Math.round((el.scrollHeight - el.clientHeight) / 2); });
  const scrolled = await panel.evaluate((el) => el.scrollTop);
  assert.ok(scrolled > 50, "il popup scorre");
  // something changes in the house while the popup is open
  await page.evaluate(() => fetch("api/casa/call", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ domain: "light", service: "toggle", data: { entity_id: "light.cucina" } }) }));
  await page.waitForTimeout(1200);
  assert.equal(await panel.evaluate((el) => el.scrollTop), scrolled, "lo scorrimento del popup non torna in alto");
  await page.keyboard.press("Escape");
  await page.waitForSelector(".casa-energy-modal", { state: "detached" });
  await done(page);
});

test("editor delle card: si apre e si chiude", { timeout: 30000 }, async () => {
  const page = await open();
  await casa(page);
  await page.click(".plan-room[data-area='soggiorno']");
  await page.click(".casa-quick [data-act='open']");
  await page.click("[data-act='edit']");
  await page.click("[data-act='card-new']");
  await page.waitForSelector(".hc-cardedit");
  await page.click("[data-act='card-close']");
  await page.waitForSelector(".hc-cardedit", { state: "detached" });
  await done(page);
});

test("chat: Home Assistant da solo, poi la via rapida", { timeout: 30000 }, async () => {
  const page = await open();
  await page.fill("#chat-input", "accendi la lampada da terra");
  await page.keyboard.press("Enter");
  // the answer is written letter by letter: wait for the whole of it
  await page.waitForFunction(() => {
    const m = document.querySelector(".msg.jarvis");
    return m?.dataset.by === "ha" && /Lampada da terra: accesa/.test(m.textContent);
  });
  await page.fill("#chat-input", "abbassa un po' la tapparella");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelectorAll(".msg.jarvis[data-by='quick']").length === 1);
  await done(page);
});

test("chat: la richiesta va a capo e il campo cresce; Invio invia", { timeout: 30000 }, async () => {
  const page = await open();
  const box = page.locator("#chat-input");
  const h0 = (await box.boundingBox()).height;
  // typed in one go (letter by letter is slow with the 3D scene on a machine without a GPU)
  await box.fill("Riassumimi le email di oggi del cliente Rossi e dimmi quali scadenze ci sono questa settimana, poi prepara una bozza");
  await box.press("End");
  await page.keyboard.press("Shift+Enter");
  await page.keyboard.insertText("con tono cordiale.");
  const h1 = (await box.boundingBox()).height;
  assert.ok(h1 > h0 * 1.8, `il campo cresce (${h0} → ${h1})`);
  assert.match(await box.inputValue(), /bozza\ncon tono/, "Shift+Invio va a capo");
  await page.keyboard.press("Enter");
  await page.waitForSelector(".msg.me");
  assert.equal(await box.inputValue(), "", "Invio invia e svuota");
  assert.ok((await box.boundingBox()).height < h0 + 2, "il campo torna a una riga");
  await done(page);
});

test("luci: la card resta semplice, colore e temperatura nel popup", { timeout: 30000 }, async () => {
  const page = await open();
  await casa(page);
  await page.click(".plan-room[data-area='soggiorno']");
  await page.click(".casa-quick [data-act='open']");
  await page.waitForSelector(".casa-room");
  assert.equal(await page.locator(".casa-room [data-act='ktemp'], .casa-room [data-act='lcolor']").count(), 0, "niente controlli in più sulla card");
  assert.equal(await page.locator("[data-act='tone'][data-e='light.faretti_tv']").count(), 0, "solo luminosità: niente pallino");
  // the LED strip (colour only, off): the popup has colours and no temperature
  await page.click("[data-act='tone'][data-e='light.striscia']");
  await page.waitForSelector(".hc-tonebox");
  assert.equal(await page.locator(".hc-tonebox [data-act='ktemp']").count(), 0);
  await page.click(".hc-tonebox [data-act='lcolor'][data-rgb='10,90,255']");
  await page.waitForFunction(() => document.querySelector(".hc-light[data-e='light.striscia']")?.classList.contains("on"));
  await page.keyboard.press("Escape");
  await page.waitForSelector(".hc-tonebox", { state: "detached" });
  // the floor lamp: temperature in the popup
  await page.click("[data-act='tone'][data-e='light.lampada_terra']");
  await page.locator(".hc-tonebox [data-act='ktemp']").evaluate((el) => {
    el.value = 5000;
    el.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await page.click("[data-act='tone-close']");
  await page.waitForFunction(() => /5000 K/.test(document.querySelector(".hc-light[data-e='light.lampada_terra']").textContent));
  await done(page);
});

test("vista Casa: meteo, oggi, icone sulla piantina, elettrodomestici, ultimi eventi", { timeout: 30000 }, async () => {
  const page = await open();
  await casa(page);
  // the weather in the HUD, the forecast in a popup
  await page.waitForFunction(() => /9°\/17°/.test(document.querySelector(".hud-wx")?.textContent || ""));
  await page.click("[data-act='weather']");
  await page.waitForSelector(".casa-wx-modal");
  assert.equal(await page.locator(".wx-day").count(), 6, "sei giorni di previsioni");
  assert.match(await page.textContent(".wx-day >> nth=1"), /Tomorrow.*Rain · 80%/s, "niente «pioggia» ripetuto");
  await page.keyboard.press("Escape");
  await page.waitForSelector(".casa-wx-modal", { state: "detached" });
  // today: the owner's deadlines, the late one first
  const today = page.locator(".hc-today");
  assert.equal(await today.count(), 4, "al massimo quattro, entro sette giorni");
  assert.match(await today.first().textContent(), /overdue/i);
  // what's going on in the rooms
  assert.equal(await page.locator(".plan-pin[data-area='soggiorno'] .plan-icons .pi").count(), 2, "presenza e musica");
  assert.equal(await page.locator(".plan-pin[data-area='lavanderia'] .plan-icons .pi").count(), 1, "la lavatrice in funzione");
  assert.equal(await page.locator(".plan-pin[data-area='cucina'] .plan-icons .pi").count(), 1, "il bollitore non ha icona");
  // appliances and recent events
  const appl = await page.textContent(".casa-right");
  assert.match(appl, /Lavatrice.*running/s);
  assert.match(appl, /Lavastoviglie.*finished \d+ min ago/s);
  assert.match(await page.textContent(".casa-left"), /Recent events.*Porta ingresso.*locked.*min ago/s);
  // ticking a deadline off
  await today.first().locator("[data-act='ddone']").click();
  await page.waitForFunction(() => document.querySelectorAll(".hc-today").length === 3 && !/Invio verbale/.test(document.querySelector(".casa-right").textContent));
  await done(page);
});

test("card libera: si costruisce a blocchi e funziona", { timeout: 40000 }, async () => {
  const page = await open();
  await casa(page);
  await page.locator(".plan-room[data-area='soggiorno']").click();
  await page.click(".casa-quick [data-act='open']");
  await page.click("[data-act='edit']");
  await page.click("[data-act='card-free']");
  await page.fill("#fb-name", "Prova libera");
  await page.click("[data-act='fb-color'][data-c='green']");
  // an interruttore: only switches and lights are offered
  await page.click("[data-act='fb-add'][data-k='toggle']");
  await page.fill("#fb-find", "presa tv");
  await page.waitForSelector("[data-act='fb-pick'][data-e='switch.presa_tv']");
  assert.equal(await page.locator("#fb-cands [data-e='sensor.temp_cucina']").count(), 0, "un sensore non è un interruttore");
  await page.click("[data-act='fb-pick'][data-e='switch.presa_tv']");
  // a big value, 2×2, with its own label
  await page.click("[data-act='fb-add'][data-k='value']");
  await page.fill("#fb-find", "clima");
  await page.click("[data-act='fb-pick'][data-e='climate.soggiorno']");
  await page.click("[data-act='fb-size'][data-w='2'][data-h='2']");
  await page.fill("#fb-label", "Qui");
  assert.match(await page.textContent("#fb-preview"), /QUI|Qui/);
  // a block without its entity can't be saved
  await page.click("[data-act='fb-add'][data-k='state']");
  await page.click("[data-act='fb-save']");
  await page.waitForSelector(".casa-toast");
  await page.click("[data-act='fb-del']");
  await page.click("[data-act='fb-save']");
  await page.waitForSelector(".fe-panel", { state: "detached" });
  const card = page.locator(".hc-free:has-text('Prova libera')");
  await card.waitFor();
  assert.ok(await card.evaluate((el) => el.classList.contains("fc-green") && el.classList.contains("flat")), "verde e pulita, lo stile di partenza");
  assert.equal(await card.locator(".fb").count(), 2);
  assert.equal(await card.locator(".fb[data-w='2'][data-h='2']").count(), 1, "il valore grande 2×2");
  // its switch works from the card
  await card.locator(".casa-switch").click();
  await page.waitForFunction(() => /off/.test(document.querySelector(".hc-free .k-toggle")?.textContent || ""));
  // and it opens again in the editor
  await card.locator("[data-act='card-edit']").click();
  await page.waitForSelector(".fe-panel");
  assert.equal(await page.inputValue("#fb-name"), "Prova libera");
  await page.click("[data-act='fb-close']");
  await done(page);
});

test("card libera: modello, colore secondo il valore, mostra solo se, domanda a Jarvis", { timeout: 40000 }, async () => {
  const page = await open();
  await casa(page);
  await page.locator(".plan-room[data-area='soggiorno']").click();
  await page.click(".casa-quick [data-act='open']");
  await page.click("[data-act='edit']");
  await page.click("[data-act='card-free']");
  await page.click("[data-act='fb-tpl'][data-t='stufa']");
  assert.ok(await page.locator(".fe-prev .fb").count() >= 3, "il modello ha messo i blocchi della stanza");
  assert.equal(await page.inputValue("#fb-name"), "Stove");
  // above 21 the temperature turns red
  await page.click(".fe-prev .k-value");
  await page.click("[data-act='fb-rule-add']");
  await page.selectOption("[data-fb='rules.0.op']", ">");
  await page.fill("[data-fb='rules.0.v']", "21");
  await page.selectOption("[data-fb='rules.0.c']", "red");
  assert.equal(await page.locator(".fe-prev .k-value.tone-red").count(), 1);
  // a block shown only while the kitchen speaker is off: hidden now, dimmed in the editor
  await page.click("[data-act='fb-add'][data-k='media']");
  await page.fill("#fb-find", "altoparlante");
  await page.click("[data-act='fb-pick'][data-e='media_player.cucina']");
  await page.click("[data-act='fb-show-add']");
  await page.click("[data-act='fb-pick'][data-e='media_player.cucina']");
  await page.selectOption("[data-fb='show.v']", "off");
  assert.equal(await page.locator(".fe-prev .k-media.hid").count(), 1);
  await page.click("[data-act='fb-add'][data-k='ask']");
  await page.fill("#fb-label", "Quanto pellet mi resta?");
  await page.click("[data-act='fb-save']");
  await page.waitForSelector(".fe-panel", { state: "detached" });
  const card = page.locator(".hc-free:has-text('Stove')");
  await card.waitFor();
  assert.equal(await card.locator(".k-media").count(), 0, "nascosto: l'altoparlante sta suonando");
  assert.equal(await card.locator(".k-value.tone-red").count(), 1);
  await card.locator(".fb-ask").click();
  await page.waitForFunction(() => /Quanto pellet mi resta\?/.test(document.querySelector("#chat-log")?.textContent || ""));
  // the card goes away: its entities (the pellet) belong to the room again for the next tests
  await page.evaluate(async () => {
    const view = await (await fetch("api/casa")).json();
    for (const c of view.areas.find((a) => a.id === "soggiorno").cards.filter((c) => c.kind === "free")) {
      await fetch(`api/casa/rooms/soggiorno/cards/${c.id}/remove`, { method: "POST" });
    }
  });
  await done(page);
});

test("card libera: Jarvis la compone, si esporta e si importa, valori da un elenco", { timeout: 40000 }, async () => {
  const page = await open();
  await casa(page);
  await page.locator(".plan-room[data-area='soggiorno']").click();
  await page.click(".casa-quick [data-act='open']");
  await page.click("[data-act='edit']");
  await page.click("[data-act='card-free']");
  await page.fill("#fb-draft-text", "la stufa con tutto");
  await page.click("[data-act='fb-draft']");
  await page.waitForFunction(() => document.querySelectorAll(".fe-prev .fb").length >= 6, null, { timeout: 15000 });
  assert.equal(await page.inputValue("#fb-name"), "Stufa");
  assert.match(await page.textContent(".casa-toast"), /left out/, "l'entità inventata è stata tolta");
  // a condition chosen from a translated list
  await page.click(".fe-prev .k-select");
  await page.click("[data-act='fb-show-add']");
  await page.fill("#fb-find", "automatica");
  await page.click("[data-act='fb-pick'][data-e='input_boolean.stufa_automatica']");
  const opts = await page.locator("select[data-fb='show.v'] option").allTextContents();
  assert.ok(opts.includes("on") && opts.includes("off"), opts.join(","));
  // export, then import it with an entity this house doesn't have
  await page.click("[data-act='fb-export']");
  const text = await page.inputValue(".fe-export");
  assert.equal(JSON.parse(text).hubnex_card, 1);
  await page.click("[data-act='fb-close']");
  await page.click("[data-act='card-import']");
  await page.fill("#fb-paste", text.replace("input_select.stufa_modo", "input_select.altra_casa"));
  await page.click("[data-act='fb-import']");
  await page.waitForFunction(() => /choose it yourself/.test(document.querySelector(".casa-toast")?.textContent || ""));
  assert.equal(await page.locator(".fe-prev .fb.sel").count(), 1, "il blocco senza entità è già selezionato");
  await page.click("[data-act='fb-close']");
  await done(page);
});

test("le card si accendono in alto: arancione se qualcosa è acceso, rosso per un allarme", { timeout: 30000 }, async () => {
  const page = await open();
  await casa(page);
  await page.evaluate(async () => {
    const post = (body) => fetch("api/casa/rooms/camera_da_letto/cards", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    await post({ name: "Finestra", kind: "free", style: "flat", blocks: [{ kind: "state", entity: "binary_sensor.finestra_camera", w: 2, h: 1 }] });
    await post({ name: "Lampada", kind: "free", style: "flat", blocks: [{ kind: "state", entity: "light.lampada_terra", w: 2, h: 1 }] });
  });
  await page.locator(".plan-room[data-area='camera_da_letto']").click();
  await page.click(".casa-quick [data-act='open']");
  await page.waitForSelector(".hc-free:has-text('Lampada')");
  assert.equal(await page.locator(".hc-free.alert:has-text('Finestra')").count(), 1, "la finestra aperta: linea rossa");
  assert.equal(await page.locator(".hc-free.on:has-text('Lampada')").count(), 1, "la lampada accesa: linea arancione");
  await page.evaluate(async () => {
    const view = await (await fetch("api/casa")).json();
    for (const c of view.areas.find((a) => a.id === "camera_da_letto").cards) await fetch(`api/casa/rooms/camera_da_letto/cards/${c.id}/remove`, { method: "POST" });
  });
  await done(page);
});

test("card scorta: pellet con giorni rimasti, −1 caricato, consegna e soglia", { timeout: 30000 }, async () => {
  const page = await open();
  await casa(page);
  await page.locator(".plan-room[data-area='soggiorno']").click();
  await page.click(".casa-quick [data-act='open']");
  const card = page.locator(".hc-stock");
  await card.waitFor();
  await page.waitForFunction(() => /about \d+ days/.test(document.querySelector(".hc-stock")?.textContent || ""));
  assert.match(await card.textContent(), /7\s*sacchi.*a day.*last delivery/s);
  for (let i = 0; i < 2; i++) { await card.locator("[data-act='stock-use']").click(); await page.waitForTimeout(250); }
  await page.waitForFunction(() => document.querySelector(".hc-stock.low") && /5\s*sacchi/.test(document.querySelector(".hc-stock").textContent));
  assert.match(await page.textContent(".hc-stock"), /To order/i);
  await page.locator(".hc-stock [data-act='stock-add']").click();
  await page.waitForFunction(() => /20\s*sacchi/.test(document.querySelector(".hc-stock")?.textContent || "") && !document.querySelector(".hc-stock.low"));
  // the owner's numbers: a delivery of 10, warn below 25
  await page.click(".hc-stock [data-act='stock-cfg']");
  await page.fill(".hc-stock [name=delivery]", "10");
  await page.fill(".hc-stock [name=low]", "25");
  await page.click(".hc-stock [data-act='stock-save']");
  await page.waitForFunction(() => /\+10/.test(document.querySelector(".hc-stock [data-act='stock-add']")?.textContent || "") && document.querySelector(".hc-stock.low"));
  await done(page);
});

test("card: robot con mappa, telecamera composta live con i sensori, media completo", { timeout: 30000 }, async () => {
  const page = await open();
  await casa(page);
  // the robot: state, battery, map and commands
  await page.locator("[data-area='corridoio']").first().click();
  await page.click(".casa-quick [data-act='open']");
  await page.waitForSelector(".hc-vacuum");
  assert.match(await page.textContent(".hc-vacuum"), /cleaning/);
  assert.equal(await page.locator(".hc-vacuum .hc-vmap img[data-cam='image.robot_mappa']").count(), 1, "la mappa");
  assert.equal(await page.locator(".hc-vacuum [data-act='vac'][data-s='pause']").count(), 1, "pausa mentre pulisce");
  await page.click("[data-act='home']");
  // the entrance camera: live picture, the vehicle sensor lit over it
  await page.locator("[data-area='giardino']").first().click();
  await page.click(".casa-quick [data-act='open']");
  await page.waitForSelector(".hc-camcomp");
  assert.equal(await page.locator(".hc-camcomp .hc-chip.on").count(), 1, "il veicolo in movimento");
  // while the stream starts (2 s in the demo) the still frame stays: never a black thumbnail
  for (let i = 0; i < 8; i++) {
    const blank = await page.evaluate(() => [...document.querySelectorAll("#casa img[data-cam]")]
      .filter((i) => i.src.includes("/stream") && !i.naturalWidth).length);
    assert.equal(blank, 0, "una miniatura nera in attesa del video");
    await page.waitForTimeout(250);
  }
  await page.waitForSelector(".hc-camcomp img[data-live]");
  await page.waitForFunction(() => document.querySelector(".hc-camcomp img[data-live]")?.naturalWidth > 0);
  const t0 = Date.now();
  await page.click(".hc-camcomp .casa-cam");
  await page.waitForFunction(() => /LIVE/.test(document.querySelector(".cam-mode")?.textContent || ""));
  assert.ok(Date.now() - t0 < 1500, `la vista grande è live subito (${Date.now() - t0} ms)`);
  assert.equal(await page.locator(".casa-overlay img.cam-live").count(), 1, "il flusso della miniatura, spostato");
  assert.equal(await page.locator("#casa img[data-live]").count(), 0, "la miniatura chiude il suo flusso");
  await page.click(".casa-overlay .casa-x");
  await page.waitForSelector(".hc-camcomp img[data-live]");
  await page.click("[data-act='home']");
  // the kitchen speaker: shuffle, repeat, source
  await page.locator("[data-area='cucina']").first().click();
  await page.click(".casa-quick [data-act='open']");
  await page.waitForSelector(".hc-media-on");
  for (const sel of ["[data-act='mshuffle']", "[data-act='mrepeat']", "[data-act='msrc']", "[data-act='mmute']"])
    assert.equal(await page.locator(`.hc-media-on ${sel}`).count(), 1, sel);
  await done(page);
});

// Inside Home Assistant (a page that plays its part around the dashboard): the thumbnails play
// its own video (HLS, a short clip in tests/ui/hls), and the big view takes it over in HD.
test("telecamere dentro Home Assistant: miniature col suo video, vista grande subito in HD", { timeout: 40000 }, async () => {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.errors = [];
  page.on("pageerror", (e) => page.errors.push(e.message));
  const asked = [];
  await page.exposeFunction("haAsked", (m) => asked.push(m));
  await page.route("**/ha-shell", (r) => r.fulfill({ contentType: "text/html", body: `<!doctype html><home-assistant></home-assistant>
    <iframe src="/" style="position:fixed;inset:0;width:100%;height:100%;border:0"></iframe>
    <script>document.querySelector("home-assistant").hass = { connection: { sendMessagePromise: async (m) => { haAsked(m.type + " " + m.entity_id); return { url: "/hls-test/index.m3u8" }; } } };</script>` }));
  await page.route("**/hls-test/*", (r) => r.fulfill({ path: path.join(__dirname, "hls", path.basename(new globalThis.URL(r.request().url()).pathname)) }));
  await page.goto(URL + "ha-shell");
  const f = page.frames()[1];
  await f.waitForSelector("#view-casa");
  await f.click("#view-casa");
  await f.waitForSelector(".plan-room[data-area='soggiorno']");
  await f.locator("[data-area='giardino']").first().click();
  await f.click(".casa-quick [data-act='open']");
  await f.waitForSelector(".hc-camcomp video[data-live]", { timeout: 15000 });
  assert.ok(asked.includes("camera/stream camera.ingresso"), "il video chiesto a Home Assistant");
  assert.equal(await f.locator(".hc-camcomp img[src*='/stream']").count(), 0, "niente MJPEG dentro Home Assistant");
  await f.click(".hc-camcomp .casa-cam");
  await f.waitForFunction(() => /HD/.test(document.querySelector(".cam-mode")?.textContent || ""), null, { timeout: 2000 });
  assert.equal(await f.locator(".casa-overlay video.cam-live").count(), 1, "il video della miniatura, spostato");
  await f.click(".casa-overlay .casa-x");
  await f.waitForSelector(".hc-camcomp video[data-live]", { timeout: 15000 });
  assert.deepEqual(page.errors, [], "errori JavaScript nella pagina");
  await page.close();
});

test("tema: chiaro per la Casa al sole, HQ resta scuro, la scelta resta sul dispositivo", { timeout: 30000 }, async () => {
  const page = await open({ width: 390, height: 844 });
  const light = async () => { await page.waitForTimeout(150); return page.evaluate(() => document.documentElement.classList.contains("light")); };
  await page.emulateMedia({ colorScheme: "dark" });
  await casa(page);
  assert.equal(await light(), false); // automatic: the phone is dark
  await page.emulateMedia({ colorScheme: "light" });
  assert.equal(await light(), true); // ...and follows it when it turns light
  assert.equal(await page.evaluate(() => getComputedStyle(document.body).backgroundColor), "rgb(238, 242, 246)");
  await page.click("#view-hq");
  assert.equal(await light(), false); // HQ and Mappa stay night scenes
  await page.click("#ha-prefs");
  await page.selectOption("#pref-theme", "dark");
  await page.click("#prefs-close");
  await casa(page);
  assert.equal(await light(), false);
  await page.click("#ha-prefs");
  await page.selectOption("#pref-theme", "light");
  await page.emulateMedia({ colorScheme: "dark" });
  await page.reload();
  await page.waitForSelector("#view-casa");
  await casa(page);
  assert.equal(await light(), true); // chosen here: stays light whatever the phone says
  assert.equal(await page.inputValue("#pref-theme"), "light");
  assert.equal(await page.getAttribute('meta[name="theme-color"]', "content"), "#eef2f6");
  await done(page);
});

test("preferenze: il backup si scarica", { timeout: 30000 }, async () => {
  const page = await open();
  await page.click("#ha-prefs");
  const [download] = await Promise.all([page.waitForEvent("download"), page.click("#backup-get")]);
  assert.match(download.suggestedFilename(), /^hubnex-backup-\d{8}-\d{4}\.zip$/);
  await done(page);
});

test("telefono: accesso Claude mostra link e codice sopra il terminale", { timeout: 30000 }, async () => {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  page.errors = [];
  page.on("pageerror", (e) => page.errors.push(e.message));
  await page.addInitScript(() => localStorage.setItem("hq_lang", "en"));
  const url = "https://claude.ai/oauth/authorize?state=test-code";
  let submitted;
  await page.route("**/api/claude/auth", (r) => r.fulfill({ json: {
    mode: "subscription", subscription_enabled: true, subscription: { status: "signed_out" }, api_key_available: false,
  } }));
  await page.route("**/api/claude/login", (r) => r.fulfill({ json: r.request().method() === "POST"
    ? { running: true } : { running: true, output: `Open ${url}\nPaste code here if prompted >` } }));
  await page.route("**/api/claude/login/code", async (r) => {
    submitted = r.request().postDataJSON().code;
    await r.fulfill({ json: { running: true } });
  });
  await page.goto(URL);
  await page.click("#ha-prefs");
  await page.click("#pref-claude-start");
  await page.locator("#pref-claude-url:not(.hidden)").waitFor();
  assert.equal(await page.getAttribute("#pref-claude-url", "href"), url);
  assert.ok(await page.locator("#pref-claude-code").evaluate((el) => el.compareDocumentPosition(document.querySelector("#pref-claude-output")) & Node.DOCUMENT_POSITION_FOLLOWING));
  assert.equal(await page.locator("#prefs").evaluate((el) => getComputedStyle(el).overflowY), "auto");
  await page.fill("#pref-claude-code", "my-code");
  await page.click("#pref-claude-send");
  assert.equal(submitted, "my-code");
  await done(page);
});

test("spesa Claude: dalla scheda in HQ, per giorno, agente e modello", { timeout: 30000 }, async () => {
  const page = await open();
  await page.click("#view-hq");
  await page.click("[data-costs]");
  await page.waitForSelector(".costs-row");
  assert.equal(await page.locator(".costs-bar").count(), 30, "una barra per giorno");
  assert.match(await page.textContent(".costs"), /Jarvis Mail/);
  assert.match(await page.textContent(".costs"), /claude-haiku-5-5/);
  assert.match(await page.textContent(".costs-budget"), /\$15\.00/, "il budget della demo");
  await page.click("[data-span='7']");
  await page.waitForFunction(() => document.querySelectorAll(".costs-bar").length === 7);
  await page.keyboard.press("Escape");
  assert.equal(await page.locator(".costs-modal").count(), 0, "Esc chiude");
  await done(page);
});

test("telefono: la spesa Claude si apre dalle preferenze", { timeout: 30000 }, async () => {
  const page = await open({ width: 390, height: 844 });
  await page.click("#ha-prefs");
  await page.click("#pref-costs");
  await page.waitForSelector(".costs-row");
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth), 390, "niente scorrimento laterale");
  await page.click("[data-costs-close]");
  assert.equal(await page.locator(".costs-modal").count(), 0);
  await done(page);
});

test("notifiche della casa: regole, canali, prova", { timeout: 30000 }, async () => {
  const page = await open();
  await page.click("#ha-prefs");
  await page.click("#pref-alerts");
  await page.waitForSelector(".al-rule");
  assert.equal(await page.locator(".al-rule").count(), 8, "otto regole, con le scorte");
  assert.match(await page.textContent(".al-active"), /Finestra camera/, "la finestra aperta col riscaldamento");
  assert.match(await page.textContent(".al-phones"), /Pixel 9/);
  await page.click("[data-al-on='night']");
  await page.waitForSelector(".al-note:has-text('Saved')");
  assert.ok(await page.locator("[data-al-on='night']").evaluate((b) => !b.classList.contains("on")), "regola spenta e salvata");
  await page.click("[data-al-test]");
  await page.waitForFunction(() => /Test sent/.test(document.querySelector(".al-note").textContent));
  await page.keyboard.press("Escape");
  assert.equal(await page.locator(".alerts-modal").count(), 0);
  await done(page);
});

test("telefono: la scheda della stanza sale dal basso", { timeout: 30000 }, async () => {
  const page = await open({ width: 390, height: 844 });
  await casa(page);
  await page.click(".plan-room[data-area='cucina']");
  await page.waitForSelector(".casa-quick");
  assert.ok(await page.evaluate(() => document.body.classList.contains("casa-sheet")));
  const box = await page.locator(".casa-quick").boundingBox();
  assert.ok(box.y > 200 && box.x < 20, "la scheda è in basso e occupa la larghezza");
  await done(page);
});

test("in inglese: Casa, stanza, Energia e preferenze senza testi italiani mancanti", { timeout: 30000 }, async () => {
  const page = await open({ width: 1440, height: 900 }, "en");
  await casa(page);
  assert.match(await page.textContent("#casa"), /Room temperatures/);
  await page.click(".plan-room[data-area='soggiorno']");
  await page.click(".casa-quick [data-act='open']");
  await page.click("[data-act='edit']");
  assert.match(await page.textContent("#casa"), /Done editing/);
  await page.click("[data-act='home']");
  await page.click("[data-act='energy']");
  await page.waitForSelector(".casa-energy-modal");
  assert.match(await page.textContent(".casa-energy-modal"), /Energy/);
  await page.keyboard.press("Escape");
  await page.click("#ha-prefs");
  assert.match(await page.textContent("#prefs"), /Preferences/);
  assert.equal(await page.getAttribute("#chat-input", "placeholder"), "Talk to Jarvis…");
  const missing = await page.evaluate(() => [...(window.__i18nMissing || [])]);
  assert.deepEqual(missing, [], "testi senza inglese mostrati nella pagina");
  await done(page);
});

test("piantina: disegna e modifica una stanza a L con mouse e tocco", { timeout: 60000 }, async () => {
  const page = await open();
  await casa(page);
  await page.click("[data-act='layout']");
  await page.waitForSelector(".ped-stage");
  await page.click("[data-ed='tool-polygon']");
  const stage = await page.locator(".ped-stage").boundingBox();
  for (const [x, y] of [[10, 10], [80, 10], [80, 30], [40, 30], [40, 80], [10, 80]]) {
    await page.mouse.click(stage.x + stage.width * x / 100, stage.y + stage.height * y / 100);
  }
  await page.click("[data-ed='finish-polygon']");
  assert.equal(await page.locator(".ped-room.sel.polygon").count(), 1);
  assert.equal(await page.locator("[data-point]").count(), 6);
  const selectedRoom = await page.locator(".ped-room.sel.polygon").getAttribute("data-room");
  assert.equal(await page.evaluate(({ stage, selectedRoom }) => document.elementFromPoint(
    stage.x + stage.width * .7, stage.y + stage.height * .7
  )?.closest(`[data-room="${selectedRoom}"]`)?.dataset.room || null, { stage, selectedRoom }), null, "de uitsparing van de L-vorm vangt geen tik op");
  await page.click("[data-edge='2']");
  assert.equal(await page.locator("[data-point]").count(), 7);
  await page.click("[data-ed='delete-point']");
  assert.equal(await page.locator("[data-point]").count(), 6);
  const vertex = await page.locator("[data-point='3']").boundingBox();
  await page.mouse.move(vertex.x + vertex.width / 2, vertex.y + vertex.height / 2);
  await page.mouse.down();
  await page.mouse.move(vertex.x + vertex.width / 2 + 18, vertex.y + vertex.height / 2 + 8);
  await page.mouse.up();
  await page.selectOption("[data-ed='area']", { label: "Soggiorno" });
  await page.click("[data-ed='save']");
  await page.waitForSelector(".plan-room.polygon[data-area='soggiorno']");
  assert.match(await page.locator(".plan-room.polygon[data-area='soggiorno']").last().evaluate((el) => getComputedStyle(el).clipPath), /polygon/);
  await page.click("[data-act='layout']");
  await page.waitForSelector(".ped-room.polygon");
  assert.equal(await page.locator(".ped-room.polygon").count(), 1, "de vorm blijft bewaard na opnieuw openen");
  await page.locator(".ped-room:not(.outline):not(.polygon)").last().click({ timeout: 5000 });
  await page.click("[data-ed='edit-points']");
  assert.equal(await page.locator("[data-point]").count(), 4, "een rechthoek kan hoekpunten krijgen");
  await page.locator("[data-ed='outline']").check();
  assert.equal(await page.locator(".ped-room.sel.polygon.outline").count(), 1);
  await done(page);

  const touch = await browser.newPage({ viewport: { width: 390, height: 844 }, hasTouch: true });
  touch.errors = [];
  touch.on("pageerror", (e) => touch.errors.push(e.message));
  await touch.goto(URL);
  await casa(touch);
  await touch.click("[data-act='layout']");
  await touch.click("[data-ed='tool-polygon']");
  const mobileStage = await touch.locator(".ped-stage").boundingBox();
  await touch.touchscreen.tap(mobileStage.x + mobileStage.width * .15, mobileStage.y + mobileStage.height * .15);
  await touch.click("[data-ed='cancel-polygon']");
  assert.equal(await touch.locator("[data-draft-point]").count(), 0);
  for (const [x, y] of [[15, 15], [70, 15], [70, 65], [15, 65]]) {
    await touch.touchscreen.tap(mobileStage.x + mobileStage.width * x / 100, mobileStage.y + mobileStage.height * y / 100);
  }
  await touch.click("[data-draft-point='0']");
  assert.equal(await touch.locator(".ped-room.sel.polygon").count(), 1);
  await done(touch);
});
