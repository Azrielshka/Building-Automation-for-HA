"""Архитектурный сторож: ядро `domain/` не зависит от Home Assistant.

Закрывает SPEC §5.7 и §2.4. Сторож разбирает AST каждого модуля `domain/` и
падает на запрещённом импорте. Критерий неподделываемый: обойти можно только
сломав сам тест, что видно в диффе.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.import_guard import forbidden_imports

DOMAIN_DIR = (
    Path(__file__).parent.parent
    / "custom_components"
    / "building_automation"
    / "domain"
)


def test_domain_has_no_forbidden_imports() -> None:
    """Ни один модуль domain/ не импортирует HA, adapters или оболочку."""
    violations: dict[str, list[str]] = {}
    for py_file in sorted(DOMAIN_DIR.glob("*.py")):
        bad = forbidden_imports(py_file)
        if bad:
            violations[py_file.name] = bad
    assert not violations, f"запрещённые импорты в ядре: {violations}"


# --- сила сторожа: он обязан ловить нарушения, а не молча пропускать ---

_CAUGHT = [
    "import homeassistant",
    "import homeassistant.core",
    "from homeassistant.core import HomeAssistant",
    "from custom_components.building_automation.adapters import store",
    "from ..adapters import store",  # relative выход выше domain/
    "from .. import coordinator",
]

_ALLOWED = [
    "from __future__ import annotations",
    "import ast",
    "from dataclasses import dataclass",
    "from .types import ScheduleMode",  # свой модуль ядра — relative level 1
    "from . import schedule",
    "from custom_components.building_automation.const import DOMAIN",
]


@pytest.mark.parametrize("source", _CAUGHT)
def test_guard_catches(tmp_path: Path, source: str) -> None:
    """Сторож ловит запрещённый импорт."""
    module = tmp_path / "m.py"
    module.write_text(source, encoding="utf-8")
    assert forbidden_imports(module), f"пропустил: {source!r}"


@pytest.mark.parametrize("source", _ALLOWED)
def test_guard_allows(tmp_path: Path, source: str) -> None:
    """Сторож не срабатывает ложно на разрешённых импортах."""
    module = tmp_path / "m.py"
    module.write_text(source, encoding="utf-8")
    assert not forbidden_imports(module), f"ложно поймал: {source!r}"
