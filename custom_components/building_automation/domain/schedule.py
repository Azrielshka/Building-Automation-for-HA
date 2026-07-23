"""Разрешение режима расписания из снимка источника (SPEC §2.2.1, §3.3)."""

from __future__ import annotations

from collections.abc import Sequence

from .types import ScheduleEvent, ScheduleMode, ScheduleResolution

# Приоритет при наложении: конкретное важнее широкого, при неоднозначности —
# режим со включённым светом (SPEC §3.3 ТЗ). Старшинство — по позиции в кортеже.
_PRIORITY: tuple[ScheduleMode, ...] = (
    ScheduleMode.BREAK,
    ScheduleMode.WINDOW,
    ScheduleMode.LESSON,
    ScheduleMode.OFF,
)

# Известные типы событий; неизвестные атрибуты источника игнорируются.
_KNOWN: dict[str, ScheduleMode] = {mode.value: mode for mode in ScheduleMode}


def resolve_schedule_mode(
    events: Sequence[ScheduleEvent],
    fallback: ScheduleMode,
) -> ScheduleResolution:
    """Определить режим расписания по активным событиям.

    Тотальна: на любом входе возвращает результат, не бросает.
    """
    active_modes = {
        _KNOWN[e.event_type] for e in events if e.active and e.event_type in _KNOWN
    }
    if not active_modes:
        return ScheduleResolution(
            mode=fallback,
            source_available=False,
            overlap=(),
        )
    ordered = tuple(m for m in _PRIORITY if m in active_modes)
    overlap = ordered if len(active_modes) > 1 else ()
    return ScheduleResolution(
        mode=ordered[0],
        source_available=True,
        overlap=overlap,
    )
