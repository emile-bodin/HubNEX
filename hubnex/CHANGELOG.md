# Changelog

## 1.24.1.c
- Floor plan: smaller floating room labels, and their float height follows the plan's size.
  Rooms at the back float lower, so a label stays over its own room and off the floor tabs.

## 1.24.1.b
- Floor plan: the floating room labels stay upright in 3D over a plan drawing too (the
  drawing's blend mode made the browser lay them flat), with the sizes of the approved design.

## 1.24.1
- Floor plan: each room's name, icons and temperature float upright above the room on a
  see-through card, on a thin stem from its middle, for more depth. Larger rooms float higher;
  a lit room turns amber, an open one red.

## 1.24.0
- Home Assistant tools per agent: `ha_mcp:` in `agents.yaml` picks the groups of the built-in
  "casa" tools an agent gets (`[read, camera]`, `none`, or every group on the add-on page when
  left out). It only narrows what the add-on page switches on.
- An agent without casa's `control` group keeps no way to act on the house: the basic
  `ha_call_service` steps aside only for an agent that really has casa's `call_service`.
- Example team: Mail, Accountant, Sales and Technical without Home Assistant tools, Butler with
  read, control and automation, Sentinel with read, automation and camera (it watches, it
  cannot act).
- Floor plan: shaped rooms keep the same edge colors as plain rooms, with their name, icons and
  temperature in the largest rectangle inside the shape.

## 1.23.0
- Conversations: several per channel, each with its own memory. The dashboard chat lists them
  (continue, new, rename, delete with undo), shows tool steps and the answer while it is
  written, and can stop an answer. Telegram: /new. Old chat history becomes one conversation.
- Home Assistant tools ported from brAIn (BRUH Automation, MIT): about 40 tools for states,
  areas, devices, typed controls, automations and traces, camera frames, dashboards, exposure
  and more, run inside HubNEX as the built-in connector "casa", with protected entities, a voice
  deny-list, the owner's confirmation for changes and an action log.
- MCP connectors: the servers' instructions reach the assistant, images come through, tools can
  be kept or excluded per connector, optional tool search, connectors on the add-on page.
- HubNEX as an MCP server at /mcp (off by default, read-only by default).
- Many new options on the add-on page, in English, Dutch and Italian.

## 1.22.1
- Dutch translation: the dashboard, the assistant, the agents, Telegram, notifications, the
  Assist integration and the add-on configuration page are available in Dutch.
- Choose the dashboard language per device under ⚙ Preferences → Language (Automatic, English,
  Nederlands). The new add-on option Language (en, nl, auto) sets the language of the assistant,
  the agents and the add-on's messages. English stays the default.

## 1.22.0
- The assistant and every agent can look at the past of the house: Home Assistant history,
  logbook, long-term statistics and a summary of habits per weekday (read-only, up to 14 days
  and 25 entities per question).

## 1.21.3
- Draw rooms with multiple corners, including L-shaped and angled walls; edit corners after drawing.
- Suggested rooms may use the actual room outline. Existing rectangular plans remain compatible.

## 1.21.2d
- Claude subscription chats now use safe mode, which keeps the saved sign-in available while disabling CLI customizations.

## 1.21.2c
- Updated the bundled Claude Code to 2.1.293 for Haiku 5.5 support.
- Model errors are no longer reported as expired Claude Code sign-ins.

## 1.21.2b
- Claude sign-in: a link that opens in the browser, and the code field shown above the output.
- Preferences scroll on small screens; clearer sign-in instructions.

## 1.21.1b
- Beta with Claude access through the Claude Code subscription and an optional API fallback.
- Add-on images distributed from the emile-bodin fork.

## 1.21.1
- Light theme: the top panel of the Home view becomes a single white card, with items divided
  by thin lines (previously a checkerboard).
- With only one camera: "tap to view it".

## 1.21.0
- **Light theme** for the Home view, high contrast, readable even in sunlight: light background,
  white cards, dark text, fuller amber and red. In **⚙ → Theme**: Automatic (follows the
  phone), Dark or Light; the choice is kept on the device. HQ and Map stay dark.

## 1.20.2
- Free card, **Clean** style like the composed cards: small labels, medium-sized values, a line
  above each block that lights up when the entity is active, times with −15/+15 next to them,
  switches with their name on the same line, the card's state in the header
  (on · active until…).
- **The top line** of all cards (free and composed) follows the same rules: orange when
  something is on or a sensor detects, red for an alarm (door or window open, water, smoke,
  gas); in a card with a main switch, such as the stove, that switch decides.

## 1.20.1
- Free card: **Clean style**, without boxes, like the composed cards, and the default for new
  cards; **Boxes** can still be chosen in the editor. Existing cards stay as they are. The style
  also travels with Export / Import.

## 1.20.0
- **Free card**, part three:
  - **Describe it to Jarvis**: write the card you want and Jarvis builds it with the house's real
    entities (made-up entities are discarded); it opens in the editor for you to check;
  - **Export / Import card**: a card becomes text to share and can be pasted into another
    house, where blocks with missing entities are left for you to choose;
  - in conditions and rules, values are picked from a **translated list** (on, open,
    playing…) instead of typing `on` or `playing`.

## 1.19.0
- **Free card**, part two:
  - **media** blocks (cover, title, controls, volume), **camera** (live) and
    **Ask Jarvis** (a ready-made question sent to the chat with one tap);
  - for every block: **colour by value** (up to 4 rules), **show only if** (an entity has a
    certain value) and **tap action** (toggle, scene or script, ask Jarvis, open a room);
  - **ready-made templates**: Stove, Entrance, Laundry, Room climate, Energy, Music, filled in
    with the room's entities;
  - blocks are moved by **dragging** them, with a finger or the mouse.

## 1.18.0
- **Free card** (part one): a block-based card on a 4-column grid, 2 on the phone. Blocks: big
  value, ring, switch, button, slider, graph, bar, time slot, selector, state and text; for each
  one entity, label, size (from 1×1 to 4×2), minimum and maximum. Card name and colour, live
  preview in the editor. Created from Edit room → + Free card.

## 1.17.0
- **Supply card** for pellets and the like: how many are left, daily consumption and days
  remaining (from Home Assistant history), last delivery, "−1 loaded" and "+delivery". It is
  recognised automatically for a Number helper or a Counter with "pellet", "bags" or "supply"
  in its name; for others choose the "Supply" type. Below the chosen threshold the card turns
  red and the **Supplies to reorder** notification arrives.
- Home Assistant **counters** and **timers** recognised in rooms.
- **Add entity**: search no longer stops at 60 results, every Home Assistant entity can be put
  in a room.

## 1.16.2
- HQ: the beam of light from Jarvis to an agent stays on **for the whole job**, pulsing, with
  bright dots flowing towards the agent; it fades when the agent is done. Previously it lasted
  a second and a half at the start. Returning to HQ, or switching location, while an agent is
  working shows its beam immediately.

## 1.16.1
- Chat: no more "Failed to fetch" with long requests (agents searching and verifying on the
  web). The dashboard no longer keeps one request open for the whole answer, which a proxy
  (Home Assistant, Nabu Casa, the app) could close after a minute or two: it immediately gets a
  job number and asks for the answer with short requests. If the network drops for a moment, it
  retries by itself.

## 1.16.0
- Richer Home view:
  - **Weather** in the dashboard bar, with the forecast for the coming days in a popup (from
    Home Assistant);
  - **Today and coming days**: deadlines for the next 7 days, with a checkmark to close them.
    Owner only: family members with home-only access don't see them;
  - **icons on the floor plan**: presence, music, robot at work, washing machine running;
  - **Appliances**: running with their power draw, and "finished … ago";
  - **Recent events**: doors, windows, locks, alarm and people over the last 24 hours.

## 1.15.1
- **Web searches adjustable per agent**: in `agents.yaml`, `max_searches: 3` limits the web
  searches of Jarvis or an agent per request (from 1 to 20; if missing it stays at 5, as
  before). Each search brings in pages to read: fewer searches lower the cost, especially for
  technical agents. The documentation has tips for spending less.

## 1.15.0
- **Other AI providers**: Jarvis and every agent can also use **OpenAI**, a **local model** with
  Ollama or LM Studio (free, no cloud) or any OpenAI-compatible service (OpenRouter, Gemini,
  Mistral, DeepSeek, Groq). The model is written with a prefix: `openai:gpt-5-mini`,
  `ollama:qwen3:14b`, `compat:model-name`; without a prefix it is Claude, as before. They can be
  mixed, for example Jarvis on Claude and mail on a local model. New options for keys and
  addresses; the Anthropic key becomes optional.
- With the other models, HubNEX reads web pages itself (public addresses only) and PDFs arrive
  as text; web search and visible thinking remain Claude-only.
- Spending: Ollama models cost nothing, for OpenAI and the others you enter the list price. The
  Anthropic credit only counts calls to Claude.

## 1.14.3
- Cameras inside Home Assistant: live thumbnails use Home Assistant's video stream (the same as
  the large HD view), no longer MJPEG, which doesn't come through with many cameras. Tapping a
  thumbnail opens the large view in HD immediately, with the same stream. Outside Home Assistant
  MJPEG remains; if a camera's video doesn't start, it falls back to snapshots.

