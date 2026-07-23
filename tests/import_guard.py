"""AST-сканер запрещённых импортов для архитектурного сторожа (SPEC §2.4, §5.7).

Ядро `domain/` не смеет знать о фреймворке. Запрещены:

- любой импорт `homeassistant` (и `homeassistant.*`);
- абсолютный импорт оболочки того же пакета
  (`custom_components.building_automation.{adapters,entities,coordinator,
  config_flow,websocket_api}`);
- относительный импорт, выходящий выше `domain/` (`from .. import ...`) —
  он ведёт в пакет оболочки.

Относительные импорты внутри самого `domain/` (`from .types import ...`)
разрешены — это ядро, ссылающееся на себя.
"""

from __future__ import annotations

import ast
from pathlib import Path

_FORBIDDEN_ROOTS = ("homeassistant",)
_SHELL_MODULES = frozenset(
    {"adapters", "entities", "coordinator", "config_flow", "websocket_api"}
)
_OWN_PACKAGE = "custom_components.building_automation"


def _is_forbidden_absolute(module: str) -> bool:
    """True, если абсолютный модуль запрещён ядру."""
    root = module.split(".", 1)[0]
    if root in _FORBIDDEN_ROOTS:
        return True
    if module.startswith(f"{_OWN_PACKAGE}."):
        tail = module[len(_OWN_PACKAGE) + 1 :].split(".", 1)[0]
        return tail in _SHELL_MODULES
    return False


def forbidden_imports(py_file: Path) -> list[str]:
    """Вернуть список запрещённых импортов в модуле (пусто, если чисто)."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bad.extend(
                alias.name for alias in node.names if _is_forbidden_absolute(alias.name)
            )
        elif isinstance(node, ast.ImportFrom):
            # level >= 2 выходит выше domain/ — в пакет оболочки.
            if node.level >= 2:
                bad.append(f"{'.' * node.level}{node.module or ''}")
            elif (
                node.level == 0
                and node.module is not None
                and _is_forbidden_absolute(node.module)
            ):
                bad.append(node.module)
    return bad
