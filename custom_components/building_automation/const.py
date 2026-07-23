"""Константы интеграции «Building Automation» (Оркестратор здания)."""

from typing import Final

DOMAIN: Final = "building_automation"

# Ключи конфигурации (entry.data), задаются в config_flow.
CONF_SCHEDULE_SOURCE: Final = "schedule_source"  # список entity_id источника
CONF_FALLBACK: Final = "fallback_mode"  # режим при недоступном расписании

# Метки (Labels) на Area. ba_floor_area и ba_type_* проставляет генератор
# ha-lighting-compilers; ba_optout — вручную (эксплуатационное решение, §3.4 ТЗ).
LABEL_FLOOR_AREA: Final = "ba_floor_area"  # агрегатная Area этажа
LABEL_TYPE_PREFIX: Final = "ba_type_"  # тип помещения: ba_type_<RoomType>
LABEL_OPT_OUT: Final = "ba_optout"  # исключение из управления расписанием

# Версия схемы хранилища (.storage). Миграция — в domain/storage_schema.py.
STORAGE_VERSION: Final = 1
STORAGE_MINOR_VERSION: Final = 1
STORAGE_KEY: Final = DOMAIN
