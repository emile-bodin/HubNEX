# Changelog

## 1.22.0b
- Accesso Claude: link apribile nel browser e campo per il codice visibile sopra l'output.
- Preferenze scorrevoli sugli schermi piccoli e indicazioni di accesso più chiare.

## 1.21.1b
- Beta con accesso a Claude tramite l'abbonamento Claude Code e fallback API facoltativo.
- Immagini dell'add-on distribuite dal fork emile-bodin.

## 1.21.1
- Tema chiaro: il riquadro in alto della Casa diventa un'unica card bianca, con le voci divise
  da linee sottili (prima a scacchiera).
- Con una sola telecamera: «tocca per vederla».

## 1.21.0
- **Tema chiaro** per la Casa, ad alto contrasto, da leggere anche al sole: sfondo chiaro, card
  bianche, testi scuri, ambra e rosso più pieni. In **⚙ → Tema**: Automatico (segue il
  telefono), Scuro o Chiaro; la scelta resta sul dispositivo. HQ e Mappa restano scuri.

## 1.20.2
- Card libera, stile **Pulito** come le card composte: etichette piccole, valori di misura
  media, una linea sopra ogni blocco che si accende quando l'entità è attiva, orari con −15/+15
  accanto, interruttori con il nome sulla stessa riga, lo stato della card nell'intestazione
  (accesa · attiva fino alle…).
- **La linea in alto** di tutte le card (libere e composte) segue le stesse regole: arancione
  quando qualcosa è acceso o un sensore rileva, rossa per un allarme (porta o finestra aperta,
  acqua, fumo, gas); in una card con un interruttore principale, come la stufa, decide lui.

## 1.20.1
- Card libera: **stile Pulito**, senza riquadri, come le card composte, e di partenza per le
  card nuove; **Riquadri** resta da scegliere nell'editor. Le card già create restano come
  sono. Lo stile viaggia anche con Esporta / Importa.

## 1.20.0
- **Card libera**, terza parte:
  - **Descrivila a Jarvis**: scrivi la card che vuoi e Jarvis la compone con le entità vere
    della casa (le entità inventate vengono scartate); si apre nell'editor da controllare;
  - **Esporta / Importa card**: una card diventa testo da condividere e si incolla in un'altra
    casa, dove i blocchi con entità mancanti restano da scegliere;
  - nelle condizioni e nelle regole i valori si scelgono da un **elenco tradotto** (acceso,
    aperta, in riproduzione…) invece di scrivere `on` o `playing`.

## 1.19.0
- **Card libera**, seconda parte:
  - blocchi **media** (copertina, titolo, comandi, volume), **telecamera** (dal vivo) e
    **Domanda a Jarvis** (una domanda pronta che parte in chat con un tocco);
  - per ogni blocco: **colore secondo il valore** (fino a 4 regole), **mostra solo se**
    (un'entità vale qualcosa) e **azione al tocco** (accendi/spegni, scena o script, chiedi a
    Jarvis, apri una stanza);
  - **modelli pronti**: Stufa, Ingresso, Lavanderia, Clima stanza, Energia, Musica, riempiti
    con le entità della stanza;
  - i blocchi si spostano **trascinandoli**, con il dito o con il mouse.

## 1.18.0
- **Card libera** (prima parte): una card a blocchi su una griglia da 4 colonne, 2 sul
  telefono. Blocchi: valore grande, anello, interruttore, pulsante, cursore, grafico, barra,
  fascia oraria, selettore, stato e testo; per ognuno entità, etichetta, dimensione (da 1×1 a
  4×2), minimo e massimo. Nome e colore della card, anteprima dal vivo nell'editor. Si crea da
  Modifica stanza → + Card libera.

