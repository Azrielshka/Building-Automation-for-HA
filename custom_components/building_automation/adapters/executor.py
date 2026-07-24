"""Адаптер исполнения: план каскада → сервисные вызовы HA (SPEC §2.3, этап 7a).

Целеуказание по `area_id` (решение §7.2): каждое действие профиля разворачивается
Home Assistant во все световые сущности целевой Area. Домен и сервис уже прошли
белый список в `domain/storage_schema`; здесь — только вызов.

**Изоляция сбоев** (§5.4 ТЗ): ошибка одного вызова не отменяет прочие. Вызовы
неблокирующие (`blocking=False`) — HA ставит их в очередь и исполняет независимо,
поэтому сбой одной команды естественно изолирован от остальных; неудачную
постановку в очередь ловим и логируем, цикл продолжается.

Грузится только в среде HA; ядро его не импортирует.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..domain.types import CascadePlan

_LOGGER = logging.getLogger(__name__)


async def execute_plan(hass: HomeAssistant, plan: CascadePlan) -> None:
    """Исполнить команды плана каскада как сервисные вызовы по `area_id`."""
    for command in plan.commands:
        action = command.action
        try:
            await hass.services.async_call(
                action.domain,
                action.service,
                {**action.data, "area_id": command.target_area_id},
                blocking=False,
            )
        except Exception:  # изоляция сбоя одной команды (§5.4 ТЗ)
            _LOGGER.exception(
                "Не удалось поставить в очередь %s.%s для area %s",
                action.domain,
                action.service,
                command.target_area_id,
            )
