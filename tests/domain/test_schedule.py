"""Тесты разрешения режима расписания (SPEC §5.1, модуль domain/schedule.py)."""

from __future__ import annotations

from custom_components.building_automation.domain.schedule import (
    resolve_schedule_mode,
)
from custom_components.building_automation.domain.types import (
    ScheduleEvent,
    ScheduleMode,
)


def test_single_active_event() -> None:
    """Активно ровно одно событие — его режим, источник доступен, аномалии нет."""
    result = resolve_schedule_mode(
        [ScheduleEvent(event_type="lesson", active=True)],
        fallback=ScheduleMode.OFF,
    )
    assert result.mode is ScheduleMode.LESSON
    assert result.source_available is True
    assert result.overlap == ()


def test_empty_input_gives_fallback() -> None:
    """Пустой вход — fallback-режим и источник помечен недоступным."""
    result = resolve_schedule_mode([], fallback=ScheduleMode.OFF)
    assert result.mode is ScheduleMode.OFF
    assert result.source_available is False
    assert result.overlap == ()


def test_overlap_resolved_by_priority() -> None:
    """Наложение lesson+break → break; аномалия перечисляет оба типа."""
    result = resolve_schedule_mode(
        [
            ScheduleEvent(event_type="lesson", active=True),
            ScheduleEvent(event_type="break", active=True),
        ],
        fallback=ScheduleMode.OFF,
    )
    assert result.mode is ScheduleMode.BREAK
    assert result.source_available is True
    assert set(result.overlap) == {ScheduleMode.LESSON, ScheduleMode.BREAK}


def test_unknown_event_type_ignored() -> None:
    """Неизвестный тип отбрасывается; известный активный побеждает без аномалии."""
    result = resolve_schedule_mode(
        [
            ScheduleEvent(event_type="lesson", active=True),
            ScheduleEvent(event_type="xyz", active=True),
        ],
        fallback=ScheduleMode.OFF,
    )
    assert result.mode is ScheduleMode.LESSON
    assert result.overlap == ()


def test_full_priority_order() -> None:
    """Все четыре типа активны одновременно — побеждает break."""
    result = resolve_schedule_mode(
        [ScheduleEvent(event_type=m.value, active=True) for m in ScheduleMode],
        fallback=ScheduleMode.OFF,
    )
    assert result.mode is ScheduleMode.BREAK
    assert len(result.overlap) == 4


def test_inactive_events_do_not_count() -> None:
    """Недоступная (inactive) сущность не считается активной → fallback."""
    result = resolve_schedule_mode(
        [ScheduleEvent(event_type="lesson", active=False)],
        fallback=ScheduleMode.OFF,
    )
    assert result.mode is ScheduleMode.OFF
    assert result.source_available is False
