"""Text made for the ear: what the voice reads instead of the written answer's symbols."""

from __future__ import annotations

import re

from hubnex.i18n import lang as current_lang

# Units after a number: "0,2 Ω" -> "0,2 ohm". Longest first, so "kWh" wins over "kW".
_UNITS = {
    "it": [
        ("kWh", "chilowattora"), ("MWh", "megawattora"), ("Wh", "wattora"),
        ("MΩ", "megaohm"), ("kΩ", "chiloohm"), ("mΩ", "milliohm"), ("Ω", "ohm"),
        ("kVA", "chilovoltampere"), ("kVAr", "chilovoltampere reattivi"), ("VA", "voltampere"),
        ("kW", "chilowatt"), ("MW", "megawatt"), ("W", "watt"),
        ("kV", "chilovolt"), ("mV", "millivolt"), ("V", "volt"),
        ("kA", "chiloampere"), ("mA", "milliampere"), ("A", "ampere"),
        ("°C", "gradi"), ("°", "gradi"), ("Hz", "hertz"),
        ("mm²", "millimetri quadrati"), ("mm2", "millimetri quadrati"), ("m²", "metri quadrati"),
        ("km", "chilometri"), ("cm", "centimetri"), ("mm", "millimetri"),
        ("ms", "millisecondi"), ("min", "minuti"), ("h", "ore"),
        ("%", "per cento"),
    ],
    "en": [
        ("kWh", "kilowatt hours"), ("MWh", "megawatt hours"), ("Wh", "watt hours"),
        ("MΩ", "megaohms"), ("kΩ", "kiloohms"), ("mΩ", "milliohms"), ("Ω", "ohms"),
        ("kVA", "kilovolt amperes"), ("kVAr", "kilovolt amperes reactive"), ("VA", "volt amperes"),
        ("kW", "kilowatts"), ("MW", "megawatts"), ("W", "watts"),
        ("kV", "kilovolts"), ("mV", "millivolts"), ("V", "volts"),
        ("kA", "kiloamps"), ("mA", "milliamps"), ("A", "amps"),
        ("°C", "degrees"), ("°F", "degrees Fahrenheit"), ("°", "degrees"), ("Hz", "hertz"),
        ("mm²", "square millimetres"), ("mm2", "square millimetres"), ("m²", "square metres"),
        ("km", "kilometres"), ("cm", "centimetres"), ("mm", "millimetres"),
        ("ms", "milliseconds"), ("min", "minutes"), ("h", "hours"),
        ("%", "percent"),
    ],
    "nl": [
        ("kWh", "kilowattuur"), ("MWh", "megawattuur"), ("Wh", "wattuur"),
        ("MΩ", "megaohm"), ("kΩ", "kiloohm"), ("mΩ", "milliohm"), ("Ω", "ohm"),
        ("kVA", "kilovoltampère"), ("kVAr", "kilovoltampère reactief"), ("VA", "voltampère"),
        ("kW", "kilowatt"), ("MW", "megawatt"), ("W", "watt"),
        ("kV", "kilovolt"), ("mV", "millivolt"), ("V", "volt"),
        ("kA", "kiloampère"), ("mA", "milliampère"), ("A", "ampère"),
        ("°C", "graden"), ("°F", "graden Fahrenheit"), ("°", "graden"), ("Hz", "hertz"),
        ("mm²", "vierkante millimeter"), ("mm2", "vierkante millimeter"), ("m²", "vierkante meter"),
        ("km", "kilometer"), ("cm", "centimeter"), ("mm", "millimeter"),
        ("ms", "milliseconden"), ("min", "minuten"), ("h", "uur"),
        ("%", "procent"),
    ],
}

# Abbreviations read as words (whole words only).
_WORDS = {
    "it": {
        "MT/BT": "media e bassa tensione", "BT/MT": "bassa e media tensione",
        "MT": "media tensione", "BT": "bassa tensione", "AT": "alta tensione",
        "e/o": "e o", "ecc.": "eccetera", "es.": "per esempio", "p.es.": "per esempio",
        "N.B.": "nota bene", "tel.": "telefono", "n.": "numero",
    },
    "en": {
        "and/or": "and or", "e.g.": "for example", "i.e.": "that is", "etc.": "etcetera",
        "approx.": "approximately", "no.": "number", "N.B.": "note",
    },
    "nl": {
        "en/of": "en of", "bijv.": "bijvoorbeeld", "bv.": "bijvoorbeeld", "d.w.z.": "dat wil zeggen",
        "enz.": "enzovoort", "ca.": "circa", "nr.": "nummer", "N.B.": "let op", "tel.": "telefoon",
    },
}

