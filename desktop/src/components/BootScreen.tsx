import { AlertTriangle, Check, Loader2, RefreshCw, Settings2 } from "lucide-react";
import type { BootStep, Phase } from "../hooks/useAxiom";

interface Props {
  phase: Phase;
  steps: BootStep[];
  error: { message: string; hint: string | null; url: string } | null;
  onRetry: () => void;
  onRestartCore: () => void;
  onOpenSettings: () => void;
}

/** The real boot sequence — every status is a probe that actually ran. */
export default function BootScreen({ phase, steps, error, onRetry, onRestartCore, onOpenSettings }: Props) {
  const failed = phase === "unavailable" || phase === "error";
  const done = steps.filter((step) => step.state === "ok").length;

  return (
    <div className="boot">
      <div className="boot-glow" aria-hidden />
      <div className="boot-inner">
        <div className="boot-mark">AXIOM</div>
        <div className="boot-tagline">LOCAL INTELLIGENCE</div>

        {!failed && (
          <div className="boot-steps">
            {steps.map((step) => (
              <div key={step.id} className={"boot-step " + step.state}>
                <span className="boot-step-icon">
                  {step.state === "ok" && <Check size={13} strokeWidth={2.4} />}
                  {step.state === "running" && <Loader2 size={13} className="spin" />}
                  {step.state === "pending" && <span className="boot-dot" />}
                  {step.state === "failed" && <AlertTriangle size={13} strokeWidth={2.2} />}
                </span>
                <span className="boot-step-label">{step.label}</span>
                {step.detail && <span className="boot-step-detail">{step.detail}</span>}
              </div>
            ))}
          </div>
        )}

        {failed && error && (
          <div className="boot-error">
            <div className="boot-error-title">
              <AlertTriangle size={16} strokeWidth={2} />
              <span>{error.message}</span>
            </div>
            {error.hint && <div className="boot-error-hint">{error.hint}</div>}
            {phase === "unavailable" && (
              <ul className="boot-error-causes">
                <li>Ollama не запущена — выполните <code>ollama serve</code></li>
                <li>неверный адрес API в настройках</li>
                <li>порт 11434 занят или соединение отклонено</li>
              </ul>
            )}
            <div className="boot-error-actions">
              <button className="btn primary" onClick={onRetry}>
                <RefreshCw size={14} strokeWidth={1.9} />
                <span>Повторить</span>
              </button>
              <button className="btn ghost" onClick={onRestartCore}>
                <RefreshCw size={14} strokeWidth={1.9} />
                <span>Перезапустить ядро</span>
              </button>
              <button className="btn ghost" onClick={onOpenSettings}>
                <Settings2 size={14} strokeWidth={1.9} />
                <span>Настройки</span>
              </button>
            </div>
          </div>
        )}

        {!failed && (
          <div className="boot-progress">
            <div className="boot-progress-bar">
              <span style={{ width: `${(done / Math.max(1, steps.length)) * 100}%` }} />
            </div>
            <div className="boot-progress-text">Запуск AXIOM…</div>
          </div>
        )}
      </div>
    </div>
  );
}
