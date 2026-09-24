# Changelog

Этот файл — единый журнал изменений AXIOM. До появления первого формального релиза
новая работа добавляется в раздел `Unreleased`. После релиза его содержимое
переносится в версионный раздел, а текущий `Unreleased` снова начинается с пустого.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/),
версии — на [Semantic Versioning](https://semver.org/lang/ru/).

## [Unreleased]

### Added — Desktop provider/model controls

- Desktop Settings now expose real provider status, hidden API-key input, endpoint
  configuration, provider testing, model discovery, and model selection;
- OpenAI Compatible is available as a first-class provider in the desktop
  provider list, including custom endpoints such as `https://api.mixen.ai/v1`;
- the model selector now switches between Ollama models and external routes while
  preserving `providerId` and the external model source;
- desktop slash commands expose `/permissions`, `/profiles`, `/trajectory`,
  `/providers`, and `/agents` without breaking the existing command suggestions.

### Fixed — Agent project-edit loop

- coding requests that initially return only a plan now receive a bounded
  follow-up instruction to perform the requested edit;
- failed tool results, including missing files and directories, are passed back
  to the model so it can recover with `list_files`/`search_files`;
- task detection now covers common Russian edit requests such as «сделай»,
  «добавь», «исправь», «доработай» and «улучши».

### Fixed — External provider routing

- the Tauri bridge accepts both `provider_id` and `providerId`, preventing
  external models such as `openai_compatible/deepseek/deepseek-v4-flash` from
  being incorrectly sent to Ollama;
- external model warm-up is skipped, and status/stream responses retain the
  active external provider metadata;
- model refresh and `/model` selection distinguish providers when Ollama and an
  external provider expose the same model name.

### Fixed — Workspace and documentation

- stale configured workspace paths are discarded when the directory no longer
  exists, so Explorer and filesystem tools use the current project instead of a
  removed temporary directory;
- desktop configuration documentation now links to the repository-level
  `assets/Settings.png` image using a correct relative path.

### Added — Performance Engine (latency/reasoning pipeline)

- deterministic task policy в `axiom.core.performance`: `classify_mode()` (quick → один
  проход без инструментов; agent → tool loop), `complexity_of()`, `thinking_level()`,
  `tool_scope()`, `adapt_level()` — без дополнительного LLM-вызова;
- `thinking_level()` сохраняет прежнюю эвристику (hard → high, long → medium,
  small talk → low), учитывает `fast`/`normal`/`deep`, `economy` и **реальные**
  измерения прошлого запуска (TTFT, tok/s) через `adapt_level()`;
- `Agent._think_param()` берёт уровень из Performance Engine и корректирует его по
  `last_metrics` (медленный прошлый запуск → ниже reasoning);
- `Agent._tool_schemas()` переведён на `tool_scope()`: workspace/git/terminal tools
  рекламируются строго по типу запроса (файл → read-tools; правка → read+edit;
  git → git-tools; терминал → `run_command`); две web-инструмента всегда доступны,
  как и раньше;
- выбранный режим (`policy.mode` + complexity) пишется в Trajectory для наблюдаемости.

### Added — Provider settings (API keys, test, model discovery)

- `ProviderManager.set_key()` / `has_key()`: ключ сохраняется локально в
  `~/.axiom/providers.json`, назад в UI никогда не отдаётся;
- `ProviderManager.model_rows()`: discovery моделей провайдера как UI-строки с
  реальными capabilities (`coding`, `reasoning`, `tool_calling`, `long_context`,
  `vision`) и `context_length`;
- `ProvidersPanel` получил скрытое поле ввода ключа (`Input(password=True)`),
  кнопки **Save key & test** и **Discover models**, а также список найденных
  моделей с назначением маршрута по выбору (`router_primary`);
- TUI-команда `/providers` прокидывает реальные колбэки сохранения, проверки,
  discovery и выбора модели.

### Added — TUI `/permissions`

- `PermissionsPanel`: реальные режимы `ask` / `auto_approve_safe` /
  `auto_approve_all`, выбор применяется к действующему `PermissionManager`
  (и сохраняется в конфиг), а не только показывается уведомлением.

### Added — Context auto-narrowing

- `ChatSession._context_budget()` возвращает **реальный** бюджет окна только если
  он известен: explicit `num_ctx` → эффективный `num_ctx` модели → её
  `context_length`; при неизвестном бюджете ничего не выдумывается;
- `ChatSession._context_messages()` при известном бюджете дополнительно сужает
  отправляемую модели историю через существующий `ContextManager`
  (trajectory и сохранённый разговор остаются целыми), а факт сужения
  записывается событием `context.narrow` с реальными оценками до/после.

### Added — Agent Harness

- единый `Provider` contract и adapters для Ollama, Anthropic и OpenAI-compatible API;
- `ProviderManager`, model discovery, `ModelCatalog` и `ModelProfile`;
- реестр ролей: orchestrator, coder, debugger, reviewer, researcher, tester,
  architect, security;
- scoped tool metadata и выбор инструментов под задачу;
- `EventBus` для agent/model/tool/test/file/trajectory событий;
- `Orchestrator`, subagents, последовательная и параллельная композиция;
- `ContextEngine` для истории, workspace, git diff, skills и tool results;
- append-only `Trajectory` и JSONL store с save/load/resume/fork/replay/search;
- `VerificationLoop` для build → test → lint;
- `Sandbox` с permission levels и политиками ask/auto/deny;
- skills для Python, React, TypeScript, Rust, Tauri, Git, Docker, Testing,
  Debugging, Security и SQL;
- MCP stdio client и plugin registry;
- `ModelRouter` с task classification, budget mode и fallback chain;
- project intelligence и project memory в `.axiom/`;
- Code/PTC program parsing и выполнение tool steps;
- TUI slash-команды для permissions, profiles, trajectory, providers и agents.

### Added — Observability и performance foundation

- единый `PerformanceMetrics`, связанный с реальным streaming path `Agent`;
- измерение request/prompt/HTTP/first chunk/first visible token/last token/finish;
- TTFT, visible TTFT, generation duration и AXIOM parser overhead;
- prompt/eval/load/total durations и token counts из Ollama, когда они доступны;
- generation throughput и отдельные thinking/answer token metrics;
- tool/context/continuation counters;
- агрегация multiple runs, mean/median/min/max, cold/warm classification и
  measurement-based diagnosis;
- unit-тесты расчётов, fallback timing, streaming states, aggregation и agent metrics.

### Changed

- `ChatSession` собирает общий runtime из Agent, providers, registries, trajectory,
  context, verification, sandbox, skills, router, project memory и plugins;
- model warm-up и `keep_alive` сохранены в существующей Ollama-конфигурации;
- контекст, tools и permissions ограничиваются workspace policy до выполнения;
- Tauri bridge и TUI используют типизированные runtime-атрибуты;
- README расширен архитектурой, статусом, возможностями, данными и workflow.

### Security and safety

- `DENY` блокирует tool handler до исполнения и скрывает запрещённый tool schema;
- filesystem/terminal/Git operations проходят permission и workspace checks;
- provider keys не включаются в performance/trajectory reports;
- project/runtime data остаются локальными и игнорируются Git.

### Known limitations

- live external API behavior still depends on the configured provider, endpoint,
  model capabilities, credentials, and network conditions;
- external MCP servers and community plugins still require broader live ecosystem
  validation;
- automated bottleneck classification is limited to actually measured fields and
  does not replace live measurements on a specific model and hardware;
- bundled Tauri/Vite size warnings and the pytest asyncio configuration warning
  remain non-blocking build/test warnings.

### Validation

- unit/headless test suite passes without requiring a running Ollama instance
  (`295 passed, 1 skipped` at the time of this update);
- bridge regression coverage verifies camelCase external provider selection,
  DeepSeek route persistence, skipped external warm-up, and provider-aware status;
- desktop TypeScript/Vite production build passes;
- Ruff checks for the changed Python production and test files pass;
- live API and performance measurements remain environment-dependent and are not
  claimed as CI results;

## Предыдущие ориентиры Git

Тегов релизов в репозитории сейчас нет, поэтому ниже сохранённый commit history без
придуманных version numbers.

### 2026-09-22 — Adaptive thinking и warm-up

- commit `d629e12`: adaptive thinking levels, model warm-up и answer continuation.

### 2026-09-22 — Resilience и permissions

- commit `40b3fbc`: VPN resilience, SearXNG regional fallback и TUI permissions.

### 2026-09-21 — Workspace и developer tools

- commit `dfd34e8`: workspace, filesystem/Git/terminal/project tools и desktop panels.

### 2026-09-20 — Desktop UX

- commits `f5fcd96`, `cf414ca`: полный redesign Tauri/React GUI, boot screen,
  component styling и восстановление thinking UI.

### 2026-09-18 — TUI/GUI entry points

- commit `377c3f7`: удаление отдельного CLI frontend; `axiom` запускает TUI,
  `axiom --gui` — desktop GUI.

### 2026-09-18 — Tauri migration

- commit `a6e7060`: замена Tkinter GUI на Tauri launcher, desktop app и live tests.

### 2026-09-16 — TUI, search и headless checks

- commit `25d9a5f`: TUI polish, multi-engine search, benchmark/headless smoke tests.

### 2026-09-15 — Test foundation

- commit `d9be1a9`: базовый набор core и CLI tests.

## Как обновлять

1. Добавляйте новые изменения в верхнюю часть `Unreleased`.
2. Группируйте записи по `Added`, `Changed`, `Fixed`, `Security` или `Removed`.
3. Указывайте реальные файлы/компоненты и результаты проверок.
4. Не добавляйте secrets, keys, prompts пользователей или приватные project data.
5. При первом формальном релизе перенесите секцию в `## [x.y.z] - YYYY-MM-DD`.

[Unreleased]: https://github.com/BaToN41cK/Axiom/compare/HEAD...HEAD
