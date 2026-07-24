# Building Automation — Оркестратор здания

Кастомная интеграция **Home Assistant** (custom component): вычисляет режим
работы здания (Урок / Перемена / Не рабочее время / Окошко) из внешнего
расписания и каскадно применяет к помещениям профили режимов — сервисные вызовы
к свету и разрешение/запрет работы автоматизаций по датчикам движения. Заменяет
разрозненные YAML-автоматизации единым механизмом с настройкой через UI.

**Документы:**

| Документ | О чём |
|---|---|
| [`docs/task.md`](docs/task.md) | постановка задачи, BDD-сценарии (шаг 1) |
| [`docs/TZ.md`](docs/TZ.md) | архитектурные требования, журнал решений (ред. 5) |
| [`SPEC.md`](SPEC.md) | спецификация: модули, типы, алгоритмы, критерии |
| [`PLAN.md`](PLAN.md) | план по этапам + changelog выполненного |
| [`CONTEXT.md`](CONTEXT.md) | доменный словарь |
| [`docs/contract-ha-lighting-compilers.md`](docs/contract-ha-lighting-compilers.md) | контракт со смежным проектом-генератором |

**Статус (2026-07-23):** этапы 0–8 закрыты. Ядро — вся политика в чистых функциях
`domain/` (покрытие ветвей 100 %, mutation ≥ 90 %); исполняющая обвязка, сущности
и сервисы; WebSocket API с точечными операциями и правами. Всё проверено на
песочнице HA 2026.5.4 (полевые тесты этапов 7 и 8). Дальше — этап 9 (панель
пусконаладчика), затем 10 (приёмка).

Контракты для панели и смежных проектов — [`SPEC.md` §2.6](SPEC.md):
команды WebSocket, события на шине, сервисы, состав сущностей.

Проект построен на шаблоне **sdd-kit** (Spec-Driven Development). Воркфлоу и
принципы качества шаблона — ниже.

---

## Структура

```
.ai/                       # источник истины (общий для всех AI-инструментов)
├── prompts/               # ШАБЛОНЫ ВОРКФЛОУ — главное, с чего начинать
│   ├── 1-task.md          #   шаг 1: сформулировать задачу + дать контекст
│   ├── 2-spec.md          #   шаг 2: составить спецификацию → SPEC.md
│   ├── 3-plan.md          #   шаг 3: сделать план → PLAN.md
│   ├── 4-improve-plan.md  #   шаг 4: улучшить план (аудит на 100%)
│   ├── 5-implement.md     #   шаг 5: итерации + тестирование (по этапам)
│   └── 6-audit.md         #   шаг 6: финальный аудит по Definition of Done
├── rules/
│   ├── styleguide.md      # @Styleguide — ядро качества + Definition of Done
│   ├── python-guidelines.md      # ядро интеграции (HA custom component)
│   ├── javascript-guidelines.md  # Custom Panel (vanilla JS + Lit, без сборки)
│   └── tooling.md                # версии, пины, команды — всё, что стареет
├── skills/                # tdd, improve-codebase-architecture, review,
│   │                      # security-best-practices, diagnose, changelog-...
│   └── ...
└── agents/                # node-specialist и др.

.claude/  .codex/  .agents/   # симлинки на .ai/ — Claude Code, Codex и др.
                             # используют ОДНИ И ТЕ ЖЕ промпты/скиллы/правила
.mcp.json                    # MCP-серверы (context7 — актуальная докуменация)
```

`.ai/` — единственный источник истины. `.claude/`, `.codex/`, `.agents/` —
симлинки на него, поэтому правила и скиллы одинаковы во всех инструментах.

---

## Воркфлоу: 7 шагов

| Шаг | Действие | Промпт |
|-----|----------|--------|
| 1 | Сформулировать задачу | [`1-task.md`](.ai/prompts/1-task.md) |
| 2 | Дать контекст | вшит в `1-task.md` + репозиторий |
| 3 | Составить спецификацию | [`2-spec.md`](.ai/prompts/2-spec.md) → `SPEC.md` |
| 4 | Сделать план | [`3-plan.md`](.ai/prompts/3-plan.md) + [`4-improve-plan.md`](.ai/prompts/4-improve-plan.md) → `PLAN.md` |
| 5 | Двигаться небольшими итерациями | [`5-implement.md`](.ai/prompts/5-implement.md) |
| 6 | Тестировать результат | вшит в `5-implement.md` |
| 7 | Делать аудит | [`6-audit.md`](.ai/prompts/6-audit.md) |

