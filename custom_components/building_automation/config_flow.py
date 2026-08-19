"""Config flow: базовая настройка интеграции (SPEC §9.1, этап 1).

Задаёт минимум для запуска — источник расписания и fallback-режим. Топология
берётся из реестра HA и здесь не настраивается. Грузится только в среде HA.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers import selector

from .const import (
    CONF_FALLBACK,
    CONF_SCHEDULE_SOURCE,
    DEFAULT_SCHEDULE_SOURCE,
    DOMAIN,
)
from .domain.types import ScheduleMode

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult

_SCHEMA = vol.Schema(
    {
        # Один сенсор, чьё состояние — режим (lesson/break/window/off).
        vol.Required(
            CONF_SCHEDULE_SOURCE, default=DEFAULT_SCHEDULE_SOURCE
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                filter=selector.EntityFilterSelectorConfig(domain="sensor"),
            ),
        ),
        vol.Required(
            CONF_FALLBACK, default=ScheduleMode.OFF.value
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[mode.value for mode in ScheduleMode],
                translation_key="schedule_mode",
            ),
        ),
    }
)


class BuildingAutomationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Диалог установки интеграции «Building Automation»."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Единственный шаг: источник расписания и fallback-режим."""
        if user_input is not None:
            return self.async_create_entry(title="Building Automation", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_SCHEMA)
