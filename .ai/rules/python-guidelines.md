# Python Guidelines — Home Assistant custom integration

Язык-специфичные правила для ядра интеграции «Building Automation». Дополняет
ядро [`styleguide.md`](styleguide.md).

Интеграция — **custom component для Home Assistant OS**. Это накладывает жёсткие
рамки: код живёт внутри чужого асинхронного рантайма, который мы не контролируем
и не можем перезапустить. Большая часть правил ниже — про то, как не сломать этот
рантайм.

Версии Python, HA и пины зависимостей — в [`tooling.md`](tooling.md).

---

## 1. Асинхронность — критические правила

Home Assistant — однопоточный `asyncio`-цикл. Блокировка цикла подвешивает **весь
дом**: перестают ходить события, отваливаются интеграции, UI замирает. Это самая
дорогая категория ошибок в проекте.

### Никакого блокирующего I/O в корутинах

**Всегда флагать** в `async def` любой синхронный вызов, который идёт в файловую
систему, сеть или спит: `open()`, `requests.*`, `time.sleep()`, `subprocess.*`,
`socket.*`, `json.load(open(...))`, любые SDK без `async`.

```python
# ПЛОХО — блокирует цикл всего Home Assistant
async def async_load_config(self) -> dict:
    with open(self._path) as f:      # синхронный файловый I/O
        return json.load(f)

# ПЛОХО — вешает цикл на 5 минут
async def async_apply(self) -> None:
    time.sleep(300)

# ХОРОШО — конфиг только через Store (см. §3)
async def async_load_config(self) -> dict:
    return await self._store.async_load() or {}

# ХОРОШО — если синхронный вызов неизбежен, уводим его в executor
async def async_read_legacy(self) -> str:
    return await self.hass.async_add_executor_job(self._read_blocking)
```

HA сам детектит часть таких вызовов и пишет в лог `Detected blocking call inside
the event loop`. Такое предупреждение в логах — **баг, а не шум**; задача не
считается готовой, пока оно есть.

### Задержки режимов — таймерами HA, а не `asyncio.sleep`

Системная задержка (в ТЗ — до нескольких минут перед сменой режима) **не должна**
быть `await asyncio.sleep(...)` внутри обработчика события. Такой сон нельзя
отменить при повторной смене режима, он переживает выгрузку config entry и
оставляет висящую корутину.

```python
# ПЛОХО — неотменяемо, переживает unload, ломается при повторной смене режима
async def _handle_schedule_change(self, new_mode: str) -> None:
    await asyncio.sleep(self._delay)
    await self._apply(new_mode)

# ХОРОШО — отменяемый таймер, снимается при новой смене режима и при unload
def _schedule_transition(self, new_mode: str) -> None:
    self._cancel_pending()
    self._unsub_timer = async_call_later(
        self.hass, self._delay, partial(self._apply_transition, new_mode)
    )
```

Правило: **у каждой отложенной операции есть владелец, который умеет её
отменить.** Если отменить нельзя — это утечка.

### Каждая подписка снимается при выгрузке

**Всегда флагать** `async_track_state_change_event`, `hass.bus.async_listen`,
`async_call_later`, `async_track_time_interval` и подобные, если возвращённый
`unsub`-колбэк не сохранён и не вызывается при выгрузке entry.

```python
# ПЛОХО — подписка переживает reload; после трёх reload'ов режим применяется трижды
hass.bus.async_listen(EVENT_SCHEDULE, self._handle)

# ХОРОШО — привязка к жизненному циклу entry
entry.async_on_unload(
    hass.bus.async_listen(EVENT_SCHEDULE, self._handle)
)
```

`entry.async_on_unload(...)` — предпочтительный способ: HA сам всё снимет.
Ручное хранение `unsub` допустимо только там, где подписка живёт короче entry.

### `@callback` против корутины

Функция, помеченная `@callback`, выполняется **синхронно внутри цикла** — в ней
нельзя ни `await`, ни делать что-либо долгое. Если обработчику нужен `await` —
это обычная `async def` без декоратора.

---

## 2. Границы интеграции (Оркестратор)

Эти правила — прямое следствие зоны ответственности из
[`docs/TZ.md`](../../docs/TZ.md) §2. Нарушение означает, что интеграция полезла в
чужую епархию.

### Наружу — состояние и события, никаких прямых вызовов исполнителей

Источник истины для нижестоящих — **сущность** Оркестратора; событие лишь
уведомляет о моменте смены. Событие без состояния теряется при старте HA и при
перезагрузке подписчика (см. `docs/TZ.md` §5.1).

**Всегда флагать** любой импорт или вызов другой кастомной интеграции
(`zone_manager` и т. п.), обращение к её данным через `hass.data[...]`, попытку
дёрнуть её сущности напрямую.