### Как пользоваться

1. Скопируй [`1-task.md`](.ai/prompts/1-task.md), заполни плейсхолдеры → отправь LLM.
2. [`2-spec.md`](.ai/prompts/2-spec.md): из задачи рождается `SPEC.md`.
3. [`3-plan.md`](.ai/prompts/3-plan.md): из спеки рождается `PLAN.md`.
4. [`4-improve-plan.md`](.ai/prompts/4-improve-plan.md): усиливаешь план до 100 % покрытия задачи.
5. [`5-implement.md`](.ai/prompts/5-implement.md): выполняешь план **по одному этапу**, TDD, тесты после каждого.
6. [`6-audit.md`](.ai/prompts/6-audit.md): финальная проверка по Definition of Done.

Подробности — в [`.ai/prompts/README.md`](.ai/prompts/README.md).

---

## Контроль качества

Девять принципов из [`@Styleguide`](.ai/rules/styleguide.md):

- **BDD** — сценарии Given/When/Then до кода.
- **TDD** — сначала упавший тест, потом код (skill `tdd`).
- **Измеримые критерии** — количественные, без возможности «мухлевать».
- **Styleguide** — единый стиль (ядро + язык-специфичный гайд).
- **Строгая типизация и AST-анализ** — `mypy --strict` / `tsc --strict`, линтер.
- **Мутационное тестирование** — `mutmut` / `stryker`, score ≥ 70 %.
- **Чеклисты** — Definition of Done пункт за пунктом.
- **Чистая архитектура** — глубокие модули, швы (skill `improve-codebase-architecture`).
- **Алгоритмы и сложность** — Big-O указывается явно.

Полный **Definition of Done** — в [`.ai/rules/styleguide.md`](.ai/rules/styleguide.md).

---

## Создание нового проекта

Цель — получить **чистую копию без истории шаблона** и с сохранёнными
симлинками (`.claude`, `.codex`, `.agents` → `.ai/`).

### Вариант 1: git clone (рекомендуется)

```bash
git clone sdd-kit my-new-project      # клон сохраняет симлинки
cd my-new-project
rm -rf .git                           # убираем историю шаблона
rm -f .claude/settings.local.json     # локальные разрешения не нужны
git init && git add -A && git commit -m "Initial commit from sdd-kit"
```

### Вариант 2: GitHub template / degit

Если шаблон лежит на GitHub — нажми **«Use this template»** либо:

```bash
npx degit <user>/sdd-kit my-new-project   # чистая копия без .git
```

### Вариант 3: cp -R

```bash
cp -R sdd-kit my-new-project          # -R на macOS сохраняет симлинки
cd my-new-project
rm -rf .git .claude/settings.local.json
git init
```

> ⚠️ Не используй `cp -RL`: флаг `-L` разыменует симлинки и превратит их в
> копии файлов — тогда `.ai/` перестанет быть единственным источником истины.

### Проверка после копирования

```bash
ls -la .claude    # skills/agents должны быть стрелками -> ../.ai/...
```

## Подгонка под проект — выполнена

Шаблон подогнан под интеграцию **«Building Automation» (Оркестратор здания)** для
Home Assistant OS.

- Язык ядра — Python (custom component), фронт — vanilla JS + Lit без сборки.
- Гайды в `.ai/rules/` переписаны под HA; `typescript-guidelines.md` удалён.
- Инструменты качества настроены: `pyproject.toml` (ruff + mypy strict + pytest),
  `jsconfig.json` (`tsc --checkJs --strict` по JSDoc), `eslint.config.js`,
  `.prettierrc`.
- Всё версионное вынесено в [`.ai/rules/tooling.md`](.ai/rules/tooling.md) — при
  обновлении Home Assistant правится только этот файл.

Пройдены шаги 1–5: `task.md`, `TZ.md`, `SPEC.md`, `PLAN.md` и реализация
этапов 0–8 (ядро, обвязка, сущности, WebSocket API). Актуальный статус и
changelog — в [`PLAN.md`](PLAN.md).
