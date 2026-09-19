import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Cpu, Eye, Loader2, RefreshCw, Sparkles, Wrench, AlertTriangle } from "lucide-react";
import type { ModelInfo } from "../types";
import { formatBytes, formatCount } from "../lib/format";

interface Props {
  models: ModelInfo[];
  active: ModelInfo | null;
  loading: boolean;
  error: string | null;
  switching: string | null;
  disabled: boolean;
  openSignal: number;
  onSelect: (name: string) => void;
  onRefresh: () => void;
}

const CAPABILITY_LABELS: { key: string; label: string; icon: typeof Eye }[] = [
  { key: "thinking", label: "Reasoning", icon: Eye },
  { key: "tools", label: "Tools", icon: Wrench },
  { key: "vision", label: "Vision", icon: Sparkles },
];

/** Describes a model in the words Ollama actually supports. */
function describe(model: ModelInfo): string {
  if (model.capabilities.includes("thinking")) return "Reasoning model";
  if (model.capabilities.includes("tools")) return "Tool-capable model";
  if (model.capabilities.includes("vision")) return "Vision model";
  if (model.capabilities.length) return "General model";
  return "Возможности неизвестны";
}

export default function ModelSelector(props: Props) {
  const { models, active, loading, error, switching, disabled, openSignal, onSelect, onRefresh } = props;
  const [open, setOpen] = useState(false);
  const [cursor, setCursor] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!openSignal) return;
    setOpen(true);
    onRefresh();
  }, [openSignal, onRefresh]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [open]);

  const items = useMemo(() => models, [models]);

  useEffect(() => {
    if (!open) return;
    const index = items.findIndex((m) => m.name === active?.name);
    setCursor(index >= 0 ? index : 0);
  }, [open, items, active?.name]);

  const choose = (name: string) => {
    onSelect(name);
    setOpen(false);
  };

  const busy = switching != null;

  /** Keyboard navigation of both the toggle and the open list. */
  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
      return;
    }
    if (!open) {
      if (event.key === "ArrowDown" || event.key === "Enter") {
        event.preventDefault();
        setOpen(true);
        onRefresh();
      }
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setCursor((c) => Math.min(items.length - 1, c + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor((c) => Math.max(0, c - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const target = items[cursor];
      if (target) choose(target.name);
    }
  };

  return (
    <div className="model-selector" ref={boxRef} onKeyDown={onKeyDown}>
      <button
        className={"model-btn" + (open ? " open" : "") + (disabled ? " disabled" : "")}
        onClick={() => {
          setOpen((v) => !v);
          if (!open) onRefresh();
        }}
        title={active ? `${active.name} — сменить модель` : "Выбрать модель"}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        {busy ? <Loader2 size={14} className="spin" /> : <Cpu size={14} strokeWidth={1.8} />}
        <span className="model-btn-label">{active?.displayName ?? "Модель не выбрана"}</span>
        {active && (
          <span className="model-btn-caps">
            {CAPABILITY_LABELS.filter((c) => active.capabilities.includes(c.key)).map((c) => (
              <c.icon key={c.key} size={12} strokeWidth={1.8} />
            ))}
          </span>
        )}
        <ChevronDown size={14} strokeWidth={1.8} className={"chevron" + (open ? " open" : "")} />
      </button>

      {open && (
        <div className="model-menu" role="listbox">
          <div className="model-menu-head">
            <span>MODEL</span>
            <button className="icon-btn tiny" onClick={onRefresh} disabled={loading} title="Обновить список из Ollama">
              {loading ? <Loader2 size={13} className="spin" /> : <RefreshCw size={13} strokeWidth={1.8} />}
            </button>
          </div>

          {error && (
            <div className="model-menu-error">
              <AlertTriangle size={13} strokeWidth={1.9} />
              <span>{error}</span>
            </div>
          )}

          <div className="model-menu-list">
            {!loading && items.length === 0 && !error && (
              <div className="model-menu-empty">
                Модели не найдены. Установите: <code>ollama pull qwen3:8b</code>
              </div>
            )}
            {items.map((model, index) => {
              const isActive = model.name === active?.name;
              const isSwitching = switching === model.name;
              return (
                <button
                  key={model.name}
                  role="option"
                  aria-selected={isActive}
                  className={"model-item" + (isActive ? " active" : "") + (index === cursor ? " cursor" : "")}
                  onMouseEnter={() => setCursor(index)}
                  onClick={() => choose(model.name)}
                >
                  <span className={"model-radio" + (isActive ? " on" : "")}>
                    {isSwitching ? (
                      <Loader2 size={11} className="spin" />
                    ) : isActive ? (
                      <Check size={11} strokeWidth={3} />
                    ) : null}
                  </span>
                  <span className="model-item-body">
                    <span className="model-item-title">
                      <span className="model-item-name">{model.displayName}</span>
                      <span className="model-item-state">
                        <span className={"dot" + (model.loaded ? " on" : "")} />
                        {model.loaded ? "Local • Ready" : "Local"}
                      </span>
                    </span>
                    <span className="model-item-sub">{describe(model)}</span>
                    <span className="model-item-meta">
                      {model.name}
                      {model.parameterSize ? ` · ${model.parameterSize}` : ""}
                      {model.quantization ? ` · ${model.quantization}` : ""}
                      {model.contextLength ? ` · ctx ${formatCount(model.contextLength)}` : ""}
                      {model.sizeBytes ? ` · ${formatBytes(model.sizeBytes)}` : ""}
                    </span>
                  </span>
                  <span className="model-item-caps">
                    {CAPABILITY_LABELS.map(({ key, icon: Icon, label }) => (
                      <span
                        key={key}
                        className={"cap" + (model.capabilities.includes(key) ? " on" : "")}
                        title={
                          model.capabilities.includes(key) ? label : `${label}: Ollama не сообщает поддержку`
                        }
                      >
                        <Icon size={12} strokeWidth={1.8} />
                      </span>
                    ))}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="model-menu-foot">
            Данные: Ollama <code>/api/tags</code> · <code>/api/ps</code>
          </div>
        </div>
      )}
    </div>
  );
}