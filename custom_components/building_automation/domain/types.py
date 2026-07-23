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


class AreaStatus(StrEnum):
    """Статус инварианта Area (SPEC §3.3 ТЗ).

    `NO_LIGHT` и `MULTIPLE_LIGHTS` — оба означают нарушение: каскад по такой
    Area не выполняется.
    """

    OK = "ok"
    NO_LIGHT = "no_light"
    MULTIPLE_LIGHTS = "multiple_lights"


class RoomType(StrEnum):
    """Тип помещения (метка на Area). Значения соответствуют генератору."""

    CLASS = "class"
    KORRIDOR = "korridor"
    RECREATION = "recreation"
    ZAL = "zal"
    SPECIAL = "special"
    HALL = "hall"


@dataclass(frozen=True)
class Floor:
    """Этаж (Floor) с необязательной агрегатной Area (SPEC §3.2 ТЗ)."""

    floor_id: FloorId
    aggregate_area_id: AreaId | None = None


@dataclass(frozen=True)
class Room:
    """Помещение (Area) — единица применения каскада.

    `status` — результат проверки инварианта Area (`evaluate_area`), вычисляется
    адаптером при сборке снимка.
    """

    area_id: AreaId
    floor_id: FloorId
    room_type: RoomType | None = None
    opt_out: bool = False
    status: AreaStatus = AreaStatus.OK


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
