# Tooling — версии, пины, команды

Всё, что имеет версию, живёт здесь. Гайды
([`python-guidelines.md`](python-guidelines.md),
[`javascript-guidelines.md`](javascript-guidelines.md)) описывают правила и на
цифры не завязаны — при обновлении HA правится только этот файл.

Проверено 2026-07-22 по PyPI и `home-assistant/core`.

---

## 1. Целевой рантайм

Версии с боевого объекта:

| Компонент | Версия |
|---|---|
| Home Assistant Core | **2026.5.4** |
| Supervisor | 2026.07.3 |
| Home Assistant OS | 17.2 |
| Frontend | 20260429.4 |

Разрабатываем **строго под Core 2026.5.4**. Последний релиз на момент проверки —
2026.7.3; расхождение учитываем в §5.

---

## 2. Python

**HA Core 2026.5.4 требует Python `>=3.14.2`** (`requires_python` в метаданных
PyPI; в `homeassistant/const.py` — `REQUIRED_PYTHON_VER = (3, 14, 2)`). Core
собирается и тестируется на 3.14.5 (`.python-version`).

**На машине разработки — `/usr/bin/python3.14` версии 3.14.4** (проверено
2026-07-22). Требование выполнено.

⚠ `python` и `python3` в PATH могут указывать на venv соседнего проекта
(`ha-lighting-compilers/.venv`). Базовый интерпретатор вызывайте **явно**:
`/usr/bin/python3.14`.

### Ограничение: Home Assistant не устанавливается

Решение по проекту: **пакет `homeassistant` в окружение не ставится, тесты с
ним не гоняются.** Это упрощает стек, но переносит часть проверок из
автоматических в ручные — см. §5.

Прямое архитектурное следствие: **вся логика пишется чистыми функциями без
`hass`**. Это уже не пожелание к стилю, а единственный способ вообще что-либо
покрыть тестами. Чем тоньше HA-обвязка, тем меньше непроверяемая часть.

### venv на этой машине

`ensurepip` сломан, `sudo` недоступен — обычный `python -m venv` не отработает.
Рабочий рецепт:

```bash
/usr/bin/python3.14 -m venv --without-pip .venv
pip3 --python .venv/bin/python install -r requirements-dev.txt
```

---

## 3. Python-стек

```
# requirements-dev.txt
pytest
pytest-asyncio
pytest-cov
mypy
ruff
mutmut
```

Всё. `pytest-homeassistant-custom-component` и пакет `homeassistant` **не
используются**.

`asyncio_mode = "auto"` в `pyproject.toml` оставлен: часть логики (расчёт
переходов, отмена отложенных операций) естественно пишется корутинами, и режим
избавляет от декоратора на каждом асинхронном тесте.

## 4. Команды качества

```bash
# Python
ruff format custom_components tests
ruff check --fix custom_components tests
mypy custom_components
pytest --cov=custom_components/building_automation --cov-branch
mutmut run                     # только модули логики, см. styleguide §1.6

# Фронт (dev-инструменты, в рантайм не попадают)
npx tsc -p jsconfig.json       # проверка типов по JSDoc, без генерации
npx eslint .
npx prettier --check .
```

`hassfest` (валидация `manifest.json`, сортировки ключей, `integration_type`)
локально для кастомной интеграции не запускается — он рассчитан на дерево core.
Официальный способ — GitHub Action:

```yaml
- uses: home-assistant/actions/hassfest@master
- uses: hacs/action@main
  with:
    category: integration
```

Известное ограничение: hassfest отвергает VCS/GitHub-ссылки в `requirements`.

---

## 5. Что не покрывается тестами

Отказ от пакета `homeassistant` (§2) означает, что часть кода не проверяется
автоматически **никогда**. Список ведётся здесь явно, чтобы это не выглядело
как «покрыли всё».

**Не покрывается юнит-тестами:**

- регистрация сущностей, устройства, платформ;
- `config_flow` — диалоги установки и валидация ввода;
- регистрация и авторизация WebSocket-команд;
- жизненный цикл config entry: setup, unload, reload, снятие подписок;
- фактическая запись и чтение `Store` (файловый слой);
- обнаружение блокирующих вызовов в событийном цикле;
- реальная отправка сервисных вызовов и публикация событий на шину.

