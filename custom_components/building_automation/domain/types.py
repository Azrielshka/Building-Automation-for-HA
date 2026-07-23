"""Типы ядра. Все структуры неизменяемы (SPEC §3.1)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

type FloorId = str
type AreaId = str


class ScheduleMode(StrEnum):
    """Режим расписания."""

    LESSON = "lesson"
    BREAK = "break"
    OFF = "off"
    WINDOW = "window"


@dataclass(frozen=True)
class ScheduleEvent:
    """Снимок одной сущности источника расписания.

    `event_type` — сырой атрибут (может быть неизвестным); `active` — сущность
    в состоянии «включено» и доступна.
    """

    event_type: str
    active: bool


@dataclass(frozen=True)
class ScheduleResolution:
    """Результат разрешения режима расписания.

    `overlap` — набор одновременно активных известных типов при аномалии
    источника; пустой кортеж, если аномалии нет.
    """

    mode: ScheduleMode
    source_available: bool
    overlap: tuple[ScheduleMode, ...]