_SYMBOLS = {
    "it": {
        "→": ", ", "⇒": ", ", "←": ", ", "·": ", ", "•": ", ", "|": ", ", "≈": " circa ",
        "≥": " maggiore o uguale a ", "≤": " minore o uguale a ", ">=": " maggiore o uguale a ",
        "<=": " minore o uguale a ", "±": " più o meno ", "×": " per ", "€": " euro ", "&": " e ",
        "~": " circa ", "§": " paragrafo ", "/": " ", "\\": " ", "=": " uguale ",
    },
    "en": {
        "→": ", ", "⇒": ", ", "←": ", ", "·": ", ", "•": ", ", "|": ", ", "≈": " about ",
        "≥": " at least ", "≤": " at most ", ">=": " at least ", "<=": " at most ",
        "±": " plus or minus ", "×": " times ", "€": " euros ", "$": " dollars ", "£": " pounds ",
        "&": " and ", "~": " about ", "§": " section ", "/": " ", "\\": " ", "=": " equals ",
    },
    "nl": {
        "→": ", ", "⇒": ", ", "←": ", ", "·": ", ", "•": ", ", "|": ", ", "≈": " ongeveer ",
        "≥": " minstens ", "≤": " hoogstens ", ">=": " minstens ", "<=": " hoogstens ",
        "±": " plus of min ", "×": " keer ", "€": " euro ", "$": " dollar ", "£": " pond ",
        "&": " en ", "~": " ongeveer ", "§": " paragraaf ", "/": " ", "\\": " ", "=": " is ",
    },
}
_MONTHS = {
    "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
           "settembre", "ottobre", "novembre", "dicembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
    "nl": ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus",
           "september", "oktober", "november", "december"],
}
_OVER = {"it": "su", "en": "out of", "nl": "op"}  # 1/300


def _unit_re(lang: str) -> re.Pattern:
    units = sorted(_UNITS[lang], key=lambda x: -len(x[0]))
    return re.compile(r"(?<=\d)\s?(" + "|".join(re.escape(u) for u, _ in units) + r")(?![\wΩ²])")


def _word_re(lang: str) -> re.Pattern:
    words = sorted(_WORDS[lang], key=len, reverse=True)
    return re.compile(r"(?<![\w/])(" + "|".join(re.escape(w) for w in words) + r")(?![\w/])")


_RE = {lng: (_unit_re(lng), dict(_UNITS[lng]), _word_re(lng)) for lng in _UNITS}


def _date(m: re.Match, lang: str = "it") -> str:
    day, month, year = int(m.group(1)), int(m.group(2)), m.group(3)
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return m.group(0)
    return f"{day} {_MONTHS[lang][month - 1]}" + (f" {year}" if year else "")


_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\u2300-\u23FF\u2B00-\u2BFF\uFE0F\u200D]"
)


VOICE_TAG = "[VOCE]"
VOICE_HINT = (
    "\n[Questa risposta verrà anche letta ad alta voce. Se è lunga (più di tre frasi, oppure con "
    f"elenchi o tabelle), scrivila completa come sempre e aggiungi in fondo una riga a parte che "
    f"inizia con {VOICE_TAG}: il riassunto da dire a voce, una o due frasi parlate, senza elenchi "
    "né simboli, che danno il succo e se serve rimandano al testo scritto. Se è breve non "
    "aggiungere nulla.]"
)
_TAG_RE = re.compile(r"\s*\[VOCE\]\s*:?\s*(.*)$", re.S)


def split_voice(reply: str) -> tuple[str, str | None]:
    """The written answer and, if Jarvis added one, the summary for the voice (VOICE_TAG)."""
    m = _TAG_RE.search(reply or "")
    if not m:
        return reply, None
    return reply[: m.start()].rstrip(), (m.group(1).strip() or None)


def for_voice(text: str, limit: int = 2500, lang: str | None = None) -> str:
    """The written answer as the voice should read it: no markdown, emoji, links or symbols,
    units and abbreviations as words, list items as sentences (a pause instead of a dash).
    `lang`: it, en or nl (default: the language of the request, else the add-on's)."""
    if not text:
        return ""
    lang = lang if lang in _UNITS else current_lang()
    t = re.sub(r"```.*?```", " ", text, flags=re.S)  # code blocks are not read
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)  # [label](url) -> label
    t = re.sub(r"https?://\S+|www\.\S+", "", t)
    t = _EMOJI.sub("", t)
    lines = []
    for line in t.splitlines():
        line = re.sub(r"^\s*(?:[-*+•·▪►]|\d+[.)])\s+", "", line)  # bullets and numbering
        line = re.sub(r"^\s*#+\s*", "", line)  # headings
        line = re.sub(r"[*_`>#]", "", line).strip()
        if not line:
            continue
        if line[-1] not in ".!?:;,":
            line += "."  # each line its own sentence: the voice pauses
        lines.append(line)
    t = " ".join(lines)
    unit_re, unit_word, word_re = _RE[lang]
    t = word_re.sub(lambda m: _WORDS[lang][m.group(1)], t)
    t = unit_re.sub(lambda m: " " + unit_word[m.group(1)], t)
    t = re.sub(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", lambda m: _date(m, lang), t)  # 1/9/2021 -> 1 settembre 2021
    t = re.sub(r"(\d)/(\d)", rf"\1 {_OVER[lang]} \2", t)  # 1/300 -> 1 su 300
    t = re.sub(r"(\d)-(\d)", r"\1 \2", t)  # CEI 64-8 -> 64 8, not "64 meno 8"
    for sym, word in _SYMBOLS[lang].items():
        t = t.replace(sym, word)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"([,.;:])[,.;:]+", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    if len(t) > limit:  # cut at the end of a sentence
        cut = t[:limit]
        t = cut[: max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! ")) + 1] or cut
    return t
