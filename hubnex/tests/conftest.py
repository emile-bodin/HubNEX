"""A scripted stand-in for the Anthropic client so tests run offline."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from hubnex.config import Settings, load_org
from hubnex.hq import HQ
from hubnex.store import Store

ROOT = Path(__file__).resolve().parent.parent


def text_block(text):
    return NS(type="text", text=text)


def tool_block(name, inp, id_="toolu_1"):
    return NS(type="tool_use", name=name, input=inp, id=id_)


def response(content, stop_reason):
    usage = NS(input_tokens=10, output_tokens=5, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return NS(content=content, stop_reason=stop_reason, usage=usage)


class _Stream:
    def __init__(self, resp):
        self.resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        async def gen():
            for block in self.resp.content:
                yield NS(type="content_block_start", content_block=block)

        return gen()

    async def get_final_message(self):
        return self.resp


class FakeClient:
    """Returns the queued responses in order and records every request."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.beta = NS(messages=NS(stream=self._stream, create=self._create))

    def _stream(self, **kwargs):
        # Snapshot messages: the loop appends to the same list afterwards.
        # Snapshot tools too: tool search adds to the same list mid-turn.
        snap = {**kwargs, "messages": list(kwargs["messages"])}
        if "tools" in kwargs:
            snap["tools"] = list(kwargs["tools"])
        self.requests.append(snap)
        return _Stream(self.responses.pop(0))

    async def _create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


class FakeTeam:
    """Stands in for the Telegram group: records what each bot posts."""

    enabled = True
    home_chat = -100

    def __init__(self):
        self.posts = []
        self.buttons = []
        self._next = 1

    async def post(self, agent_id, text, chat_id=None, buttons=None, reply_to=None):
        self.posts.append({"agent": agent_id, "text": text, "chat": chat_id, "buttons": buttons})
        self._next += 1
        return (chat_id or self.home_chat, self._next)

    async def set_buttons(self, agent_id, chat_id, msg_id, buttons):
        self.buttons.append((msg_id, buttons))


@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=str(tmp_path / "t.db"), agents_file=str(ROOT / "config" / "agents.yaml"), casa_file=str(tmp_path / "casa.yaml"))


@pytest.fixture
def make_hq(settings):
    def make(responses, team=None):
        return HQ(
            settings, load_org(settings.agents_file), Store(settings.db_path), client=FakeClient(responses), team=team
        )

    return make
