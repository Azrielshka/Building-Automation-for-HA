"""Константы интеграции «Building Automation» (Оркестратор здания)."""

from typing import Final

DOMAIN: Final = "building_automation"

# Версия схемы хранилища (.storage). Миграция — в domain/storage_schema.py.
STORAGE_VERSION: Final = 1
STORAGE_MINOR_VERSION: Final = 1
STORAGE_KEY: Final = DOMAIN