## 1.17.0
- **Card Scorta** per il pellet e simili: quanti ne restano, consumo al giorno e giorni
  rimasti (dallo storico di Home Assistant), ultima consegna, "−1 caricato" e "+consegna".
  La riconosce da sola un aiutante Numero o un Contatore con "pellet", "sacchi" o "scorta"
  nel nome; per gli altri si sceglie il tipo "Scorta". Sotto la soglia scelta la card diventa
  rossa e arriva la notifica **Scorte da riordinare**.
- **Contatori** e **timer** di Home Assistant riconosciuti nelle stanze.
- **Aggiungi entità**: la ricerca non si ferma più a 60 risultati, ogni entità di Home
  Assistant si può mettere in una stanza.

## 1.16.2
- HQ: il fascio di luce da Jarvis a un agente resta acceso **per tutto il lavoro**, pulsando,
  con dei punti luminosi che scorrono verso l'agente; quando l'agente ha finito sfuma. Prima
  durava un secondo e mezzo all'inizio. Tornando sull'HQ, o cambiando sede, mentre un agente
  lavora, il suo fascio c'è subito.

## 1.16.1
- Chat: niente più "Failed to fetch" con le richieste lunghe (agenti che cercano e verificano
  sul web). La dashboard non tiene aperta una sola richiesta per tutta la risposta, che un
  proxy (Home Assistant, Nabu Casa, l'app) poteva chiudere dopo un minuto o due: riceve
  subito un numero di lavoro e chiede la risposta con richieste brevi. Se la rete cade un
  momento, riprova da sola.

## 1.16.0
- Vista Casa più ricca:
  - **Meteo** nel cruscotto, con le previsioni dei prossimi giorni in un popup (da Home
    Assistant);
  - **Oggi e prossimi giorni**: le scadenze dei prossimi 7 giorni, con la spunta per chiuderle.
    Solo per il proprietario: i familiari con accesso alla sola casa non le vedono;
  - **icone sulla piantina**: presenza, musica, robot al lavoro, lavatrice in funzione;
  - **Elettrodomestici**: in funzione con la potenza, e "finito … fa";
  - **Ultimi eventi**: porte, finestre, serrature, allarme e persone delle ultime 24 ore.

## 1.15.1
- **Ricerche web regolabili per agente**: in `agents.yaml`, `max_searches: 3` limita le ricerche
  web di Jarvis o di un agente per ogni richiesta (da 1 a 20; se manca restano 5, come prima).
  Ogni ricerca porta pagine da leggere: con meno ricerche la spesa scende, soprattutto per gli
  agenti tecnici. Nella documentazione, i consigli per spendere meno.

## 1.15.0
- **Altri fornitori AI**: Jarvis e ogni agente possono usare anche **OpenAI**, un **modello
  locale** con Ollama o LM Studio (gratis, senza cloud) o qualsiasi servizio compatibile con
  OpenAI (OpenRouter, Gemini, Mistral, DeepSeek, Groq). Il modello si scrive con il prefisso:
  `openai:gpt-5-mini`, `ollama:qwen3:14b`, `compat:nome-modello`; senza prefisso è Claude,
  come prima. Si possono mescolare, per esempio Jarvis su Claude e la posta su un modello
  locale. Nuove opzioni per chiavi e indirizzi; la chiave Anthropic diventa facoltativa.
- Con gli altri modelli la lettura delle pagine web la fa HubNEX (solo indirizzi pubblici), i
  PDF arrivano come testo; la ricerca web e i pensieri visibili restano solo con Claude.
- Spesa: i modelli di Ollama costano zero, per OpenAI e gli altri si inserisce il prezzo di
  listino. Il credito Anthropic scala solo le chiamate a Claude.

## 1.14.3
- Telecamere dentro Home Assistant: le miniature dal vivo usano il video di Home Assistant
  (lo stesso della vista grande in HD), non più l'MJPEG che con molte telecamere non arriva.
  Toccando una miniatura la vista grande si apre subito in HD, con lo stesso video. Fuori da
  Home Assistant resta l'MJPEG; se il video di una telecamera non parte, si torna alle foto.

## 1.14.2
- Telecamere: niente più miniature nere. L'ultima foto resta visibile finché il video dal vivo
  non mostra davvero un'immagine. Se dopo 10 secondi il video non è arrivato, la miniatura resta
  sulle foto aggiornate ogni 5 secondi.

## 1.14.1
- Telecamere: la vista grande si apre subito. Usa il video già in corso nella miniatura invece
  di aprirne uno nuovo, e dentro Home Assistant il video in alta qualità parte insieme, non più
  dopo aver aspettato il primo fotogramma (fino a 10 secondi di attesa con alcune telecamere).

## 1.14.0
- Card del **robot aspirapolvere**: stato, batteria, la sua **mappa** (dallo stesso dispositivo,
  si aggiorna ogni 5 secondi e mostra il robot che si muove), Pulisci/Pausa, Base, Trova e
  potenza di aspirazione. Nelle stanze ha il gruppo "Pulizia".
- **Telecamere dal vivo**: le miniature sono video (fino a 3 alla volta), toccandole si aprono
  grandi già dal vivo; dentro Home Assistant si passa al suo video in alta qualità.
- **Card composta con telecamera**: l'immagine al posto della scritta "idle", i sensori sopra
  l'immagine (rossi quando scattano, "da quanto" quando sono a riposo), lo stato in chiaro.
- **Card dei media** più completa: copertina grande con sfondo sfumato, artista e album, app,
  avanzamento, casuale/ripeti, silenzia, volume e sorgente, secondo quello che il dispositivo
  supporta.

## 1.13.2
- Card delle luci di nuovo minimale: colore e temperatura stanno in un popup, che si apre dal
  piccolo pallino accanto allo stato (solo sulle lampadine che li hanno). Nel popup:
  luminosità, temperatura da calda a fredda, colori e selettore.

## 1.13.1
- Card delle luci: cursore della temperatura colore (da calda a fredda) e colori, con un
  selettore per qualsiasi altro colore, solo sulle lampadine che li supportano. Un colore scelto
  su una luce spenta la accende di quel colore.

## 1.13.0
- Allegati: foto, album, PDF e file di testo all'assistente e agli agenti, da Telegram (con la
  richiesta nella didascalia, o rispondendo alla foto) e dalla dashboard (graffetta, fotocamera
  del telefono, incolla o trascina). L'assistente li passa all'agente a cui delega il lavoro;
  la conversazione ne tiene solo il codice, e chiunque del team può riguardarli
  (`view_attachment`). Restano 30 giorni. API: `POST /api/attachments`.