## 1.14.2
- Cameras: no more black thumbnails. The last snapshot stays visible until the live video
  actually shows an image. If the video hasn't arrived after 10 seconds, the thumbnail stays on
  snapshots refreshed every 5 seconds.

## 1.14.1
- Cameras: the large view opens immediately. It uses the video already playing in the
  thumbnail instead of opening a new one, and inside Home Assistant the high-quality video
  starts at the same time, no longer after waiting for the first frame (up to 10 seconds with
  some cameras).

## 1.14.0
- **Robot vacuum** card: state, battery, its **map** (from the same device, refreshed every 5
  seconds and showing the robot moving), Clean/Pause, Dock, Locate and suction power. In rooms
  it has the "Cleaning" group.
- **Live cameras**: thumbnails are video (up to 3 at a time); tapping them opens them large and
  already live; inside Home Assistant it switches to its high-quality video.
- **Composed card with camera**: the image instead of the word "idle", sensors over the image
  (red when triggered, "how long ago" when at rest), the state in plain words.
- More complete **media card**: large cover with a blurred background, artist and album, app,
  progress, shuffle/repeat, mute, volume and source, depending on what the device supports.

## 1.13.2
- Light card minimal again: colour and temperature are in a popup, opened from the small dot
  next to the state (only on bulbs that have them). In the popup: brightness, temperature from
  warm to cool, colours and a picker.

