"""Типы ядра. Все структуры неизменяемы (SPEC §3.1)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    # Разрыв цикла: topology импортирует types (Floor/Room/AreaStatus),
    # а OrchestratorState ссылается на TopologySnapshot только в аннотации.
    from .topology import TopologySnapshot

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
    """Этаж (Floor) с необязательной агрегатной Area (SPEC §3.2 ТЗ).

    `light_entity_id` — помеченный `ba_area_light` групповой свет агрегатной Area
    этажа (этап 12); цель схлопывания. `None`, если не найден/не единственный.
    """

    floor_id: FloorId
    aggregate_area_id: AreaId | None = None
    light_entity_id: str | None = None


@dataclass(frozen=True)
class Room:
    """Помещение (Area) — единица применения каскада.

    `status` — результат проверки инварианта Area (`evaluate_area`), вычисляется
    адаптером при сборке снимка. `light_entity_id` — помеченный `ba_area_light`
    групповой свет помещения (этап 12): при `status == OK` задан, иначе `None`.
    """

    area_id: AreaId
    floor_id: FloorId
    room_type: RoomType | None = None
    opt_out: bool = False
    status: AreaStatus = AreaStatus.OK
    light_entity_id: str | None = None


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


# Управление автояркостью датчиков соседней интеграции (этап 11). Такие действия
# адресуют датчики освещённости помещения, а не групповой свет — у них нет
# агрегатной цели этажа, поэтому каскад их не схлопывает (см. is_room_pinned).
AUTOBRIGHTNESS_DOMAIN: Final = "arvid_dali_center"
AUTOBRIGHTNESS_SERVICE: Final = "set_autobrightness"


def is_room_pinned(action: Action) -> bool:
    """Действие приколочено к Area помещения (адресует датчики, не свет).

    Групповой свет схлопывается в агрегатную Area этажа; автояркость живёт на
    датчиках помещений, агрегатной цели у неё нет — такое действие всегда
    исполняется по Area помещения (этап 11).
    """
    return (
        action.domain == AUTOBRIGHTNESS_DOMAIN
        and action.service == AUTOBRIGHTNESS_SERVICE
    )


@dataclass(frozen=True)
class ModeSettings:
    """Настройки режима с областью действия «здание» (SPEC §5.1 ТЗ)."""

    delay_seconds: int
    sensors_allowed: bool
    sensors_allowed_by_floor: Mapping[FloorId, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class Config:
    """Конфигурация Оркестратора: профили и настройки режимов (SPEC §3.1).

    `opted_out_areas` — помещения, исключённые из управления по расписанию. Это
    **операционная политика** Оркестратора: хранится в его `.storage`, а не
    меткой в реестре HA (решение Q3=C). Каскад пропускает такие помещения с
    причиной OPT_OUT; оболочка накладывает это множество на снимок топологии.
    """

    modes: Mapping[ScheduleMode, ModeSettings]
    actions_object: Mapping[ScheduleMode, ActionSet]
    actions_by_floor: Mapping[tuple[FloorId, ScheduleMode], ActionSet]
    actions_by_room_type: Mapping[tuple[RoomType, ScheduleMode], ActionSet]
    actions_by_area: Mapping[tuple[AreaId, ScheduleMode], ActionSet]
    fallback_mode: ScheduleMode
    opted_out_areas: frozenset[AreaId] = frozenset()


@dataclass(frozen=True)
class ControlState:
    """Снимок режима управления — вход планировщика каскада (SPEC §2.2.4)."""

    building: ControlMode
    floors: Mapping[FloorId, FloorControl] = field(default_factory=dict)


class TargetKind(StrEnum):
    """Вид цели команды каскада (этап 12).

    Свет целится по конкретной световой сущности; автояркость (room-pinned) — по
    Area помещения, т.к. сервис `set_autobrightness` сам отбирает датчики Area.
    """

    ENTITY = "entity"
    AREA = "area"


@dataclass(frozen=True)
class Command:
    """Одна команда каскада: применить действие к цели.

    `target` — `entity_id` световой сущности (`ENTITY`) либо `area_id`
    помещения (`AREA`); вид указывает `target_kind`.
    """

    target: str
    target_kind: TargetKind
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


# --- Машина состояний (SPEC §2.2.5) ---

type Instant = float  # монотонное время в секундах; приходит параметром now


class EventSource(StrEnum):
    """Источник смены режима в доменном событии."""

    SCHEDULE = "schedule"
    MANUAL = "manual"


@dataclass(frozen=True)
class PendingTransition:
    """Отложенный переход: целевой режим и момент применения."""

    target_mode: ScheduleMode
    apply_at: Instant


@dataclass(frozen=True)
class OrchestratorState:
    """Полное состояние Оркестратора — вход и выход `decide`.

    Несёт снимки `config` и `topology`, чтобы `decide` был самодостаточным.
    `applied_mode` = None означает «ничего ещё не применено» (до первого старта).
    """

    config: Config
    topology: TopologySnapshot
    control: ControlState
    schedule_mode: ScheduleMode
    source_available: bool
    applied_mode: ScheduleMode | None
    pending: PendingTransition | None


# Входы decide (дискриминируемый union).
@dataclass(frozen=True)
class ScheduleChanged:
    """Источник расписания пересчитан."""

    resolution: ScheduleResolution


@dataclass(frozen=True)
class TimerFired:
    """Сработал таймер отложенного перехода."""


@dataclass(frozen=True)
class Started:
    """Старт Home Assistant: сверка сохранённого режима с вычисленным."""

    resolution: ScheduleResolution


@dataclass(frozen=True)
class ControlModeChanged:
    """Переключение режима управления зданием или этажом."""

    building: ControlMode | None = None
    floor_id: FloorId | None = None
    floor_control: FloorControl | None = None


type Input = ScheduleChanged | TimerFired | Started | ControlModeChanged


# Операции с таймером отложенного перехода.
@dataclass(frozen=True)
class NoTimerOp:
    """Таймер не трогать."""


@dataclass(frozen=True)
class SetTimer:
    """Завести таймер отложенного перехода."""

    apply_at: Instant
    target_mode: ScheduleMode


@dataclass(frozen=True)
class CancelTimer:
    """Снять отложенный переход."""


type TimerOp = NoTimerOp | SetTimer | CancelTimer


# Доменные события.
@dataclass(frozen=True)
class ModeChanged:
    """Режим фактически сменён."""

    new_mode: ScheduleMode
    previous_mode: ScheduleMode | None
    source: EventSource


@dataclass(frozen=True)
class ModeWarning:
    """Предупреждение о предстоящей смене режима."""

    target_mode: ScheduleMode
    apply_at: Instant


@dataclass(frozen=True)
class TransitionCancelled:
    """Отложенный переход отменён."""

    cancelled_mode: ScheduleMode


type DomainEvent = ModeChanged | ModeWarning | TransitionCancelled


@dataclass(frozen=True)
class Decision:
    """Решение машины: новое состояние и что исполнить (SPEC §2.2.5)."""

    state: OrchestratorState
    plan: CascadePlan | None
    timer_op: TimerOp
    events: tuple[DomainEvent, ...]
    gates: Mapping[FloorId, bool]
