"""Константы интеграции «Building Automation» (Оркестратор здания)."""

from typing import Final

DOMAIN: Final = "building_automation"

# Ключи конфигурации (entry.data), задаются в config_flow.
CONF_SCHEDULE_SOURCE: Final = "schedule_source"  # список entity_id источника
CONF_FALLBACK: Final = "fallback_mode"  # режим при недоступном расписании

# Версия схемы хранилища (.storage). Миграция — в domain/storage_schema.py.
STORAGE_VERSION: Final = 1
STORAGE_MINOR_VERSION: Final = 1
STORAGE_KEY: Final = DOMAIN