## 1.13.1
- Light card: colour temperature slider (from warm to cool) and colours, with a picker for any
  other colour, only on bulbs that support them. A colour chosen on a light that is off turns
  it on in that colour.

## 1.13.0
- Attachments: photos, albums, PDFs and text files for the assistant and agents, from Telegram
  (with the request in the caption, or by replying to the photo) and from the dashboard
  (paperclip, phone camera, paste or drag). The assistant passes them to the agent it delegates
  the work to; the conversation keeps only their ID, and anyone on the team can look at them
  again (`view_attachment`). They are kept for 30 days. API: `POST /api/attachments`.

## 1.12.3
- Dashboard chat: the request wraps and the field grows to about 6 lines, then scrolls. Enter
  sends, Shift+Enter adds a new line.

## 1.12.2
- Mail: Read and Reply buttons without emoji (the priority dots remain).
- Fixed: without a separate bot for Jarvis Mail, mail buttons arrive at the Jarvis bot and now
  work (previously they were ignored, and since 1.12.0 mistaken for house notification
  buttons). House notification buttons have their own code.

## 1.12.1
- Mail: new option "Senders not to report" (addresses, @domains or words like noreply): no
  Telegram message and no classification, so no Claude credit spent.
- Clearer house notifications: low batteries, unreachable devices and security sensors say
  which device and in which room ("Door sensor (Entrance) 8%").
- No emoji in house notifications or in credit and budget alerts; urgent alerts on Telegram
  start with "URGENT:".

