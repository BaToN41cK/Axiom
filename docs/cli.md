# CLI-фронтенд

CLI — тонкая обёртка над тем же ядром, что и TUI. Никакого интерфейса:
только stdin/stdout, поэтому AXIOM можно встраивать в скрипты и пайплайны.

```bash
axiom -p "вопрос"      # one-shot
echo "вопрос" | axiom  # pipe
axiom --json -p "..."  # NDJSON-события
```

## Режимы

| Режим | Как попасть | Что происходит |
|---|---|---|
| One-shot | `axiom -p "..."` или `axiom "..."` | вопрос → полный ответ в stdout → выход |
| Pipe | `echo "..." \| axiom` | stdin не TTY → текст становится промптом |
| JSON-поток | `axiom --json -p "..."` | каждая строка — JSON-событие ядра |
| Список моделей | `axiom --list-models` | `/api/tags`: имя, размер, capabilities |

Автоматический выбор: любой CLI-флаг **или** непустой stdin → CLI;
иначе → TUI. Явно: `python -m axiom` без аргументов всегда TUI.

## Флаги

| Флаг | Значение |
|---|---|
| `-p`, `--prompt` | промпт (эквивалентно позиционному аргументу) |
| `-m`, `--model` | модель только для этого запуска |
| `-s`, `--search` | принудительный web search перед ответом |
| `--no-search` | запретить web search для этого запуска |
| `--think auto\|on\|off` | reasoning: как у модели / обязательно / выключить |
| `--show-reasoning` | печатать reasoning в stderr (в stdout остаётся только ответ) |
| `--json` | NDJSON-поток событий вместо текста |
| `--list-models` | показать модели и выйти |
| `--ollama-url` | переопределить адрес Ollama |
| `--version`, `--help` | версия / справка |

Коды возврата: `0` — успех, `1` — ошибка выполнения, `2` — ошибка
использования, `130` — прервано пользователем (Ctrl+C).

## Примеры

```bash
# быстрый вопрос
axiom -p "что такое asyncio?"

# с reasoning (deepseek-r1) и без — сравнить
axiom --think on  -p "докажи, что sqrt(2) иррационален"
axiom --think off -p "докажи, что sqrt(2) иррационален"

# модель с vision/tools, принудительный поиск
axiom -m gemma4:12b -s -p "какие сегодня главные новости в мире AI?"

# перевод файла
Get-Content notes.txt | axiom -p "переведи на английский"

# сохранить поток событий
axiom --json -p "объясни TCP" > events.ndjson
```

## Формат `--json` (NDJSON)

Каждая строка — одно событие ядра (`axiom.core.events`), сериализованное в
JSON. Поле `type` определяет событие:

```jsonc
{"type": "status",   "state": "connecting", "detail": "deepseek-r1:8b"}
{"type": "status",   "state": "thinking"}
{"type": "reasoning", "text": "Нужно вспомнить определение …"}
{"type": "status",   "state": "receiving"}
{"type": "content",  "text": "asyncio — это "}
{"type": "content",  "text": "библиотека Python …"}
{"type": "done", "state": "completed", "duration_ms": 4821,
 "tokens_out": 128, "tokens_in": 45, "tokens_per_second": 26.5}
```

Событие поиска:

```jsonc
{"type": "search_result", "query": "news", "sources": [
  {"index": 1, "title": "python.org", "url": "https://…", "snippet": "…"}]}
```

Событие ошибки:

```jsonc
{"type": "error", "message": "Ollama is not reachable.",
 "kind": "ollama_unavailable", "hint": "Check that Ollama is running …"}
```

Состояния (`state`) те же, что в TUI: `idle, connecting, thinking, tool_call,
searching, receiving, completed, cancelled, error`. Поток всегда завершается
событием `done`.
