"""Типы ядра. Все структуры неизменяемы (SPEC §3.1)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

type FloorId = str
type AreaId = str


class ScheduleMode(StrEnum):
    """Режим расписания."""

    LESSON = "lesson"
    BREAK = "break"
    OFF = "off"
    WINDOW = "window"


class ControlMode(StrEnum):
    """Режим управления зданием (SPEC §4.1 ТЗ)."""

    AUTO = "auto"
    MANUAL = "manual"


class FloorControl(StrEnum):
    """Режим управления этажа: по зданию либо ручной стоп."""

    BY_BUILDING = "by_building"
    MANUAL = "manual"


class SkipReason(StrEnum):
    """Причина, по которой помещение пропущено каскадом (SPEC §2.2.4).

    Порядок проверки фиксирован: BUILDING_MANUAL → FLOOR_MANUAL → OPT_OUT →
    ORPHANED → INVARIANT_BROKEN.
    """

    BUILDING_MANUAL = "building_manual"
    FLOOR_MANUAL = "floor_manual"
    OPT_OUT = "opt_out"
    ORPHANED = "orphaned"
    INVARIANT_BROKEN = "invariant_broken"


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


@dataclass(frozen=True)
class Action:
    """Одно действие профиля: сервисный вызов к групповому светильнику.

    Домен ограничен `light`/`switch`, сервис — `turn_on`/`turn_off`
    (валидируется в storage_schema, SPEC §4.2 ТЗ).
    """

    domain: str
    service: str
    data: Mapping[str, Any] = field(default_factory=dict)


# Набор действий — кортеж ради хешируемости (нужна для схлопывания, SPEC §4.1).
type ActionSet = tuple[Action, ...]


@dataclass(frozen=True)
class ModeSettings:
    """Настройки режима с областью действия «здание» (SPEC §5.1 ТЗ)."""

    delay_seconds: int
    sensors_allowed: bool
    sensors_allowed_by_floor: Mapping[FloorId, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class Config:
    """Конфигурация Оркестратора: профили и настройки режимов (SPEC §3.1)."""

    modes: Mapping[ScheduleMode, ModeSettings]
    actions_object: Mapping[ScheduleMode, ActionSet]
    actions_by_floor: Mapping[tuple[FloorId, ScheduleMode], ActionSet]
    actions_by_room_type: Mapping[tuple[RoomType, ScheduleMode], ActionSet]
    actions_by_area: Mapping[tuple[AreaId, ScheduleMode], ActionSet]
    fallback_mode: ScheduleMode


@dataclass(frozen=True)
class ControlState:
    """Снимок режима управления — вход планировщика каскада (SPEC §2.2.4)."""

    building: ControlMode
    floors: Mapping[FloorId, FloorControl] = field(default_factory=dict)


@dataclass(frozen=True)
class Command:
    """Одна команда каскада: применить действие к целевой Area."""

    target_area_id: AreaId
    action: Action


@dataclass(frozen=True)
class SkipEntry:
    """Пропущенное помещение с причиной."""

    area_id: AreaId
    reason: SkipReason


@dataclass(frozen=True)
class CascadePlan:
    """План каскада: команды к исполнению и отчёт о пропусках (SPEC §2.2.4)."""

    commands: tuple[Command, ...]
    skipped: tuple[SkipEntry, ...]
