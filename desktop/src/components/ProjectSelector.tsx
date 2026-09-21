import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, FolderOpen, Globe, MessageSquare, Pin, X } from "lucide-react";
import type { ProjectInfo } from "../types";

interface Props {
  current: ProjectInfo | null;
  recent: ProjectInfo[];
  pinned: ProjectInfo[];
  onOpen: () => void;
  onSwitch: (path: string) => void;
  onClear: () => void;
  onRemove: (path: string) => void;
  onTogglePin: (path: string) => void;
}

/**
 * Project/workspace selector in the top bar (§3).
 * Reuses the existing backend (set_workspace / clear_workspace / pin) —
 * the "Global Chat" entry is the real `clear_workspace` bridge command.
 */
export default function ProjectSelector(props: Props) {
  const { current, recent, pinned, onOpen, onSwitch, onClear, onRemove, onTogglePin } = props;
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, []);
  const others = recent.filter((r) => r.path !== current?.path);
  const currentPinned = pinned.some((p) => p.path === current?.path);
  return (
    <div className="ws-selector" ref={ref}>
      <button
        className={"ws-current" + (current ? "" : " none")}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={current?.path ?? "Глобальный чат — проект не открыт"}
      >
        {current ? (
          <FolderOpen size={14} strokeWidth={1.8} />
        ) : (
          <Globe size={14} strokeWidth={1.8} />
        )}
        <span className="ws-name">{current?.name ?? "Global Chat"}</span>
        {current && <span className="ws-kind">{current.kind}</span>}
        <ChevronDown size={13} strokeWidth={1.8} className={"chevron" + (open ? " open" : "")} />
      </button>
      {open && (
        <div className="ws-menu" role="listbox">
          <div className="ws-menu-title">Проекты</div>
          {current && (
            <div className="ws-item active">
              <span className="ws-dot">{currentPinned ? "◆" : "●"}</span>
              <span className="ws-item-text">
                <span className="ws-item-name">{current.name}</span>
                <span className="ws-item-path">{current.path}</span>
              </span>
              <button
                className="icon-btn tiny"
                title={currentPinned ? "Открепить проект" : "Прикрепить проект"}
                onClick={() => void onTogglePin(current.path)}
              >
                <Pin size={12} strokeWidth={1.8} fill={currentPinned ? "currentColor" : "none"} />
              </button>
            </div>
          )}
          {pinned.filter((p) => p.path !== current?.path).length > 0 && (
            <div className="ws-subtitle">Прикрепленные</div>
          )}
          {pinned
            .filter((p) => p.path !== current?.path)
            .map((p) => (
              <div key={p.path} className="ws-item">
                <button
                  className="ws-item-main"
                  onClick={() => {
                    setOpen(false);
                    void onSwitch(p.path);
                  }}
                >
                  <span className="ws-dot">◆</span>
                  <span className="ws-item-text">
                    <span className="ws-item-name">{p.name}</span>
                    <span className="ws-item-path">{p.path}</span>
                  </span>
                </button>
                <button className="icon-btn tiny" title="Открепить проект" onClick={() => void onTogglePin(p.path)}>
                  <Pin size={12} strokeWidth={1.8} fill="currentColor" />
                </button>
              </div>
            ))}
          {others.length > 0 && <div className="ws-subtitle">Недавние</div>}
          {others.map((p) => (
            <div key={p.path} className="ws-item">
              <button
                className="ws-item-main"
                onClick={() => {
                  setOpen(false);
                  void onSwitch(p.path);
                }}
              >
                <span className="ws-dot">○</span>
                <span className="ws-item-text">
                  <span className="ws-item-name">{p.name}</span>
                  <span className="ws-item-path">{p.path}</span>
                </span>
              </button>
              <button className="icon-btn tiny" title="Убрать из списка" onClick={() => void onRemove(p.path)}>
                <X size={12} strokeWidth={1.8} />
              </button>
            </div>
          ))}
          <div className="ws-menu-sep" />
          {!current && (
            <div className="ws-item active">
              <button className="ws-item-main" disabled>
                <Check size={14} strokeWidth={2} className="ws-check" />
                <span className="ws-item-text">
                  <span className="ws-item-name">Global Chat</span>
                  <span className="ws-item-path">Без папки проекта</span>
                </span>
              </button>
            </div>
          )}
          {current && (
            <button
              className="ws-global"
              onClick={() => {
                setOpen(false);
                void onClear();
              }}
              title="Общаться без проекта: файловые инструменты отключены"
            >
              <MessageSquare size={14} strokeWidth={1.8} /> Global Chat
            </button>
          )}
          <button className="ws-open" onClick={() => { setOpen(false); void onOpen(); }}>
            <FolderOpen size={14} strokeWidth={1.8} /> Открыть проект…
          </button>
        </div>
      )}
    </div>
  );
}
