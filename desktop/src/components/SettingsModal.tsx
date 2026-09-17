import { useEffect, useState } from "react";
import { RefreshCw, X } from "lucide-react";
import type { AxiomConfig } from "../types";

interface Props {
  config: AxiomConfig;
  onClose: () => void;
  onSave: (patch: Partial<AxiomConfig>) => void;
  onRestartCore: () => void;
}

export default function SettingsModal({ config, onClose, onSave, onRestartCore }: Props) {
  const [draft, setDraft] = useState<AxiomConfig>(config);

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
      think: draft.think,
      web_search_enabled: draft.web_search_enabled,
      search_max_sources: Number(draft.search_max_sources),
      search_read_sources: Number(draft.search_read_sources),
      show_reasoning: draft.show_reasoning,
      reasoning_expanded: draft.reasoning_expanded,
      animations: draft.animations,
      save_history: draft.save_history,
      temperature: draft.temperature === null ? null : Number(draft.temperature),
      system_prompt: draft.system_prompt,
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

        <div className="modal-body">
          <label className="field">
            <span className="field-label">Ollama URL</span>
            <input
              value={draft.ollama_url}
              onChange={(e) => set("ollama_url", e.target.value)}
              placeholder="http://127.0.0.1:11434"
              spellCheck={false}
            />
          </label>

          <label className="field">
            <span className="field-label">Thinking (Ollama think flag)</span>
            <div className="seg">
              {[
                { v: null as boolean | null, label: "Авто" },
                { v: true, label: "Вкл" },
                { v: false, label: "Выкл" },
              ].map((o) => (
                <button
                  key={o.label}
                  className={"seg-btn" + (draft.think === o.v ? " active" : "")}
                  onClick={() => set("think", o.v)}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </label>

          <div className="field-row">
            <Toggle label="Web Search" value={draft.web_search_enabled} onChange={(v) => set("web_search_enabled", v)} />
            <Toggle label="Показывать reasoning" value={draft.show_reasoning} onChange={(v) => set("show_reasoning", v)} />
            <Toggle label="Сохранять историю" value={draft.save_history} onChange={(v) => set("save_history", v)} />
            <Toggle label="Анимации" value={draft.animations} onChange={(v) => set("animations", v)} />
          </div>

          <div className="field-pair">
            <label className="field">
              <span className="field-label">Максимум источников (1–10)</span>
              <input
                type="number"
                min={1}
                max={10}
                value={draft.search_max_sources}
                onChange={(e) => set("search_max_sources", Number(e.target.value))}
              />
            </label>
            <label className="field">
              <span className="field-label">Читаемых источников (0–10)</span>
              <input
                type="number"
                min={0}
                max={10}
                value={draft.search_read_sources}
                onChange={(e) => set("search_read_sources", Number(e.target.value))}
              />
            </label>
          </div>

          <label className="field">
            <span className="field-label">Temperature (пусто = по умолчанию)</span>
            <input
              type="number"
              step="0.1"
              min={0}
              max={2}
              value={draft.temperature ?? ""}
              placeholder="—"
              onChange={(e) =>
                set("temperature", e.target.value === "" ? null : Number(e.target.value))
              }
            />
          </label>

          <label className="field">
            <span className="field-label">System prompt (пусто = по умолчанию)</span>
            <textarea
              rows={3}
              value={draft.system_prompt ?? ""}
              placeholder="—"
              onChange={(e) => set("system_prompt", e.target.value || null)}
            />
          </label>
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

function Toggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="toggle">
      <span>{label}</span>
      <span
        className={"switch" + (value ? " on" : "")}
        role="switch"
        aria-checked={value}
        onClick={() => onChange(!value)}
      >
        <span className="knob" />
      </span>
    </label>
  );
}