## 1.12.3
- Chat della dashboard: la richiesta va a capo e il campo cresce fino a circa 6 righe, poi
  scorre. Invio invia, Shift+Invio va a capo.

## 1.12.2
- Posta: pulsanti Leggi e Rispondi senza emoji (restano i pallini della priorità).
- Corretto: senza un bot separato per Jarvis Mail, i pulsanti della posta arrivano al bot di
  Jarvis e ora funzionano (prima venivano ignorati, e dalla 1.12.0 scambiati per pulsanti delle
  notifiche della casa). I pulsanti delle notifiche della casa hanno un codice tutto loro.

## 1.12.1
- Posta: nuova opzione "Mittenti da non segnalare" (indirizzi, @domini o parole come noreply):
  niente messaggio su Telegram e niente classificazione, quindi niente credito Claude.
- Notifiche della casa più chiare: batterie scariche, dispositivi non raggiungibili e sensori di
  sicurezza dicono quale dispositivo e in quale stanza ("Sensore porta (Ingresso) 8%").
- Niente emoji nelle notifiche della casa e negli avvisi di credito e budget; gli avvisi urgenti
  su Telegram iniziano con "URGENTE:".

## 1.12.0
- Notifiche della casa, senza Claude: perdite/fumo/gas (subito, anche di notte), finestre aperte
  con riscaldamento/condizionatore acceso o pioggia, casa vuota con porte/cancello/serrature
  aperti, consumo alto, luci accese di notte, batterie scariche, dispositivi non raggiungibili.
