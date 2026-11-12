"""English output for the add-on's existing Italian message keys."""

from __future__ import annotations

from contextvars import ContextVar

from hubnex.i18n_en import EN

LANGS = ("en",)
_system = "en"
REQUEST_LANG: ContextVar[str | None] = ContextVar("request_lang", default=None)


def norm(lang: str | None) -> str | None:
    return "en" if lang else None


def set_system_lang(lang: str | None) -> None:
    global _system
    _system = norm(lang) or _system


def system_lang() -> str:
    return _system


def lang() -> str:
    return REQUEST_LANG.get() or _system


def tr(text: str, **values) -> str:
    out = EN.get(text, text)
    return out.format(**values) if values else out


def tr_sys(text: str, **values) -> str:
    out = EN.get(text, text)
    return out.format(**values) if values else out