```python
# ПЛОХО — жёсткая связность с исполнителем; Оркестратор о нём знать не должен
from custom_components.zone_manager import ZoneManager
hass.data["zone_manager"].disable_sensors(floor_id)

# ХОРОШО — публикуем факт, подписчики разбираются сами
hass.bus.async_fire(
    EVENT_BUILDING_MODE_CHANGED,
    {
        "area_id": area_id,
        "floor_id": floor_id,
        "new_mode": new_mode,
        "previous_mode": previous_mode,
        "source": source,
    },
)
```

Payload события — контракт. Его состав зафиксирован в
[`docs/TZ.md`](../../docs/TZ.md) §7.5; менять состав или имена ключей можно
только через правку SPEC. Гранулярность — **помещение** (Area): профили
наследуются до помещения и у помещения есть собственный opt-out, поэтому одного
`floor_id` недостаточно.

Отдельно флагать обращения к уровням **ниже помещения** — зонам
(`light.<room>_<n>`) и отдельным светильникам (`light.l_*`). Это периметр
`zone_manager`, Оркестратор туда не лезет.

### Никаких динамических `script.*` / `automation.*` и генерации YAML

**Всегда флагать** попытку создать сущность в домене `script` или `automation`,
записать YAML-файл в конфиг пользователя, дёрнуть `automation.reload` /
`script.reload`. Это измеримый критерий приёмки из
[`docs/task.md`](../../docs/task.md) — вся логика живёт в Python, состояние в
`.storage`.

### Низкоуровневая логика — вне периметра

**Всегда флагать** появление в коде: таймаутов датчиков движения, диммирования по
присутствию, расчёта уровней для соседних зон, работы с DALI/MQTT-протоколами.
Оркестратор только разрешает и запрещает нижестоящим работать — через события.

---

## 3. Хранение конфигурации

Единственный способ персистентности — `homeassistant.helpers.storage.Store`
(файл JSON в `.storage`). Прямая работа с путями и `open()` запрещена.

- У `Store` **обязательно** задаётся `version` и миграция. Схема будет меняться —
  панель пусконаладчика редактирует топологию здания.
- Миграция делается **наследованием и переопределением `_async_migrate_func`**.
  Параметра `async_migrate_func` в конструкторе `Store` не существует — это
  типовая ошибка, которую LLM уверенно генерирует. Сигнатура метода — три
  аргумента (`old_major_version`, `old_minor_version`, `old_data`); легаси-форма
  на два аргумента в новом коде запрещена.
- Частые записи из UI — через `async_delay_save`, а не `async_save` на каждый
  чих: иначе панель засыпает диск записями.
- Данные, прочитанные из `Store`, — **недоверенный вход**. Их пишет UI и правит
  рука. Валидируйте при загрузке (`voluptuous`/дата-классы), не считайте, что
  структура та же, что при записи.

```python
# ПЛОХО — свой путь, свой формат, синхронный I/O, нулевая миграция
with open(hass.config.path(".storage/building_automation"), "w") as f:
    json.dump(self._config, f)

# ХОРОШО
class BuildingStore(Store[dict[str, Any]]):
    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        ...

self._store = BuildingStore(
    hass, STORAGE_VERSION, STORAGE_KEY, minor_version=STORAGE_MINOR_VERSION
)
# async_delay_save принимает ФУНКЦИЮ, а не данные: правки до сброса на диск
# попадут в файл, потому что функция вызывается в момент записи.
self._store.async_delay_save(self._data_to_save, SAVE_DELAY)
```

Состояние интеграции в рантайме хранится в `entry.runtime_data`, а **не** в
`hass.data[DOMAIN]`. Флагать `hass.data[DOMAIN][entry.entry_id] = ...` в новом
коде: это легаси-форма, у неё есть валидатор в hassfest.

---

## 4. Типизация

`mypy --strict`, 0 ошибок. Отдельно:

- Аннотируйте **всё**, включая `-> None` у корутин без возврата.
- Режимы, источники смены режима, ключи payload — не «голые» строки, а `StrEnum`
  / `Final`-константы в `const.py`. Опечатка в строке режима иначе всплывёт
  только на объекте.
- Структуры конфигурации (профиль режима, узел топологии) — `dataclass`, не
  `dict[str, Any]`, протащенный через пять слоёв.
- `# type: ignore` — только с кодом ошибки и комментарием почему
  (`# type: ignore[arg-type]  # HA не типизирует ...`).

---

## 5. Общие правила Python

Действуют независимо от Home Assistant.

### Fail fast — не прячьте ошибки

```python
# ПЛОХО — все три варианта скрывают проблему
except Exception:
    pass

except Exception as e:
    _LOGGER.error(e)     # залогировал и поехал дальше со сломанным состоянием
    return {}

try:
    do_work()
except:                   # голый except ловит и KeyboardInterrupt, и SystemExit
    log_error()

# ХОРОШО — конкретное исключение, которое действительно умеем обработать
try:
    data = json.loads(text)
except json.JSONDecodeError:
    data = {}

# ХОРОШО — ловим широко только чтобы залогировать, и обязательно пробрасываем
try:
    result = something()
except Exception:
    _LOGGER.exception("Не удалось применить профиль режима")
    raise
```

