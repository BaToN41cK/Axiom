import { useState, useEffect } from "react";
import {
  Globe,
  Info,
  Keyboard,
  MessageSquare,
  RefreshCw,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  Wrench,
  X,
} from "lucide-react";
import type { ReactNode } from "react";
import type { AxiomConfig, ProviderModelRow, ProviderRow } from "../types";
import type { SettingsSection } from "../hooks/useAxiom";

interface Props {
  config: AxiomConfig;
  section: SettingsSection;
  setSection: (section: SettingsSection) => void;
  onClose: () => void;
  onSave: (patch: Partial<AxiomConfig>) => void;
  onRestartCore: () => void;
  providerRows: ProviderRow[];
  providerModels: ProviderModelRow[];
  providerLoading: boolean;
  onProviderTest: (id: string) => Promise<void>;
  onProviderSaveKey: (id: string, key: string) => Promise<void>;
  onProviderSetBaseUrl: (id: string, baseUrl: string) => Promise<void>;
  onProviderDiscover: (id: string) => Promise<void>;
  onProviderPickModel: (providerId: string, model: string) => Promise<void>;
}

const SECTIONS: { key: SettingsSection; label: string; icon: ReactNode }[] = [
  { key: "general", label: "Общие", icon: <Settings2 size={14} strokeWidth={1.8} /> },
  { key: "appearance", label: "Вид", icon: <Sparkles size={14} strokeWidth={1.8} /> },
  { key: "models", label: "Модели", icon: <SlidersHorizontal size={14} strokeWidth={1.8} /> },
  { key: "providers", label: "Провайдеры", icon: <Globe size={14} strokeWidth={1.8} /> },
  { key: "chat", label: "Чат", icon: <MessageSquare size={14} strokeWidth={1.8} /> },
  { key: "tools", label: "Инструменты", icon: <Wrench size={14} strokeWidth={1.8} /> },
  { key: "shortcuts", label: "Горячие клавиши", icon: <Keyboard size={14} strokeWidth={1.8} /> },
  { key: "about", label: "О программе", icon: <Info size={14} strokeWidth={1.8} /> },
];

const SHORTCUTS: { keys: [string, string] | string; label: string }[] = [
  { keys: "Ctrl+N", label: "Новый разговор" },
  { keys: "Ctrl+B", label: "Показать/скрыть боковую панель" },
  { keys: "Ctrl+K", label: "Поиск по разговорам" },
  { keys: "Ctrl+,", label: "Настройки" },
  { keys: "Ctrl+/", label: "Фокус в поле ввода" },
  { keys: "Enter", label: "Отправить сообщение" },
  { keys: "Shift+Enter", label: "Перенос строки" },
  { keys: "Ctrl+Enter", label: "Отправить с веб-поиском" },
  { keys: "Esc", label: "Остановить генерацию / закрыть окно" },
  { keys: "Ctrl+V", label: "Вставить изображение (vision-модели)" },
];