- Arrivano sull'app di Home Assistant (push con pulsanti Chiudi/Spegni), su Telegram e nelle
  notifiche di Home Assistant, a scelta per ogni regola. Un avviso per problema, che sparisce da
  solo quando il problema è risolto; ore di silenzio; nessuna azione senza il tuo tocco.
- Si configurano in ⚙ Preferenze → Notifiche della casa, con entità da escludere e notifica di
  prova.
- Test: il popup Energia aspetta il grafico del giorno prima di provare lo scorrimento.

## 1.11.0
- Storico della spesa Claude: clic sul riquadro della spesa in HQ (o ⚙ Preferenze → Spesa
  Claude). Oggi, mese, stima a fine mese, una barra per giorno (7/30/90 giorni), spesa per
  agente e per modello con chiamate e token.
- Nuova opzione `monthly_budget_usd`: avviso all'80% e al 100% del budget del mese, nel gruppo
  Telegram e nelle notifiche di Home Assistant. Solo un avviso, niente si ferma.
- La spesa di ogni chiamata a Claude è registrata per giorno, agente e modello (inclusa nel
  backup).

## 1.10.1
- Guida completa in inglese (DOCS.en.md) e team di esempio in inglese: con la lingua
  inglese, al primo avvio l'add-on crea agents.yaml già tradotto.
- README del progetto in inglese (quello italiano resta in README.it.md) e presentazione
  in inglese con screenshot della dashboard in inglese.
- Corretto: l'etichetta "Risposta rapida" sotto i messaggi ora segue la lingua della dashboard.
- Guida italiana: spostato al posto giusto il paragrafo "Se l'integrazione non viene rilevata".

## 1.10.0
- L'add-on parla inglese: nuova opzione "Lingua" (auto = quella di Home Assistant, it, en).
  - Jarvis e gli agenti rispondono in inglese (le istruzioni in agents.yaml possono restare
    in italiano);
  - registro attività, Telegram (messaggi, pulsanti, posta), notifiche ed errori in inglese;
  - la dashboard riceve gli errori nella lingua di chi la usa, Assist risponde nella lingua
    in cui gli parli;
  - la voce legge unità, simboli e date in inglese ("kilowatt hours", "1 September").
- Fuori dall'Italia le fasce energetiche partono da "tariffa unica" invece del calendario ARERA.
- Un test controlla che ogni messaggio dell'add-on abbia la sua traduzione.

## 1.9.0
- La dashboard parla inglese: scelta da sola in base alla lingua di Home Assistant di chi la
  apre, o a mano in ⚙ Preferenze → Lingua. Tutti i testi (Casa, card, Energia, piantina, HQ,
  mappa, chat, preferenze) sono tradotti; un test controlla che il dizionario resti completo.
- Numeri, date e ore nel formato della lingua scelta; il microfono ascolta nella stessa lingua.
- Corretto: il fumetto "Leggo la posta…" dell'assistente non compariva mai.

- Per chi sviluppa: `dev/demo.py` (HubNEX con una casa e un Claude finti), test della
  dashboard nel browser a ogni modifica, guida CONTRIBUTING.

## 1.8.11
- L'integrazione Assist ha la sua icona in Dispositivi e servizi (Home Assistant 2026.3 o
  successivo).

## 1.8.10
- Integrazione Assist aggiunta a mano: niente più indirizzo predefinito della copia locale
  (`local-hubnex`), che con l'add-on del repository è sbagliato; la finestra spiega che di
  solito basta riavviare l'add-on e confermare "HubNEX rilevato".

## 1.8.9
- Backup di HubNEX dalle Preferenze: un file con memoria e mappa neurale, scadenze, chat,
  impostazioni della Casa, piantina ed energia, `agents.yaml`. Senza le opzioni dell'add-on (chiavi API, Telegram, posta).
