# AXIOM — PRODUCTION UPGRADE & TODO EXECUTION

Ты работаешь над существующим репозиторием **Axiom**.

Репозиторий:
`https://github.com/BaToN41cK/Axiom`

Твоя задача — **не переписывать проект с нуля**, а внимательно изучить существующую кодовую базу и довести Axiom до действительно рабочего, быстрого и визуально качественного состояния.

Axiom — это terminal AI workspace для Ollama.

Основные требования:

* Ollama-first
* streaming
* настоящее reasoning
* настоящий final answer
* рабочие slash-команды
* рабочие tools
* быстрый response pipeline
* современный красивый TUI
* стабильная state machine
* отсутствие ложных `Completed ✓`
* отсутствие зависаний
* совместимость с reasoning и non-reasoning моделями

---

# 0. ГЛАВНЫЙ ПРИНЦИП

**REAL FIRST.**

Не делай UI-имитацию функций.

Если интерфейс показывает:

`Thinking`

— модель действительно должна находиться в reasoning-фазе.

Если интерфейс показывает:

`Search`

— должен реально выполняться search tool.

Если интерфейс показывает:

`Tool`

— должен реально выполняться tool.

Если показывается:

`Completed ✓`

— генерация действительно должна быть успешно завершена и должен существовать непустой финальный ответ.

Никаких fake animations, которые создают видимость работы AI.

UI должен отражать реальные события backend.

---

# 1. СНАЧАЛА ИЗУЧИ ПРОЕКТ

Перед изменением кода:

1. Изучи всю структуру репозитория.
2. Найди:

   * Ollama client
   * streaming implementation
   * streaming parser
   * state machine
   * chat/send pipeline
   * tools registry
   * slash commands
   * TUI/frontend
   * panels/widgets
   * config
   * history
   * persistence
   * splash
3. Определи, какие части уже работают.
4. Не удаляй существующую архитектуру без необходимости.
5. Не создавай параллельную реализацию уже существующей функции.
6. Сохраняй public API там, где это возможно.
7. После каждого крупного изменения запускай тесты.

Не предполагай архитектуру — **прочитай фактический код проекта**.

---

# 2. CRITICAL FEATURE — НАСТОЯЩЕЕ REASONING

Это самая важная задача.

Сейчас недостаточно показывать:

`Thinking...`

Нужно показывать **реальное содержимое reasoning модели**, если Ollama/model его предоставляет.

Поведение должно быть максимально похоже на современные reasoning-интерфейсы:

```text
┌─ Thinking ───────────────────────────────┐
│ I need to determine what the user means… │
│ First I should inspect the available…    │
│ Then I can formulate the final answer…   │
└───────────────────────────────────────────┘
```

Во время генерации reasoning постепенно появляется в streaming режиме.

Например:

```text
Thinking
  ├─ The user is asking about...
  ├─ I should first determine...
  ├─ There are two possible approaches...
  └─ The better approach is...
```

После завершения reasoning:

```text
Thinking ✓
```

Затем reasoning **ПОЛНОСТЬЮ исчезает из основного chat output**.

После этого начинается:

```text
Axiom:

Here is the final answer...
```

То есть пользователь не должен видеть reasoning внутри финального сообщения.

---

# 3. REASONING НЕ ДОЛЖЕН ПОПАДАТЬ В FINAL ANSWER

Критическое правило:

```text
reasoning != content
```

Никогда не смешивай их.

Pipeline должен логически выглядеть так:

```text
OLLAMA STREAM
      │
      ▼
STREAM PARSER
      │
      ├── reasoning chunk
      │        │
      │        ▼
      │   REASONING EVENT
      │
      └── content chunk
               │
               ▼
          CONTENT EVENT
```

Например:

```python
StreamEvent(
    type="reasoning",
    text="I need to analyze..."
)
```

затем:

```python
StreamEvent(
    type="content",
    text="The answer is..."
)
```

UI должен знать разницу между ними.

---

# 4. ПОДДЕРЖАТЬ ВСЕ REASONING FORMATS

Parser должен быть максимально устойчивым.

Обязательно поддержать:

### A. Ollama native reasoning fields

Если Ollama возвращает reasoning отдельным полем — использовать именно его.

### B. Legacy `<think>` format

Поддерживать:

```text
<think>
reasoning...
</think>
final answer...
```

### C. Partial tags

