# HubNEX

*Italiano · [English](https://github.com/P1pp89/HubNEX/blob/main/hubnex/DOCS.en.md)*

Il quartier generale AI per casa e lavoro: un assistente (di serie si chiama **Jarvis**) con il
suo team di agenti Claude, una dashboard 3D nella barra laterale di Home Assistant, la plancia
della casa, il gruppo Telegram, la voce e i connettori per i programmi del tuo lavoro.

## Primo avvio

1. In **Configurazione** usa la chiave API Anthropic predefinita oppure la modalità abbonamento personale qui sotto. Avvia l'add-on e attiva **Mostra nella barra laterale**.

### Abbonamento Claude personale (un solo utente)

Imposta `claude_auth_mode` su `subscription`, attiva `claude_subscription_enabled` e riavvia l'add-on. Apri HubNEX → Preferenze → Accesso Claude → **Accedi a Claude**. Il browser non si apre da solo dall'add-on: premi **Apri la pagina di accesso Claude** e, se richiesto, incolla il codice nel campo subito sotto il link. L'add-on usa la CLI Claude Code originale di Anthropic e conserva il suo accesso in `/data`; HubNEX non riceve password o cookie del browser. Controlla che lo stato sia **Collegato** prima di usare l'AI.

Per usare la chiave API solo come riserva, scegli `hybrid`, attiva `claude_api_fallback` e inserisci `anthropic_api_key`. La riserva interviene solo se la CLI o il suo accesso non sono disponibili. Le chiamate API hanno una fatturazione separata su Anthropic Console; l'abbonamento ha i limiti d'uso di Claude Code. Il riquadro Spesa conta le chiamate API, non quelle in abbonamento. Questa modalità è destinata a un proprietario che usa il proprio account, non a più utenti di Home Assistant.
Claude Code mostra l'avanzamento degli agenti, ma la CLI non espone gli stessi riassunti dei pensieri visibili del percorso API diretto.
2. Apri **HubNEX** dalla barra laterale: vedi il quartier generale con l'assistente e gli agenti.
3. Scrivigli nella chat in basso. Per la casa usa già Home Assistant: non serve creare token,
   l'add-on accede tramite il Supervisor.
4. Racconta chi sei e come lavori in `agents.yaml` (sotto): più sa, più è utile.

Tutto il resto è facoltativo e si aggiunge quando vuoi, in quest'ordine consigliato:

| Cosa | Dove | Sezione |
| --- | --- | --- |
| Il tuo team, la tua azienda | `agents.yaml` | Il team |
| Piantina della casa | Casa → ⚙ Piantina | Vista Casa |
| Parlare con Assist (app, speaker) | integrazione HubNEX + Assistenti vocali | Voce |
| Voce nella dashboard | opzione *Voce da Home Assistant* o ElevenLabs | Voce |
| Gruppo Telegram | opzioni dei bot | Il gruppo Telegram |
| Posta di lavoro | opzioni IMAP/SMTP | Posta di lavoro |
| I programmi del lavoro | `connectors` in `agents.yaml` | Connettori |
| Tablet o telefono fuori da HA | Token HQ e porta | Usarla fuori da Home Assistant |

Ogni opzione della scheda **Configurazione** ha la sua spiegazione accanto al campo.

## Il team: `agents.yaml`

Al primo avvio viene creato `agents.yaml` nella cartella di configurazione dell'add-on,
`/addon_configs/<id>_hubnex/agents.yaml`. Lo apri con l'add-on **File editor** o **Studio Code
Server**, oppure via Samba nella condivisione `addon_configs`. Dopo una modifica **riavvia
l'add-on**.

- `boss`: l'assistente che coordina tutto: nome, carattere, istruzioni, strumenti.
- `companies`: le tue "aziende" (il lavoro, la casa, un'associazione…), con reparti e agenti.
  Ogni agente ha un ruolo, istruzioni e gli strumenti che può usare.
- `connectors`: i programmi del tuo lavoro (vedi **Connettori**).
- Routine: compiti che un agente fa da solo a orari fissi. Sono **spente** finché non scrivi
  `enabled: true`.

Il file d'esempio è commentato riga per riga.

## Connettori: i programmi del tuo lavoro

HubNEX si collega ai programmi che usi al lavoro (gestionale, calendario, CRM, Notion,
database…) tramite **MCP** (Model Context Protocol), lo standard aperto per collegare le AI ai
programmi. Molti software hanno già un "server MCP", e chi sviluppa un gestionale può
aggiungerne uno.

In `agents.yaml`:

```yaml
connectors:
  - name: Gestionale                    # nome mostrato a te e agli agenti
    url: https://esempio.it/mcp         # indirizzo del server MCP
    token: la-tua-chiave                # se il server la chiede (Authorization: Bearer …)
    agents: [boss, tecnico]             # chi lo può usare (omesso = tutti; boss = l'assistente)
```

HubNEX legge da solo quali strumenti offre il programma e li dà agli agenti indicati.

- Gli strumenti che **leggono** li usano liberamente.
- Quelli che **modificano** i dati non partono subito: ti vengono mostrati con un riepilogo e
  **✅ Conferma / ❌ Annulla**, nel gruppo Telegram e nel pannello "Da approvare" della
  dashboard. Partono solo dopo il tuo ok, una volta sola anche se premi due volte.
- Come lo capisce: il server dichiara quali strumenti sono di sola lettura. Se non lo dichiara,
  sono di sola lettura quelli che iniziano con `get`, `list`, `search`, `read`, `find`… e tutti
  gli altri chiedono conferma. Puoi correggere con `free: [nome]` (mai conferma) e
  `always_confirm: [nome]` (sempre), oppure `confirm: always` per l'intero connettore.
- `/stato` nel gruppo Telegram dice se ogni connettore risponde e quanti strumenti offre; gli
  errori compaiono anche nell'attività della dashboard.

## Voce

Puoi parlare con l'assistente in tre modi. Tutti sono facoltativi.

**1. Assist di Home Assistant** (app, smart speaker, parola di attivazione)

L'add-on installa da solo l'integrazione **HubNEX**, che rende l'assistente un *agente di
conversazione* di Assist. Il riconoscimento e la voce li fa Home Assistant, con il motore che
preferisci: Piper (locale e gratuito), Home Assistant Cloud, ElevenLabs, Google…

1. Avvia l'add-on: arriva una notifica. **Riavvia Home Assistant**.
2. Impostazioni → Dispositivi e servizi: compare **HubNEX rilevato** → *Configura* → *Invia*.
3. Impostazioni → Assistenti vocali → il tuo assistente → **Agente di conversazione**: scegli
   l'assistente di HubNEX e lascia attivo **"Preferisci gestire i comandi localmente"**: i
   comandi semplici ("accendi la luce della cucina") li esegue Home Assistant, subito e senza
   consumare credito; tutto il resto va all'assistente.

Se l'integrazione non viene rilevata: Dispositivi e servizi → Aggiungi → "HubNEX", con
l'indirizzo dell'add-on (`http://<hostname dell'add-on>:8765`, l'hostname è nella pagina
dell'add-on) e il **Token HQ**. Di solito basta riavviare l'add-on HubNEX.

Le risposte a voce sono brevi (al massimo due frasi). Ogni richiesta, da Assist o dalla
dashboard, segue la strada più veloce possibile:

1. **Home Assistant da solo** ("accendi la luce della cucina"): istantaneo, senza AI. Assist lo
   fa già; la dashboard lo prova per prima. Esponi le entità ad Assist e dai loro un alias con
   il nome che pronunci. Serrature, allarme e porte non passano mai di qui.
2. **La via rapida** per le altre richieste sulla casa: il **Modello per i comandi rapidi** (di
   serie Haiku) con l'elenco delle entità e del loro stato già in mano. Nella chat, sotto la
   risposta, compare la scritta RISPOSTA RAPIDA (o HOME ASSISTANT per il punto 1).
3. **Jarvis** con il suo modello e tutte le istruzioni per tutto il resto: domande complesse,
   lavoro, agenti, serrature e allarme (con la conferma).

**2. Dashboard** (microfono e altoparlante nella barra in basso)

- Quello che dici lo riconosce il browser (gratis). I browser lo permettono solo su `https://`:
  funziona dall'app di Home Assistant e da Nabu Casa, non da `http://homeassistant.local`.
- L'assistente risponde con la voce scelta nella configurazione:
  - **Voce da Home Assistant**: scrivi un motore di sintesi vocale di Home Assistant, per
    esempio `tts.piper` (locale, gratuito) o `tts.home_assistant_cloud`. Ha la precedenza.
    In **Voce del motore di Home Assistant** puoi scegliere la voce per nome (per esempio
    `Rinaldo` o `Diego` con Home Assistant Cloud): se il nome non esiste, il messaggio d'errore
    elenca quelle disponibili. La lingua è quella di Home Assistant;
  - oppure **ElevenLabs**: chiave API (elevenlabs.io → Profilo → API Keys), ID della voce
    (Voices → la voce → ID) e modello (`eleven_flash_v2_5`, il più economico, parla italiano).
- Se la voce non parte, sotto la risposta compare il motivo.
- Prima di leggere, il testo viene preparato per l'ascolto: niente simboli, emoji o link,
  unità e sigle in parole (Ω → "ohm", kW → "chilowatt", MT/BT → "media e bassa tensione"),
  date per esteso, una pausa per ogni punto di un elenco. Lo scritto resta com'è.
- **Risposte a voce**: `completa` (la voce legge tutta la risposta) oppure `riassunto`: per le
  risposte lunghe la voce dice solo il succo in una o due frasi e il testo scritto resta
  completo. Le risposte brevi vengono lette per intero. Vale per la dashboard con
  l'altoparlante acceso e per i vocali di Telegram; Assist risponde già in due frasi.

**3. Telegram**: mandi un vocale, viene trascritto con ElevenLabs e l'assistente risponde anche
a voce (`telegram_voice_replies`). La trascrizione dei vocali richiede ElevenLabs.

**Note su ElevenLabs (piano gratuito):** le voci prese dalla libreria pubblica non si possono
usare tramite API; l'account può essere bloccato per "attività insolita" anche con caratteri
disponibili. In questi casi il messaggio d'errore lo dice.

## Il gruppo Telegram

Un gruppo con **un bot per l'assistente** e, facoltativo, **uno per l'agente della posta**. Gli
agenti senza un bot proprio parlano tramite l'assistente, con il loro nome davanti.

1. Crea i bot con @BotFather (`/newbot`) e disattiva la privacy di gruppo (*Bot Settings →
   Group Privacy → Turn off*), poi aggiungili a un gruppo.
2. Metti i token nella configurazione, avvia e scrivi `/id` nel gruppo: ti dice l'ID del gruppo
   (numero negativo, `allowed_chat_id`) e il tuo (`allowed_user_id`). I bot ignorano tutti gli
   altri.

Uso:

- Messaggio normale → risponde l'assistente, che fa da sé o delega. L'agente a cui delega
  risponde direttamente nel gruppo.
- Rispondi a un messaggio dell'agente della posta, o scrivi `@nome_bot_mail` → risponde lui.
- Rispondi a una **bozza** con cosa cambiare ("più formale") → arriva la nuova versione.
- Comandi: `/id`, `/stato`, `/posta` (controlla subito la posta), `/regole`.

Un bot può essere ascoltato da un solo programma: due installazioni con gli stessi token vanno
in conflitto.

## Allegati: foto e documenti

Puoi mandare all'assistente e agli agenti **foto, PDF e file di testo** (txt, csv, md, json):
utile, per esempio, dal cantiere.

- **Telegram**: invia una foto, un album o un file, con la richiesta nella didascalia ("guarda
  questa crepa: è da preoccuparsi?"). Oppure rispondi a una foto già inviata con la domanda. Come
  per i messaggi, va all'assistente; per un agente con un bot suo, rispondi a un suo messaggio o
  scrivi `@nome_bot` nella didascalia. Senza testo, l'assistente guarda e ti chiede cosa serve.
- **Dashboard**: la graffetta accanto al campo della chat (dal telefono anche la fotocamera); puoi
  anche incollare uno screenshot o trascinare i file sulla chat. Le foto grandi vengono
  rimpicciolite prima dell'invio, per consumare meno dati.
- **API**: `POST /api/attachments?name=foto.jpg` con il file come corpo → `{"id": …}`; poi
  `"attachments": ["id"]` in `/api/chat` o in `/api/agents/{id}/task`.

L'assistente vede gli allegati e, quando delega un lavoro, li passa all'agente insieme al
compito. La conversazione ne conserva solo una nota con il loro codice (`#1a2b3c4d`): le foto non
si pagano di nuovo a ogni messaggio e chiunque del team può riguardarle quando servono ("nella
foto di prima…").

Limiti: 20 MB per file (lo stesso limite dei bot Telegram), PDF fino a 100 pagine, 10 allegati
per messaggio. Le foto sono ruotate come scattate e ridotte a 1568 pixel sul lato lungo (quello
che Claude legge comunque). Word ed Excel non si leggono direttamente: salvali in PDF (o CSV per
un foglio). Ogni foto costa circa quanto 1.500 parole di testo; un PDF circa 1.500–3.000 per
pagina. Gli allegati restano 30 giorni in `/data/allegati`, poi vengono cancellati.

## Posta di lavoro

Imposta IMAP/SMTP del tuo provider (server, porte SSL 993/465, utente, password).

- Ogni `check_interval_minutes` controlla la casella, classifica le nuove email (alta, media,
  bassa) e ti avvisa da `notify_min_priority` in su. Le email non vengono segnate come lette.
- **Mittenti da non segnalare** (`mail_ignore`): separati da virgola, un indirizzo
  (`offerte@negozio.it`), un dominio (`@newsletter.it`) o una parola dell'indirizzo (`noreply`).
  Le loro email restano nella casella e Jarvis Mail le legge se glielo chiedi, ma non arriva
  nessun messaggio su Telegram e non vengono nemmeno classificate (niente credito Claude).
- **Niente parte senza di te**: ogni risposta è una bozza con Invia, Salva in Bozze, Modifica,
  Scarta, su Telegram e nella dashboard.
- **Firma**: puoi incollare quella in HTML del tuo programma di posta.
- Nelle istruzioni dell'agente della posta elenca i tuoi **clienti importanti**: le loro email
  hanno priorità alta.

## Vista Casa

Il pulsante **⌂ Casa** apre la plancia di Home Assistant. In alto il **cruscotto**: chi è in
casa, allarme, clima medio, luci accese, energia e telecamere; sotto le scene. Ogni entità ha la
sua **card**: luci (tocca la card, barra della luminosità; se la lampadina li ha, il pallino
accanto allo stato apre temperatura colore e colori), clima con quadrante, tapparelle con la
finestra disegnata, valvole, media con copertina, avanzamento, casuale/ripeti, volume e sorgente, **robot
aspirapolvere** con la sua mappa (dove il robot si vede muovere), stato, batteria e comandi,
prese con il consumo, porte e finestre
(rosse quando aperte, "da quanto"), sensori con il grafico delle ultime 24 ore, persone,
telecamere. Le **serrature** con un codice in Home Assistant chiedono il codice sul tastierino,
le altre una conferma nella card; l'**allarme** si disinserisce con il tastierino. Le **stanze sono le aree di Home
Assistant**: le entità di un'area (o del suo dispositivo) compaiono da sole nella stanza.

Intorno alla piantina, a colpo d'occhio:

- **Meteo** nel cruscotto: condizione, temperatura, minima/massima e pioggia; un tocco apre le
  previsioni dei prossimi giorni, con umidità e vento. Usa l'entità `weather.*` di Home Assistant.
- **Oggi e prossimi giorni**: le scadenze tue e degli agenti nei prossimi 7 giorni, con la spunta
  per chiuderle. Lo vedi solo tu: gli utenti di Home Assistant con accesso alla sola casa no.
- **Sulla piantina**, sotto il nome della stanza: una persona dove c'è presenza o movimento, una
  nota dove suona qualcosa, il robot dove pulisce, una lavatrice dove lavatrice o lavastoviglie
  sono in funzione.
- **Elettrodomestici**: lavatrice, lavastoviglie, asciugatrice, forno e bollitore con una presa
  che misura la potenza (riconosciuti dal nome): "in funzione" e, per 3 ore, "finito … fa".
- **Ultimi eventi**: le ultime variazioni delle ultime 24 ore di porte, finestre, serrature,
  allarme e persone.

**Scorte (pellet e simili).** Un aiutante *Numero* o un *Contatore* di Home Assistant con
"pellet", "sacchi" o "scorta" nel nome diventa una card **Scorta**; per gli altri scegli
"Scorta" nel tipo, modificando la stanza. Mostra quanti ne restano, quanti se ne usano al giorno
e da quando (dallo storico degli ultimi 30 giorni), i **giorni rimasti** e l'ultima consegna;
**−1 caricato** quando ne usi uno, **+consegna** quando arriva il pellet. In **Imposta** scegli
quanti ne arrivano in una consegna e sotto quanti avvisarti: allora la card diventa rossa e
arriva la notifica **Scorte da riordinare** (regola nelle Notifiche della casa).

**Card libera.** Con **Modifica stanza → + Card libera** costruisci una card a blocchi su una
griglia da 4 colonne (2 sul telefono). Blocchi: **valore grande**, **indicatore ad anello**,
**interruttore**, **pulsante** (scena, script, pulsante), **cursore** (luminosità o numero),
**grafico** delle ultime 24 ore, **barra**, **fascia oraria** (un orario di inizio e uno di fine),
**selettore**, **stato** (com'è e da quanto) e **testo**. Per ogni blocco scegli l'entità (la
ricerca propone solo quelle adatte), un'etichetta, la dimensione (da 1×1 a 4×2) e, per anello e
barra, minimo e massimo; **Prima/Dopo** lo spostano. La card ha un nome, un colore e uno stile
(**Pulito**, di partenza: i blocchi direttamente sulla card; **Riquadri**: ognuno nel suo); al centro
dell'editor vedi l'anteprima con i valori veri. Si riapre con **Modifica**.

Altri blocchi: **media** (copertina, titolo, comandi e volume), **telecamera** (dal vivo, un tocco
la apre in grande) e **Domanda a Jarvis** (una domanda pronta: un tocco la manda in chat). Per
ogni blocco puoi anche impostare:

- **Colore secondo il valore**: fino a 4 regole, es. "sopra 23 → rosso", "sotto 19 → azzurro",
  "uguale a open → arancio";
- **Mostra solo se**: il blocco compare solo quando un'entità vale qualcosa (es. la TV "uguale a
  playing"); nell'editor resta visibile, sbiadito;
- **Al tocco**: accendi/spegni, avvia una scena o uno script, chiedi a Jarvis, apri un'altra stanza.

I valori sono quelli di Home Assistant: `on`, `off`, `open`, `playing`… oppure un numero. Per
partire veloce ci sono i **modelli** (Stufa, Ingresso, Lavanderia, Clima stanza, Energia, Musica),
che prendono le entità adatte della stanza; i blocchi si spostano anche **trascinandoli**.

La **linea in alto** di ogni card (libera o composta) si accende da sola: arancione quando qualcosa
è acceso o un sensore rileva, rossa per un allarme (porta o finestra aperta, acqua, fumo, gas). In
una card con un interruttore principale, come la stufa, decide lui; le regole di colore impostate
a mano si aggiungono a queste.

**Descrivila a Jarvis**: in cima all'editor scrivi cosa vuoi ("la stufa con temperatura,
accensione, orari e pellet; rossa sopra 23 gradi") e tocca **Crea**: Jarvis compone la card con
le entità vere della casa (quelle che non esistono vengono scartate) e la apre nell'editor, da
controllare e salvare. È una richiesta a Claude, pochi centesimi.

**Esporta / Importa card**: **Esporta** copia la card come testo, da condividere; **Modifica
stanza → Importa card** la incolla in un'altra casa, e i blocchi con entità che lì non ci sono
restano da scegliere. Nelle condizioni e nelle regole, con "uguale a" e "diverso da", il valore
si sceglie da un elenco (acceso/spento, aperta/chiusa, in riproduzione…).

**Aggiungere entità.** Con **Modifica stanza → Aggiungi entità** puoi mettere in una stanza
qualsiasi entità di Home Assistant, anche senza area o di un tipo che HubNEX non disegna
(compare con il suo stato). Gli aiutanti nascono senza area: assegnala in Home Assistant oppure
aggiungili da qui.

- **Piantina**: **⚙ Piantina** apre l'editor.
  1. **Carica planimetria**: una foto o un PDF della pianta (i margini bianchi vengono
     tolti da soli). Resta solo nella cartella dell'add-on.
  2. **Proponi le stanze**: Claude guarda la pianta e propone le stanze, già collegate alle
     aree di Home Assistant quando il nome corrisponde (una richiesta, pochi centesimi).
  3. Sistema a mano: trascina una stanza per spostarla, l'angolo in basso a destra per
     ridimensionarla, trascina sul vuoto (o **+ Stanza**) per disegnarne una nuova. Nel
     pannello scegli l'area, oppure "solo disegno" per un ambiente senza entità; **contorno**
     per balconi e terrazzi. Spunta le aree **Fuori casa** (giardino, parcheggio…).
  4. **Salva piantina**. Con **+ Piano** aggiungi altri piani.

  Chi preferisce può usare **Testo** e scrivere la disposizione in YAML (posizioni `x, y, w, h`
  in percentuale del disegno); facoltativo `energy: { power: sensor.…, today: sensor.… }`.
  Tutto finisce in `casa.yaml` nella cartella dell'add-on; senza piantina le aree compaiono
  come riquadri.
  ```yaml
  floors:
    - name: Piano terra
      aspect: 1.2          # larghezza / altezza del disegno
      rooms:
        - { area: Soggiorno, x: 0, y: 0, w: 50, h: 60 }
        - { area: Cucina, x: 50, y: 0, w: 50, h: 60 }
        - { area: Camera da letto, x: 0, y: 60, w: 100, h: 40 }
  outside: [Giardino]
  ```
- **Nomi**: se a un'entità hai dato degli **alias** in Home Assistant (impostazioni
  dell'entità → Alias), HubNEX mostra il primo; altrimenti il nome di Home Assistant. Nella
  ricerca per aggiungere entità valgono tutti i nomi.
- **Energia**: tocca "Energia" nel cruscotto: si apre un popup (F1 arancione, F2 blu, F3 verde). Tre viste a scelta, anche insieme: **il reattore**
  (il periodo diviso per fascia attorno alla potenza adesso, in % del contatore), **la
  giornata** (la potenza di oggi sulle fasce, con i kWh per fascia) e **la bolletta** (spesa,
  stima a fine periodo al ritmo attuale, fasce a confronto col periodo precedente e un
  consiglio quando una fascia cresce). Con **Configura** scegli le viste e i tuoi sensori: la
  fascia (calendario ARERA calcolato da HubNEX con i festivi, un tuo sensore, o tariffa unica),
  i kWh per fascia (es. i contatori "utility meter" di Home Assistant: da loro arrivano inizio
  del periodo e confronto), prezzi o spesa, la potenza e la taglia del contatore, altri valori
  (tensione, fattore di potenza…). Nessun calcolo usa l'AI.
- **Persone**: le persone di Home Assistant (Impostazioni → Persone, con l'app sul telefono o un
  dispositivo di tracciamento) compaiono in alto nella Casa: *a casa*, *fuori* o il nome della
  zona in cui si trovano.
- **Orari e impostazioni**: gli helper di Home Assistant si usano dalla Casa. Un orario
  (`input_datetime`, `time`) si cambia toccando l'ora o con −15 / +15; i numeri con il cursore,
  le liste scegliendo l'opzione, i testi scrivendo. Il valore lo salva Home Assistant e le
  automazioni lo usano come prima.
- **Card su misura**: in *Modifica stanza* → **+ Nuova card** dai un nome, aggiungi le entità
  (anche di altre stanze), le metti in ordine, scegli il **gruppo** (Clima, Luci…; di base
  quello della prima entità) e piccola o larga. Esempio: una card
  "Stufa" con l'ora di accensione e di spegnimento mostra anche la fascia sulla giornata e
  "attiva fino alle 22:00"; se nella card c'è l'interruttore che attiva gli orari (es.
  "automatica", si sceglie nell'editor), da spento la card dice "orari non attivi". I sensori numerici mostrano il grafico delle
  ultime 24 ore: nell'editor lo spegni con l'interruttore "grafico", sulle card singole con
  "Togli grafico" in modifica. Sempre in modifica ogni card si sposta dentro il suo gruppo
  (trascinando ⋮⋮ o con ‹ ›), si rinomina solo in HubNEX, diventa larga o piccola, si toglie;
  *Ordine automatico* rimette l'ordine di partenza. Tutto resta in HubNEX: in Home Assistant non cambia nulla.
- **Stanza**: toccala per la scheda rapida, **Apri stanza** per tutte le entità divise per
  tipo. Con più sensori di temperatura scegli quale usare ("temperatura da").
- **Modifica stanza**: aggiungi **qualsiasi entità** di Home Assistant (anche quelle che Home
  Assistant nasconde, come i lettori nascosti da Music Assistant), spostando l'area anche in Home
  Assistant (consigliato) o solo nella plancia; **Togli** la nasconde solo dalla plancia; **Mostra come** cambia il
  tipo (Luce, Presa / interruttore, Cancello / porta a impulso, Sirena, Solo stato). Per un relè
  che accende una luce è ancora meglio "Mostra come → Luce" nelle impostazioni dell'entità in
  Home Assistant: così anche Assist e l'assistente la trattano da luce.
- **Media**: accendi e spegni, ▶ / ❚❚ e volume.
- **Telecamere**: le miniature nelle stanze sono **dal vivo** (fino a 3 alla volta, le altre si
  aggiornano ogni 5 secondi); toccandone una si apre grande, subito dal vivo, e dentro Home
  Assistant passa al suo video in alta qualità. In una **card composta** con una telecamera e i
  suoi sensori (un veicolo, una persona, il movimento), i sensori compaiono sopra l'immagine e si
  accendono in rosso quando scattano. Il pulsante **Telecamere** in alto le mostra tutte.
- **Allarme**: pulsante in alto con lo stato; In casa / Fuori / Notte e Disinserisci con
  tastierino per il codice.
- I comandi della vista Casa vanno diretti a Home Assistant e **non usano credito Claude**.

## Notifiche della casa

HubNEX controlla la casa da solo e ti avvisa quando qualcosa non va. **Non usa Claude**: sono
regole fisse sugli stati di Home Assistant, quindi gli avvisi sono immediati e gratis. Si
configurano in ⚙ Preferenze → **Notifiche della casa**.

| Regola | Quando avvisa |
|---|---|
| Perdite, fumo, gas | Un sensore di acqua, fumo, gas o monossido scatta: subito, anche nelle ore di silenzio |
| Finestre aperte | Una finestra resta aperta con il riscaldamento o il condizionatore acceso, o mentre piove |
| Casa vuota | Tutte le persone sono fuori e una porta, il cancello o una serratura sono aperti. Pulsante **Chiudi** |
| Consumo alto | La potenza della casa (il sensore scelto in Energia) resta sopra la soglia |
| Luci accese di notte | Luci ancora accese nella fascia notturna (23:30–06:00 di serie). Pulsante **Spegni** |
| Batterie scariche | Sensori con la batteria sotto il 15% |
| Dispositivi non raggiungibili | Dispositivi che non rispondono da più di un'ora |

**Dove arrivano**, regola per regola:

- **App** di Home Assistant sul telefono: notifica push con i pulsanti. HubNEX trova da solo i
  telefoni con l'app; puoi escluderne qualcuno. Gli avvisi urgenti arrivano con priorità alta.
- **Telegram**, nel gruppo di Jarvis, con gli stessi pulsanti.
- **Home Assistant**: le notifiche nella campanella.

Come si comportano:

- ogni regola aspetta che il problema duri qualche minuto (lo scegli tu), così una finestra
  aperta per un attimo non disturba;
- avvisa **una volta** per problema; se nel frattempo se ne aggiunge un altro (una seconda
  finestra) aggiorna l'avviso;
- quando il problema si risolve, la notifica sul telefono e nella campanella **sparisce da
  sola**, e su Telegram spariscono i pulsanti;
- nelle **ore di silenzio** gli avvisi aspettano la fine della fascia (tranne perdite, fumo e
  gas);
- **agisce solo se premi un pulsante** della notifica. Senza il tuo tocco non cambia nulla.

In ogni regola, «Controlla N di N» elenca le entità che guarda: togli la spunta a quelle da
ignorare (per esempio un sensore di umidità del terreno visto come perdita d'acqua). **Invia una
prova** manda una notifica su tutti i canali in uso.

## Mappa neurale

Il pulsante **✺ Mappa** mostra la "mente" del team in 3D: l'assistente al centro, aziende,
reparti e agenti, e intorno tutto ciò che il team sa (memorie, compiti, scadenze, bozze),
collegato a chi l'ha prodotto e alle parole chiave in comune. Cerca un nome per evidenziare
tutto quello che lo riguarda.

## Niente iniziative senza il tuo ordine

- Le routine sono spente finché non scrivi `enabled: true`. Anche accese, **non possono
  cambiare nulla in casa**, e lo stesso vale per gli eventi delle automazioni: guardano e ti
  scrivono cosa propongono.
- Gli agenti fanno solo il compito ricevuto; il resto lo propongono.
- Le modifiche ai programmi collegati e le email partono solo dopo la tua conferma.
- **Le tue regole**: quando dici all'assistente qualcosa che deve valere sempre ("non fare
  mai…", "d'ora in poi…"), la salva come regola per **tutto** il team. `/regole` le elenca.

## Usarla fuori da Home Assistant

**Con Nabu Casa** (consigliato): apri HubNEX dalla barra laterale, copia l'indirizzo e
aggiungilo alla schermata Home del telefono.

**Solo in rete locale**: imposta un **Token HQ**, scrivi `8765` nella porta (Configurazione →
Rete), riavvia e apri `http://IP-DI-HOME-ASSISTANT:8765`. Puoi installarla come app dal menu del
browser.

**Aprire HubNEX all'avvio di Home Assistant**: dentro Home Assistant, in alto **⚙** →
interruttore. Vale solo per il tuo account; gli altri utenti restano sulla loro plancia.

**Lingua**: la dashboard è in italiano o in inglese, secondo la lingua di Home Assistant di chi
la apre (non italiano = inglese). In alto **⚙ → Lingua** si sceglie a mano, solo per quel
browser. Jarvis, gli agenti, Telegram e i messaggi dell'add-on seguono l'opzione **Lingua**
nella configurazione (auto = quella di Home Assistant).

**Tema chiaro, per leggere al sole**: in alto **⚙ → Tema**. **Automatico** segue il telefono
(chiaro di giorno se il telefono è in chiaro), **Chiaro** e **Scuro** lo fissano. Vale per la
Casa: HQ e Mappa restano scuri. La scelta resta su quel dispositivo, così il telefono può
essere chiaro e il tablet a muro scuro.

**Solo la Casa, per chi vuole solo accendere una luce**: in alto **⚙** → spegni **Schede HQ e
Mappa** (HubNEX apre direttamente la Casa) e/o **Assistente AI** (spariscono chat, voce e
approvazioni: nessun credito Claude). Dentro Home Assistant la scelta è salvata con l'account
di chi è collegato e vale su tutti i suoi dispositivi; fuori resta nel browser. È una comodità,
non un blocco: chiunque può riaccenderle dallo stesso menu.

**Utenti non amministratori**: HubNEX compare nella barra laterale di **tutti** gli utenti di
Home Assistant. Chi non è amministratore ha solo la **Casa**: luci, clima, tapparelle, scene,
telecamere e allarme (con codice), come in Home Assistant. Non vede l'assistente, la posta, gli
agenti, l'attività e i costi, e non può modificare piantina e stanze. Il controllo lo fa l'add-on
a ogni richiesta, non solo l'interfaccia. Per dare tutto anche a loro: opzione
**Utenti non amministratori → completo**.

## Eventi dalle automazioni

Le automazioni possono passare un evento all'assistente, che ti scrive cosa propone. Con un
**Token HQ**, in `configuration.yaml`:

```yaml
rest_command:
  hubnex_event:
    url: "http://<hostname dell'add-on>:8765/api/ha/event"
    method: POST
    headers:
      Authorization: "Bearer IL_TUO_TOKEN_HQ"
    content_type: "application/json"
    payload: '{"message": "{{ message }}"}'
```

## Sicurezza

- Dalla barra laterale accedi solo tu, perché passi dal login di Home Assistant.
- La porta 8765 è chiusa di default; se la apri serve il **Token HQ**.
- I servizi in **Servizi HA bloccati** (serrature, disinserimento allarme) l'assistente non li
  chiama mai da solo; dalla plancia puoi farlo tu, con conferma o codice.
- Le chiavi stanno solo nella configurazione dell'add-on e in `agents.yaml`, sul tuo Home
  Assistant.

## Altri fornitori AI: OpenAI e modelli locali

Claude resta il consigliato, ma Jarvis e ogni agente possono usare anche **OpenAI** o un
**modello locale** (Ollama, LM Studio), gratis e senza cloud. Il modello si sceglie per nome,
con il prefisso del fornitore:

| Scrivi | Fornitore | Opzioni da compilare |
|---|---|---|
| `claude-sonnet-5-5` | Anthropic (come prima) | Chiave API Anthropic |
| `openai:gpt-5-mini` | OpenAI | Chiave API OpenAI |
| `ollama:qwen3:14b` | Ollama, sul tuo computer o server | Indirizzo di Ollama, es. `http://192.168.1.20:11434` |
| `compat:nome-modello` | Qualsiasi servizio compatibile con OpenAI: LM Studio, OpenRouter, Gemini, Mistral, DeepSeek, Groq | Indirizzo (fino a `/v1`) e, se serve, chiave |

Si scrive in **Modello di Jarvis**, **Modello di Jarvis Mail** e **Modello per i comandi
rapidi**, oppure per un singolo agente in `agents.yaml` con `model: ollama:qwen3:14b`. Si
possono mescolare: per esempio Jarvis su Claude e la posta su un modello locale gratuito. Se
usi solo altri fornitori, la chiave Anthropic può restare vuota.

Esempi di indirizzi per `compat`:

- LM Studio: `http://IP-DEL-PC:1234/v1`
- OpenRouter: `https://openrouter.ai/api/v1` (modelli come `compat:openai/gpt-5-mini`)
- Gemini: `https://generativelanguage.googleapis.com/v1beta/openai` (modelli come `compat:gemini-2.5-flash`)

**Cosa cambia rispetto a Claude**

- La **ricerca web** c'è solo con Claude. La **lettura di una pagina** da un link (`web_fetch`)
  la fa HubNEX stesso e funziona con tutti, solo su indirizzi pubblici.
- Le **foto** arrivano ai modelli che le vedono; i **PDF** arrivano come testo.
- I **pensieri** di Jarvis nella vista 3D compaiono solo con Claude.
- **Spesa**: i modelli di Ollama costano zero. Per quelli `openai` e `compat` scrivi il prezzo
  del listino in **Prezzo input/output altri modelli** ($ per milione di token), altrimenti non
  vengono contati. Il **credito Anthropic** scala solo le chiamate a Claude.
- **Qualità**: Jarvis usa molti strumenti (casa, memoria, team). I modelli locali piccoli li
  usano peggio: per un uso vero servono modelli da almeno 14 miliardi di parametri che
  supportano gli strumenti (qwen3, llama3.1, mistral-small). Con quelli più piccoli, meglio
  affidargli solo agenti semplici, come la posta.

## Credito Anthropic

Il riquadro **Credito Claude** è una **stima**: in `anthropic_credit_usd` scrivi il saldo che
vedi su console.anthropic.com → Billing e HubNEX scala il costo di ogni richiesta. Sotto 1 $
ricevi un avviso. Con `0` vedi solo quanto hai speso.

### Storico della spesa

Clic sul riquadro **Spesa/Credito Claude** in HQ (sul telefono: ⚙ Preferenze → **Spesa Claude**)
per aprire lo storico:

- **oggi**, **questo mese** e la **stima a fine mese**, calcolata sul ritmo dei giorni passati;
- una barra per giorno negli ultimi 7, 30 o 90 giorni (passaci sopra per cifra e chiamate);
- la spesa **per agente** (Jarvis, Jarvis Mail, gli agenti del team, la proposta della
  piantina) e **per modello** (Sonnet, Haiku…), con le chiamate e i token.

Con `monthly_budget_usd` imposti un budget mensile: all'80% e al 100% ricevi un avviso nel
gruppo Telegram e nelle notifiche di Home Assistant, e nel popup compare la barra del budget.
È solo un avviso: HubNEX non si ferma. Lo storico parte dall'installazione di questa versione
ed è incluso nel backup.

Le cifre sono la stima di HubNEX con i prezzi di listino di ogni chiamata: il conto esatto è su
console.anthropic.com.

Per spendere poco: l'agente della posta usa il modello economico; con Assist i comandi semplici
li fa Home Assistant; le routine e le ricerche web consumano, usale quando servono. In
`agents.yaml`, per Jarvis e per ogni agente:

- `effort: medium` invece di `high`: ragiona ancora, ma si dilunga meno;
- `max_searches: 3`: al massimo 3 ricerche web per richiesta invece di 5. Ogni ricerca porta
  dentro pagine di risultati, che poi vengono rilette a ogni passaggio;
- quando cambi argomento in chat, chiudi la conversazione (×): le domande nuove non si
  trascinano dietro gli ultimi scambi.

## Dati e backup

Memoria, scadenze, bozze, regole e cronologia sono in `/data/hubnex.db`; `agents.yaml` e
`casa.yaml` nella cartella di configurazione dell'add-on. Finiscono tutti nei backup di Home
Assistant.

### Backup di HubNEX e trasferimento su un'altra installazione

Da **⚙ Preferenze → Backup → Scarica** ottieni un unico file `.zip` con tutto ciò che HubNEX
sa: memoria e mappa neurale, scadenze, chat, impostazioni della Casa (card, nomi, ordine,
energia), piantina con le sue immagini e `agents.yaml`. Le opzioni dell'add-on (chiave Anthropic,
Telegram, posta) **non** sono incluse; `agents.yaml` sì, con gli eventuali token dei connettori
MCP: custodisci il file come una password. Solo per gli amministratori.

**Ripristina → Carica…** su un'altra installazione mette tutto al suo posto e riavvia HubNEX.
I file che sostituisce restano accanto con il suffisso `.prima-del-ripristino`.

Per passare da una copia locale (`/addons/local`) all'add-on del repository:

1. Nella copia locale: **Preferenze → Backup → Scarica**.
2. Nella pagina dell'add-on locale: **Configurazione → ⋮ → Modifica in YAML**, copia tutto
   (sono le tue opzioni e chiavi) e **arresta** l'add-on locale.
3. Installa HubNEX dal repository, apri **Configurazione → ⋮ → Modifica in YAML**, incolla,
   salva e avvia.
4. Apri HubNEX: **Preferenze → Ripristina → Carica…** e scegli il backup. HubNEX si riavvia
   con i tuoi dati.
5. Assist: in **Dispositivi e servizi** elimina la vecchia integrazione HubNEX, poi
   **riavvia l'add-on HubNEX**: compare "HubNEX rilevato", premi *Configura* (nessun token da
   inserire).
6. Quando tutto funziona, disinstalla l'add-on locale.
