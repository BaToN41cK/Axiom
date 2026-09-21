import { useEffect } from "react";

interface Props {
  pending: { name: string; detail: string } | null;
  onDecision: (allow: boolean) => void;
}

/** Dangerous-operation confirmation (§11): nothing executes before Allow. */
export default function ConfirmDialog(props: Props) {
  const { pending, onDecision } = props;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onDecision(false);
    };
    if (pending) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pending, onDecision]);
  if (!pending) return null;
  return (
    <div className="modal-backdrop" onClick={() => onDecision(false)}>
      <div className="modal confirm" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>⚠ {pending.name}</h2>
        </div>
        <div className="modal-body">
          <code className="confirm-detail">{pending.detail}</code>
          <p className="about-text">Опасная операция. Подтвердите выполнение — действие реально изменит файлы или систему.</p>
        </div>
        <div className="modal-foot">
          <button className="btn ghost" onClick={() => onDecision(false)}>Отмена</button>
          <div className="modal-foot-spacer" />
          <button className="btn danger" onClick={() => onDecision(true)}>Разрешить</button>
        </div>
      </div>
    </div>
  );
}
