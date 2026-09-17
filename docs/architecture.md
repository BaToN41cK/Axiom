# Архитектура AXIOM

Документ описывает, как устроен проект и почему. Краткая версия правил живёт в
корневом `README.md`, здесь — детали с указанием модулей.

---

## Два принципа

### 1. REAL FIRST

Axiom не симулирует работу AI. Запрещены fake responses, fake reasoning,
fake web search, fake статусы, fake счётчики токенов и статические
демо-данные в production flow.

Практические следствия:

* reasoning существует в UI только тогда, когда модель реально прислала поле
  `thinking` (или legacy `<think>`-теги в контенте);
* блок «WEB SEARCH» в сообщении возникает только после реального вызова
  `SearchProvider`;
* статус `COMPLETED` невозможен при пустом ответе — в `ChatSession` встроена
  empty-answer protection (`axiom/core/chat.py`);
* capabilities модели берутся из ответа `/api/tags`; если Ollama не сообщила
  возможность — она показывается как `unknown`, а не `supported`
  (`axiom/core/models.py::ModelInfo.supports`).

### 2. UI ≠ LOGIC

Axiom — это ядро, у которого есть фронтенды. Ядро не знает слов «Textual»,
«Rich», «Qt»: оно общается снаружи только через:

* **команды** — методы `ChatSession` (`send`, `cancel`, `switch_model`,
  `new_conversation`, `load_conversation`, `refresh_models`, `reconnect` ...);
* **события** — `AsyncIterator[ChatEvent]` из `ChatSession.send()`;
* **структуры данных** — pydantic-модели из `axiom/core/events.py`.

Фронтенд — тонкий адаптер: подписывается на события, рисует их, шлёт команды
обратно. Проверка чистоты — тест `test_no_ui_imports` (см. `TODO.md`).

---

## Карта модулей

```text
src/axiom/
├── __init__.py            ← __version__ + публичный API
├── __main__.py            ← единственное место выбора фронтенда
├── core/                  ← frontend-agnostic ядро
│   ├── events.py          ← ChatEvent: все события потока
│   ├── state.py           ← GenerationState (перечисление)
│   ├── state_machine.py   ← валидатор переходов
│   ├── chat.py            ← ChatSession: send/cancel/startup/история
│   ├── agent.py           ← агентный цикл: model → tools → model → answer
│   ├── models.py          ← discovery + capabilities (ModelRegistry)
│   ├── ollama.py          ← HTTP-клиент + адаптивный streaming-парсер
│   ├── config.py          ← загрузка/сохранение конфигурации
│   ├── history.py         ← Conversation + HistoryStore (JSON-файлы)
│   ├── errors.py          ← доменные ошибки (AxiomError и наследники)
│   ├── tools/             ← base / registry / web_search
│   └── search/            ← provider (ABC) / duckduckgo
├── frontends/
│   ├── tui/               ← Textual: app.py + widgets/ + theme.tcss
│   └── gui/               ← лаунчер `axiom --gui` (main.py), само приложение в desktop/
└── shared/                ← данные для всех фронтендов: theme, logo, formatting
```

Ответственность каждого модуля — одна; новых «параллельных» реализаций одной
функции нет (правило §50 исходной спецификации).

---

## Поток событий (ChatEvent)

`ChatSession.send()` возвращает `AsyncIterator[ChatEvent]`. Типы
(`axiom/core/events.py`):

| Событие | Поля | Когда возникает |
|---|---|---|
| `StatusChange` | `state`, `detail` | подтверждённый переход state machine |
| `ReasoningChunk` | `text` | дельта реального reasoning |
| `ContentChunk` | `text` | дельта реального ответа |
| `ToolCallEvent` | `name`, `arguments` | модель запросила инструмент |
| `ToolResultEvent` | `name`, `ok`, `content`, `error`, `duration_ms` | результат реального выполнения |
| `SearchResultEvent` | `query`, `sources: list[SourceItem]` | поиск вернул источники (`index`, `title`, `url`, `snippet`) |
| `ErrorEvent` | `message`, `kind`, `hint` | ошибка пользователя (никогда traceback) |
| `Done` | `state`, `duration_ms`, `tokens_out`, `tokens_in`, `tokens_per_second` | терминальное событие с метриками Ollama |