export default function SettingsModal({
  config,
  section,
  setSection,
  onClose,
  onSave,
  onRestartCore,
  providerRows,
  providerModels,
  providerLoading,
  onProviderTest,
  onProviderSaveKey,
  onProviderSetBaseUrl,
  onProviderDiscover,
  onProviderPickModel,
}: Props) {
  const [draft, setDraft] = useState<AxiomConfig>(config);

  useEffect(() => {
    setDraft(config);
  }, [config]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const set = <K extends keyof AxiomConfig>(key: K, value: AxiomConfig[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));

  const save = () => {
    const patch: Partial<AxiomConfig> = {
      ollama_url: draft.ollama_url,
      model: draft.model,
      web_search_enabled: draft.web_search_enabled,
      workspace_tools_enabled: draft.workspace_tools_enabled,
      workspace_root: draft.workspace_root,
      access_mode: draft.access_mode,
      terminal_enabled: draft.terminal_enabled,
      search_max_sources: Number(draft.search_max_sources),
      search_read_sources: Number(draft.search_read_sources),
      search_timeout: Number(draft.search_timeout),
      history_limit: Number(draft.history_limit),
      show_reasoning: draft.show_reasoning,
      reasoning_expanded: draft.reasoning_expanded,
      theme: draft.theme,
      animations: draft.animations,
      save_history: draft.save_history,
      temperature: draft.temperature === null ? null : Number(draft.temperature),
      system_prompt: draft.system_prompt,
      think: draft.think,
      thinking_mode: draft.thinking_mode,
      keep_alive: draft.keep_alive,
      warmup_model: draft.warmup_model,
      num_ctx: draft.num_ctx === null ? null : Number(draft.num_ctx),
      num_predict: draft.num_predict === null ? null : Number(draft.num_predict),
      context_messages: Number(draft.context_messages),
      density: draft.density,
      font_size: Number(draft.font_size),
      sidebar_open: draft.sidebar_open,
      sidebar_width: Number(draft.sidebar_width),
      render_markdown: draft.render_markdown,
      auto_scroll: draft.auto_scroll,
      show_metrics: draft.show_metrics,
      show_context: draft.show_context,
      permission_mode: draft.permission_mode,
      router_enabled: draft.router_enabled,
    };
    onSave(patch);
    onClose();
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Настройки</h2>
          <button className="icon-btn" onClick={onClose}>
            <X size={16} strokeWidth={1.8} />
          </button>
        </div>

        <div className="modal-body settings-layout">
          <nav className="settings-nav">
            {SECTIONS.map((s) => (
              <button
                key={s.key}
                className={"settings-nav-item" + (section === s.key ? " active" : "")}
                onClick={() => setSection(s.key)}
              >
                <span className="settings-nav-icon">{s.icon}</span>
                {s.label}
              </button>
            ))}
          </nav>

          <div className="settings-content">
            {section === "general" && <GeneralSection draft={draft} set={set} />}
            {section === "models" && <ModelsSection draft={draft} set={set} config={config} onRestartCore={onRestartCore} />}
            {section === "providers" && <ProvidersSection rows={providerRows} models={providerModels} loading={providerLoading} onTest={onProviderTest} onSaveKey={onProviderSaveKey} onSetBaseUrl={onProviderSetBaseUrl} onDiscover={onProviderDiscover} onPickModel={onProviderPickModel} />}
            {section === "chat" && <ChatSection draft={draft} set={set} />}
            {section === "tools" && <ToolsSection draft={draft} set={set} />}
            {section === "appearance" && <AppearanceSection draft={draft} set={set} />}
            {section === "shortcuts" && <ShortcutsSection />}
            {section === "about" && <AboutSection />}
          </div>
        </div>

        <div className="modal-foot">
          <button className="btn ghost" onClick={onRestartCore}>
            <RefreshCw size={14} strokeWidth={1.8} />
            <span>Перезапустить ядро</span>
          </button>
          <div className="modal-foot-spacer" />
          <button className="btn ghost" onClick={onClose}>
            Отмена
          </button>
          <button className="btn primary" onClick={save}>
            Сохранить
          </button>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ sections

interface SectionProps {
  draft: AxiomConfig;
  set: <K extends keyof AxiomConfig>(key: K, value: AxiomConfig[K]) => void;
}
function ProvidersSection({ rows, models, loading, onTest, onSaveKey, onSetBaseUrl, onDiscover, onPickModel }: {
  rows: ProviderRow[]; models: ProviderModelRow[]; loading: boolean;
  onTest: (id: string) => Promise<void>; onSaveKey: (id: string, key: string) => Promise<void>;
  onSetBaseUrl: (id: string, baseUrl: string) => Promise<void>;
  onDiscover: (id: string) => Promise<void>; onPickModel: (providerId: string, model: string) => Promise<void>;
}) {
  const [selected, setSelected] = useState(rows[0]?.id ?? "openai");
  const [key, setKey] = useState("");
  const row = rows.find((item) => item.id === selected) ?? rows[0];
  const providerModels = models.filter((item) => item.provider_id === selected);
  return <div className="provider-settings">
    <Row label="Provider" hint="Статус и endpoint берутся из реального ProviderManager">
      <select value={selected} onChange={(e) => { setSelected(e.target.value); setKey(""); }}>
        {rows.map((item) => <option key={item.id} value={item.id}>{item.label} · {item.status}</option>)}
      </select>
    </Row>
    <Row label="API key" hint="Ключ сохраняется локально и никогда не возвращается в GUI">
      <input type="password" value={key} placeholder={row?.configured ? "•••••••• (сохранён)" : "не задан"} onChange={(e) => setKey(e.target.value)} />
    </Row>
    <Row label="Base URL" hint="Для OpenAI Compatible укажите endpoint с /v1, например http://localhost:8000/v1">
      <div className="provider-endpoint"><input value={row?.base_url || ""} placeholder="https://api.example.com/v1" onChange={(e) => { const value = e.target.value; if (row) { row.base_url = value; } }} /><button className="btn ghost" onClick={() => void onSetBaseUrl(selected, row?.base_url || "")}>Сохранить URL</button></div>
    </Row>
    <div className="settings-actions">
      <button className="btn ghost" disabled={!row || loading} onClick={() => void onSaveKey(selected, key)}>Сохранить ключ</button>
      <button className="btn ghost" disabled={!row || loading} onClick={() => void onTest(selected)}>Test</button>
      <button className="btn ghost" disabled={!row || loading} onClick={() => void onDiscover(selected)}>Discover models</button>
    </div>
    <Row label="Модель маршрута" hint="Выбранная модель будет реально использоваться следующим запросом">
      <select value="" onChange={(e) => { if (e.target.value) void onPickModel(selected, e.target.value); }}>
        <option value="">Выберите модель…</option>
        {providerModels.map((item) => <option key={item.id} value={item.model}>{item.label} · {item.capabilities.join(", ")}</option>)}
      </select>
    </Row>
  </div>;
}



function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="settings-row">
      <div className="settings-row-text">
        <div className="settings-row-label">{label}</div>
        {hint && <div className="settings-row-hint">{hint}</div>}
      </div>
      <div className="settings-row-control">{children}</div>
    </div>
  );
}

function Toggle({ value, onChange }: { value: boolean | null; onChange: (v: boolean) => void }) {
  return (
    <button
      className={"switch" + (value ? " on" : "")}
      role="switch"
      aria-checked={!!value}
      onClick={() => onChange(!value)}
    >
      <span className="switch-knob" />
    </button>
  );
}

function GeneralSection({ draft, set }: SectionProps) {
  return (
    <>
      <Row label="Сохранять историю" hint="Разговоры хранятся локально в ~/.axiom">
        <Toggle value={draft.save_history} onChange={(v) => set("save_history", v)} />
      </Row>
      <Row label="Лимит истории" hint="Сколько последних разговоров хранить">
        <input
          type="number"
          min={0}
          max={500}
          value={draft.history_limit}
          onChange={(e) => set("history_limit", Number(e.target.value))}
        />
      </Row>
      <Row label="Temperature" hint="Пусто — значение модели по умолчанию">
        <input
          type="number"
          step={0.1}
          min={0}
          max={2}
          value={draft.temperature ?? ""}
          placeholder="auto"
          onChange={(e) => set("temperature", e.target.value === "" ? null : Number(e.target.value))}
        />
      </Row>
      <Row label="Системный промпт" hint="Пусто — встроенный промпт AXIOM">
        <textarea
          rows={3}
          value={draft.system_prompt ?? ""}
          placeholder="по умолчанию"
          onChange={(e) => set("system_prompt", e.target.value || null)}
        />
      </Row>
    </>
  );
}

function ModelsSection({ draft, set, config, onRestartCore }: SectionProps & { config: AxiomConfig; onRestartCore: () => void }) {
  return (
    <>
      <Row label="Ollama URL" hint={`Текущее соединение: ${config.ollama_url}`}>
        <input
          value={draft.ollama_url}
          spellCheck={false}
          onChange={(e) => set("ollama_url", e.target.value)}
        />
      </Row>
      <Row label="Think-режим" hint="Уровень рассуждений: авто — решает ядро по запросу">
        <select
          value={
            draft.think === null || draft.think === false
              ? "auto"
              : draft.think === true
                ? "on"
                : draft.think
          }
          onChange={(e) => {
            const v = e.target.value;
            set(
              "think",
              v === "auto" ? null : v === "on" ? true : (v as "low" | "medium" | "high" | "max"),
            );
          }}
        >
          <option value="auto">Авто</option>
          <option value="on">Всегда</option>
          <option value="low">Низкий</option>
          <option value="medium">Средний</option>
          <option value="high">Высокий</option>
          <option value="max">Максимум</option>
        </select>
      </Row>
      <Row label="Режим мышления" hint="Пресет глубины reasoning, когда Think = Авто">
        <select
          value={draft.thinking_mode}
          onChange={(e) =>
            set("thinking_mode", e.target.value as AxiomConfig["thinking_mode"])
          }
        >
          <option value="auto">Авто (по запросу)</option>
          <option value="fast">Быстрый</option>
          <option value="normal">Обычный</option>
          <option value="deep">Глубокий</option>
        </select>
      </Row>
      <Row label="Прогрев модели" hint="Загрузить модель в память сразу после старта">
        <Toggle value={draft.warmup_model} onChange={(v) => set("warmup_model", v)} />
      </Row>
      <Row label="Держать модель в памяти" hint='Ollama keep_alive, например "30m" или "1h"'>
        <input
          value={draft.keep_alive}
          spellCheck={false}
          onChange={(e) => set("keep_alive", e.target.value)}
        />
      </Row>
      <Row label="Контекстное окно" hint="Пусто — по умолчанию модели (num_ctx)">
        <input
          type="number"
          min={512}
          max={131072}
          step={512}
          value={draft.num_ctx ?? ""}
          placeholder="auto"
          onChange={(e) => set("num_ctx", e.target.value === "" ? null : Number(e.target.value))}
        />
      </Row>
      <Row label="Максимум ответа" hint="Лимит токенов генерации (num_predict), пусто — авто">
        <input
          type="number"
          min={16}
          max={131072}
          value={draft.num_predict ?? ""}
          placeholder="auto"
          onChange={(e) =>
            set("num_predict", e.target.value === "" ? null : Number(e.target.value))
          }
        />
      </Row>
      <Row label="Ядро AXIOM" hint="Перезапуск Python-ядра и повторная проверка Ollama">
        <button className="btn ghost" onClick={onRestartCore}>
          Перезапустить
        </button>
      </Row>
    </>
  );
}

function ChatSection({ draft, set }: SectionProps) {
  return (
    <>
      <Row label="Markdown" hint="Рендеринг ответов в Markdown с подсветкой кода">
        <Toggle value={draft.render_markdown} onChange={(v) => set("render_markdown", v)} />
      </Row>
      <Row label="Показывать reasoning" hint="Отображать thinking-блоки модели, когда они есть">
        <Toggle value={draft.show_reasoning} onChange={(v) => set("show_reasoning", v)} />
      </Row>
      <Row label="Раскрывать reasoning" hint="Thinking-блоки развёрнуты по умолчанию">
        <Toggle value={draft.reasoning_expanded} onChange={(v) => set("reasoning_expanded", v)} />
      </Row>
      <Row label="Автоскролл" hint="Следить за потоком генерации">
        <Toggle value={draft.auto_scroll} onChange={(v) => set("auto_scroll", v)} />
      </Row>
      <Row label="Метрики ответа" hint="Время, токены, скорость после генерации">
        <Toggle value={draft.show_metrics} onChange={(v) => set("show_metrics", v)} />
      </Row>
      <Row label="Индикатор контекста" hint="Заполнение контекстного окна модели">
        <Toggle value={draft.show_context} onChange={(v) => set("show_context", v)} />
      </Row>
      <Row label="Сообщений в контексте" hint="Сколько последних сообщений отправлять модели">
        <input
          type="number"
          min={4}
          max={200}
          value={draft.context_messages}
          onChange={(e) => set("context_messages", Number(e.target.value))}
        />
      </Row>
    </>
  );
}

function ToolsSection({ draft, set }: SectionProps) {
  return (
    <>
      <Row label="Веб-поиск" hint="Инструмент поиска в интернете (требует сеть, остальное — локально)">
        <Toggle value={draft.web_search_enabled} onChange={(v) => set("web_search_enabled", v)} />
      </Row>
      <Row
        label="Файлы проекта"
        hint="Разрешить модели читать и редактировать файлы этой папки: list_files, read_file, write_file, edit_file"
      >
        <Toggle
          value={draft.workspace_tools_enabled}
          onChange={(v) => set("workspace_tools_enabled", v)}
        />
      </Row>
      <Row label="Режим разрешений" hint="ask · auto_approve_safe · auto_approve_all">
        <select value={draft.permission_mode} onChange={(e) => set("permission_mode", e.target.value as AxiomConfig["permission_mode"])}>
          <option value="ask">Спрашивать каждый раз</option>
          <option value="auto_approve_safe">Автоматически: безопасные действия</option>
          <option value="auto_approve_all">Автоматически: все действия</option>
        </select>
      </Row>
      <Row label="Доступ AI" hint="read_only — только чтение · workspace — внутри проекта · full — весь ПК (осторожно)">
        <select value={draft.access_mode} onChange={(e) => set("access_mode", e.target.value as AxiomConfig["access_mode"])}>
          <option value="read_only">Только чтение</option>
          <option value="workspace">Проект (workspace)</option>
          <option value="full">Полный доступ</option>
        </select>
      </Row>
      <Row label="Терминал AI" hint="Разрешить модели выполнять команды в папке проекта">
        <Toggle value={draft.terminal_enabled} onChange={(v) => set("terminal_enabled", v)} />
      </Row>
      <Row label="Источников на запрос" hint="Сколько результатов возвращает поиск">
        <input
          type="number"
          min={1}
          max={20}
          value={draft.search_max_sources}
          onChange={(e) => set("search_max_sources", Number(e.target.value))}
        />
      </Row>
      <Row label="Читать источники" hint="Сколько страниц загружать целиком для ответа">
        <input
          type="number"
          min={0}
          max={10}
          value={draft.search_read_sources}
          onChange={(e) => set("search_read_sources", Number(e.target.value))}
        />
      </Row>
      <Row label="Таймаут поиска, с" hint="Лимит ожидания поисковых провайдеров">
        <input
          type="number"
          min={1}
          max={120}
          value={draft.search_timeout}
          onChange={(e) => set("search_timeout", Number(e.target.value))}
        />
      </Row>
    </>
  );
}

const DENSITY_LABELS: Record<AxiomConfig["density"], string> = {
  compact: "Плотно",
  comfortable: "Обычно",
  spacious: "Просторно",
};

function AppearanceSection({ draft, set }: SectionProps) {
  return (
    <>
      <Row label="Тема">
        <select value={draft.theme} onChange={(e) => set("theme", e.target.value)}>
          <option value="obsidian">Obsidian (тёмная)</option>
          <option value="light">Светлая</option>
        </select>
      </Row>
      <Row label="Анимации" hint="Плавные переходы интерфейса">
        <Toggle value={draft.animations} onChange={(v) => set("animations", v)} />
      </Row>
      <Row label="Плотность" hint="Отступы сообщений и списков">
        <select
          value={draft.density}
          onChange={(e) => set("density", e.target.value as AxiomConfig["density"])}
        >
          {(Object.keys(DENSITY_LABELS) as AxiomConfig["density"][]).map((d) => (
            <option key={d} value={d}>
              {DENSITY_LABELS[d]}
            </option>
          ))}
        </select>
      </Row>
      <Row label="Размер шрифта, px">
        <input
          type="number"
          min={11}
          max={20}
          value={draft.font_size}
          onChange={(e) => set("font_size", Number(e.target.value))}
        />
      </Row>
      <Row label="Боковая панель открыта">
        <Toggle value={draft.sidebar_open} onChange={(v) => set("sidebar_open", v)} />
      </Row>
      <Row label="Ширина панели, px">
        <input
          type="number"
          min={200}
          max={480}
          value={draft.sidebar_width}
          onChange={(e) => set("sidebar_width", Number(e.target.value))}
        />
      </Row>
    </>
  );
}

function AboutSection() {
  return (
    <div className="settings-about">
      <div className="about-brand">AXIOM</div>
      <div className="about-sub">LOCAL INTELLIGENCE</div>
      <p className="about-text">
        Локальная AI-workspace поверх Ollama: стриминг, reasoning, инструменты, веб-поиск
        и история разговоров — всё выполняется на вашей машине. Без API-ключей,
        облаков и обязательного интернета.
      </p>
    </div>
  );
}

function ShortcutsSection() {
  return (
    <div className="shortcuts-list">
      {SHORTCUTS.map((item) => (
        <div className="settings-row" key={item.label}>
          <div className="settings-row-text">
            <div className="settings-row-label">{item.label}</div>
          </div>
          <div className="settings-row-control">
            <span className="shortcut-keys">
              <kbd>{item.keys}</kbd>
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