## 1.12.0
- House notifications, without Claude: leaks/smoke/gas (immediately, even at night), windows
  open with heating/air conditioning on or rain, empty house with doors/gate/locks open, high
  consumption, lights on at night, low batteries, unreachable devices.
- They arrive in the Home Assistant app (push with Dismiss/Turn off buttons), on Telegram and in
  Home Assistant notifications, chosen per rule. One alert per problem, which disappears by
  itself when the problem is solved; quiet hours; no action without your tap.
- Configured in ⚙ Preferences → House notifications, with entities to exclude and a test
  notification.
- Tests: the Energy popup waits for the day's graph before testing scrolling.

## 1.11.0
- Claude spending history: click the spending panel in HQ (or ⚙ Preferences → Claude
  spending). Today, month, end-of-month estimate, one bar per day (7/30/90 days), spending per
  agent and per model with calls and tokens.
- New option `monthly_budget_usd`: alert at 80% and 100% of the monthly budget, in the Telegram
  group and in Home Assistant notifications. Only an alert, nothing stops.
- The cost of every Claude call is recorded per day, agent and model (included in the backup).

## 1.10.1
- Full guide in English (DOCS.en.md) and example team in English: with English as the
  language, the add-on creates an already translated agents.yaml on first start.
- Project README in English (the Italian one stayed in README.it.md) and presentation in
  English with screenshots of the English dashboard.
- Fixed: the "Quick answer" label under messages now follows the dashboard language.
- Italian guide: the "If the integration isn't detected" paragraph moved to the right place.

