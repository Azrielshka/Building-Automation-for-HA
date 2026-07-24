"""Адаптер публикации: доменные события ядра → шина HA (SPEC §2.3, этап 7a).

Событие — импульс без памяти (ТЗ §10); мониторинг строится не на нём, а на
состоянии сущностей (их обновляет координатор через `async_set_updated_data`).
Здесь только трансляция доменных событий машины на шину для внешних подписчиков
(дашборд, автоматизации, MQTT-мост).

События здания-широкие: `floor_id`/`area_id` в payload отсутствуют — поле
контракта зарезервировано под будущую детализацию по этажам.

Грузится только в среде HA; ядро его не импортирует.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..const import (
    EVENT_MODE_CHANGED,
    EVENT_MODE_WARNING,
    EVENT_TRANSITION_CANCELLED,
)
from ..domain.types import ModeChanged, ModeWarning, TransitionCancelled

if TYPE_CHECKING:
    from collections.abc import Iterable

    from homeassistant.core import HomeAssistant

    from ..domain.types import DomainEvent


def publish_events(hass: HomeAssistant, events: Iterable[DomainEvent]) -> None:
    """Разослать доменные события машины на шину HA."""
    for event in events:
        if isinstance(event, ModeChanged):
            hass.bus.async_fire(
                EVENT_MODE_CHANGED,
                {
                    "new_mode": event.new_mode.value,
                    "previous_mode": (
                        event.previous_mode.value
                        if event.previous_mode is not None
                        else None
                    ),
                    "source": event.source.value,
                },
            )
        elif isinstance(event, ModeWarning):
            hass.bus.async_fire(
                EVENT_MODE_WARNING,
                {
                    "target_mode": event.target_mode.value,
                    "apply_at": event.apply_at,
                },
            )
        elif isinstance(event, TransitionCancelled):
            hass.bus.async_fire(
                EVENT_TRANSITION_CANCELLED,
                {"cancelled_mode": event.cancelled_mode.value},
            )
