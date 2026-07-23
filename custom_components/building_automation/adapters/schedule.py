"""Адаптер источника расписания: сущности Home Assistant → снимок ядра.

Шов между реестром состояний HA и чистой функцией `resolve_schedule_mode`
(SPEC §2.3). Сам модуль грузится только в среде HA — ядро его не импортирует.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..domain.types import ScheduleEvent

if TYPE_CHECKING:
    from collections.abc import Iterable

    from homeassistant.core import HomeAssistant


def read_schedule_events(
    hass: HomeAssistant,
    source_entity_ids: Iterable[str],
) -> list[ScheduleEvent]:
    """Собрать снимок событий расписания из состояний HA.

    Сущность считается активной, только если её состояние ровно `"on"`;
    `unavailable`/`unknown` и отсутствующие сущности активными не считаются
    (SPEC §5.1). Атрибут `event_type` берётся как есть — неизвестные значения
    отбрасывает ядро.
    """
    events: list[ScheduleEvent] = []
    for entity_id in source_entity_ids:
        state = hass.states.get(entity_id)
        if state is None:
            continue
        event_type = str(state.attributes.get("event_type", ""))
        events.append(ScheduleEvent(event_type=event_type, active=state.state == "on"))
    return events
