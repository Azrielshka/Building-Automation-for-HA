"""Чтение состояния автояркости по помещениям (этап 11, индикация).

Соседняя интеграция `arvid_dali_center` держит у каждого датчика освещённости
сущность-тумблер `switch.*` (`on` — автояркость работает, `off` —
приостановлена). Для мониторинга агрегируем эти тумблеры по Area помещения.

Опознавание — по префиксу `switch.il_*` (решение владельца: `il` — тип
«освещённость», устойчивее произвольного имени). Handoff советует не парсить
имена, но надёжного признака в реестре он не даёт, а объект использует этот
префикс. Это **только индикация**: управление идёт по `area_id` через сервис и
от опознавания не зависит; ошибочный/переименованный тумблер максимум исказит
показанное состояние, но не поведение.

Грузится только в среде HA; ядро его не импортирует.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

if TYPE_CHECKING:
    from collections.abc import Iterable

    from homeassistant.core import HomeAssistant

    from ..domain.types import AreaId

_PREFIX = "il_"


def read_autobrightness_by_area(
    hass: HomeAssistant, area_ids: Iterable[AreaId]
) -> tuple[dict[AreaId, str], list[str]]:
    """Состояние автояркости по помещениям + список наблюдаемых сущностей.

    Возвращает `(by_area, entities)`:
    - `by_area[area_id]` — `"on"` / `"off"` / `"mixed"` для помещений, где найден
      хотя бы один `switch.il_*`; помещения без тумблеров в словарь не попадают
      (панель покажет «—»);
    - `entities` — отсортированный список entity_id тумблеров, чтобы панель
      подписалась на их изменения (живая индикация).
    """
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    wanted = set(area_ids)
    by_area: dict[AreaId, list[str]] = {}
    entities: list[str] = []
    for state in hass.states.async_all("switch"):
        object_id = state.entity_id.split(".", 1)[1]
        if not object_id.startswith(_PREFIX):
            continue
        area = _area_of(ent_reg, dev_reg, state.entity_id)
        if area is None or area not in wanted:
            continue
        by_area.setdefault(area, []).append(state.state)
        entities.append(state.entity_id)
    return {area: _aggregate(states) for area, states in by_area.items()}, sorted(
        entities
    )


def _area_of(
    ent_reg: er.EntityRegistry, dev_reg: dr.DeviceRegistry, entity_id: str
) -> str | None:
    """Area сущности: явная у записи, иначе унаследованная от устройства."""
    entry = ent_reg.async_get(entity_id)
    if entry is None:
        return None
    if entry.area_id is not None:
        return entry.area_id
    if entry.device_id is not None:
        device = dev_reg.async_get(entry.device_id)
        if device is not None:
            return device.area_id
    return None


def _aggregate(states: list[str]) -> str:
    """Свести состояния тумблеров помещения: все on / все off / иначе mixed.

    `states` непустой (в словарь попадают только помещения с тумблерами).
    Недоступные (`unavailable`/`unknown`) дают `mixed` — состояние неоднородно.
    """
    if all(state == "on" for state in states):
        return "on"
    if all(state == "off" for state in states):
        return "off"
    return "mixed"