Обязательно корректно обрабатывать случай, когда streaming chunk разрезает tag:

```text
<thi
nk>
```

или:

```text
</thi
nk>
```

Нельзя показывать пользователю мусор вроде:

```text
<thi
```

### D. Reasoning-only chunks

### E. Content-only models

Например:

```text
content
content
content
```

должно работать без reasoning.

### F. Reasoning → content

```text
reasoning
reasoning
reasoning
content
content
content
```

### G. Content → reasoning

Если конкретная модель/формат неожиданно меняет порядок, parser не должен ломаться.

### H. Empty reasoning

Не показывать пустую панель Thinking.

---

# 5. REASONING STATE MACHINE

Добавь/улучши состояние примерно такого типа:

```text
IDLE
  ↓
REQUESTING
  ↓
THINKING
  ↓
ANSWERING
  ↓
COMPLETED
```

Также:

```text
REQUESTING → ERROR
THINKING → CANCELLED
ANSWERING → CANCELLED
```

При переходе:

```text
THINKING → ANSWERING
```

reasoning panel должен закрываться.

Важно:

`Thinking ✓` может существовать как краткий status indicator, но **сам reasoning текст не должен оставаться в final answer**.

---

# 6. REASONING UI

Сделай reasoning визуально красивым.

Не используй огромный постоянно раскрытый блок.

Во время reasoning:

```text
╭─ Thinking ───────────────────────────────╮
│ ▸ Analyzing the request...               │
│ ▸ Checking possible approaches...        │
│ ▸ Formulating the response...            │
╰──────────────────────────────────────────╯
```

После завершения:

```text
✓ Thinking completed
```

и panel исчезает.

Затем появляется финальный ответ.

Предпочтительный UX:

```text
User
 │
 ▼
Thinking
 │
 ├─ live reasoning
 │
 ▼
Answer
 │
 ▼
Completed ✓
```

---

# 7. НЕ ИМИТИРОВАТЬ REASONING

Не генерируй fake reasoning.

Запрещено:

```python
fake_thinking_messages = [...]
```

или:

```text
Analyzing...
Planning...
Thinking...
```

если модель на самом деле ничего такого не прислала.

Status messages допустимы только как описание реального состояния.

Например:

```text
Thinking...
```

можно показывать, пока parser действительно получает reasoning.

Но сам reasoning должен быть настоящим содержимым stream.

---

# 8. FINAL ANSWER MUST ALWAYS BE VISIBLE

Исправить критический баг:

Сейчас возможна ситуация:

```text
Thinking
Thinking
Planning
Completed ✓
```

но самого ответа модели пользователь не видит.

Такого быть не должно.

После завершения streaming:

1. Собрать весь `content`.
2. Проверить, что он не пустой.
3. Отобразить его.
4. Только после этого выставлять `COMPLETED`.

Нельзя:

```text
COMPLETED → answer later
```

Должно быть:

```text
stream finished
↓
content assembled
↓
content validated
↓
answer rendered
↓
COMPLETED
```

Если answer пустой:

```text
✗ Model returned an empty response
```

а не:

```text
Completed ✓
```

---

# 9. STREAMING PERFORMANCE

Сделать Axiom заметно быстрее.

Главная цель:

**минимальная задержка между Ollama chunk и отображением его в TUI.**

Проверь:

* buffering
* unnecessary sleeps
* excessive UI refresh
* synchronous blocking
* duplicate parsing
* повторный рендер всего сообщения на каждый token
* лишние allocations
* лишние serialization/deserialization
* блокирующие tool calls
* блокирующие network calls
* чрезмерный polling

Не делай искусственную задержку:

```python
sleep(...)
```

для имитации печати.

Текст должен появляться с реальной скоростью модели.

---

# 10. OPTIMIZE UI REFRESH

Не нужно полностью перерисовывать весь экран на каждый token.

Используй разумное batching:

```text
incoming tokens
      ↓
buffer
      ↓
small UI batch
      ↓
render
```

Но batching не должен создавать заметную задержку.

Цель:

* smooth streaming
* low CPU
* low latency
* no flickering
* no terminal tearing

---

# 11. MODEL RESPONSE LATENCY

Проверь Ollama request configuration.

Не ставь искусственно слишком маленький timeout.

Не делай:

```text
30 sec hard timeout
```

если модель реально продолжает работать.

