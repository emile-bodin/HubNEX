"""The add-on's languages: English (default) or Dutch. The Italian text in the code is the key
("gettext style"): tr("bozza sconosciuta") is its English from i18n_en.EN, or its Dutch from
i18n_nl.NL. Placeholders: tr("{n} stanze", n=3).

The language is the add-on's (option "language", else Home Assistant's own) for what the
add-on says by itself (activity feed, Telegram, notifications); a dashboard request carries
the viewer's language (X-HubNEX-Lang), which then wins for the answer to that request.
"""

from __future__ import annotations

from contextvars import ContextVar

from hubnex.i18n_en import EN
from hubnex.i18n_nl import NL

LANGS = ("en", "nl")
_system = "en"
REQUEST_LANG: ContextVar[str | None] = ContextVar("request_lang", default=None)


def norm(lang: str | None) -> str | None:
    """'nl-NL' / 'nl-BE' -> 'nl'; anything else -> 'en'; empty -> None."""
    if not lang:
        return None
    return "nl" if str(lang).lower().startswith("nl") else "en"


def set_system_lang(lang: str | None) -> None:
    global _system
    _system = norm(lang) or _system


def system_lang() -> str:
    return _system


def lang() -> str:
    return REQUEST_LANG.get() or _system


def _text(text: str, language: str) -> str:
    if language == "nl" and text in NL:
        return NL[text]
    return EN.get(text, text)


def tr(text: str, **values) -> str:
    out = _text(text, lang())
    return out.format(**values) if values else out


def tr_sys(text: str, **values) -> str:
    """In the add-on's own language, whatever request is being served (feed, Telegram…)."""
    out = _text(text, _system)
    return out.format(**values) if values else out
