# AXIOM — ОСТАВШИЕСЯ РАБОТЫ

Исходная спецификация (принципы REAL FIRST / UI ≠ LOGIC, агентный цикл, state machine, splash, Ollama-клиент, streaming parser, slash-команды, панели и т.д.) уже реализована в ядре и виджетах. Этот файл содержит **только незавершённые работы**. Номера § ссылаются на пункты исходной спецификации.

Реализовано и не требует доработки:

* `core/` целиком — chat, agent, ollama (+адаптивный parser), models, config, history, state_machine, events, errors, tools (base/registry/web_search), search (provider/duckduckgo)
* `shared/` — theme, logo, formatting
* `frontends/cli/` — one-shot / pipe / `--json`
* `frontends/gui/` — пустой контракт (GUI slot)
* `__main__.py` — диспетчер фронтендов
* TUI-виджеты: `commands`, `header`, `messages`, `prompt`, `reasoning`, `search`, `splash`
* `panels.py` — база (`PanelScreen`) и `ModelPanel`
* `pyproject.toml` — src-layout, entry point `axiom`, package-data для `.tcss`

---

## 1. Дописать `frontends/tui/widgets/panels.py` ✅ ГОТОВО

- [x] `HistoryPanel` (`/history`) — реальные conversations из `HistoryStore.list()`, группировка Today/Yesterday через `fmt.history_bucket`, Enter — открыть (вернуть id), Delete — удалить (`session.delete_conversation`) (§18, §21)
- [x] `SettingsPanel` (`/settings`) — переключатели `web_search_enabled`, `show_reasoning`, `reasoning_expanded`, `animations`, `save_history`; поля `temperature`, `system_prompt`; сохранение через `Config.save()` (§33)
- [x] `HelpPanel` (`/help`) — описание команд из `COMMANDS` и управление интерфейсом; это справочная панель, а НЕ hotkeys-строка внизу главного экрана (§38)
- [x] `StatusPanel` (`/status`) — реальный Ollama URL и версия, активная модель, capabilities как их реально отдал Ollama (`unknown` — если не сообщены), метрики последней генерации (§23, §44, §45)
- [x] `ModelPanel`: добавлена клавиша `r` — реальный refresh списка моделей

## 2. Создать `frontends/tui/app.py` — главный экран и связка ✅ ГОТОВО

- [x] `AxiomApp(App)` + `WorkspaceScreen`: compose = Header, ChatView, PromptBar; `CSS_PATH = "theme.tcss"`; регистрация темы obsidian
- [x] Метод `start_workspace()` — вызывается из `SplashScreen` после успешного startup
- [x] Маппинг событий CORE → виджеты: `StatusChange`, `ReasoningChunk`, `ContentChunk`, `SearchResultEvent` (включая чтение источников), `ToolCallEvent`/`ToolResultEvent`, `ErrorEvent`, `Done` (§12–§15)
- [x] Отправка: `ChatSession.send()` в worker'е, запрет второй отправки во время генерации
- [x] Stop: Stop в PromptBar и `Ctrl+C` (только пока генерация реально идёт, через `check_action`) → `session.cancel()`
- [x] Slash-команды: выполнение всех команд из `COMMANDS`; `/model <name>` с аргументом; ↑↓ навигация по меню команд из промпта (§16, §17, §18)
- [x] Результат `ModelPanel` → `session.switch_model()`, обновить Header/StatusBar (§6, §22)
- [x] `HistoryPanel` → `load_conversation()` + перерисовка ChatView; `/new`, `/clear` → `new_conversation()` / `clear_messages()`
- [x] StatusBar: только реальные данные — модель, `● Ollama`, токены и tok/s из `Done` (§23, §44)
- [x] Ошибки — аккуратный error-box, никогда не traceback (§24)
- [x] `main()` для импорта из `__main__.py` и `frontends/tui/__init__.py`
- [x] Клик по источнику поиска открывает URL в браузере

## 3. Создать `frontends/tui/theme.tcss` ✅ ГОТОВО

- [x] Полный stylesheet под obsidian-палитру: чёрный фон, багровый акцент точечно (≤5–7% экрана), приглушённый серый текст (§2)
- [x] Стили для всех существующих классов/id: splash, header, сообщения, reasoning, search, prompt, command-menu, panel*, status
- [x] Адаптивность через относительные единицы (Textual 8 не поддерживает `@media`): панель 90%/min-width, компактные отступы (§34)

## 4. Создать `tests/`

Тесты идут против установленного пакета (editable install уже настроен).

- [ ] `tests/core/test_ollama_parser.py` — reasoning/content, legacy `<think>`, частичные теги на границах чанков, tool calls, финальные metadata, мусорные строки, flush
- [ ] `tests/core/test_state_machine.py` — валидные/невалидные переходы, финальные состояния, `reset`
- [ ] `tests/core/test_chat.py` — поток событий `send()`, cancel, empty-answer protection, сохранение conversation
- [ ] `tests/core/test_tools_registry.py` — permissions (NEVER блокируется), неизвестный tool, исключения обработчиков
- [ ] `tests/frontends/test_cli.py` — `-p`, `--json`, pipe
- [ ] `tests/core/test_no_ui_imports.py` — `axiom.core` не тянет textual/rich/pyqt/toga

## 5. Создать `README.md` (§52) ✅ ГОТОВО + docs/

- [x] `README.md` — свойства, требования, установка, Ollama setup, запуск (TUI/CLI), slash-команды, конфигурация, troubleshooting, структура
- [x] `docs/index.md` — индекс документации
- [x] `docs/architecture.md` — принципы, карта модулей, события, state machine, агентный цикл, tools, парсер, персистентность
- [x] `docs/tui.md` — экраны, клавиши, команды, панели
- [x] `docs/cli.md` — режимы, флаги, коды возврата, формат NDJSON-событий
- [x] `docs/configuration.md` — все поля конфига и правила применения
- [x] `docs/development.md` — правила кода, тесты, добавление tools/фронтендов

## 6. Cleanup (§51) ✅ ГОТОВО

- [x] Удалены `_probe_stream.py`, `_probe_textual.py`, `__pycache__` из корня и `src`
- [x] В `src/` не осталось TODO/FIXME/PLACEHOLDER-маркеров (включая `# <<PANELS-NEXT>>`)

## 7. Финальная runtime-верификация (§35, §41)

- [x] Реальная Ollama v0.34.0: `/api/tags`, реальный streaming; вывод модели (`OK`) реально попал в ANSWER — headless smoke-тест прошёл (splash → workspace → генерация → `/status`)
- [ ] Сценарий `reasoning → content` на deepseek-r1:8b проверить глазами в реальном терминале
- [ ] Сценарий `content only` (gemma4:12b) проверить глазами в реальном терминале
- [ ] Ollama выключена → splash показывает красивую ошибку, Retry/Exit работают
- [ ] Пустой ответ → понятная ошибка, никаких ложных `Completed ✓` (§43)
- [ ] Slash-команды, автокомплит, стрелки, мышь, скролл, resize — ручная проверка UX
- [ ] История и конфиг persist между запусками
- [ ] Установка с чистого окружения (`pip install -e .` в свежем venv), entry point `axiom`
