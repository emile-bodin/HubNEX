"""What brAIn's server read from its process environment, per tool call in HubNEX.

brAIn runs one server process per channel, so it reads who is asking (BRAIN_CHANNEL), whether
voice may only reach exposed entities (BRAIN_EXPOSED_ONLY), the deny-list and the protected
entities from its environment once. Inside HubNEX one server answers every channel, so the
ported module reads those through here instead: `CALL` holds the current call's values (set by
bridge.InProcessServer for each call, in a copied context), `STATIC` the add-on-wide ones.
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from typing import Any

# The current call: {"env": {...}, "exposed_only": bool, "denied_services": [...],
# "protected_entities": [...]} — see bridge.InProcessServer.call_context.
CALL: ContextVar[dict] = ContextVar("hubnex_brain_call", default={})

_NOWHERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".absent")
# Paths of brAIn's own files that must never exist here: its YOLO switch (stands every rule
# down), its tripwire file, its memory and its ledger. HubNEX keeps its ledger in its database.
STATIC: dict[str, str] = {
    "BRAIN_YOLO_FILE": os.path.join(_NOWHERE, "yolo"),
    "BRAIN_HONEYTOKEN_FILE": os.path.join(_NOWHERE, "honeytoken"),
    "BRAIN_MEMORY_DIR": os.path.join(_NOWHERE, "memory"),
    "BRAIN_ACTION_LEDGER": os.path.join(_NOWHERE, "actions.jsonl"),
    "BRAIN_SHARED_DIR": _NOWHERE,
    "BRAIN_INTEGRATION_DIR": _NOWHERE,
    "BRAIN_BROWSER_TOKEN_FILE": os.path.join(_NOWHERE, "browser_token"),
    "BRAIN_PANEL_URL": "http://127.0.0.1:9",  # nothing listens: bridge replaces the panel calls anyway
}


def env(key: str, default: Any = None) -> Any:
    values = CALL.get().get("env") or {}
    if key in values:
        return values[key]
    return STATIC.get(key, default)


def env_has(key: str) -> bool:
    return key in (CALL.get().get("env") or {}) or key in STATIC


class CtxFlag:
    """A module-level flag of brAIn's that is true or false per call."""

    def __init__(self, name: str):
        self.name = name

    def __bool__(self) -> bool:
        return bool(CALL.get().get(self.name))

    def __repr__(self) -> str:
        return f"CtxFlag({self.name}={bool(self)})"


class CtxList(list):
    """A module-level list of brAIn's (deny-list, protected entities) whose items are per call."""

    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def _items(self) -> list:
        return list(CALL.get().get(self.name) or ())

    def __iter__(self):
        return iter(self._items())

    def __len__(self) -> int:
        return len(self._items())

    def __bool__(self) -> bool:
        return bool(self._items())

    def __contains__(self, item) -> bool:
        return item in self._items()

    def __getitem__(self, i):
        return self._items()[i]

    def __repr__(self) -> str:
        return f"CtxList({self.name}={self._items()!r})"