Три правила: 1) по возможности убрать `try/except` вообще; 2) ловить **конкретные**
исключения; 3) поймал `Exception` — перевыброси после логирования.

Исключение из правила — там, где HA требует иного: в `async_setup_entry` при
недоступности внешнего сенсора корректно бросить `ConfigEntryNotReady` (HA сам
повторит), а не глотать ошибку.

### Импорты — только на верхнем уровне модуля

**Всегда флагать** `import` внутри функции или метода и `try/except ImportError`
вокруг импорта. Зависимости интеграции объявлены в `manifest.json` и
устанавливаются заранее — «опциональных бэкендов» в этом проекте нет.

Единственное исключение — `if TYPE_CHECKING:` для разрыва циклических импортов
при аннотациях.

### Никакого защитного `getattr()` по известным типам

```python
# ПЛОХО — ModeProfile имеет поле delay; getattr прячет AttributeError
delay = getattr(profile, "delay", 0)

# ХОРОШО — падает громко, если контракт типа изменился
delay = profile.delay
```

### Изменяемые значения по умолчанию

```python
# ПЛОХО — список общий для всех вызовов, мутации копятся между вызовами
def add_action(action, actions=[]):
    actions.append(action)
    return actions

# ХОРОШО
def add_action(action, actions=None):
    if actions is None:
        actions = []
    actions.append(action)
    return actions
```

### `assert` — не для валидации

Ассерты вырезаются под `python -O`. Для проверки данных из UI, `Store` или
сервисных вызовов — только явный `if/raise`.

```python
# ПЛОХО
assert floor_id is not None, "floor_id required"

# ХОРОШО
if floor_id is None:
    raise ValueError("floor_id required")
```

### Прочее, что флагается в ревью

- Затенение встроенных имён (`list`, `dict`, `id`, `type`, `input`, `format`, …).
- `== None` / `== True` / `== False` вместо `is` / `is not`.
- Изменение коллекции во время итерации по ней.
- `+=` на строке в цикле (O(n²)) — вместо этого `"".join(...)`.
- Позднее связывание в замыканиях внутри цикла (`lambda: i` вместо `lambda i=i: i`).
- `open()` без `with`.

---

## 6. Стиль и структура

- PEP 8, `snake_case` для функций и переменных, `PascalCase` для классов.
- Модуль логгера — `_LOGGER = logging.getLogger(__name__)`, всегда на уровне модуля.
- Все константы, домен, имена событий и ключи payload — в `const.py`, ничего
  «в строках по месту».
- Докстринги — у публичных классов и функций. HA-стиль: одна строка в
  повелительном наклонении.
- `dataclass` вместо словаря, когда у структуры больше 3–4 полей.

Раскладка файлов интеграции (детали — в SPEC, здесь только принцип):

```
custom_components/building_automation/
├── __init__.py          # setup/unload entry — тонкий, без логики
├── const.py             # домен, режимы, имена событий, ключи storage
├── coordinator.py       # Машина состояний — ядро, сюда основное покрытие
├── config_flow.py       # базовая настройка (ТЗ §5.1)
├── storage.py           # обёртка над Store + миграции
├── websocket_api.py     # команды для Custom Panel (ТЗ §5.2)
├── manifest.json
└── www/                 # статика панели (см. javascript-guidelines.md)
```

Правило глубины модулей из ядра styleguide здесь означает: `__init__.py` и
`config_flow.py` — тонкие обвязки HA, вся логика режимов и задержек — в
`coordinator.py` и рядом, и она **тестируется без поднятия HA**.

---

## 7. Тестирование

Стек и пины — в [`tooling.md`](tooling.md). Правила:

- Бизнес-логика Машины состояний должна тестироваться **без** `hass`: чистые
  функции «текущее состояние + событие → решение». HA-обвязка тестируется
  отдельно и тонко. Если для проверки перехода режима нужно поднимать весь HA —
  логика прибита к фреймворку, это дефект архитектуры.

  В этом проекте требование жёстче обычного: пакет `homeassistant` **не
  устанавливается вообще**, тесты с ним не гоняются. Значит логика, не
  отделённая от обвязки, не будет покрыта никогда. Всё, что можно посчитать
  чистой функцией, — считается чистой функцией, включая сериализацию и миграцию
  схемы хранилища. Перечень непокрываемого и ручной чек-лист — в
  [`tooling.md`](tooling.md) §5.
- Время в тестах — только через `freezegun` / `async_fire_time_changed`. Реальные
  ожидания (`asyncio.sleep` в тесте) запрещены: задержки в ТЗ измеряются
  минутами, тест столько идти не может.
- Покрытие `coordinator.py` — > 90 % (критерий из `docs/task.md`), считается по
  веткам.
- Каждый BDD-сценарий из SPEC → минимум один тест с говорящим именем.
