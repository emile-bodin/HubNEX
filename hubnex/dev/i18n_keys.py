"""The Italian texts that need an English (and Dutch) version.
Dashboard: every t("…") in web/*.js and the data-i18n texts and attributes of web/index.html.
Add-on (--python): every tr("…") / tr_sys("…") in hubnex/**/*.py.
    python dev/i18n_keys.py [--python] [--missing] [--lang en|nl]"""

import json
import re
import sys
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
PY_CALL = re.compile(r'''\btr(?:_sys)?\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+|'(?:[^'\\]|\\.)*')''')
CALL = re.compile(r'\bt\(\s*"((?:[^"\\]|\\.)*)"')


def js_keys() -> set[str]:
    keys = set()
    for f in WEB.glob("*.js"):
        if f.name.startswith("i18n"):
            continue
        for m in CALL.finditer(f.read_text(encoding="utf-8")):
            keys.add(json.loads(f'"{m.group(1)}"'))
    return keys


def html_keys() -> set[str]:
    src = (WEB / "index.html").read_text(encoding="utf-8")
    keys = set()
    for m in re.finditer(r"<(\w+)([^>]*\bdata-i18n\b[^>]*)>([^<]*)", src):
        if "data-i18n-attr" in m.group(2) and not re.search(r"\bdata-i18n(?!-)", m.group(2)):
            continue
        text = unescape(m.group(3)).strip()
        if text:
            keys.add(text)
    for m in re.finditer(r'<\w+([^>]*\bdata-i18n-attr="([^"]+)"[^>]*)>', src):
        for attr in m.group(2).split(","):
            v = re.search(rf'\b{attr}="([^"]*)"', m.group(1))
            if v and v.group(1).strip():
                keys.add(unescape(v.group(1)))
    return keys


def py_keys() -> set[str]:
    keys = set()
    for f in (ROOT / "hubnex").rglob("*.py"):
        for m in PY_CALL.finditer(f.read_text(encoding="utf-8")):
            lit = m.group(1)
            if lit.startswith("'"):  # a single-quoted literal (inside an f-string)
                keys.add(lit[1:-1].replace("\\'", "'"))
                continue
            parts = re.findall(r'"((?:[^"\\]|\\.)*)"', lit)  # adjacent literals join
            keys.add("".join(json.loads(f'"{p}"') for p in parts))
    return keys


def py_texts(lang: str = "en") -> dict:
    from importlib import util
    spec = util.spec_from_file_location(f"i18n_{lang}", ROOT / "hubnex" / f"i18n_{lang}.py")
    mod = util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, lang.upper())


def js_texts(lang: str = "en") -> dict:
    src = (WEB / f"i18n-{lang}.js").read_text(encoding="utf-8")
    body = src[src.index("{"): src.rindex("}") + 1]
    return json.loads(body)


if __name__ == "__main__":
    python = "--python" in sys.argv
    keys = py_keys() if python else js_keys() | html_keys()
    lang = sys.argv[sys.argv.index("--lang") + 1] if "--lang" in sys.argv else "en"
    if "--missing" in sys.argv:
        have = py_texts(lang) if python else js_texts(lang)
        keys = keys - set(have)
    print(json.dumps(sorted(keys), ensure_ascii=False, indent=0))
