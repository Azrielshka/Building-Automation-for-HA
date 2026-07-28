# Building Automation — Оркестратор здания

Кастомная интеграция **Home Assistant** (custom component): вычисляет режим
работы здания (Урок / Перемена / Не рабочее время / Окошко) из внешнего
расписания и каскадно применяет к помещениям профили режимов — сервисные вызовы
к свету и разрешение/запрет работы автоматизаций по датчикам движения. Заменяет
разрозненные YAML-автоматизации единым механизмом с настройкой через UI.

## Документы

| Документ | О чём |
|---|---|
| [`docs/task.md`](docs/task.md) | постановка задачи, BDD-сценарии |
| [`docs/TZ.md`](docs/TZ.md) | архитектурные требования, журнал решений |
| [`SPEC.md`](SPEC.md) | спецификация: модули, типы, алгоритмы, критерии, §2.6 внешние контракты |
| [`PLAN.md`](PLAN.md) | план по этапам + changelog выполненного |
| [`CONTEXT.md`](CONTEXT.md) | доменный словарь |
| [`docs/mode-matrix.md`](docs/mode-matrix.md) | как устроены профили и матрица режимов, сценарии настройки |
| [`docs/external-interface.md`](docs/external-interface.md) | что Оркестратор выставляет наружу (сущности, гейт, события, сервисы) |
| [`docs/acceptance-protocol.md`](docs/acceptance-protocol.md) | протокол приёмки (этап 10): метрики, чек-лист, что осталось на объекте |
| [`docs/contract-ha-lighting-compilers.md`](docs/contract-ha-lighting-compilers.md) | контракт со смежным проектом-генератором |

## Установка через HACS

Интеграция подключается как **custom repository** (в дефолтный каталог HACS не
публикуется — это приватная сборка под объект).

1. HACS → ⋮ (вверху справа) → **Custom repositories**.
2. Репозиторий: `https://github.com/Azrielshka/Building-Automation-for-HA`,
   категория — **Integration**. Добавить.
3. Найти «Building Automation — Оркестратор здания» в списке, установить,
   **перезапустить Home Assistant**.
4. Настройки → Устройства и службы → **Добавить интеграцию** → Building
   Automation.

> HACS видит только **публичные** репозитории и тянет **релизы** (не просто
> теги). Условия: репозиторий публичный, на нужный тег опубликован GitHub
> Release. Обновления интеграции = новые релизы.

Альтернатива без HACS — скопировать `custom_components/building_automation/` в
`config/custom_components/` вручную и перезапустить HA.

## Статус

**Этапы 0–10 закрыты (тег `0.5.0`).** Реализовано и проверено на песочнице
HA 2026.5.4; приёмка — [`docs/acceptance-protocol.md`](docs/acceptance-protocol.md).
Остаточный полевой пункт до `v1.0.0` — подтверждение видимого света на объекте с
живым DALI.

- **Ядро** (`domain/`) — вся политика в чистых функциях без `hass`: разрешение
  расписания, топология и инвариант Area, профили с наследованием, каскад со
  схлопыванием, машина состояний, схема хранилища. Покрытие ветвей 100 %,
  mutation ≥ 90 %.
- **Обвязка** — сущности (`select`/`switch`/`sensor`/`binary_sensor`), сервисы
  (`set_control_mode`, `reapply`), исполнение каскада, таймеры, события на шину.
- **WebSocket API** — точечные операции над профилями (атомарные, идемпотентные)
  и права (правка — только админ).
- **Панель пусконаладчика** — vanilla JS + Lit без сборки: мониторинг и матрица
  режимов, opt-out помещений, яркость для `light`, индикатор источника.
- **Приёмка** — `hassfest` (CI) зелёный, единый зелёный снимок, fail-open гейта,
  права (неадмин), Bronze-правила. Смежный генератор реализовал свою часть
  контракта.

Актуальный changelog — в [`PLAN.md`](PLAN.md).

## Структура репозитория

```
custom_components/building_automation/   интеграция
├── domain/          ЯДРО — чистые функции без hass, покрыто тестами
├── adapters/        швы к Home Assistant (реестры, сервисы, шина, Store, таймеры)
├── *.py             платформы сущностей, coordinator, config_flow, websocket_api
└── www/             панель (vanilla JS + Lit, без сборки)
tests/domain/        тесты ядра
docs/                требования, контракты, руководства
.ai/                 методология и правила (см. ниже)
```

## Методология

Проект ведётся по **Spec-Driven Development** (шаблон `sdd-kit`): задача → спека →
план → реализация по этапам под TDD → аудит. Источник истины методологии —
каталог [`.ai/`](.ai/) (`.claude/`, `.codex/`, `.agents/` — симлинки на него, так
что правила и скиллы одинаковы во всех инструментах):

- [`.ai/prompts/`](.ai/prompts/) — промпты воркфлоу (1-task … 6-audit);
- [`.ai/rules/styleguide.md`](.ai/rules/styleguide.md) — принципы качества и
  Definition of Done;
- [`.ai/rules/python-guidelines.md`](.ai/rules/python-guidelines.md),
  [`.ai/rules/javascript-guidelines.md`](.ai/rules/javascript-guidelines.md),
  [`.ai/rules/tooling.md`](.ai/rules/tooling.md) — правила под этот проект
  (Python custom component, панель vanilla JS + Lit, версии и команды).

Инструменты качества: `pyproject.toml` (ruff + mypy strict + pytest + mutmut),
`jsconfig.json` (`tsc --checkJs --strict` по JSDoc), `eslint.config.js`,
`.prettierrc`.