Но и бесконечное зависание запрещено.

Используй корректный cancellation-aware timeout architecture.

---

# 12. CANCELLATION

Ctrl+C / cancel должен корректно останавливать:

* Ollama stream
* parser
* tool execution
* UI streaming
* state machine

После cancel:

```text
THINKING → CANCELLED
```

или:

```text
ANSWERING → CANCELLED
```

Никакого:

```text
Completed ✓
```

после отмены.

---

# 13. REAL TOOLS

Slash-команды и tools должны быть реально рабочими.

Никаких декоративных:

```text
/search
/web
/tool
```

которые только показывают UI.

Каждый tool должен:

1. зарегистрироваться в registry;
2. иметь schema;
3. иметь permission;
4. валидировать arguments;
5. выполнять handler;
6. возвращать structured result;
7. обрабатывать exceptions;
8. показывать реальный status в UI.

---

# 14. SLASH COMMANDS

Проверь все slash commands.

Минимально:

```text
/help
/status
/model
/models
/clear
/reset
/history
/search
/exit
/quit
```

Используй только реально существующие команды проекта.

Если команда уже существует — исправь её, а не создавай дубликат.

---

# 15. AUTOCOMPLETE

При вводе:

```text
/
```

должен появляться красивый autocomplete.

Например:

```text
╭─ Commands ───────────────────────────────╮
│ /help       Show help                    │
│ /model      Change model                 │
│ /models     List models                  │
│ /status     System status                │
│ /clear      Clear conversation           │
│ /history    Conversation history         │
│ /search     Web search                   │
│ /exit       Exit Axiom                   │
╰──────────────────────────────────────────╯
```

Поддержать:

* arrows
* Enter
* Escape
* Tab
* mouse selection, если framework поддерживает

---

# 16. REAL WEB SEARCH TOOL

Если web search уже присутствует в архитектуре:

проверить, что он действительно выполняется.

Flow:

```text
User
 ↓
Model
 ↓
tool request
 ↓
search
 ↓
search results
 ↓
Model
 ↓
final answer
```

UI:

```text
⌕ Searching web...
✓ Search completed
```

Но status должен появляться только при реальном выполнении.

Если internet unavailable:

```text
✗ Search unavailable
```

с понятной причиной.

---

# 17. TOOL PERMISSIONS

Проверить permissions.

`NEVER` должен действительно блокировать tool.

Не должно быть:

```text
permission = NEVER
↓
tool executes anyway
```

Обязательно добавить tests.

---

# 18. TOOL ERRORS

Tool exception не должен убивать весь chat session.

Например:

```text
ToolError
```

должен превратиться в controlled result:

```text
✗ Tool failed

Reason:
...
```

После этого state machine должна перейти в корректное состояние.

---

# 19. BEAUTIFUL TUI UPGRADE

Полностью проведи UX/UI audit существующего терминального интерфейса.

Цель:

**Axiom должен выглядеть как современный premium terminal AI workspace.**

Не копируй интерфейс один в один у другого проекта.

Можно использовать идеи:

* Oh My Pi
* modern coding agents
* DeepSeek-style reasoning UX
* modern terminal dashboards
* minimal dark developer tools

Но дизайн должен оставаться уникальным для Axiom.

---

# 20. VISUAL HIERARCHY

Главный экран должен иметь:

```text
╭──────────────────────────────────────────────────────╮
│ AXIOM                         Qwen3 / Ollama    ● LIVE │
├──────────────────────────────────────────────────────┤
│                                                      │
│  conversation                                       │
│                                                      │
│  User                                                │
│  ────────────────────────────────────────────────     │
│  ...                                                 │
│                                                      │
│  Axiom                                               │
│  ...                                                 │
│                                                      │
├──────────────────────────────────────────────────────┤
│  /command or message...                         ↵   │
├──────────────────────────────────────────────────────┤
│ Ollama ●  Model: qwen3:8b  Tokens: 1.2k  12 tok/s  │
╰──────────────────────────────────────────────────────╯
```

Не обязательно использовать именно этот layout.

Главное:

* чистый
* современный
* компактный
* хорошо читаемый
* минимум визуального шума
* хорошая типографика
* аккуратные borders
* плавный streaming
* понятные состояния

---

# 21. HEADER

В header показывать только полезную информацию.

Например:

```text
AXIOM
Qwen3:8B
OLLAMA ●
```