- Ripristino dallo stesso pannello: applicato al riavvio, che parte da solo; i file sostituiti
  restano come `.prima-del-ripristino`. Serve anche per passare dalla copia locale all'add-on
  del repository (vedi la documentazione).
- Installazione e aggiornamenti molto più rapidi: Home Assistant scarica l'immagine già
  pronta (Raspberry/ARM e PC) invece di costruire HubNEX.
- Il repository ha i controlli automatici (test, dashboard, manifesto), moduli per le
  segnalazioni e la pagina sulla sicurezza.

## 1.8.8
- Chi ha risposto nella chat è una piccola scritta nello stile di HubNEX (HOME ASSISTANT,
  RISPOSTA RAPIDA), senza emoji.

## 1.8.7
- Dashboard e Assist seguono la strada più veloce:
  1. dashboard: prima le frasi di Home Assistant (istantaneo, senza AI);
  2. la via rapida per le richieste sulla casa (Haiku con l'elenco delle entità);
  3. Jarvis con il suo modello per tutto il resto. Le domande complesse fatte ad Assist ora
     arrivano a Jarvis, non restano su Haiku.
- Serrature, allarme e porte non passano mai da Home Assistant o dalla via rapida: decide
  Jarvis, con la conferma.
- Nella chat della dashboard "⚡ Home Assistant" o "⚡ risposta rapida" dice chi ha risposto.

## 1.8.6
- Comandi vocali (Assist) più veloci:
  - nuova opzione "Modello per i comandi vocali", di serie Haiku: Telegram e dashboard
    restano sul modello di Jarvis;
  - Jarvis riceve l'elenco delle entità della casa con area e stato, quindi comanda subito
    senza cercarle e risponde alle domande sullo stato senza strumenti;
  - istruzioni e cronologia più leggere per la voce (può sempre delegare agli agenti).

## 1.8.5
- I popup della Casa (Energia compresa) scorrono senza la barra di scorrimento chiara, come il
  resto di HubNEX.

## 1.8.4
- Energia torna a essere un popup, come gli altri della barra in alto: si chiude con ×, con
  un clic sullo sfondo o con Esc. Impostazioni invariate.
- I popup della Casa stanno in un livello a parte: gli aggiornamenti dal vivo della casa non
  li ridisegnano più, e un popup si aggiorna solo quando cambia ciò che mostra, senza perdere
  lo scorrimento.
- Nuovi colori delle fasce, ben distinti: F1 arancione, F2 blu, F3 verde. Anche "fascia
  adesso" prende il colore della fascia in corso.

## 1.8.3
- Nuova opzione "Risposte a voce": completa (come prima) o riassunto. Con riassunto, quando la
  risposta è lunga Jarvis aggiunge una o due frasi da dire a voce e la voce legge solo quelle;
  il testo scritto resta completo. Dashboard (altoparlante acceso) e vocali di Telegram.

## 1.8.2
- La voce legge un testo preparato per l'ascolto: niente simboli, emoji e link; unità e sigle
  in parole (Ω, kW, kWh, °, MT/BT…), date per esteso, pause al posto dei trattini degli
  elenchi. Vale per la dashboard, i vocali di Telegram e Assist.
- Nuova opzione "Voce del motore di Home Assistant": la voce per nome (es. Rinaldo con Home
  Assistant Cloud). La lingua è sempre quella di Home Assistant, anche senza voce scelta.
- ElevenLabs: crediti esauriti, chiave sbagliata e piano gratuito bloccato hanno ora messaggi
  distinti (prima tutti "chiave API non valida").

## 1.8.1
- Energia è una pagina come quelle delle stanze (← Casa per tornare), non più un popup: lo
  scorrimento non torna in alto con gli aggiornamenti dal vivo. Anche gli editor mantengono
  la posizione.
- "Fuori casa" e le altre aree non toccano più la piantina.
- Temperature delle stanze allineate qualunque sia il numero di decimali.

## 1.8.0
- Pannello Energia (tocca "Energia" nel cruscotto della Casa) con tre viste a scelta:
  - il reattore: il periodo diviso per fascia F1/F2/F3 attorno alla potenza adesso;
  - la giornata: la potenza di oggi sullo sfondo delle fasce, kWh di oggi per fascia;
  - la bolletta: spesa, stima a fine periodo, fasce col confronto sul periodo precedente e un
    consiglio quando una fascia cresce.
- Configurabile da HubNEX: viste, fascia (calendario ARERA con festivi, un proprio sensore,
  tariffa unica), kWh per fascia, prezzi o spesa, potenza e contatore, altri valori.
- Le finestre (editor, codice, energia) si aprono sotto la barra in alto e nascondono la chat.

## 1.7.5
- Grafico a scelta: nell'editor della card su misura ogni sensore numerico ha l'interruttore
  "grafico"; sulle card singole, in "Modifica stanza", "Togli grafico" / "Mostra grafico".

## 1.7.4
- Card su misura: i sensori numerici (luce, temperatura, consumo…) hanno il grafico delle
  ultime 24 ore, come nelle card singole.
- La linea sopra ogni entità di una card su misura si accende d'ambra quando quell'entità è
  attiva (movimento rilevato, interruttore acceso…) e di rosso per un allarme (finestra
  aperta, acqua, fumo).

## 1.7.3
- Card con orari: l'interruttore che li attiva (es. "automatica") conta. Acceso: "attiva fino
  alle…" / "si attiva alle…"; spento: "automatica spenta · orari non attivi" e fascia grigia.
- Nell'editor della card: "Gli orari valgono quando è acceso" (automatico dal nome, un
  interruttore a scelta, o nessuno).

