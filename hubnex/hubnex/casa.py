"""The house view: Home Assistant areas and their entities, laid out on the owner's floor plan.

Rooms are Home Assistant areas. The floor plan (`casa.yaml` in the add-on configuration)
only says where each area is drawn; which entities are in a room comes from Home Assistant,
plus the owner's adjustments made in the dashboard ("show this one here too", "hide that").
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from hubnex.i18n import tr

if TYPE_CHECKING:
    from hubnex.integrations.ha_ws import HAWatcher

# Domains shown in the house view, and what kind of control each gets.
KINDS = {
    "light": "light", "switch": "switch", "fan": "switch", "input_boolean": "switch",
    "climate": "climate", "cover": "cover", "media_player": "media", "lock": "lock",
    "alarm_control_panel": "alarm", "scene": "scene", "script": "script", "button": "button",
    "input_button": "button", "sensor": "sensor", "binary_sensor": "binary", "camera": "camera",
    "vacuum": "vacuum", "water_heater": "climate", "humidifier": "switch", "valve": "valve", "siren": "siren",
    "person": "person", "device_tracker": "person", "remote": "switch",
    # helpers the owner sets from the dashboard (the stove's start time, a target, a mode…)
    "input_datetime": "datetime", "time": "datetime", "date": "datetime", "datetime": "datetime",
    "input_number": "number", "number": "number", "counter": "number", "timer": "sensor", "input_select": "select", "select": "select",
    "input_text": "text", "text": "text",
}
ATTRS = (
    "friendly_name", "brightness", "rgb_color", "color_mode", "current_temperature", "temperature",
    "target_temp_step", "min_temp", "max_temp", "hvac_modes", "hvac_action", "current_position",
    "unit_of_measurement", "device_class", "media_title", "source", "supported_color_modes",
    "supported_features", "code_format", "code_arm_required", "media_artist", "volume_level",
    "entity_picture", "media_position", "media_duration", "media_position_updated_at", "color_temp_kelvin",
    "min_color_temp_kelvin", "max_color_temp_kelvin",
    "fan_speed", "fan_speed_list", "status", "source_list", "shuffle", "repeat", "is_volume_muted",
    "media_album_name", "app_name", "media_series_title",
    "current_humidity", "battery_level", "hvac_action",
    "humidity", "wind_speed", "wind_speed_unit",  # the weather
    "minimum", "maximum",  # counters
    "has_date", "has_time", "min", "max", "step", "mode", "options",
    "last_period", "last_reset", "meter_period",  # utility meters: the previous period, its start
)
# What the owner can say an entity really is, whatever its Home Assistant domain
# (a relay "switch" that drives a light, a gate opened by an impulse…).
SHOW_AS = {"light", "switch", "gate", "siren", "sensor", "stock"}
# A number or counter with one of these in its name is a stock (pellet bags, water bottles…):
# shown as such without being asked.
STOCK_WORDS = re.compile(r"pellet|sacch|scorta|scorte|stock|bags?\b", re.I)
STOCK_DEFAULT = {"delivery": 15, "low": 5}
ALERT_CLASSES = {"door", "window", "opening", "garage_door", "smoke", "moisture", "gas", "safety", "problem", "carbon_monoxide"}

EXAMPLE_LAYOUT = """\
# Piantina della vista Casa. Ogni stanza è un'area di Home Assistant (stesso nome o ID).
# x, y, w, h sono in percentuale del disegno (0-100). Le aree che non compaiono qui
# vengono mostrate sotto la piantina; quelle in "outside" nel gruppo "Fuori casa".
floors:
  - name: Piano terra
    aspect: 1.06        # larghezza / altezza del disegno
    rooms:
      - { area: Soggiorno, x: 0, y: 0, w: 50, h: 60 }
      - { area: Cucina, x: 50, y: 0, w: 50, h: 60 }
      - { area: Camera da letto, x: 0, y: 60, w: 100, h: 40 }
