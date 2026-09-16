# AXIOM — ОСТАВШИЕСЯ РАБОТЫ

> Файл переписан 2026-09-15: выполненные и проверенные пункты исходной
> спецификации удалены. Ниже — **только незавершённые работы**.

## Текущее состояние (кратко, всё проверено)

- Ядро (`axiom.core`): Ollama-клиент, streaming parser (native `thinking`,
  legacy ` sway`, частичные теги, tool calls, metadata), state machine, chat,
  history/config persistence, tools registry, DuckDuckGo search provider —
  реализовано и покрыто тестами.
- Reasoning: native reasoning stream отделён от content, панель Thinking
  схлопывается после завершения, reasoning не попадает в финальный ответ.
- TUI: splash (реальные пробы + Retry/Exit), workspace, reasoning-панель,
  отмена генерации, автокомплит команд, scroll-follow.
- Тесты: `pytest` — **41 passed**.
- Headless runtime-верификация против реальной Ollama v0.34.0
  (deepseek-r1:8b — reasoning, gemma4:12b — content-only): см. `.smoke/*.py`.

---

## 1. Интерактивная UX-проверка (только живой терминал)

Headless-проверкой не покрывается. Прогнать вручную в реальном терминале:

- [ ] Slash-команды: `/help`, `/status`, `/model`, `/models`, `/clear`,
      `/history`, `/search`, `/settings`, `/exit` — каждая реально выполняется
- [ ] Autocomplete: `/` открывает меню, стрелки, Tab, Escape, Enter
- [ ] Клавиши: Ctrl+C как Stop во время генерации, Ctrl+L, End (follow)
- [ ] Мышь: колесо, скролл истории, клики по source/tool-строкам
- [ ] Scrolling: чтение истории не дёргает viewport вниз; End возвращает follow
- [ ] Resize: окно меняет размер без поломки layout

## 2. Реальный web-search round-trip

Ядро и UI проверены против реального DuckDuckGo (2026-09-15):

- [x] `/search <query>` в TUI: реальный запрос → DuckDuckGo → панель
      «WEB SEARCH» с N источниками → ответ модели с опорой на источники
      (`.smoke/tui_search_smoke.py`, deepseek-r1:8b — работает даже без
      capability `tools`)
- [x] `-s` в CLI: полный поток `searching → tool_call(web_search) →
      tool_result(ok) → search_result(5 источников) → read_source(fetch_url) →
      generating`; `-s` теперь **форсирует** поиск, даже если настройка
      `web_search_enabled: false`
- [x] `fetch_url` — реальные страницы прочитаны в потоке (read_source)
- [x] HTML-entities в заголовках/сниппетах декодируются (`Python's`, а не
      `Python&#x27;s`); в UI уходит реальный запрос, а не имя tool

Осталось проверить:

- [x] Tool-call, инициированный **самой моделью** (gemma4:12b, capability
      `tools`): модель сама вызывает `web_search` → результат → финальный ответ
      (`.smoke/model_tool_smoke.py`, 2026-09-16: tool_call web_search →
      tool_result ok → completed)
- [x] Нет интернета → понятная причина, чат выживает
      (`.smoke/search_unavailable_smoke.py`, 2026-09-16: провайдер на
      unroutable-адрес, force_search → failed tool result «Web search is
      unavailable» → финальный ответ → COMPLETED; настоящая физическая изоляция
      сети не эмулировалась, но путь ошибки пройден end-to-end)

## 3. Performance benchmark (§34 исходной спецификации)

- [x] Скрипт `.smoke/benchmark.py`: измеряет `TTFT`, первый reasoning-чанк,
      первый content-чанк, total, tok/s — на deepseek-r1:8b и gemma4:12b,
      выводит таблицу как в §34. Прогнан 2026-09-16 (CPU): TTFT 0.2–0.5s,
      tok/s 1.8–3.9 (CPU-инференс, без GPU — цифры только для сравнения
      регрессий).
- [x] Latency без деградации: искусственных задержек нет, UI-обновления
      батчатся (полного redraw на каждый токен нет).

## 4. GUI frontend (tkinter)

Реализован (`src/axiom/frontends/gui/app.py`), но не проверялся:

- [ ] Ручной прогон: splash-пробы, генерация, reasoning-панель, cancel,
      slash-команды, история

## 5. Мелочи

- [x] Чистая установка в свежем venv повторно после последних правок
      (`pip install -e .`, entry point `axiom` — `axiom --list-models`
      работает, 2026-09-16)
- [x] `ruff check` по проекту: 0 ошибок (конфиг `[tool.ruff]` добавлен в
      pyproject.toml; автофиксы + правки DTZ/SIM/E501 в formatting.py,
      ollama.py, events.py, agent.py, reasoning.py, panels.py)
- [x] Прогнать `pytest`: 41 passed
- [x] Закоммитить текущий TUI-редизайн и headless-верификацию

---

## Как проверять (инструменты уже готовы)

```powershell
# unit-тесты
python -m pytest -q

# headless TUI-смоуки против реальной Ollama (каждый со своим чистым AXIOM_HOME)
$env:AXIOM_HOME = "$PWD\.smoke\home-1"; python .smoke\tui_smoke.py
$env:AXIOM_HOME = "$PWD\.smoke\home-2"; python .smoke\tui_reasoning_smoke.py
$env:AXIOM_HOME = "$PWD\.smoke\home-3"; python .smoke\tui_cancel_smoke.py
$env:AXIOM_HOME = "$PWD\.smoke\home-4"; python .smoke\splash_retry_smoke.py
$env:AXIOM_HOME = "$PWD\.smoke\home-5"; python .smoke\tui_search_smoke.py

# CLI
axiom --list-models
axiom --json --show-reasoning -m deepseek-r1:8b -p "..."
```

Важно: `OllamaClient` читает `config.json` при конструировании
`ChatSession` — URL/модель нужно класть в конфиг **до** старта сессии.