## 1.7.2
- Card su misura: gli interruttori stanno in una colonna, uno sotto l'altro con il loro nome,
  invece di finire in fondo alle altre entità.
- Un input_boolean (es. "automatica") non conta più come "stufa accesa/spenta": lo stato viene
  solo da un interruttore, una luce o un termostato vero.
- Le card della stessa riga hanno la stessa altezza, anche tra gruppi affiancati.

## 1.7.1
- I gruppi della stanza (Luci, Clima, Prese…) restano sempre, anche dopo aver creato una card o
  cambiato l'ordine; non c'è più "Le mie card".
- Ogni card su misura va in un gruppo: si sceglie nell'editor ("Gruppo"), di base quello della
  prima entità.
- Spostare una card (trascinando o con ‹ ›) la muove dentro il suo gruppo.

## 1.7.0
- Orari, numeri, liste e testi di Home Assistant (input_datetime, time, date, input_number,
  number, input_select, select, input_text, text) si comandano dalla Casa: ora grande con
  −15 / +15, cursore, scelta dell'opzione, campo di testo.
- Card su misura: in "Modifica stanza" → "+ Nuova card" si compone una card con più entità
  (es. la stufa con accensione e spegnimento, fascia della giornata e "attiva fino alle…").
- Disposizione della stanza: card da spostare (trascinando o con ‹ ›), rinominare solo in
  HubNEX, rendere larghe o piccole, togliere; "Ordine automatico" per tornare ai gruppi.

## 1.6.0
- Vista Casa più sobria, in stile Jarvis: carattere Saira, numeri sottili, stati in minuscolo,
  card piatte e più piccole senza etichetta del tipo; una sottile linea ambra in alto quando
  una cosa è accesa, rossa quando c'è un problema.
- Cruscotto come una riga sottile; scene, interruttori e cursori più discreti; modalità del
  clima e dell'allarme come parole sottolineate; "Spegni tutte" e "Sblocca" come link.

## 1.5.1
- Le card tornano al carattere di prima (niente testo monospaziato negli stati).
- "Spegni tutte" non sposta più in basso le card delle luci rispetto alle sezioni accanto.

