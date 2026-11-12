# HubNEX

*[English](README.md) · Italiano*

**Il quartier generale AI per casa e lavoro**, come add-on per Home Assistant.

[![Controlli](https://github.com/P1pp89/HubNEX/actions/workflows/ci.yaml/badge.svg)](https://github.com/P1pp89/HubNEX/actions/workflows/ci.yaml)

**[Guarda la presentazione →](https://p1pp89.github.io/HubNEX/)**

![La vista Casa di HubNEX](docs/img/casa.jpg)

Un assistente (di serie si chiama Jarvis) coordina un team di agenti AI (Claude), ognuno con il
suo ruolo: posta, amministrazione, ricerche tecniche, casa, sicurezza… Gli parli dalla dashboard
3D nella barra laterale di Home Assistant, da un gruppo Telegram o a voce con Assist.

- **Dashboard 3D**: il quartier generale con gli agenti al lavoro, la mappa neurale di ciò che
  il team sa, il nucleo animato che ascolta, pensa e parla.
- **Vista Casa**: la plancia di Home Assistant sulla piantina olografica della tua casa, con
  stanze, luci, clima, tapparelle, telecamere dal vivo e allarme. Comandi diretti, in tempo
  reale, senza costi AI.
- **Team configurabile** in `agents.yaml`: aziende, reparti, agenti, istruzioni, routine.
- **Connettori MCP**: collega i programmi del tuo lavoro (gestionali, calendari, CRM…). Gli
  agenti leggono liberamente; ogni modifica parte solo dopo il tuo ✅.
- **Posta**: smistamento delle email e bozze di risposta che approvi tu.
- **Telegram**: un gruppo con un bot per l'assistente e uno per la posta, vocali, foto e documenti compresi.
- **Voce**: Assist di Home Assistant (anche locale con Piper), ElevenLabs o la sintesi vocale di
  Home Assistant nella dashboard.
- **Niente iniziative senza il tuo ordine**: routine spente di default, nessuna azione in casa
  senza una tua richiesta, regole permanenti che valgono per tutto il team.

## Installazione

1. Home Assistant → Impostazioni → Componenti aggiuntivi → **Store** → ⋮ → **Repository** →
   aggiungi `https://github.com/P1pp89/HubNEX`.
2. Installa **HubNEX**, apri **Configurazione**, inserisci la chiave API Anthropic (oppure scegli
   l'abbonamento Claude Code personale descritto nella documentazione), **Avvia** e attiva
   **Mostra nella barra laterale**.

La guida completa (team, connettori, voce, Telegram, posta, vista Casa) è in
[`hubnex/DOCS.md`](hubnex/DOCS.md), visibile anche nella scheda **Documentazione** dell'add-on.

La modalità API richiede un account Anthropic Console con credito. In un'installazione privata
per un solo utente puoi invece accedere alla CLI Claude Code inclusa con il tuo abbonamento;
vedi la documentazione. HubNEX usa Claude Sonnet per l'assistente e gli agenti e
Claude Haiku per la posta. I comandi della vista Casa e, con Assist, i comandi semplici di Home
Assistant non consumano credito.

**Altri fornitori AI.** Ogni agente può usare anche **OpenAI** o un **modello locale** con Ollama
o LM Studio (gratis, senza cloud), oppure qualsiasi servizio compatibile con OpenAI
(OpenRouter, Gemini, Mistral…): scrivi il modello come `openai:gpt-5-mini` o
`ollama:qwen3:14b`. Claude resta il consigliato: la ricerca web e i pensieri visibili di Jarvis
ci sono solo con lui. Dettagli nella documentazione.

## Senza Home Assistant (Docker)

```bash
cd hubnex
cp .env.example .env        # compila le chiavi
docker compose up -d --build
# dashboard: http://<ip-macchina>:8765/?token=<HQ_TOKEN>
```

## API

Tutte richiedono `Authorization: Bearer <HQ_TOKEN>` (o `?token=`).

| Metodo | Percorso | |
|---|---|---|
| GET | `/api/state` | Stato completo (team, attività, scadenze, statistiche) |
| POST | `/api/chat` | `{"text": "...", "attachments": []}` → risposta dell'assistente |
| POST | `/api/attachments?name=` | Foto, PDF o file di testo (corpo grezzo) → `{"id"}` per `attachments` |
| POST | `/api/agents/{id}/task` | `{"task": "...", "wait": false}` assegna un compito |
| POST | `/api/deadlines` | `{"title", "due", "notes"}` |
| POST | `/api/tts` | `{"text"}` → audio della voce configurata |
| POST | `/api/ha/event` | Evento da un'automazione di Home Assistant |
| GET | `/api/casa` | Vista Casa: piantina, aree, entità e stati |
| WS | `/ws?token=` | Stream live per la dashboard |

## Sviluppo

```bash
cd hubnex
pip install -r requirements-dev.txt
pytest
```

I test usano un client Claude finto: nessuna chiamata reale e nessun costo. L'integrazione
Assist (`hubnex/integration/hubnex`) ha i suoi test su un Home Assistant di prova:

```bash
cd hubnex/integration
pip install pytest-homeassistant-custom-component
# hassil e home-assistant-intents nelle versioni fissate da quell'Home Assistant:
pip install -c "$(python -c 'import homeassistant,os;print(os.path.dirname(homeassistant.__file__))')/package_constraints.txt" hassil home-assistant-intents
pytest -p pytest_homeassistant_custom_component
```

Struttura: `hubnex/hq.py` (il team, lo stato, la delega), `hubnex/llm.py` (ciclo agente Claude),
`hubnex/connectors.py` e `hubnex/integrations/mcp.py` (connettori MCP), `hubnex/actions.py`
(azioni da confermare), `hubnex/casa.py` (vista Casa), `hubnex/maildesk.py` (posta),
`hubnex/tools/` (strumenti degli agenti), `hubnex/integrations/` (Home Assistant, Telegram,
IMAP/SMTP, ElevenLabs), `web/` (dashboard: Three.js e hls.js inclusi, funziona anche senza
internet).

## Sostieni HubNEX

HubNEX è gratuito e open source, e lo resterà. Se ogni giorno ti restituisce qualche minuto,
aiuta a tenere acceso il reattore: **[sostienilo con PayPal](https://www.paypal.com/donate/?hosted_button_id=HTZJULXKFP8M4)**. Ogni contributo diventa
nuove funzioni, più test e correzioni più rapide.

Anche una stella su GitHub aiuta: porta HubNEX a chi ne ha bisogno.

## Licenza

[MIT](LICENSE). Include [Three.js](https://threejs.org) (MIT) e
[hls.js](https://github.com/video-dev/hls.js) (Apache 2.0): vedi [NOTICE](NOTICE).

HubNEX non è affiliato ad Anthropic, Home Assistant, ElevenLabs né a Marvel: "Jarvis" è solo il
nome di serie dell'assistente e si cambia in `agents.yaml`.