outside: []
# energy: { power: sensor.consumo_casa, today: sensor.energia_oggi }
"""


class LayoutError(ValueError):
    pass


PLAN_IMAGE = re.compile(r"pianta-[0-9]{1,2}\.jpg")
MAX_UPLOAD = 25 * 1024 * 1024


def plan_image(data: bytes) -> tuple[bytes, float]:
    """A floor plan (photo, image or PDF) as a JPEG trimmed of empty margins, and its aspect.

    Plans usually sit in the middle of a big white sheet: trimming lets the drawing fill the
    house view."""
    import io

    from PIL import Image, ImageOps

    if data[:5] == b"%PDF-":
        import pypdfium2 as pdfium

        page = pdfium.PdfDocument(data)[0]
        w, h = page.get_size()
        img = page.render(scale=min(2400 / max(w, h), 4)).to_pil()
    else:
        try:
            img = Image.open(io.BytesIO(data))
            img = ImageOps.exif_transpose(img)
        except Exception as exc:
            raise LayoutError(tr("formato non riconosciuto: usa una foto, un'immagine o un PDF")) from exc
    img = img.convert("RGB")
    ink = ImageOps.invert(img.convert("L")).point(lambda v: 255 if v > 40 else 0)
    box = ink.getbbox()
    if box:
        pad = int(max(img.size) * 0.02)
        box = (max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, img.width), min(box[3] + pad, img.height))
        img = img.crop(box)
    img.thumbnail((2400, 2400))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    return out.getvalue(), round(img.width / img.height, 3)


SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "rooms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "area": {"type": "string"},
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "w": {"type": "number"},
                    "h": {"type": "number"},
                    "outline": {"type": "boolean"},
                    "points": {"type": "array", "items": {"type": "object", "properties": {
                        "x": {"type": "number"}, "y": {"type": "number"}},
                        "required": ["x", "y"], "additionalProperties": False}},
                },
                "required": ["label", "area", "x", "y", "w", "h", "outline", "points"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["rooms"],
    "additionalProperties": False,
}


def suggest_prompt(areas: list[str]) -> str:
    names = "\n".join(f"- {a}" for a in areas) or "- (nessuna area)"
    return (
        "Questa è la planimetria di un piano di un'abitazione. Individua ogni stanza e restituisci "
        "la sua forma: x e y dell'angolo in alto a sinistra, w e h del rettangolo che la contiene, "
        "tutti in percentuale (0-100) dell'IMMAGINE INTERA. Per stanze non rettangolari, "
        "inclusi corridoi a L, indica i vertici ordinati del contorno in points [{x,y}, ...]. "
        "Per i rettangoli usa points: []. Includi corridoi, bagni, ripostigli, lavanderie. "
        "Balconi, terrazzi, verande e giardini che circondano la casa mettili con outline=true.\n"
        "label: il nome scritto sul disegno (o una descrizione breve se manca). Ignora quote e misure.\n"
        "area: scegli l'area di Home Assistant corrispondente da questo elenco, scritta esattamente "
        "così, oppure stringa vuota se nessuna corrisponde:\n" + names
    )


def clean_suggestion(raw: dict, areas: list[str]) -> tuple[list[dict], int]:
    """Rooms from the model, kept inside the drawing, with only real area names."""
    known = {a.lower(): a for a in areas}
    rooms, skipped = [], 0
    for r in raw.get("rooms", [])[:60]:
        try:
            points = r.get("points") or []
            if points:
                points, box = polygon_box(points)
            else:
                x, y = max(0.0, min(float(r["x"]), 99.0)), max(0.0, min(float(r["y"]), 99.0))
                w, h = max(1.0, min(float(r["w"]), 100 - x)), max(1.0, min(float(r["h"]), 100 - y))
                box = {"x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1)}
        except (LayoutError, KeyError, TypeError, ValueError):
            skipped += 1
            continue
        area = known.get(str(r.get("area", "")).strip().lower(), "")
        rooms.append({"area": area or str(r.get("label", "")).strip()[:60] or "Stanza", "linked": bool(area),
                      **box, **({"points": points} if points else {}), "outline": bool(r.get("outline"))})
    return rooms, skipped


def polygon_box(raw: list) -> tuple[list[dict], dict]:
    """Validate a simple polygon and return its points and containing box."""
    # ponytail: 32 corners cover room outlines; raise this and the API limit for detailed tracing.
    if not isinstance(raw, list) or not 3 <= len(raw) <= 32:
        raise LayoutError("Il contorno richiede da 3 a 32 angoli")
    try:
        points = [{"x": float(p["x"]), "y": float(p["y"])} for p in raw]
    except (KeyError, TypeError, ValueError) as exc:
        raise LayoutError("Angoli non validi") from exc
    if any(not math.isfinite(v) or not 0 <= v <= 100 for p in points for v in p.values()):
        raise LayoutError("Angoli fuori dal disegno (0-100)")
    points = [{k: round(v, 1) for k, v in p.items()} for p in points]
    vertices = [(p["x"], p["y"]) for p in points]
    if len(set(vertices)) != len(vertices):
        raise LayoutError("Angoli ripetuti")
    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def intersects(a, b, c, d):
        ab1, ab2, cd1, cd2 = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
        if ab1 * ab2 < 0 and cd1 * cd2 < 0:
            return True
        return any(v == 0 and min(u[0], w[0]) <= q[0] <= max(u[0], w[0])
                   and min(u[1], w[1]) <= q[1] <= max(u[1], w[1])
                   for v, u, w, q in ((ab1, a, b, c), (ab2, a, b, d), (cd1, c, d, a), (cd2, c, d, b)))

    n = len(vertices)
    for i in range(n):
        for j in range(i + 1, n):
            if j == i + 1 or (i == 0 and j == n - 1):
                continue
            if intersects(vertices[i], vertices[(i + 1) % n], vertices[j], vertices[(j + 1) % n]):
                raise LayoutError("Il contorno incrocia sé stesso")
    area = sum(x * vertices[(i + 1) % n][1] - y * vertices[(i + 1) % n][0]
               for i, (x, y) in enumerate(vertices))
    if abs(area) < 0.2:
        raise LayoutError("Contorno senza superficie")
    xs, ys = [p["x"] for p in points], [p["y"] for p in points]
    return points, {"x": min(xs), "y": min(ys), "w": round(max(xs) - min(xs), 1), "h": round(max(ys) - min(ys), 1)}


# Italian spellings are accepted too.
ALIASES = {"piani": "floors", "stanze": "rooms", "fuori": "outside", "energia": "energy", "nome": "name",
           "proporzione": "aspect", "contorno": "outline", "potenza": "power", "oggi": "today"}


def downsample(points: list[tuple[str, str]], buckets: int = 48) -> list[list]:
    """Numeric history for a sparkline: at most `buckets` points [iso time, value]."""
    vals = []
    for t, v in points:
        try:
            vals.append([t, float(v)])
        except (TypeError, ValueError):
            continue
    if len(vals) <= buckets:
        return vals
    step = len(vals) / buckets
    return [vals[int(i * step)] for i in range(buckets - 1)] + [vals[-1]]


def _keys(d: dict) -> dict:
    return {ALIASES.get(str(k).lower(), str(k).lower()): v for k, v in d.items()}


def parse_layout(text: str) -> dict:
    """Validated floor plan from YAML; raises LayoutError with a readable message."""
    try:
        raw = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise LayoutError(tr("YAML non valido: {a}", a=exc)) from exc
    if not isinstance(raw, dict):
        raise LayoutError(tr("il file deve iniziare con floors: (oppure rooms: per un solo piano)"))
    raw = _keys(raw)
    if "rooms" in raw and "floors" not in raw:  # a single floor written without "floors:"
        raw["floors"] = [{"name": raw.pop("name", "Piano terra"), "aspect": raw.pop("aspect", None), "rooms": raw.pop("rooms")}]
    unknown = set(raw) - {"floors", "outside", "energy"}
    if unknown:
        raise LayoutError(tr("chiave sconosciuta: {a} (valide: floors, outside, energy)", a=', '.join(sorted(unknown))))
    if not raw.get("floors"):
        raise LayoutError(tr("nessun piano: manca floors: con almeno una stanza"))
    floors = []
    for i, f in enumerate(raw.get("floors") or [], 1):
        if not isinstance(f, dict):
            raise LayoutError(tr("piano {a}: formato non valido (controlla i trattini e i rientri)", a=i))
        f = _keys(f)
        rooms = []
        for j, r in enumerate(f.get("rooms") or [], 1):
            r = _keys(r) if isinstance(r, dict) else r
            if not isinstance(r, dict) or not (r.get("area") or r.get("label")):
                raise LayoutError(f"piano {i}, stanza {j}: serve 'area'")
            if r.get("points") is not None:
                try:
                    points, box = polygon_box(r["points"])
                except LayoutError as exc:
                    raise LayoutError(f"piano {i}, stanza {r.get('area')}: {exc}") from exc
            else:
                try:
                    box = {k: float(r[k]) for k in ("x", "y", "w", "h")}
                except (KeyError, TypeError, ValueError) as exc:
                    raise LayoutError(tr("piano {a}, stanza {b}: servono x, y, w, h numerici", a=i, b=r.get('area'))) from exc
                if (not all(math.isfinite(v) for v in box.values()) or box["w"] <= 0 or box["h"] <= 0
                        or min(box["x"], box["y"]) < 0 or box["x"] + box["w"] > 100.5 or box["y"] + box["h"] > 100.5):
                    raise LayoutError(tr("piano {a}, stanza {b}: fuori dal disegno (0-100)", a=i, b=r.get('area')))
            rooms.append({"area": str(r.get("area") or r.get("label")), **box,
                          **({"points": points} if r.get("points") is not None else {}), "outline": bool(r.get("outline"))})
        aspect = float(f.get("aspect") or 1.4)
        image = str(f.get("image") or "")
        if image and not PLAN_IMAGE.fullmatch(image):
            raise LayoutError(tr("piano {a}: nome dell'immagine non valido", a=i))
        floors.append({"name": str(f.get("name") or f"Piano {i}"), "aspect": max(0.3, min(aspect, 4.0)),
                       "rooms": rooms, **({"image": image} if image else {})})
        if not rooms:
            raise LayoutError(tr("piano {a}: nessuna stanza (manca rooms:)", a=i))
    energy = _keys(raw.get("energy") or {}) if isinstance(raw.get("energy"), dict) else {}
    return {
        "floors": floors,
        "outside": [str(a) for a in raw.get("outside") or []],
        "energy": {k: str(v) for k, v in energy.items() if k in ("power", "today") and v},
    }


class Casa:
    def __init__(self, watcher: "HAWatcher", layout_path: str | Path, store):
        self.ha = watcher
        self.path = Path(layout_path)
        self.store = store
        self.layout = {"floors": [], "outside": [], "energy": {}}
        self.layout_error: str | None = None
        self._mtime: float | None = None
        self.adjust: dict[str, dict] = {"extra": {}, "hidden": {}, "temp": {}, "kind": {}, "cards": {}, "order": {}, "names": {}, "size": {}}
        self.shown: set[str] = set()  # entities on screen: only their changes go to the dashboard

    async def load(self) -> None:
        self.adjust = await self.store.get("casa_adjust", {"extra": {}, "hidden": {}})
        self.adjust.setdefault("temp", {})
        self.adjust.setdefault("kind", {})
        for key in ("cards", "order", "names", "size", "energy"):
            self.adjust.setdefault(key, {})
        self.layout_text()  # parse the saved floor plan

    # ------------------------------------------------------------------ floor plan
    def layout_text(self) -> str:
        if not self.path.exists():
            self.layout, self.layout_error, self._mtime = {"floors": [], "outside": [], "energy": {}}, None, None
            return EXAMPLE_LAYOUT
        self._mtime = self.path.stat().st_mtime
        text = self.path.read_text(encoding="utf-8")
        try:
            self.layout, self.layout_error = parse_layout(text), None
        except LayoutError as exc:
            self.layout_error = str(exc)
        return text

    # ------------------------------------------------------------------ floor plan images and editor
    def save_plan_image(self, floor: int, data: bytes) -> tuple[str, float]:
        if len(data) > MAX_UPLOAD:
            raise LayoutError(tr("file troppo grande (massimo 25 MB)"))
        image, aspect = plan_image(data)
        name = f"pianta-{floor}.jpg"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        (self.path.parent / name).write_bytes(image)
        return name, aspect

    def plan_image_path(self, name: str) -> Path | None:
        if not PLAN_IMAGE.fullmatch(name):
            return None
        p = self.path.parent / name
        return p if p.exists() else None

    def save_layout_data(self, data: dict) -> None:
        """The editor's plan as casa.yaml (still readable and editable by hand)."""
        floors = []
        for f in data.get("floors", []):
            floor = {"name": f.get("name") or "Piano", "aspect": round(float(f.get("aspect") or 1.4), 3)}
            if f.get("image"):
                floor["image"] = f["image"]
            if any(r.get("points") is None and any(r.get(k) is None for k in ("x", "y", "w", "h")) for r in f.get("rooms", [])):
                raise LayoutError("Per una stanza rettangolare servono x, y, w, h")
            floor["rooms"] = [
                {"area": r["area"], **({"points": r["points"]} if r.get("points") is not None
                                      else {k: round(float(r[k]), 1) for k in ("x", "y", "w", "h")}),
                 **({"outline": True} if r.get("outline") else {})}
                for r in f.get("rooms", [])
            ]
            floors.append(floor)
        doc = {"floors": floors, "outside": list(data.get("outside") or [])}
        if data.get("energy"):
            doc["energy"] = data["energy"]
        text = "# Piantina della vista Casa (scritta dall'editor: puoi modificarla anche a mano)\n"
        text += yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=200)
        self.save_layout(text)

    def host_path(self) -> str:
        """Where the owner finds casa.yaml: /config in the add-on is /addon_configs/<slug>."""
        if str(self.path.parent) == "/config":
            import socket

            return f"/addon_configs/{socket.gethostname().replace('-', '_')}/casa.yaml"
        return str(self.path)

    def save_layout(self, text: str) -> None:
        self.layout = parse_layout(text)  # refuse a broken plan before touching the file
        self.layout_error = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text, encoding="utf-8")
        self._mtime = self.path.stat().st_mtime

    # ------------------------------------------------------------------ owner's adjustments
    async def show_here(self, area_id: str, entity_id: str) -> None:
        for other in self.adjust["extra"].values():
            if entity_id in other:
                other.remove(entity_id)
        self.adjust["extra"].setdefault(area_id, []).append(entity_id)
        self._unhide(area_id, entity_id)
        await self.store.put("casa_adjust", self.adjust)

    async def moved_in_ha(self, area_id: str, entity_id: str) -> None:
        self._unhide(area_id, entity_id)
        for other in self.adjust["extra"].values():
            if entity_id in other:
                other.remove(entity_id)
        await self.store.put("casa_adjust", self.adjust)

    async def hide(self, area_id: str, entity_id: str) -> None:
        extra = self.adjust["extra"].get(area_id, [])
        if entity_id in extra:
            extra.remove(entity_id)
        else:
            self.adjust["hidden"].setdefault(area_id, []).append(entity_id)
        await self.store.put("casa_adjust", self.adjust)

    async def set_temperature(self, area_id: str, entity_id: str | None) -> None:
        """The sensor that gives the room its temperature (None: let the view choose)."""
        temp = self.adjust.setdefault("temp", {})
        if entity_id:
            temp[area_id] = entity_id
        else:
            temp.pop(area_id, None)
        await self.store.put("casa_adjust", self.adjust)

    async def set_kind(self, entity_id: str, kind: str | None) -> None:
        """Show an entity as another kind in the dashboard (None: as Home Assistant says)."""
        kinds = self.adjust.setdefault("kind", {})
        if kind:
            if kind not in SHOW_AS:
                raise ValueError(tr("tipo sconosciuto: {a}", a=kind))
            kinds[entity_id] = kind
        else:
            kinds.pop(entity_id, None)
        await self.store.put("casa_adjust", self.adjust)

    def stock_of(self, entity_id: str) -> dict:
        """A stock's settings, or the defaults."""
        return {**STOCK_DEFAULT, **self.adjust.get("stock", {}).get(entity_id, {})}

    def stocks(self) -> list[str]:
        """The entities shown as a stock (pellet bags…): by name, or chosen by the owner."""
        return sorted(e for e in self.ha.states if (self.compact(e) or {}).get("k") == "stock")

    async def set_stock(self, entity_id: str, delivery: int, low: int) -> None:
        """A stock's settings: how many come in a delivery, below how many to warn."""
        self.adjust.setdefault("stock", {})[entity_id] = {"delivery": delivery, "low": low}
        await self.store.put("casa_adjust", self.adjust)

    # cards the owner composes in a room, their order, names and sizes (HubNEX only)
    async def save_card(self, area_id: str, card_id: str | None, name: str, entities: list[str], size: str, group: str | None = None, enable: str | None = None, nochart: list[str] | None = None, blocks: list[dict] | None = None, color: str = "", style: str = "") -> str:
        cards = self.adjust.setdefault("cards", {}).setdefault(area_id, [])
        card_id = card_id or f"c{max([int(c['id'][1:]) for c in cards if c['id'][1:].isdigit()] or [0]) + 1}"
        card = {"id": card_id, "name": name.strip()[:60] or "Card", "entities": list(dict.fromkeys(entities))[:24], "size": size}
        if blocks is not None:  # a free card: its blocks on a 4-column grid
            card.update(kind="free", blocks=blocks[:24])
            if color:
                card["color"] = color
            if style:
                card["style"] = style
        if group:
            card["group"] = group
        if enable is not None:  # "" = the owner said: no switch, the times always apply
            card["enable"] = enable
        if nochart:
            card["nochart"] = [e for e in nochart if e in card["entities"]]
        for i, c in enumerate(cards):
            if c["id"] == card_id:
                cards[i] = card
                break
        else:
            cards.append(card)  # placed at the end of its group, until the owner moves it
        await self.store.put("casa_adjust", self.adjust)
        return card_id

    async def delete_card(self, area_id: str, card_id: str) -> None:
        self.adjust["cards"][area_id] = [c for c in self.adjust.setdefault("cards", {}).get(area_id, []) if c["id"] != card_id]
        order = self.adjust.setdefault("order", {}).get(area_id, [])
        if f"card:{card_id}" in order:
            order.remove(f"card:{card_id}")
        await self.store.put("casa_adjust", self.adjust)

    async def set_order(self, area_id: str, items: list[str]) -> None:
        self.adjust.setdefault("order", {})[area_id] = list(dict.fromkeys(items))[:300]
        await self.store.put("casa_adjust", self.adjust)

    async def set_display(self, entity_id: str, name: str | None = None, size: str | None = None, *, rename: bool = False, resize: bool = False, chart: bool | None = None) -> None:
        """Name, size and chart of an entity's card in HubNEX (None: back to Home Assistant's name / normal)."""
        if chart is not None:
            hidden = self.adjust.setdefault("nochart", [])
            if chart and entity_id in hidden:
                hidden.remove(entity_id)
            elif not chart and entity_id not in hidden:
                hidden.append(entity_id)
        if rename:
            if name and name.strip():
                self.adjust["names"][entity_id] = name.strip()[:60]
            else:
                self.adjust.setdefault("names", {}).pop(entity_id, None)
        if resize:
            if size in ("wide",):
                self.adjust["size"][entity_id] = size
            else:
                self.adjust.setdefault("size", {}).pop(entity_id, None)
        await self.store.put("casa_adjust", self.adjust)

    def energy_config(self) -> dict:
        from hubnex.energy import clean_config

        cfg = clean_config(self.adjust.get("energy") or {})
        if not cfg["power"]:
            cfg["power"] = self.layout["energy"].get("power")  # the floor plan's, if set
        return cfg

    async def set_energy_config(self, raw: dict) -> dict:
        from hubnex.energy import clean_config

        cfg = clean_config(raw)
        known = lambda e: e in self.ha.states  # noqa: E731
        cfg["bands"] = {k: v for k, v in cfg["bands"].items() if known(v)}
        cfg["prices"] = {k: v for k, v in cfg["prices"].items() if known(v)}
        cfg["readouts"] = [e for e in cfg["readouts"] if known(e)]
        for key in ("band_sensor", "total", "cost", "power"):
            if cfg[key] and not known(cfg[key]):
                cfg[key] = None
        self.adjust["energy"] = cfg
        await self.store.put("casa_adjust", self.adjust)
        return cfg

    def _unhide(self, area_id: str, entity_id: str) -> None:
        hidden = self.adjust["hidden"].get(area_id, [])
        if entity_id in hidden:
            hidden.remove(entity_id)

    # ------------------------------------------------------------------ building the view
    def visible(self, entity_id: str) -> bool:
        domain = entity_id.split(".", 1)[0]
        if domain not in KINDS:
            return False
        reg = self.ha.entities.get(entity_id) or {}
        return not (reg.get("disabled_by") or reg.get("hidden_by") or reg.get("entity_category"))

    def compact(self, entity_id: str, state: dict | None = None) -> dict | None:
        s = state if state is not None else self.ha.states.get(entity_id)
        if not s:
            return None
        attrs = s.get("attributes") or {}
        reg = self.ha.entities.get(entity_id) or {}
        # The first alias set in Home Assistant wins: it is the name the owner chose for the house.
        name = (
            self.adjust.get("names", {}).get(entity_id)  # renamed in HubNEX
            or (reg.get("aliases") or [None])[0] or reg.get("name") or attrs.get("friendly_name") or reg.get("original_name") or entity_id
        )
        native = KINDS.get(entity_id.split(".", 1)[0], "other")
        shown = self.adjust.get("kind", {}).get(entity_id)
        if not shown and native == "number" and STOCK_WORDS.search(f"{entity_id} {name}"):
            shown = "stock"
        out = {
            "s": s.get("state"),
            "n": name,
            "k": shown or native,
            "a": {k: attrs[k] for k in ATTRS if k in attrs and k != "friendly_name"},
        }
        if s.get("last_changed"):
            out["lc"] = s["last_changed"]  # since when (an open window, a person in a zone)
        if shown:
            out["nk"] = native  # what Home Assistant says it is
        if entity_id.startswith("vacuum."):
            out["mp"] = self.vacuum_map(entity_id)
        return out

    def vacuum_map(self, entity_id: str) -> str | None:
        """The map of a robot vacuum: a camera or image entity of the same device (Roborock,
        Xiaomi, Valetudo draw the robot on it), else one whose name says map and robot."""
        maps = [e for e in self.ha.states if e.split(".")[0] in ("camera", "image")]
        dev = (self.ha.entities.get(entity_id) or {}).get("device_id")
        same = [e for e in maps if dev and (self.ha.entities.get(e) or {}).get("device_id") == dev]
        is_map = lambda e: any(w in e for w in ("map", "mappa"))  # noqa: E731
        if same:
            return sorted(same, key=lambda e: not is_map(e))[0]
        token = entity_id.split(".", 1)[1].split("_")[0]
        named = [e for e in maps if is_map(e) and token in e]
        return named[0] if named else None

    def area_entities(self) -> dict[str, list[str]]:
        rooms: dict[str, list[str]] = {a: [] for a in self.ha.areas}
        for eid in self.ha.states:
            area = self.ha.area_of(eid)
            if area in rooms and self.visible(eid):
                rooms[area].append(eid)
        for area, eids in self.adjust["extra"].items():
            for eid in eids:
                if area in rooms and eid in self.ha.states and eid not in rooms[area]:
                    rooms[area].append(eid)
        for area, eids in self.adjust["hidden"].items():
            if area in rooms:
                rooms[area] = [e for e in rooms[area] if e not in eids]
        return rooms

    def _area_id(self, ref: str) -> str | None:
        if ref in self.ha.areas:
            return ref
        low = ref.strip().lower()
        return next((a for a, v in self.ha.areas.items() if (v.get("name") or "").strip().lower() == low), None)

    def _refresh_layout(self) -> None:
        """Pick up a casa.yaml edited by hand (File editor, Samba) without a restart."""
        mtime = self.path.stat().st_mtime if self.path.exists() else None
        if mtime != self._mtime:
            self.layout_text()

    def power_sensors(self, eids: set[str]) -> dict[str, str]:
        """For plugs and switches: the power sensor of the same device, shown on their card."""
        by_device: dict[str, str] = {}
        for eid, st in self.ha.states.items():
            if eid.startswith("sensor.") and (st.get("attributes") or {}).get("device_class") == "power":
                dev = (self.ha.entities.get(eid) or {}).get("device_id")
                if dev:
                    by_device.setdefault(dev, eid)
        out = {}
        for eid in eids:
            if eid.split(".", 1)[0] in ("switch", "light", "fan", "media_player", "climate", "water_heater"):
                dev = (self.ha.entities.get(eid) or {}).get("device_id")
                if dev and dev in by_device:
                    out[eid] = by_device[dev]
        return out

    def build(self) -> dict:
        self._refresh_layout()
        rooms = self.area_entities()
        floors, placed = [], set()
        for f in self.layout["floors"]:
            drawn = []
            for r in f["rooms"]:
                aid = self._area_id(r["area"])
                if aid:
                    placed.add(aid)
                drawn.append({**r, "area_id": aid, "name": self.ha.areas[aid]["name"] if aid else r["area"]})
            floors.append({**f, "rooms": drawn})
        outside_ids = [a for a in (self._area_id(x) for x in self.layout["outside"]) if a]
        placed.update(outside_ids)
        areas = [
            {
                "id": aid,
                "name": a.get("name") or aid,
                "floor": (self.ha.floors.get(a.get("floor_id") or "") or {}).get("name"),
                "entities": sorted(rooms.get(aid, []), key=lambda e: (e.split(".", 1)[0], e)),
                "outside": aid in outside_ids,
                "temp": self.adjust.get("temp", {}).get(aid),
                "cards": self.adjust.get("cards", {}).get(aid, []),
                "order": self.adjust.get("order", {}).get(aid, []),
                "placed": aid in placed,
            }
            for aid, a in sorted(self.ha.areas.items(), key=lambda kv: (kv[1].get("name") or "").lower())
        ]
        scenes = sorted(e for e in self.ha.states if e.startswith("scene.") and self.visible(e))
        # The alarm is for the whole house: always reachable, with or without an area.
        alarms = sorted(e for e in self.ha.states if e.startswith("alarm_control_panel.") and self.visible(e))
        weather = next((e for e in sorted(self.ha.states) if e.startswith("weather.")), None)
        # Who is at home: Home Assistant's people (home, away or the zone they are in).
        people = sorted(e for e in self.ha.states if e.startswith("person.") and not (self.ha.entities.get(e) or {}).get("disabled_by"))
        energy = {k: v for k, v in self.layout["energy"].items() if v in self.ha.states}
        in_cards = {e for cards in self.adjust.get("cards", {}).values() for c in cards for e in c["entities"] if e in self.ha.states}
        from hubnex.energy import entities as energy_entities

        energy_cfg = self.energy_config()
        in_cards |= {e for e in energy_entities(energy_cfg) if e in self.ha.states}
        power = self.power_sensors({e for a in areas for e in a["entities"]} | in_cards)
        shown = {e for a in areas for e in a["entities"]} | in_cards | set(scenes) | set(alarms) | set(energy.values()) | set(people) | set(power.values())
        if weather:
            shown.add(weather)
        self.shown = shown
        states = {e: self.compact(e) for e in shown}
        return {
            "ready": self.ha.ready.is_set(),
            "floors": floors,
            "areas": areas,
            "scenes": scenes,
            "alarms": alarms,
            "people": people,
            "power": power,
            "sizes": dict(self.adjust.get("size", {})),
            "nochart": list(self.adjust.get("nochart", [])),  # sensors whose chart the owner turned off
            "energy_panel": energy_cfg,
            "weather": weather,
            "stock": {**{e: dict(STOCK_DEFAULT) for e, s in states.items() if s and s["k"] == "stock"},
                      **self.adjust.get("stock", {})},  # bags in a delivery, warning threshold
            "energy": energy,
            "states": {e: s for e, s in states.items() if s},
            "layout_error": self.layout_error,
            "layout_file": self.host_path(),
        }

    def candidates(self, query: str = "", area_id: str | None = None, limit: int = 500, include_here: bool = False) -> list[dict[str, Any]]:
        """Entities that could be added to a room, for the dashboard's search: everything Home
        Assistant has, also what it hides (e.g. players hidden by Music Assistant) or files as
        diagnostic; the usual devices first."""
        q = query.strip().lower()
        here = set() if include_here else set(self.area_entities().get(area_id or "", []))
        out = []
        for eid in sorted(self.ha.states, key=lambda e: (not self.visible(e), e)):
            if eid in here or (self.ha.entities.get(eid) or {}).get("disabled_by"):
                continue
            c = self.compact(eid)
            # Also by the other names: Home Assistant's own and every alias.
            reg = self.ha.entities.get(eid) or {}
            friendly = (self.ha.states[eid].get("attributes") or {}).get("friendly_name") or ""
            also = " ".join([friendly, reg.get("name") or "", *(reg.get("aliases") or [])])
            if q and q not in f"{eid} {c['n']} {also}".lower():
                continue
            area = self.ha.area_of(eid)
            out.append({
                "entity_id": eid,
                "name": c["n"],
                "area": (self.ha.areas.get(area) or {}).get("name") if area else None,
                "registered": eid in self.ha.entities,
                "hidden": not self.visible(eid),
                "state": c,  # so a card being composed can show it at once
            })
            if len(out) >= limit:
                break
        return out