## 1.5.0
- Vista Casa ridisegnata in stile HUD: cruscotto in alto (persone, allarme, clima, luci,
  energia, telecamere) e scene esagonali.
- Una card per ogni tipo di entità: luci, clima con quadrante, tapparelle, valvole, media con
  copertina, avanzamento, comandi e volume, prese con il consumo del dispositivo, serrature,
  allarme, porte/finestre con "da quanto", sensori con il grafico delle ultime 24 ore, persone,
  sirene, telecamere.
- Scheda rapida della stanza con anelli di temperatura e umidità, luci come tasti, "da tenere
  d'occhio" e telecamera; sul telefono sale dal basso (trascina giù per chiudere, su per aprire).
- Serrature: con codice in Home Assistant il tastierino, altrimenti conferma nella card.
- Consumo della stanza nella pagina della stanza.

## 1.4.2
- Valvole (irrigazione, acqua): sezione propria con Apri / Chiudi (e Ferma, se la valvola lo
  permette). Prima erano trattate come tapparelle e i comandi non arrivavano.

## 1.4.1
- Scadenze: la spunta "fatto" è centrata nel suo riquadro e allineata al testo.

## 1.4.0
- Modifica stanza: si può aggiungere qualsiasi entità di Home Assistant, anche quelle nascoste
  (es. lettori di Music Assistant) o di diagnostica; le solite prima, con l'entity_id accanto.
- Persone: nella Casa compare chi è a casa, chi è fuori e in quale zona.
- Media: riproduci/pausa e volume, con titolo e artista.

## 1.3.1
- Nomi delle entità: se in Home Assistant hai dato degli alias a un'entità, la vista Casa
  mostra il primo; la ricerca per aggiungere entità trova anche gli alias.
- Documentazione: percorso consigliato per configurare tutto, nel primo avvio.

## 1.3.0
- HubNEX è visibile a tutti gli utenti di Home Assistant, non solo agli amministratori.
- Chi non è amministratore ha solo la Casa (comandi dei dispositivi, telecamere, allarme):
  assistente, posta, agenti, attività, costi e modifiche alla piantina restano agli
  amministratori. Il controllo è fatto dall'add-on su ogni richiesta. Nuova opzione
  "Utenti non amministratori" (casa / completo).

## 1.2.0
- Preferenze per utente: si possono spegnere le schede HQ e Mappa (HubNEX si apre sulla Casa)
  e l'assistente AI (niente chat, voce e approvazioni). Dentro Home Assistant valgono per
  l'account e lo seguono su tutti i dispositivi.

## 1.1.0
- Editor della piantina: carica una foto o un PDF della planimetria, sposta, ridimensiona e
  disegna le stanze con il dito o il mouse, collega ognuna a un'area di Home Assistant.
- "Proponi le stanze": Claude legge la planimetria e propone la disposizione da rifinire.
- La planimetria compare in trasparenza sotto la piantina olografica.
- Il YAML resta disponibile dal pulsante "Testo".

## 1.0.0
Prima versione pubblica.
- Assistente con team di agenti Claude configurabile in `agents.yaml` (aziende, reparti,
  agenti, istruzioni, routine spente di default, regole permanenti).
- Dashboard 3D: quartier generale, mappa neurale, nucleo animato durante la conversazione.
- Vista Casa: piantina olografica delle aree di Home Assistant, scheda rapida e pagina stanza,
  modifica delle entità (anche spostando l'area in Home Assistant), "Mostra come", telecamere
  dal vivo, allarme con tastierino.
- Connettori MCP per i programmi del lavoro, con conferma per ogni modifica.
- Posta IMAP/SMTP con smistamento e bozze da approvare.
- Gruppo Telegram con un bot per l'assistente e uno per la posta, vocali compresi.
- Voce: integrazione Assist (agente di conversazione), ElevenLabs o sintesi vocale di Home
  Assistant nella dashboard.
- Stima del credito Anthropic, eventi dalle automazioni, apertura all'avvio per singolo utente.
