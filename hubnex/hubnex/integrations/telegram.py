"""The Telegram group where the owner talks to the team (design of the original Jarvis add-on).

Jarvis has a bot; an agent may have its own bot too (today: Jarvis Mail). In the group:
- a normal message goes to Jarvis, who answers or delegates;
- replying to an agent's message, or writing @its_bot, talks to that agent directly;
- replying to a draft with what to change produces a new version of the draft;
- photos, albums and files (PDF, text) go along with their caption, or with the text that
  replies to them, to whoever the message is for.
Agents without a bot speak through Jarvis' bot, with their name in front.
Only the configured group and user are obeyed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ChatType
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from hubnex.attachments import MAX_BYTES, MAX_PER_MESSAGE, Attachment, AttachmentError
from hubnex.context import CURRENT_CHAT
from hubnex.maildesk import MAIL_AGENT_ID, Buttons
from hubnex.speech import for_voice
from hubnex.i18n import tr_sys

if TYPE_CHECKING:
    from hubnex.config import Settings
    from hubnex.hq import HQ

log = logging.getLogger("hubnex.telegram")
TG_LIMIT = 4000
JARVIS = "jarvis"
ALBUM_WAIT = 1.5  # seconds: the photos of an album arrive one by one
FILES = filters.PHOTO | filters.Document.ALL


def _markup(buttons: Buttons | None) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(t, callback_data=d) for t, d in row] for row in buttons])


def speakable(text: str) -> str:
    """The answer as the voice should read it, kept short for a voice note."""
    return for_voice(text, limit=1500)


class TelegramTeam:
    def __init__(self, settings: "Settings", hq: "HQ"):
        self.settings = settings
        self.hq = hq
        tokens = {JARVIS: settings.telegram_token_jarvis}
        if settings.telegram_token_mail:
            tokens[MAIL_AGENT_ID] = settings.telegram_token_mail
        self.apps: dict[str, Application] = {
            key: Application.builder().token(token).build() for key, token in tokens.items() if token
        }
        self._albums: dict[tuple[int, str], dict] = {}  # albums still arriving
        self._register()

    # ------------------------------------------------------------------ interface used by the HQ
    @property
    def enabled(self) -> bool:
        return JARVIS in self.apps

    @property
    def home_chat(self) -> int | None:
        return int(self.settings.telegram_chat_id) if self.settings.telegram_chat_id else None

    def _bot_for(self, agent_id: str | None):
        key = agent_id if agent_id in self.apps else JARVIS
        return self.apps[key].bot, key != (agent_id or JARVIS)

    async def post(
        self,
        agent_id: str | None,
        text: str,
        chat_id: int | None = None,
        buttons: Buttons | None = None,
        reply_to: int | None = None,
    ) -> tuple[int, int] | None:
        """Send as the agent's bot (or Jarvis' bot, signed with the agent's name)."""
        chat_id = chat_id or self.home_chat
        if not chat_id:
            return None
        bot, borrowed = self._bot_for(agent_id)
        if borrowed:
            text = f"{self.hq.agent_name(agent_id)}:\n{text}"
        text = text.strip() or "…"
        chunks = [text[i : i + TG_LIMIT] for i in range(0, len(text), TG_LIMIT)]
        last = None
        for i, chunk in enumerate(chunks):
            last_chunk = i == len(chunks) - 1
            last = await bot.send_message(
                chat_id,
                chunk,
                reply_markup=_markup(buttons) if last_chunk else None,
                reply_to_message_id=reply_to if i == 0 else None,
                disable_web_page_preview=True,
            )
        return (chat_id, last.message_id) if last else None

    async def set_buttons(self, agent_id: str | None, chat_id: int, msg_id: int, buttons: Buttons | None) -> None:
        bot, _ = self._bot_for(agent_id)
        try:
            await bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=_markup(buttons))
        except Exception:
            log.warning("Impossibile aggiornare i pulsanti del messaggio %s", msg_id)

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        for key, app in self.apps.items():
            await app.initialize()
            await app.start()
            await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
            log.info("Bot %s avviato come @%s", key, app.bot.username)
        if not self.settings.telegram_chat_id:
            log.warning("allowed_chat_id vuoto: scrivi /id a Jarvis nel gruppo e completa la configurazione.")

    async def stop(self) -> None:
        for app in self.apps.values():
            try:
                await app.updater.stop()
                await app.stop()
                await app.shutdown()
            except Exception:
                log.exception("stop telegram")

    # ------------------------------------------------------------------ access control
    def allowed(self, update: Update) -> bool:
        chat, user = update.effective_chat, update.effective_user
        if not chat or not user:
            return False
        if self.settings.telegram_user_id and str(user.id) != self.settings.telegram_user_id:
            return False
        if self.settings.telegram_chat_id and str(chat.id) == self.settings.telegram_chat_id:
            return True
        # private chat with a bot: only for the authorised user
        return chat.type == ChatType.PRIVATE and bool(self.settings.telegram_user_id)

    def addressed_to(self, update: Update) -> str | None:
        """Which agent bot (not Jarvis) a group message is for: reply to it or @mention."""
        return self._addressed(update.effective_message)

    def _addressed(self, msg) -> str | None:
        for key, app in self.apps.items():
            if key == JARVIS:
                continue
            replied = msg.reply_to_message
            if replied and replied.from_user and replied.from_user.id == app.bot.id:
                return key
            uname = (app.bot.username or "").lower()
            if uname and f"@{uname}" in (msg.text or msg.caption or "").lower():
                return key
        return None

    # ------------------------------------------------------------------ handlers
    def _register(self) -> None:
        for key, app in self.apps.items():
            app.add_handler(CommandHandler(["start", "id"], self.cmd_id))
            app.add_handler(CommandHandler("stato", self.cmd_stato))
            app.add_handler(CommandHandler("posta", self.cmd_posta))
            app.add_handler(CommandHandler("regole", self.cmd_regole))
            if key == JARVIS:
                app.add_handler(CommandHandler(["nuovo", "new", "nieuw"], self.cmd_nuovo))
            app.add_error_handler(self._on_error)
            if key == JARVIS:
                app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text_jarvis))
                app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self.on_voice_jarvis))
                app.add_handler(MessageHandler(FILES, self._file_handler(JARVIS)))
                app.add_handler(CallbackQueryHandler(self.on_button_jarvis))
            else:
                app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._agent_text_handler(key)))
                app.add_handler(MessageHandler(FILES, self._file_handler(key)))
                app.add_handler(CallbackQueryHandler(self._agent_button_handler(key)))

    async def _on_error(self, update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        log.error("Errore Telegram: %s", ctx.error, exc_info=ctx.error)

    async def cmd_id(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.effective_message.reply_text(
            f"chat id: {update.effective_chat.id}\nuser id: {update.effective_user.id}\n\n"
            + tr_sys("Inserisci questi valori in allowed_chat_id e allowed_user_id nella configurazione dell'add-on.")
        )

    async def cmd_stato(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.allowed(update):
            return
        lines = [tr_sys("{name} operativo.", name=self.hq.org.boss_name), f"{tr_sys('Modelli')}: {self.settings.model} / mail {self.settings.model_mail}"]
        if self.hq.maildesk:
            lines.append(await self.hq.maildesk.status())
        if self.hq.ha.enabled:
            lines.append("Home Assistant: " + ("OK" if await self.hq.ha.ping() else tr_sys("non raggiungibile")))
        if self.hq.connectors.enabled:
            lines.extend(await self.hq.connectors.status())
        await update.effective_message.reply_text("\n".join(lines))

    async def cmd_nuovo(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """/new: Jarvis starts a new conversation in this chat (the old one stays on the dashboard)."""
        if not self.allowed(update):
            return
        await self.hq.new_session(f"telegram:{update.effective_chat.id}")
        await update.effective_message.reply_text(tr_sys("Nuova conversazione: ricomincio da capo."))

    async def cmd_regole(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.allowed(update):
            return
        rules = "\n".join(f"{i}. {r}" for i, r in enumerate(self.hq.rules, 1))
        await update.effective_message.reply_text(
            f"{tr_sys('Le tue regole, valide per tutto il team')}:\n{rules}" if rules else
            tr_sys("Nessuna regola salvata. Dimmi pure \"d'ora in poi…\" o \"non fare mai…\" e la salvo.")
        )

    async def cmd_posta(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.allowed(update):
            return
        if not self.hq.maildesk:
            await update.effective_message.reply_text(tr_sys("Casella email non configurata."))
            return
        await self.hq.maildesk.check(manual_chat=update.effective_chat.id)

    # --- Jarvis
    async def _ask_jarvis(
        self, update: Update, ctx, text: str, voice: bool, attachments: list[Attachment] | None = None
    ) -> None:
        chat_id = update.effective_chat.id
        CURRENT_CHAT.set(chat_id)
        await ctx.bot.send_chat_action(chat_id, ChatAction.TYPING)
        try:
            speak = voice and self.settings.telegram_voice_replies and self.hq.tts_enabled
            answer, said, _ = await self.hq.converse(f"telegram:{chat_id}", text, spoken=speak, attachments=attachments)
        except Exception as exc:
            log.exception("Errore Jarvis")
            answer, said = f"{tr_sys('Mi scusi, qualcosa è andato storto')}: {exc}", None
        if not answer:
            return  # the delegated agent already answered in the group
        await self.post(JARVIS, answer, chat_id)
        if voice and self.settings.telegram_voice_replies and self.hq.tts_enabled:
            await ctx.bot.send_chat_action(chat_id, ChatAction.RECORD_VOICE)
            try:
                audio, ctype = await self.hq.speak_audio(speakable(said or answer))
            except Exception as exc:
                await self.post(JARVIS, f"🔇 {tr_sys('Risposta solo scritta')}: {exc}", chat_id)
                return
            if "mpeg" in ctype or "ogg" in ctype or "mp4" in ctype:
                await ctx.bot.send_voice(chat_id, voice=bytes(audio))
            else:  # e.g. WAV from Piper: Telegram plays it as an audio file
                await ctx.bot.send_audio(chat_id, audio=bytes(audio), filename="risposta.wav", title="Risposta")

    async def on_text_jarvis(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        if not msg or not msg.text:
            return
        if not self.allowed(update):
            if not self.settings.telegram_chat_id:
                await msg.reply_text(tr_sys("Configurazione incompleta: scrivi /id e inserisci gli id nell'add-on."))
            return
        if update.effective_chat.type != ChatType.PRIVATE and self.addressed_to(update):
            return  # for another agent's bot
        text = msg.text.replace(f"@{ctx.bot.username}", "").strip()
        await self._ask_jarvis(update, ctx, text, voice=False, attachments=await self._replied_files(msg, ctx))

    async def on_voice_jarvis(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        if not self.allowed(update):
            return
        if not self.hq.voice.stt_enabled:
            await msg.reply_text(tr_sys("Per i vocali serve la chiave ElevenLabs nella configurazione."))
            return
        audio = msg.voice or msg.audio
        await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        data = await (await ctx.bot.get_file(audio.file_id)).download_as_bytearray()
        text = await self.hq.voice.transcribe(bytes(data))
        if not text:
            await msg.reply_text(tr_sys("Non ho capito il vocale."))
            return
        await msg.reply_text(f"🎙 «{text}»")
        await self._ask_jarvis(update, ctx, text, voice=True)

    async def on_button_jarvis(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """✅/❌ on actions in connected programs proposed by the agents."""
        q = update.callback_query
        if not self.allowed(update):
            await q.answer(tr_sys("Non autorizzato"))
            return
        kind, key, decision = (q.data.split(":") + ["", "", ""])[:3]
        if kind in ("n", "d") and MAIL_AGENT_ID not in self.apps:
            # mail buttons posted with Jarvis' bot (no separate Jarvis Mail bot)
            await self._agent_button_handler(MAIL_AGENT_ID)(update, ctx)
            return
        if kind == "h":  # a button on a notification about the house
            try:
                done = await self.hq.alerts.press(key)
            except Exception as exc:
                await q.answer(str(exc)[:190], show_alert=True)
                return
            await q.answer(tr_sys("Fatto") if done else tr_sys("Non più necessario"))
            await q.edit_message_reply_markup(None)
            return
        if kind != "a":
            await q.answer()
            return
        CURRENT_CHAT.set(q.message.chat.id)
        action = await self.hq.store.action(int(key))
        if not action or action["status"] != "open":
            await q.answer(tr_sys("Azione non più in attesa"))
            return
        await q.answer(tr_sys("Un attimo…") if decision == "ok" else tr_sys("Annullata"))
        try:
            await self.hq.actions.decide(int(key), decision == "ok")
        except Exception as exc:  # the action's message in the group already says what went wrong
            log.warning("action %s: %s", key, exc)

    # --- agents with their own bot
    def _agent_text_handler(self, agent_id: str):
        async def handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
            msg = update.effective_message
            if not msg or not msg.text or not self.allowed(update):
                return
            private = update.effective_chat.type == ChatType.PRIVATE
            if not private and self.addressed_to(update) != agent_id:
                return  # not for me: Jarvis answers
            chat_id = update.effective_chat.id
            text = msg.text.replace(f"@{ctx.bot.username}", "").strip()
            if agent_id == MAIL_AGENT_ID and self.hq.maildesk and msg.reply_to_message:
                draft = await self.hq.store.draft_by_message(chat_id, msg.reply_to_message.message_id)
                if draft:
                    CURRENT_CHAT.set(chat_id)
                    try:
                        await self.hq.maildesk.revise(draft, text)
                    except Exception as exc:
                        log.exception("Errore bozza")
                        await self.post(agent_id, f"{tr_sys('Errore')}: {exc}", chat_id)
                    return
            await self._ask_agent(agent_id, chat_id, ctx, text, await self._replied_files(msg, ctx))

        return handler

    async def _ask_agent(self, agent_id: str, chat_id: int, ctx, text: str, attachments: list[Attachment]) -> None:
        """The owner talks to an agent directly (replying to it or with @its_bot)."""
        CURRENT_CHAT.set(chat_id)
        await ctx.bot.send_chat_action(chat_id, ChatAction.TYPING)
        try:
            answer = await self.hq.run_agent(
                agent_id, text, "user", history_channel=f"telegram:{chat_id}:{agent_id}", attachments=attachments
            )
            await self.post(agent_id, answer, chat_id)
            files = f" ({len(attachments)} allegati)" if attachments else ""
            await self.hq.note(
                f"Il proprietario ha chiesto a {self.hq.agent_name(agent_id)}{files}: «{text}». Risposta: {answer[:800]}",
                chat_id,
            )
        except Exception as exc:
            log.exception("Errore agente %s", agent_id)
            await self.post(agent_id, f"{tr_sys('Errore')}: {exc}", chat_id)

    # --- photos and files
    async def _download(self, msg, ctx) -> Attachment:
        """The photo or file of a message, saved as an attachment. AttachmentError if not usable."""
        if msg.photo:
            item, name, mime = msg.photo[-1], "foto.jpg", "image/jpeg"  # the largest size
        elif msg.document:
            item, name, mime = msg.document, msg.document.file_name, msg.document.mime_type
        else:
            raise AttachmentError(tr_sys("formato non supportato: invia foto, PDF o file di testo"))
        if (item.file_size or 0) > MAX_BYTES:
            raise AttachmentError(tr_sys("file troppo grande (massimo 20 MB)"))
        data = await (await ctx.bot.get_file(item.file_id)).download_as_bytearray()
        return await asyncio.to_thread(self.hq.attachments.save, bytes(data), name, mime)

    async def _replied_files(self, msg, ctx) -> list[Attachment]:
        """A text that replies to a photo or file brings that file along."""
        replied = msg.reply_to_message
        if not replied or not (replied.photo or replied.document):
            return []
        try:
            return [await self._download(replied, ctx)]
        except AttachmentError as exc:
            await msg.reply_text(f"{tr_sys('Allegato non usato')}: {exc}")
        except Exception:
            log.exception("download allegato")
        return []

    def _for_me(self, agent_id: str, private: bool, msgs: list) -> bool:
        """Whether photos/files are for this bot: an agent's when replied to or @mentioned
        (in any message of an album: only the first has the caption), else Jarvis'."""
        if private:
            return True
        targets = {self._addressed(m) for m in msgs}
        return agent_id in targets if agent_id != JARVIS else not (targets - {None})

    def _file_handler(self, agent_id: str):
        """Photos and files: for Jarvis, or for this agent when addressed to its bot."""

        async def handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
            msg = update.effective_message
            if not msg or not self.allowed(update):
                return
            private = update.effective_chat.type == ChatType.PRIVATE
            if not msg.media_group_id:
                if self._for_me(agent_id, private, [msg]):
                    await self._send_files(agent_id, update, ctx, [msg], private)
                return
            # An album: one update per photo. Each bot collects it, then the one it is for answers.
            key = (agent_id, update.effective_chat.id, msg.media_group_id)
            album = self._albums.get(key)
            if album is None:
                album = self._albums[key] = {"msgs": [], "update": update, "private": private}
                asyncio.create_task(self._flush_album(key, ctx))  # the handler returns: the next photos arrive
            album["msgs"].append(msg)

        return handler

    async def _flush_album(self, key: tuple[str, int, str], ctx) -> None:
        await asyncio.sleep(ALBUM_WAIT)
        album = self._albums.pop(key, None)
        agent_id = key[0]
        if album and self._for_me(agent_id, album["private"], album["msgs"]):
            try:
                await self._send_files(agent_id, album["update"], ctx, album["msgs"], album["private"])
            except Exception:
                log.exception("album")

    async def _send_files(self, agent_id: str, update: Update, ctx, msgs: list, private: bool) -> None:
        files, problems = [], []
        for m in msgs[:MAX_PER_MESSAGE]:
            try:
                files.append(await self._download(m, ctx))
            except AttachmentError as exc:
                problems.append(str(exc))
            except Exception as exc:
                log.exception("download allegato")
                problems.append(str(exc))
        if problems:
            await msgs[0].reply_text(f"{tr_sys('Allegato non usato')}: " + "; ".join(dict.fromkeys(problems)))
        if not files:
            return
        text = next((m.caption for m in msgs if m.caption), "") or ""
        text = text.replace(f"@{ctx.bot.username}", "").strip()
        await self._deliver(agent_id, update, ctx, text, files)

    async def _deliver(self, agent_id: str, update: Update, ctx, text: str, files: list[Attachment]) -> None:
        if agent_id == JARVIS:
            await self._ask_jarvis(update, ctx, text, voice=False, attachments=files)
        else:
            await self._ask_agent(agent_id, update.effective_chat.id, ctx, text, files)

    def _agent_button_handler(self, agent_id: str):
        async def handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
            q = update.callback_query
            if not self.allowed(update):
                await q.answer(tr_sys("Non autorizzato"))
                return
            kind, key, action = (q.data.split(":") + ["", "", ""])[:3]
            desk = self.hq.maildesk
            if agent_id != MAIL_AGENT_ID or desk is None:
                await q.answer()
                return
            chat_id = q.message.chat.id
            CURRENT_CHAT.set(chat_id)
            if kind == "d":

                async def answer(text: str | None, alert: bool) -> None:
                    await q.answer(text, show_alert=alert)

                async def edit(buttons: Buttons | None) -> None:
                    await q.edit_message_reply_markup(_markup(buttons))

                await desk.draft_action(int(key), action, answer, edit)
            elif kind == "n":
                await q.answer()
                await ctx.bot.send_chat_action(chat_id, ChatAction.TYPING)
                try:
                    reply = await self.hq.run_agent(
                        MAIL_AGENT_ID,
                        desk.request_for_button(int(key), action),
                        "user",
                        history_channel=f"telegram:{chat_id}:{MAIL_AGENT_ID}",
                    )
                    await self.post(MAIL_AGENT_ID, reply, chat_id)
                except Exception as exc:
                    log.exception("Errore pulsante")
                    await self.post(MAIL_AGENT_ID, f"{tr_sys('Errore')}: {exc}", chat_id)
            else:
                await q.answer()

        return handler