Инвариант: после `Done` поток завершается; `Done.state` — одно из
`COMPLETED / CANCELLED / ERROR`.

## State machine генерации

`axiom/core/state.py` + `state_machine.py`. Состояния:

```text
IDLE → CONNECTING → THINKING ⇄ TOOL_CALL ⇄ SEARCHING → RECEIVING → COMPLETED
                                                                → CANCELLED / ERROR
```

Правила:

* busy-состояния (`CONNECTING/THINKING/TOOL_CALL/SEARCHING/RECEIVING`) могут
  переходить друг в друга — реальный цикл агента нелинеен;
* любой busy-стейт → финальный (`COMPLETED/CANCELLED/ERROR`);
* из финального разрешён только переход в `IDLE` (новая отправка делает
  `machine.reset()`);
* недопустимый переход вызывает `InvalidTransitionError` — UI не может
  показать статус, которого не было в реальности.

`Agent._status()` эмитит `StatusChange` только если переход разрешён —
state machine это единственный источник статусов.

## Агентный цикл

`axiom/core/agent.py`:

```text
USER → CONTEXT (последние 40 сообщений) → SYSTEM PROMPT
     → MODEL STREAM
        ├── reasoning deltas → ReasoningChunk
        ├── content deltas   → ContentChunk
        └── tool_calls?
              ├── web_search → SearchProvider.search → источники
              │     └── чтение топ-N страниц (fetch_url) → блок результатов
              ├── результат → system-сообщение → MODEL снова
              └── максимум MAX_TOOL_ROUNDS = 3 раундов
     → финальный ANSWER
```

Принудительный поиск (`/search`, флаг `-s`) выполняется до первого вызова
модели: результаты подмешиваются в system prompt. Если поиск недоступен,
агент честно сообщает об этом модели и отвечает без источников.

## Инструменты и права

`axiom/core/tools/`: `ToolDefinition` (name, description, JSON-schema
параметров, permission) + `ToolRegistry.execute()`.

| Инструмент | Назначение | Permission |
|---|---|---|
| `web_search` | реальный поиск DuckDuckGo (HTML/lite endpoints, без ключей) | `ALWAYS` |
| `fetch_url` | чтение текста страницы для источников | `ALWAYS` |

`Permission.NEVER` блокирует вызов даже если модель его запросила; исключения
обработчиков превращаются в структурированный `ToolResult(ok=False)` — тул
никогда не валит агента. Произвольный доступ к файлам/шеллу отсутствует
(правило LOCAL FILE ACCESS = OFF); архитектура позволяет добавить tool
с нужным permission позже.

## Streaming-парсер Ollama

`axiom/core/ollama.py::ChatStreamParser` — адаптивный разбор NDJSON
`/api/chat`:

* `message.thinking` — авторитетный reasoning;
* legacy-модели: `<think>...</think>` внутри content, включая частичные теги
  на границах чанков (буферизация + `flush()`);
* `message.tool_calls` → `ToolCallRequest` (arguments строкой → JSON);
* финальный `done`-чанк → метрики (`eval_count`, `eval_duration`, ...);
* ошибки: `InvalidResponseError` на мусор, `OllamaUnavailableError` на обрыв;
  неизвестные поля игнорируются, поток не падает.

## Модели и capabilities

`axiom/core/models.py::ModelRegistry` читает `/api/tags`. Из
`capabilities: ["completion", "tools", "thinking", "vision"]` строится
`ModelInfo.supports()`: `True/False` — если Ollama сообщила, `None` (`unknown`)
— если нет. Reasoning включается по реальной capability (или по явному
`think` из конфига), а не по названию модели.

## Персистентность

* `Config` — атомарная запись JSON (`*.json.tmp` → replace), устойчива к
  мусору: невалидные поля отбрасываются.
* `HistoryStore` — по файлу JSON на разговор; повреждённые файлы пропускаются
  при листинге; разговор сохраняется после каждого завершённого оборота
  (включая частичный вывод при отмене).

