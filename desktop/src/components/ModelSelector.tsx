import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Cpu, Eye, Wrench } from "lucide-react";
import type { ModelInfo } from "../types";

interface Props {
  models: ModelInfo[];
  active: ModelInfo | null;
  onSelect: (name: string) => void;
}

export default function ModelSelector({ models, active, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, []);

  return (
    <div className="model-selector" ref={ref}>
      <button className="model-btn" onClick={() => setOpen((v) => !v)} title="Выбор модели">
        <Cpu size={14} strokeWidth={1.8} />
        <span>{active?.displayName ?? "Модель"}</span>
        <ChevronDown size={14} strokeWidth={1.8} className={"chevron" + (open ? " open" : "")} />
      </button>
      {open && (
        <div className="model-menu">
          {models.length === 0 && <div className="model-menu-empty">Нет доступных моделей</div>}
          {models.map((m) => (
            <button
              key={m.name}
              className={"model-item" + (m.name === active?.name ? " active" : "")}
              onClick={() => {
                onSelect(m.name);
                setOpen(false);
              }}
            >
              <div className="model-item-main">
                <span className="model-item-name">{m.displayName}</span>
                <span className="model-item-meta">
                  {m.parameterSize || m.name}
                  {m.contextLength ? ` · ctx ${Math.round(m.contextLength / 1024)}k` : ""}
                  {` · ${m.sizeGb} GB`}
                </span>
              </div>
              <div className="model-item-caps">
                {m.capabilities.includes("thinking") && (
                  <span title="Reasoning">
                    <Eye size={12} />
                  </span>
                )}
                {m.capabilities.includes("tools") && (
                  <span title="Tools / Web Search">
                    <Wrench size={12} />
                  </span>
                )}
              </div>
              {m.name === active?.name && <Check size={14} strokeWidth={2} />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
