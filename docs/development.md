# Разработка

## Окружение

```bash
git clone https://github.com/BaToN41cK/Axiom.git
cd Axiom
pip install -e ".[dev]"
```

Запуск из исходников без установки не требуется: editable-установка
регистрирует пакет и entry point `axiom`.

```bash
axiom                # TUI
axiom -p "ping"      # CLI
pytest               # тесты (набор добавляется — см. TODO.md, раздел 4)
```

## Правила, которые нельзя нарушать

1. **Один пакет** — `axiom`, всё внутри `src/axiom/` (src-layout).
2. **`core/` не импортирует UI** — ни `textual`, ни `rich`, ни `pyqt`.
   Контролируется тестом `tests/core/test_no_ui_imports.py`.
3. **Фронтенды не импортируют друг друга** — `tui` не знает про `cli`.
4. **`shared/` — только данные**: палитра, глифы, логотип, форматтеры.
   Никакого I/O и состояния.
5. **`__main__.py` — единственное место выбора фронтенда.**
6. **REAL FIRST** — никаких моков и заглушек в production flow; незавершённая
   функция честно сообщает о недоступности.
7. **Не ломать работающее** — `inspect → understand → change → test`
   (правило §50 исходной спецификации).

## Тестовая инфраструктура

`pyproject.toml` уже настроен: `pytest`, `asyncio_mode = "auto"`,
`testpaths = ["tests"]`. Планируемый набор (см. `TODO.md`):

```text
tests/core/test_ollama_parser.py   reasoning/content, legacy <think>, чанки, метрики
tests/core/test_state_machine.py   переходы, финалы, reset
tests/core/test_chat.py            send-поток, cancel, empty-answer, история
tests/core/test_tools_registry.py  permissions, неизвестный tool, исключения
tests/core/test_no_ui_imports.py   core не тянет UI-фреймворки
tests/frontends/test_cli.py        -p / --json / pipe
```

Headless smoke-проверка TUI (использовалась при разработке):
`App.run_test()` + реальная Ollama — splash → workspace → генерация → ANSWER.

## Как добавить инструмент (tool)

1. Опишите `ToolDefinition` (name, description, JSON-schema, permission)
   в `axiom/core/tools/<имя>.py`.
2. Реализуйте async-обработчик, возвращающий `ToolResult`.
3. Зарегистрируйте в `ToolRegistry` (см. `WebSearchTool.register`).
4. UI менять **не нужно**: фронтенды рендерят `ToolCallEvent`/`ToolResultEvent`
   и `StatusChange(detail=...)`-generic.

```python
definition = ToolDefinition(
    name="my_tool",
    description="What it does (for the model).",
    parameters={"type": "object", "properties": {...}, "required": [...]},
    permission=ToolPermission.ALWAYS,   # ASK — потребует явного разрешения позже
)
registry.register(definition, my_handler)
```

## Как добавить фронтенд

Контракт — `axiom/frontends/gui/__init__.py::GuiBackend` (Protocol):
конструктор принимает `ChatSession`, `send()` возвращает поток `ChatEvent`,
`cancel()` останавливает генерацию. Реализация может быть на чём угодно
(Qt/Toga/web) — ядро менять не придётся. Пока `create_backend()` честно
бросает `NotImplementedError`.

## Стиль и практики

* Типизация везде (`from __future__ import annotations`), pydantic для
  событий/конфига/истории.
* Доменные ошибки — наследники `AxiomError` (message + hint); наружу не
  просачивается ни traceback.
* Долгие операции — только `async`/workers; UI никогда не блокируется.
* Статусы — проекции `GenerationState`; парсинг ответа не доверяет формату
  (адаптивный parser + empty-answer protection).
* Cleanup-чеклист перед релизом — §51 исходной спецификации: без
  TODO/FIXME/MOCK/DEMO/PLACEHOLDER в ключевых функциях, без мёртвого кода.

## Навигация по коду

| Хочешь понять… | Смотри |
|---|---|
| как стримится ответ | `core/ollama.py` (клиент + парсер) → `core/agent.py` (`_stream_pass`) |
| откуда берутся статусы | `core/state_machine.py`, `core/agent.py` (`_status`) |
| как работает поиск | `core/search/duckduckgo.py`, `core/tools/web_search.py`, `core/agent.py` (`_execute_tool`, `_read_sources`) |
| как TUI подписан на ядро | `frontends/tui/app.py` (`_dispatch_event`) |
| как устроены панели | `frontends/tui/widgets/panels.py` |
| где сохраняются разговоры | `core/history.py` |
