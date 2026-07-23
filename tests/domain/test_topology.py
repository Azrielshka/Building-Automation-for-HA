"""Тесты снимка топологии и инварианта Area (SPEC §5.2, domain/topology.py)."""

from __future__ import annotations

from custom_components.building_automation.domain.topology import (
    TopologySnapshot,
    evaluate_area,
)
from custom_components.building_automation.domain.types import (
    AreaStatus,
    Floor,
    Room,
)


def test_single_light_is_ok() -> None:
    """Ровно одна световая сущность в Area — инвариант соблюдён."""
    assert evaluate_area(["light.room_obshchii"]) is AreaStatus.OK


def test_two_lights_is_multiple() -> None:
    """Две световые сущности — нарушение инварианта."""
    result = evaluate_area(["light.room_obshchii", "light.l_1_1_1"])
    assert result is AreaStatus.MULTIPLE_LIGHTS


def test_no_lights_is_no_light() -> None:
    """Нет световых сущностей — нарушение (например, забыли назначить группу)."""
    assert evaluate_area([]) is AreaStatus.NO_LIGHT


def _snapshot() -> TopologySnapshot:
    """Этаж f1 с агрегатной Area и двумя помещениями."""
    return TopologySnapshot(
        floors={"f1": Floor(floor_id="f1", aggregate_area_id="area_floor1")},
        rooms={
            "area_101": Room(area_id="area_101", floor_id="f1"),
            "area_102": Room(area_id="area_102", floor_id="f1"),
        },
    )


def test_rooms_of_returns_floor_rooms_without_aggregate() -> None:
    """rooms_of возвращает помещения этажа; агрегатная Area в список не входит."""
    rooms = _snapshot().rooms_of("f1")
    area_ids = {r.area_id for r in rooms}
    assert area_ids == {"area_101", "area_102"}
    assert "area_floor1" not in area_ids


def test_aggregate_area_of_returns_floor_aggregate() -> None:
    """aggregate_area_of возвращает агрегатную Area этажа."""
    assert _snapshot().aggregate_area_of("f1") == "area_floor1"
