"""Разрешение режима расписания из состояния источника (SPEC §2.2.1, §3.3).

Источник — **один** сенсор, чьё СОСТОЯНИЕ прямо и есть режим (`lesson` / `break`
/ `window` / `off`). Приоритет типов и наложения разрешает сам источник, поэтому
здесь — только маппинг «состояние → режим» и признак доступности.
"""

from __future__ import annotations

from .types import ScheduleMode, ScheduleResolution

# Известные состояния источника → режим. Иначе — источник недоступен, fallback.
_KNOWN: dict[str, ScheduleMode] = {mode.value: mode for mode in ScheduleMode}


def resolve_schedule_mode(
    raw_state: str | None,
    fallback: ScheduleMode,
) -> ScheduleResolution:
    """Определить режим по состоянию источника.

    `raw_state` — состояние сенсора расписания (или `None`, если сенсора нет).
    Известное состояние → его режим, источник доступен. Иначе (`None`,
    `unavailable`/`unknown`, неизвестное значение) → fallback, источник
    недоступен. Тотальна: на любом входе возвращает результат, не бросает.
    """
    mode = _KNOWN.get(raw_state or "")
    if mode is None:
        return ScheduleResolution(mode=fallback, source_available=False)
    return ScheduleResolution(mode=mode, source_available=True)
