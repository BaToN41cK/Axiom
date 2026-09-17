# Конфигурация

## Расположение

| Файл/папка | Назначение |
|---|---|
| `~/.axiom/config.json` | конфигурация |
| `~/.axiom/history/*.json` | сохранённые разговоры (по файлу на разговор) |

Переменная окружения `AXIOM_HOME` переопределяет корневую папку:

```powershell
$env:AXIOM_HOME = "D:\axiom-data"
```

Первый запуск работает без ручной настройки: `config.json` создаётся
автоматически, модель выбирается из обнаруженных.

## Поля config.json

| Поле | Тип | По умолчанию | Описание |
|---|---|---|---|
| `ollama_url` | str | `http://127.0.0.1:11434` | адрес Ollama API |
| `model` | str \| null | `null` | выбранная модель; `null` → авто-выбор первой доступной |
| `think` | bool \| null | `null` | `null` — следовать capability модели; `true/false` — явный запрос reasoning |
| `web_search_enabled` | bool | `true` | разрешить агенту web search |
| `search_max_sources` | int 1–10 | `5` | сколько источников удерживать |
| `search_read_sources` | int 0–10 | `3` | сколько страниц реально читать |
| `show_reasoning` | bool | `true` | показывать reasoning в UI |
| `reasoning_expanded` | bool | `false` | блок reasoning раскрыт сразу |
| `theme` | str | `"obsidian"` | имя темы |
| `animations` | bool | `true` | спиннеры/анимация заставки |
| `save_history` | bool | `true` | сохранять разговоры между запусками |
| `temperature` | float \| null 0–2 | `null` | температура; `null` — параметр не отправляется |
| `system_prompt` | str \| null | `null` | системный промпт; `null` — встроенный |

## Как и когда применяются настройки

* Через панель `/settings` изменения **сохраняются сразу** (каждое
  переключение/Save вызывает `Config.save()` — атомарная запись через
  временный файл).
* `web_search_enabled`, `temperature`, `system_prompt`, `think`,
  `search_read_sources` читаются ядром **при каждой генерации** — применяются
  без перезапуска.
* `reasoning_expanded`, `animations` влияют на **новые** сообщения/запуски.
* Повреждённый `config.json` не приводит к падению: валидные поля
  сохраняются, невалидные отбрасываются (`Config.load`).

## Настройки на один запуск

Все настройки меняются через панель `/settings` в TUI (или Settings в GUI)
и сохраняются в `config.json`. Разовых флагов командной строки больше нет —
`axiom` всегда запускает TUI, `axiom --gui` — десктопный GUI.