Можно добавить:

```text
Tokens
Speed
Context
Status
```

Но не перегружать интерфейс.

---

# 22. FOOTER

Footer может показывать:

```text
Model: qwen3:8b
Context: 8.4k
Output: 1.2k
Speed: 18 tok/s
```

Данные должны быть реальными.

Нельзя показывать случайные значения.

---

# 23. STATUS SYSTEM

Создать единую систему real-time status.

Например:

```text
● Connecting
● Thinking
● Searching
● Using tool
● Generating
✓ Completed
✗ Error
■ Cancelled
```

Каждый статус должен соответствовать реальному backend state.

Не должно существовать нескольких несвязанных status systems.

---

# 24. SPLASH SCREEN

Улучшить splash.

Он должен быть:

* быстрым
* красивым
* минималистичным
* без долгого ожидания
* соответствовать Axiom branding

Показывать:

```text
AXIOM

initializing...
connecting to Ollama...
loading workspace...
```

Но каждый этап должен отражать реальную операцию.

Если Ollama недоступна:

```text
╭─ Ollama unavailable ─────────────────────╮
│ Cannot connect to local Ollama server.   │
│                                          │
│ [R] Retry       [E] Exit                 │
╰──────────────────────────────────────────╯
```

Retry действительно должен повторять connection attempt.

---

# 25. MOUSE / KEYBOARD

Проверить:

* arrows
* Enter
* Escape
* Ctrl+C
* Ctrl+L
* mouse wheel
* scrolling
* resize

Resize не должен ломать layout.

---

# 26. SCROLLING

Если conversation длинный:

* пользователь должен иметь возможность scroll вверх;
* новые chunks не должны насильно возвращать viewport вниз, если пользователь читает историю;
* если пользователь находится внизу — streaming автоматически следует за ответом.

---

# 27. MODEL SWITCHING

Проверить:

```text
/models
/model
```

Модели должны реально браться из Ollama.

Не использовать hardcoded список, если API Ollama может вернуть реальные модели.

После смены модели:

```text
Model changed:
qwen3:8b → deepseek-r1:8b
```

И следующий запрос должен реально идти в новую модель.

---

# 28. CONVERSATION PERSISTENCE

Проверить:

* history
* config
* selected model
* conversation state

между запусками.

Не сохранять секреты или ненужные transient states.

---

# 29. TESTS

Создать:

```text
tests/core/test_ollama_parser.py
tests/core/test_state_machine.py
tests/core/test_chat.py
tests/core/test_tools_registry.py
tests/frontends/test_cli.py
tests/core/test_no_ui_imports.py
```

---

# 30. OLLAMA PARSER TESTS

Обязательно протестировать:

```text
reasoning + content
```

```text
<think> + content
```

```text
partial <think>
```

```text
partial </think>
```

```text
reasoning only
```

```text
content only
```

```text
empty response
```

```text
tool call
```

```text
metadata
```

```text
garbage/non-content lines
```

```text
flush
```

---

# 31. STATE MACHINE TESTS

Проверить:

```text
IDLE → REQUESTING
REQUESTING → THINKING
THINKING → ANSWERING
ANSWERING → COMPLETED
```

и:

```text
REQUESTING → ERROR
THINKING → CANCELLED
ANSWERING → CANCELLED
```

Невалидные переходы должны быть запрещены.

---

# 32. CHAT TESTS

Проверить:

* streaming
* cancellation
* empty answer
* conversation persistence
* reasoning
* content
* tool execution
* tool failure

---

# 33. NO UI IMPORTS

`axiom.core` не должен импортировать:

```text
textual
rich
pyqt
toga
```

если архитектура проекта предусматривает frontend isolation.

Core должен оставаться frontend-independent.

---

# 34. PERFORMANCE TEST

Создать простой benchmark.

Измерять:

```text
request start
first Ollama chunk
first reasoning chunk
first content chunk
stream finished
UI completed
```

Пример:

```text
TTFT:          0.42s
Reasoning:     2.31s
First answer:  3.08s
Total:         8.74s
Speed:         17.4 tok/s
```

Не ухудшать latency без причины.

---

# 35. REAL OLLAMA VERIFICATION

Использовать реальный Ollama.

Проверить:

```text
/api/tags
```

и реальный streaming API.

Минимально проверить:

```text
deepseek-r1:8b
```

для reasoning.

И content-only модель, например существующую модель из локального Ollama environment.

Не предполагать, что конкретная модель всегда присутствует — сначала проверить `/api/tags`.

---

# 36. ОБЯЗАТЕЛЬНЫЙ REASONING SCENARIO

Проверка:

```text
User:
Explain why 2 + 2 = 4.
```

Во время генерации должно быть примерно:

```text
Thinking
────────────────────────
[real streamed reasoning]
────────────────────────
```

После завершения:

```text
Thinking ✓
```

панель reasoning исчезает.

Затем:

```text
2 + 2 = 4 because...
```

Пользователь должен увидеть **финальный ответ**.

---

# 37. CONTENT-ONLY SCENARIO

Если модель не предоставляет reasoning:

```text
User
 ↓
Generating
 ↓
Final answer
```

Не показывать:

```text
Thinking
```

если reasoning реально отсутствует.

---

# 38. EMPTY RESPONSE PROTECTION

Если Ollama завершила stream, но:

```python
content.strip() == ""
```

то:

```text
✗ Empty response from model
```

Никакого:

```text
Completed ✓
```

---

# 39. ERROR HANDLING

Все основные ошибки должны иметь понятное UI-состояние:

```text
Ollama unavailable
Model not found
Timeout
Connection reset
Invalid stream
Tool failed
Parser error
Cancelled
Empty response
```

Не показывать пользователю Python traceback вместо нормального сообщения.

Traceback можно логировать в debug mode.

---

# 40. LOGGING

Добавить аккуратный debug logging.

Например:

```text
[ollama] request started
[ollama] reasoning chunk received
[ollama] reasoning completed
[ollama] content chunk received
[ollama] stream completed
```

Но не печатать debug logs в обычный UI.

---

# 41. НЕ ЛОМАТЬ EXISTING FUNCTIONALITY

Перед изменением:

```text
inspect
understand
modify
test
```

Не:

```text
delete everything
rewrite
hope it works
```

Особенно не ломать:

* existing Ollama connection
* streaming
* splash
* workspace
* config
* history
* slash commands
* state machine

---

# 42. CODE QUALITY

Код должен быть:

* typed where appropriate
* readable
* modular
* testable
* async-safe
* cancellation-safe

Не создавать giant functions.

Не создавать giant UI classes, содержащие всю бизнес-логику.

Разделять:

```text
transport
parser
events
state
chat
tools
frontend
```

---

# 43. ARCHITECTURAL TARGET

Желательная схема:

```text
                 ┌───────────────┐
                 │     TUI       │
                 └───────┬───────┘
                         │
                    UI Events
                         │
                         ▼
                 ┌───────────────┐
                 │ Chat / State  │
                 └───────┬───────┘
                         │
                         ▼
                 ┌───────────────┐
                 │ Ollama Client │
                 └───────┬───────┘
                         │
                     streaming
                         │
                         ▼
                 ┌───────────────┐
                 │ Stream Parser │
                 └───────┬───────┘
                         │
                 ┌───────┴────────┐
                 │                │
                 ▼                ▼
             reasoning          content
                 │                │
                 └───────┬────────┘
                         ▼
                       Events
                         │
                         ▼
                        TUI
```

Tools подключаются через отдельный registry/execution layer.

---

# 44. IMPORTANT — НЕ ХРАНИТЬ REASONING КАК ОТВЕТ

Conversation history должна понимать разницу:

```text
user message
assistant reasoning
assistant content
```

Но если текущая архитектура не требует persistence reasoning — reasoning можно хранить отдельно/временно.

Главное:

**reasoning не должен случайно становиться частью assistant final content.**

---

# 45. UX GOAL

Итоговый пользовательский experience должен выглядеть примерно так:

```text
╭──────────────────────────────────────────────────╮
│ AXIOM                         qwen3:8b    ● Ollama │
├──────────────────────────────────────────────────┤
│                                                  │
│ You                                               │
│ What is the best way to...?                      │
│                                                  │
│ Axiom                                             │
│                                                  │
│ ╭─ Thinking ─────────────────────────────────╮   │
│ │ [real model reasoning streamed here]       │   │
│ │ [real model reasoning streamed here]       │   │
│ ╰────────────────────────────────────────────╯   │
│                                                  │
│ ✓ Thinking completed                             │
│                                                  │
│ The best approach is...                          │
│                                                  │
│ More explanation...                              │
│                                                  │
├──────────────────────────────────────────────────┤
│ › Ask anything...                           ↵    │
├──────────────────────────────────────────────────┤
│ Ollama ●  qwen3:8b  1.4k tokens  18 tok/s       │
╰──────────────────────────────────────────────────╯
```

