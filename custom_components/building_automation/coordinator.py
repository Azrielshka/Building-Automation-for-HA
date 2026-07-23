"""Координатор: связывает снимки HA с ядром и держит текущий результат.

Оболочка (SPEC §2.3). На этапе 1 отвечает только за режим расписания: читает
источник, гоняет `resolve_schedule_mode`, обновляет подписчиков по изменению
источника (push, без опроса). Грузится только в среде HA.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .adapters.schedule import read_schedule_events
from .const import CONF_FALLBACK, CONF_SCHEDULE_SOURCE, DOMAIN
from .domain.schedule import resolve_schedule_mode
from .domain.types import ScheduleMode, ScheduleResolution

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import Event, EventStateChangedData, HomeAssistant

_LOGGER = logging.getLogger(__name__)


class BuildingCoordinator(DataUpdateCoordinator[ScheduleResolution]):
    """Держит текущее разрешение расписания и рассылает обновления сущностям."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Инициализировать координатор из конфигурации entry."""
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self.entry = entry
        self._source_ids: list[str] = list(entry.data[CONF_SCHEDULE_SOURCE])
        self._fallback = ScheduleMode(entry.data[CONF_FALLBACK])

    async def _async_update_data(self) -> ScheduleResolution:
        """Пересчитать режим расписания из текущих состояний источника."""
        events = read_schedule_events(self.hass, self._source_ids)
        return resolve_schedule_mode(events, self._fallback)

    async def async_config_entry_first_refresh(self) -> None:
        """Первый расчёт и подписка на изменения источника."""
        await super().async_config_entry_first_refresh()
        self.entry.async_on_unload(
            async_track_state_change_event(
                self.hass, self._source_ids, self._handle_source_change
            )
        )

    @callback
    def _handle_source_change(self, event: Event[EventStateChangedData]) -> None:
        """Пересчитать и разослать обновление при изменении источника."""
        self.async_set_updated_data(
            resolve_schedule_mode(
                read_schedule_events(self.hass, self._source_ids),
                self._fallback,
            )
        )
