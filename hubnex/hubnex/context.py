"""Per-request context shared across the HQ without threading it through every call."""

from contextvars import ContextVar

# Telegram chat the current conversation comes from (None = dashboard, routine, API...).
# Delegated agents answer there with their own bot, drafts are shown there.
CURRENT_CHAT: ContextVar[int | None] = ContextVar("current_chat", default=None)

# Who started the work: "owner" (the owner asked, directly or through Jarvis), "routine"
# (scheduled) or "event" (a Home Assistant automation). Only the owner's requests may change
# things in the house; routines and events can look and report.
ORIGIN: ContextVar[str] = ContextVar("origin", default="owner")

# Whether the current conversation turn is spoken by Assist (voice): the built-in Home Assistant
# tools then reach only what is exposed to Assist and refuse the voice deny-list.
VOICE: ContextVar[bool] = ContextVar("voice", default=False)