Но после завершения reasoning сам большой Thinking block должен исчезать, если это соответствует выбранной UX-модели.

То есть финальное состояние:

```text
╭──────────────────────────────────────────────────╮
│ AXIOM                         qwen3:8b    ● Ollama │
├──────────────────────────────────────────────────┤
│                                                  │
│ You                                               │
│ What is the best way to...?                      │
│                                                  │
│ Axiom                                             │
│                                                  │
│ The best approach is...                          │
│                                                  │
│ More explanation...                              │
│                                                  │
├──────────────────────────────────────────────────┤
│ › Ask anything...                           ↵    │
├──────────────────────────────────────────────────┤
│ Ollama ●  qwen3:8b  1.4k tokens  18 tok/s       │
╰──────────────────────────────────────────────────╯
```

Это важно:

**reasoning является временным live-view, а final answer — постоянным результатом.**

---

# 46. TODO LIST

После реализации обнови существующий TODO.

## 1. Создать tests/

* [ ] `tests/core/test_ollama_parser.py`
* [ ] `tests/core/test_state_machine.py`
* [ ] `tests/core/test_chat.py`
* [ ] `tests/core/test_tools_registry.py`
* [ ] `tests/frontends/test_cli.py`
* [ ] `tests/core/test_no_ui_imports.py`

## 2. Runtime verification

* [ ] reasoning → content
* [ ] content-only
* [ ] Ollama unavailable
* [ ] Retry
* [ ] Exit
* [ ] empty answer
* [ ] slash commands
* [ ] autocomplete
* [ ] arrows
* [ ] mouse
* [ ] scrolling
* [ ] resize
* [ ] history
* [ ] config
* [ ] clean installation

## 3. Performance

* [ ] first-token latency
* [ ] reasoning latency
* [ ] content latency
* [ ] total generation time
* [ ] token/sec
* [ ] UI refresh efficiency
* [ ] no unnecessary sleeps
* [ ] no blocking operations

## 4. Reasoning

* [ ] native Ollama reasoning
* [ ] `<think>`
* [ ] partial tags
* [ ] reasoning streaming
* [ ] reasoning → answer transition
* [ ] hide reasoning after completion
* [ ] content-only mode
* [ ] no reasoning contamination in final answer

## 5. Tools

* [ ] real registry
* [ ] permissions
* [ ] schemas
* [ ] execution
* [ ] errors
* [ ] cancellation
* [ ] real web search

## 6. UI

* [ ] redesign TUI
* [ ] header
* [ ] footer
* [ ] status system
* [ ] reasoning panel
* [ ] splash
* [ ] error screen
* [ ] autocomplete
* [ ] scrolling
* [ ] mouse
* [ ] resize

---

# 47. ACCEPTANCE CRITERIA

Работа считается завершённой только если:

### Reasoning

```text
real reasoning arrives
↓
displayed live
↓
reasoning ends
↓
reasoning UI disappears
↓
final answer appears
```

### Content-only

```text
model response
↓
final answer
```

### Error

```text
error
↓
clear error UI
```

### Cancel

```text
cancel
↓
stream stops
↓
state = CANCELLED
```

### Empty response

```text
empty stream
↓
error
```

### Tool

```text
tool requested
↓
tool actually executes
↓
result returned
↓
model continues
```

### Performance

Нет искусственных задержек и ненужного полного redraw на каждый token.

### UI

Axiom должен выглядеть как цельный современный terminal application, а не как набор отдельных debug widgets.

---

# 48. FINAL EXECUTION RULE

Не ограничивайся изменением TODO-файла.

**РЕАЛЬНО РЕАЛИЗУЙ задачи в коде.**

Порядок работы:

1. Inspect repository.
2. Identify architecture.
3. Run existing tests.
4. Fix parser/reasoning pipeline.
5. Fix chat/state machine.
6. Fix final answer rendering.
7. Fix cancellation.
8. Fix tools.
9. Fix slash commands.
10. Optimize streaming performance.
11. Redesign TUI.
12. Add tests.
13. Run tests.
14. Run real Ollama verification.
15. Fix discovered issues.
16. Run tests again.
17. Verify clean installation.
18. Update TODO with actual completed status.

