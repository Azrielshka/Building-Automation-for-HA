"""Адаптер исполнения: план каскада → сервисные вызовы HA (SPEC §2.3, этап 7a).

Целеуказание (этап 12): свет — по конкретной световой сущности (`entity_id`),
автояркость (room-pinned) — по `area_id` (сервис сам отбирает датчики Area). Вид
цели несёт `Command.target_kind`. Домен и сервис уже прошли белый список в
`domain/storage_schema`; здесь — только вызов.

**Изоляция сбоев** (§5.4 ТЗ): ошибка одного вызова не отменяет прочие. Вызовы
неблокирующие (`blocking=False`) — HA ставит их в очередь и исполняет независимо,
поэтому сбой одной команды естественно изолирован от остальных; неудачную
постановку в очередь ловим и логируем, цикл продолжается.

Грузится только в среде HA; ядро его не импортирует.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..domain.types import TargetKind

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..domain.types import CascadePlan

_LOGGER = logging.getLogger(__name__)


async def execute_plan(hass: HomeAssistant, plan: CascadePlan) -> None:
    """Исполнить команды плана каскада: свет — по entity_id, автояркость — по area."""
    for command in plan.commands:
        action = command.action
        target_field = (
            "entity_id" if command.target_kind is TargetKind.ENTITY else "area_id"
        )
        try:
            await hass.services.async_call(
                action.domain,
                action.service,
                {**action.data, target_field: command.target},
                blocking=False,
            )
        except Exception:  # изоляция сбоя одной команды (§5.4 ТЗ)
            _LOGGER.exception(
                "Не удалось поставить в очередь %s.%s для %s=%s",
                action.domain,
                action.service,
                target_field,
                command.target,
            )