**Как это компенсируется:**

1. **Логика выносится из обвязки до предела.** Всё, что можно посчитать чистой
   функцией, считается чистой функцией: приоритет расписания, fallback,
   наследование профилей, правило схлопывания, проверка инварианта Area,
   решение об отмене отложенного перехода, **сериализация и миграция схемы
   хранилища**. Тонкая обвязка вокруг них — несколько строк, которые видно
   глазами.
2. **Ручной чек-лист на полевом тесте.** Проверяется на объекте, результат
   фиксируется в протоколе:

   - [ ] Интеграция ставится и настраивается через UI, сущности появляются.
   - [ ] Перезагрузка config entry не плодит дубли обработчиков (смена режима
         после трёх перезагрузок применяется один раз).
   - [ ] Конфигурация переживает перезапуск Home Assistant без потерь.
   - [ ] Миграция схемы отрабатывает на реальном файле старой версии.
   - [ ] В логе нет `Detected blocking call inside the event loop`.
   - [ ] В логе нет предупреждений о deprecated-вызовах HA.
   - [ ] Панель открывается, WS-команды проходят, неадмин получает отказ.

⚠ **Типы тоже не помогают.** Без установленного пакета `homeassistant` у mypy
нет его стабов: `import-not-found` подавлен, весь HA-API виден как `Any`.
То есть неверное использование HA-API не ловится **ни тестами, ни типами** —
только ревью и полевым тестом. Это самая большая брешь проекта, и её стоит
осознавать при оценке рисков.

Если решение изменится, минимальный шаг — поставить `homeassistant` как
зависимость **только для проверки типов** (без запуска тестов с ним): это
вернёт mypy зрение по обвязке, не меняя тестовый стек.

**Как это настроено в `pyproject.toml`.** Ядро `domain/` — полный `mypy --strict`.
Обвязочные модули наследуют классы HA, которые без пакета видны как `Any`, из-за
чего strict-проверки (`misc`, `no-any-return`, `untyped-decorator`, `call-arg`)
шумят на пустом месте. Для них — отдельный `[[tool.mypy.overrides]]`,
отключающий именно эти коды; список модулей пополняется при добавлении новой
обвязки. Плюс `mypy_path="."` + `namespace_packages` + `explicit_package_bases` —
без них mypy именует модули `building_automation.*` и overrides не матчатся
(пакет `custom_components` — namespace, без `__init__`).

---

## 6. API-контракт HA: что использовать и чего избегать

Эти пункты — не стиль, а совместимость с 2026.5.4. Ошибка здесь = интеграция не
загрузится или отвалится на ближайшем обновлении.

### Обязательные современные формы

| Надо | Не надо | Почему |
|---|---|---|
| `entry.runtime_data` | `hass.data[DOMAIN][entry.entry_id]` | Правило Bronze `runtime-data`, есть валидатор hassfest |
| `async_forward_entry_setups` (мн. ч.) | `async_forward_entry_setup`, `async_setup_platforms` | Единственная документированная форма |
| `hass.http.async_register_static_paths([StaticPathConfig(...)])` | `register_static_path` | Удалён из core, в текущем дереве отсутствует |
| `_attr_has_entity_name = True` | ручные префиксы в именах | Правило Bronze `has-entity-name` |
| `hass.config_entries.async_update_entry(...)` | прямая мутация entry | Мутация не сохраняется и не рассылает обновления |

Типизированный entry (нужен и для `strict-typing`, и просто по-человечески):

```python
type BuildingAutomationConfigEntry = ConfigEntry[BuildingCoordinator]

async def async_setup_entry(
    hass: HomeAssistant, entry: BuildingAutomationConfigEntry
) -> bool:
    coordinator = BuildingCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True
```

Python 3.14 — можно и нужно использовать PEP 695 (`type X = ...`,
`class Store[_T]`), core пишет именно так.

### Store: миграция — переопределением метода

Частая ошибка: параметра `async_migrate_func` в конструкторе **нет**. Миграция
делается наследованием:

```python
class BuildingStore(Store[dict[str, Any]]):
    async def _async_migrate_func(
        self, old_major_version: int, old_minor_version: int, old_data: dict[str, Any]
    ) -> dict[str, Any]:
        ...
```