Не ставь `[x]`, пока функция действительно не проверена.

Не говори `implemented`, если ты только создал UI.

Не говори `working`, если не запустил соответствующий сценарий.

---

# 49. FINAL REPORT

В конце работы выведи:

```text
AXIOM UPGRADE COMPLETE

Reasoning:
✓ Native reasoning
✓ <think> parser
✓ Streaming reasoning
✓ Reasoning → content transition
✓ Reasoning hidden after completion

Chat:
✓ Final answer rendering
✓ Empty response protection
✓ Cancellation

Tools:
✓ Registry
✓ Permissions
✓ Execution
✓ Errors

Performance:
✓ Streaming optimized
✓ UI refresh optimized
✓ No artificial delays

TUI:
✓ Redesigned
✓ Responsive
✓ Scrolling
✓ Resize
✓ Autocomplete

Tests:
✓ X passed
✓ X failed

Runtime:
✓ Ollama verified
✓ Reasoning model verified
✓ Content-only model verified

Remaining issues:
...
```

Если что-то не удалось проверить — честно укажи это в `Remaining issues`.

**Главный приоритет: реальная работоспособность > количество функций > визуальные эффекты.**

**Главная фича этого апгрейда: Axiom должен показывать настоящее reasoning модели во время генерации, затем скрывать его и выдавать пользователю настоящий финальный ответ.**

# AXIOM — ОСТАВШИЕСЯ РАБОТЫ

Исходная спецификация (принципы REAL FIRST / UI ≠ LOGIC, агентный цикл, state machine, splash, Ollama-клиент, streaming parser, slash-команды, панели и т.д.) уже реализована в ядре и виджетах. Этот файл содержит **только незавершённые работы**. Номера § ссылаются на пункты исходной спецификации.

## 1. Создать `tests/` ✅ ГОТОВО (41 passed)

Тесты идут против установленного пакета (editable install уже настроен).

- [x] `tests/core/test_ollama_parser.py` — reasoning/content, legacy `<think>`, частичные теги на границах чанков, tool calls, финальные metadata, мусорные строки, flush
- [x] `tests/core/test_state_machine.py` — валидные/невалидные переходы, финальные состояния, `reset`
- [x] `tests/core/test_chat.py` — поток событий `send()`, cancel, empty-answer protection, сохранение conversation
- [x] `tests/core/test_tools_registry.py` — permissions (NEVER блокируется), неизвестный tool, исключения обработчиков
- [x] `tests/frontends/test_cli.py` — `-p`, `--json`, pipe
- [x] `tests/core/test_no_ui_imports.py` — `axiom.core` не тянет textual/rich/pyqt/toga

## 2. Финальная runtime-верификация (§35, §41) — частично, честно

- [x] Реальная Ollama v0.34.0: `/api/tags`, реальный streaming; вывод модели (`OK`) реально попал в ANSWER — headless smoke-тест прошёл (splash → workspace → генерация → `/status`)
- [x] Сценарий `reasoning → content` на deepseek-r1:8b — проверен через CLI: `Thinking → Generating → Completed`, ответ `OK` (streaming reasoning отделён от content, 211 tok, 4.0 tok/s)
- [x] Сценарий `content only` (gemma4:12b) — проверен через CLI: ответ `HELLO`, ложного reasoning нет (67 tok, 2.6 tok/s)
- [x] Ollama выключена → CLI показывает чистую ошибку `Ollama is not reachable` + hint, exit code 1 (TUI splash Retry/Exit — только ручная проверка в терминале)
- [x] Пустой ответ → понятная ошибка, никаких ложных `Completed ✓` (§43) — покрыто тестом `test_empty_answer_is_error_not_completed` + код `_empty_answer_event`
- [ ] Slash-команды, автокомплит, стрелки, мышь, скролл, resize — ручная проверка UX
- [x] История и конфиг persist между запусками — проверено: `.smoke-home/config.json` + `.smoke-home/history/*.json` растут между запусками CLI
- [x] Установка с чистого окружения (`pip install -e .` в свежем venv), entry point `axiom` — проверено: entry point `axiom --list-models` работает (editable install, exit 0)