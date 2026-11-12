"""The HubNEX assistant as an Assist conversation agent."""

from __future__ import annotations

import logging
from typing import Literal

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import HubNEXClient, HubNEXError
from .const import CONF_TOKEN, CONF_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([HubNEXConversationEntity(entry, HubNEXClient(hass, entry.data[CONF_URL], entry.data[CONF_TOKEN]))])


class HubNEXConversationEntity(conversation.ConversationEntity):
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, entry: ConfigEntry, client: HubNEXClient) -> None:
        self._client = client
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="HubNEX",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        return "*"

    async def _async_handle_message(
        self, user_input: conversation.ConversationInput, chat_log: conversation.ChatLog
    ) -> conversation.ConversationResult:
        try:
            reply = await self._client.ask(user_input.text, "en")
        except HubNEXError as err:
            _LOGGER.warning("HubNEX unreachable: %s", err)
            reply = "I'm sorry, I can't reach HubNEX right now."
        chat_log.async_add_assistant_content_without_tools(
            conversation.AssistantContent(agent_id=user_input.agent_id, content=reply or "Done.")
        )
        return conversation.async_get_result_from_chat_log(user_input, chat_log)