## 1.10.0
- The add-on speaks English: new "Language" option (auto = Home Assistant's, it, en).
  - Jarvis and the agents answer in English (the instructions in agents.yaml can stay in
    Italian);
  - activity log, Telegram (messages, buttons, mail), notifications and errors in English;
  - the dashboard receives errors in its user's language, Assist answers in the language you
    speak to it;
  - the voice reads units, symbols and dates in English ("kilowatt hours", "1 September").
- Outside Italy, energy time bands default to "single rate" instead of the ARERA calendar.
- A test checks that every add-on message has its translation.

## 1.9.0
- The dashboard speaks English: chosen automatically from the Home Assistant language of the
  person opening it, or manually in ⚙ Preferences → Language. All texts (Home, cards, Energy,
  floor plan, HQ, map, chat, preferences) are translated; a test checks that the dictionary
  stays complete.
- Numbers, dates and times in the chosen language's format; the microphone listens in the same
  language.
- Fixed: the assistant's "Reading the mail…" bubble never appeared.

- For developers: `dev/demo.py` (HubNEX with a fake house and a fake Claude), dashboard tests in
  the browser on every change, CONTRIBUTING guide.

## 1.8.11
- The Assist integration has its own icon in Devices & services (Home Assistant 2026.3 or
  later).

## 1.8.10
- Assist integration added manually: no more default address of the local copy
  (`local-hubnex`), which is wrong with the repository add-on; the dialog explains that
  restarting the add-on and confirming "HubNEX discovered" is usually enough.

## 1.8.9
- HubNEX backup from Preferences: one file with memory and neural map, deadlines, chat, Home
  settings, floor plan and energy, `agents.yaml`. Without the add-on options (API keys,
  Telegram, mail).
- Restore from the same panel: applied on restart, which starts by itself; replaced files are
  kept as `.prima-del-ripristino`. Also useful for moving from the local copy to the repository
  add-on (see the documentation).
- Much faster installation and updates: Home Assistant downloads the prebuilt image
  (Raspberry/ARM and PC) instead of building HubNEX.
- The repository has automatic checks (tests, dashboard, manifest), issue forms and the
  security page.

## 1.8.8
- Who answered in the chat is shown as a small label in HubNEX style (HOME ASSISTANT, QUICK
  ANSWER), without emoji.

## 1.8.7
- Dashboard and Assist take the fastest route:
  1. dashboard: Home Assistant's sentences first (instant, no AI);
  2. the quick route for house requests (Haiku with the list of entities);
  3. Jarvis with its own model for everything else. Complex questions asked to Assist now reach
     Jarvis instead of staying on Haiku.
- Locks, alarm and doors never go through Home Assistant or the quick route: Jarvis decides,
  with confirmation.
- In the dashboard chat, "⚡ Home Assistant" or "⚡ quick answer" shows who answered.

## 1.8.6
- Faster voice commands (Assist):
  - new option "Model for voice commands", Haiku by default: Telegram and the dashboard stay on
    Jarvis's model;
  - Jarvis receives the list of the house's entities with area and state, so it acts
    immediately without looking them up and answers state questions without tools;
  - lighter instructions and history for voice (it can still delegate to agents).

## 1.8.5
- Home popups (Energy included) scroll without the light scrollbar, like the rest of HubNEX.

## 1.8.4
- Energy is a popup again, like the others in the top bar: closed with ×, a click on the
  background or Esc. Settings unchanged.
- Home popups live in a separate layer: live house updates no longer redraw them, and a popup
  only updates when what it shows changes, without losing the scroll position.
- New, clearly distinct band colours: F1 orange, F2 blue, F3 green. "Current band" also takes
  the colour of the active band.

## 1.8.3
- New option "Spoken answers": full (as before) or summary. With summary, when the answer is
  long Jarvis adds one or two sentences to be spoken and the voice reads only those; the written
  text stays complete. Dashboard (speaker on) and Telegram voice messages.

## 1.8.2
- The voice reads text prepared for listening: no symbols, emoji or links; units and
  abbreviations as words (Ω, kW, kWh, °, MV/LV…), dates spelled out, pauses instead of list
  dashes. Applies to the dashboard, Telegram voice messages and Assist.
- New option "Home Assistant engine voice": the voice by name (e.g. Rinaldo with Home Assistant
  Cloud). The language is always Home Assistant's, even with no voice chosen.
- ElevenLabs: exhausted credits, wrong key and blocked free plan now have distinct messages
  (previously all "invalid API key").

## 1.8.1
- Energy is a page like the room pages (← Home to go back), no longer a popup: scrolling no
  longer jumps to the top with live updates. Editors also keep their position.
- "Away" and the other areas no longer affect the floor plan.
- Room temperatures aligned regardless of the number of decimals.

## 1.8.0
- Energy panel (tap "Energy" in the Home dashboard bar) with three views to choose from:
  - the reactor: the period split by band F1/F2/F3 around the current power;
  - the day: today's power over the bands in the background, today's kWh per band;
  - the bill: cost, end-of-period estimate, bands compared with the previous period, and a tip
    when a band grows.
- Configurable from HubNEX: views, band (ARERA calendar with holidays, your own sensor, single
  rate), kWh per band, prices or cost, power and meter, other values.
- Windows (editor, code, energy) open below the top bar and hide the chat.

## 1.7.5
- Optional graph: in the custom card editor every numeric sensor has a "graph" switch; on single
  cards, in "Edit room", "Remove graph" / "Show graph".

## 1.7.4
- Custom card: numeric sensors (light, temperature, consumption…) have the graph of the last 24
  hours, as in single cards.
- The line above each entity in a custom card lights up amber when that entity is active
  (motion detected, switch on…) and red for an alarm (window open, water, smoke).

## 1.7.3
- Cards with schedules: the switch that enables them (e.g. "automatic") counts. On: "active
  until…" / "activates at…"; off: "automatic off · schedule inactive" and a grey band.
- In the card editor: "Schedules apply when it is on" (automatic from the name, a switch of your
  choice, or none).

## 1.7.2
- Custom card: switches sit in a column, one under the other with their name, instead of ending
  up below the other entities.
- An input_boolean (e.g. "automatic") no longer counts as "stove on/off": the state only comes
  from a real switch, light or thermostat.
- Cards in the same row have the same height, even across side-by-side groups.

## 1.7.1
- Room groups (Lights, Climate, Outlets…) always stay, even after creating a card or changing
  the order; "My cards" is gone.
- Every custom card goes into a group: chosen in the editor ("Group"), by default that of the
  first entity.
- Moving a card (dragging or with ‹ ›) moves it within its group.

## 1.7.0
- Home Assistant times, numbers, lists and texts (input_datetime, time, date, input_number,
  number, input_select, select, input_text, text) can be controlled from the Home view: large
  time with −15 / +15, slider, option choice, text field.
- Custom card: in "Edit room" → "+ New card" you compose a card with several entities (e.g. the
  stove with on and off times, the day's time band and "active until…").
- Room layout: cards can be moved (dragging or with ‹ ›), renamed in HubNEX only, made wide or
  small, removed; "Automatic order" to go back to groups.

## 1.6.0
- Plainer Home view, in Jarvis style: Saira font, thin numbers, lowercase states, flat and
  smaller cards without a type label; a thin amber line on top when something is on, red when
  there is a problem.
- Dashboard bar as a thin row; scenes, switches and sliders more discreet; climate and alarm
  modes as underlined words; "Turn all off" and "Unlock" as links.

## 1.5.1
- Cards are back to the previous font (no monospaced text in states).
- "Turn all off" no longer pushes the light cards down relative to the neighbouring sections.

## 1.5.0
- Home view redesigned in HUD style: dashboard bar at the top (people, alarm, climate, lights,
  energy, cameras) and hexagonal scenes.
- One card per entity type: lights, climate with dial, covers, valves, media with cover,
  progress, controls and volume, outlets with the device's consumption, locks, alarm,
  doors/windows with "how long ago", sensors with the graph of the last 24 hours, people,
  sirens, cameras.
- Room quick sheet with temperature and humidity rings, lights as buttons, "keep an eye on" and
  camera; on the phone it slides up from the bottom (drag down to close, up to open).
- Locks: with a code in Home Assistant, the keypad; otherwise confirmation in the card.
- Room consumption on the room page.

## 1.4.2
- Valves (irrigation, water): their own section with Open / Close (and Stop, if the valve
  allows it). Previously they were treated as covers and the commands didn't arrive.

## 1.4.1
- Deadlines: the "done" checkmark is centred in its box and aligned with the text.

## 1.4.0
- Edit room: any Home Assistant entity can be added, including hidden ones (e.g. Music
  Assistant players) or diagnostic ones; the usual ones first, with the entity_id next to them.
- People: the Home view shows who is home, who is away and in which zone.
- Media: play/pause and volume, with title and artist.

## 1.3.1
- Entity names: if you gave an entity aliases in Home Assistant, the Home view shows the first
  one; the search for adding entities also finds aliases.
- Documentation: recommended path to set everything up, on first start.

## 1.3.0
- HubNEX is visible to all Home Assistant users, not only administrators.
- Non-administrators only get the Home view (device controls, cameras, alarm): assistant, mail,
  agents, activity, costs and floor plan changes remain for administrators. The check is done
  by the add-on on every request. New option "Non-admin users" (home / full).

## 1.2.0
- Per-user preferences: the HQ and Map tabs can be turned off (HubNEX opens on the Home view),
  as can the AI assistant (no chat, voice or approvals). Inside Home Assistant they apply to the
  account and follow it across all devices.

## 1.1.0
- Floor plan editor: upload a photo or PDF of the floor plan, move, resize and draw rooms with a
  finger or the mouse, link each one to a Home Assistant area.
- "Suggest rooms": Claude reads the floor plan and suggests a layout to refine.
- The floor plan appears transparently under the holographic map.
- The YAML remains available from the "Text" button.

## 1.0.0
First public release.
- Assistant with a team of Claude agents configurable in `agents.yaml` (companies,
  departments, agents, instructions, routines off by default, permanent rules).
- 3D dashboard: headquarters, neural map, animated core during the conversation.
- Home view: holographic floor plan of Home Assistant areas, quick sheet and room page, entity
  editing (including moving the area in Home Assistant), "Show as", live cameras, alarm with
  keypad.
- MCP connectors for work programs, with confirmation for every change.
- IMAP/SMTP mail with sorting and drafts to approve.
- Telegram group with one bot for the assistant and one for mail, voice messages included.
- Voice: Assist integration (conversation agent), ElevenLabs or Home Assistant text-to-speech
  in the dashboard.
- Anthropic credit estimate, events from automations, open on startup per user.
