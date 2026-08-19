"""Тесты разрешения режима расписания (SPEC §5.1, модуль domain/schedule.py).

Источник — один сенсор, чьё состояние прямо и есть режим.
"""

from __future__ import annotations

from custom_components.building_automation.domain.schedule import (
    resolve_schedule_mode,
)
from custom_components.building_automation.domain.types import ScheduleMode


def test_known_state_gives_its_mode() -> None:
    """Известное состояние → его режим, источник доступен."""
    result = resolve_schedule_mode("lesson", fallback=ScheduleMode.OFF)
    assert result.mode is ScheduleMode.LESSON
    assert result.source_available is True


def test_window_state() -> None:
    """Состояние window → режим Окно."""
    result = resolve_schedule_mode("window", fallback=ScheduleMode.OFF)
    assert result.mode is ScheduleMode.WINDOW
    assert result.source_available is True


def test_off_is_explicit_available_state() -> None:
    """`off` — явное состояние расписания: режим Off, источник доступен."""
    result = resolve_schedule_mode("off", fallback=ScheduleMode.LESSON)
    assert result.mode is ScheduleMode.OFF
    assert result.source_available is True


def test_none_gives_fallback() -> None:
    """Сенсора нет (None) → fallback, источник недоступен."""
    result = resolve_schedule_mode(None, fallback=ScheduleMode.OFF)
    assert result.mode is ScheduleMode.OFF
    assert result.source_available is False


def test_unknown_states_give_fallback() -> None:
    """`unavailable`/`unknown`/мусор/пусто → fallback, источник недоступен."""
    for bad in ("unavailable", "unknown", "xyz", ""):
        result = resolve_schedule_mode(bad, fallback=ScheduleMode.WINDOW)
        assert result.mode is ScheduleMode.WINDOW, bad
        assert result.source_available is False, bad
