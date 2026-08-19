"""Адаптер источника расписания: состояние сенсора → снимок ядра.

Источник — **один** сенсор (`sensor.event_schedule_mode`), чьё состояние прямо и
есть режим. Шов между реестром состояний HA и чистой `resolve_schedule_mode`
(SPEC §2.3). Грузится только в среде HA — ядро его не импортирует.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def read_schedule_state(hass: HomeAssistant, entity_id: str) -> str | None:
    """Состояние сенсора расписания или `None`, если сущности нет.

    `unavailable`/`unknown` возвращаются как есть — ядро трактует их (и `None`)
    как недоступность источника и применяет fallback.
    """
    state = hass.states.get(entity_id)
    return state.state if state is not None else None