Сигнатура — **3 аргумента**. Легаси-форма на 2 аргумента ещё поддерживается через
интроспекцию, но в новом коде запрещена.

Полезное в текущем API: `minor_version`, `max_readable_version` (чтение данных,
записанных более новой версией — переживает откат HA), `async_delay_save(fn)`
принимает **функцию**, а не данные.

### manifest.json кастомной интеграции

Обязательны: `domain`, `name`, `codeowners`, `documentation`, `dependencies`,
`requirements`, `integration_type`, `iot_class`, **`version`** (только для
кастомных, формат AwesomeVersion — CalVer/SemVer), **`issue_tracker`** (требует
HACS). Опционально: `config_flow`, `after_dependencies`, `loggers`,
`single_config_entry`.

Для нашего случая: **`integration_type: "hub"`** (не `"system"` — системные
интеграции намеренно скрыты из UI-списка «Добавить интеграцию», проверено на
объекте 2026-07-23), `iot_class: "calculated"` — интеграция ничего не опрашивает,
а вычисляет режим из
чужих сущностей.

### Шкала качества

Градуированная шкала (Bronze…Platinum) на кастомные интеграции **не
распространяется** — они всегда в спецтире 📦 Custom. Но кодовые правила Bronze
применимы и полезны: `runtime-data`, `has-entity-name`, `entity-unique-id`,
`config-entry-unloading`, `entity-event-setup`, `common-modules`. Правила `docs-*`
и `brands` нацелены на репозиторий core — нас не касаются.

### Грядущее ломающее (готовиться сейчас)

**Реестр устройств: одно устройство — одна config entry** — приезжает в Core
**2026.8** (мы на 2026.5.4, то есть это следующее крупное обновление объекта).
Окно совместимости до 2027.8, есть временный shim, но **новый код нужно писать
сразу под новый API**:

- `DeviceEntry.config_entries` / `primary_config_entry` → `DeviceEntry.config_entry_id`
- `DeviceInfo["via_device"]` → `via_device_id`
- `DeviceRegistry.async_get_device()` → `async_get_device_by_identifier()` / `async_get_device_by_connection()`
- `async_update_device(add_config_entry_id=…)` → `new_config_entry_id=`

Прочее актуальное: флаг `home_assistant_start` в `async_initialize_triggers`
объявлен устаревшим (удаление 2027.8); константы `CONCENTRATION_*` заменены на
`UnitOfDensity` / `UnitOfRatio` (с 2026.7).

> HA сообщает об устаревших вызовах через `frame.report_usage`. Для **кастомных**
> интеграций поведение по умолчанию — `LOG`, тогда как для core — `ERROR`. То
> есть мы получаем предупреждение в логе там, где core падает. Эти строки в логе
> — ранние сигналы удалений 2027.x, их нельзя игнорировать.

---

## 7. Фронтенд

Frontend объекта — 20260429.4. Внутри него собран **Lit 3.3.3**.

⚠️ **Но импортировать его из панели нельзя.** В шаблоне страницы HA нет import
map, поэтому bare-спецификатор `import { LitElement } from "lit"` в стороннем
модуле не разрешится. Официальная документация по кастомным панелям устарела —
она показывает `lit-element@2.4.0` с unpkg, это на два мажора старше собранного
в HA. Официальной поддерживаемой схемы «взять Lit у HA» **не существует**.

**Решение: Lit вендорится в репозиторий.**

| | Версия | Где |
|---|---|---|
| Lit (вендоренный) | **3.3.3** | `custom_components/building_automation/www/vendor/lit-3.3.3.js` |

Версия выбрана совпадающей с собранной во фронтенде HA — не потому, что мы её
оттуда берём (это невозможно), а чтобы панель вела себя так же, как штатные
компоненты HA, и чтобы при отладке не расходилось поведение.

Обоснование и запрещённые альтернативы (CDN, `Object.getPrototypeOf` по
внутренностям фронтенда) — в
[`javascript-guidelines.md`](javascript-guidelines.md) §2.

Статика отдаётся из интеграции через `hass.http.async_register_static_paths(...)`,
панель регистрируется через `panel_custom.async_register_panel(..., module_url=…)`.
