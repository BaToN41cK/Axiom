import { Check, ChevronDown, Globe, Loader2, TriangleAlert, X, Ban, FileText } from "lucide-react";
import { useState } from "react";
import type { SourceItem, ToolActivity } from "../types";
import { toolLabel } from "../hooks/useAxiom";

interface ToolProps {
  calls: ToolActivity[];
}

function ToolGlyph({ name }: { name: string }) {
  if (name === "web_search") return <Globe size={13} strokeWidth={1.8} />;
  if (name === "fetch_url") return <FileText size={13} strokeWidth={1.8} />;
  return <Globe size={13} strokeWidth={1.8} />;
}

/** Tool activity with real running / success / failed / cancelled states. */
export function ToolActivityList({ calls }: ToolProps) {
  if (calls.length === 0) return null;
  return (
    <div className="tool-list">
      {calls.map((call, index) => (
        <div key={`${call.name}-${index}`} className={"tool-card " + call.state}>
          <div className="tool-card-head">
            <span className="tool-icon">
              <ToolGlyph name={call.name} />
            </span>
            <span className="tool-name">{toolLabel(call.name)}</span>
            <span className="tool-state">
              {call.state === "running" && (
                <>
                  <Loader2 size={12} className="spin" /> выполняется
                </>
              )}
              {call.state === "ok" && (
                <>
                  <Check size={12} strokeWidth={2.3} /> готово
                </>
              )}
              {call.state === "failed" && (
                <>
                  <X size={12} strokeWidth={2.3} /> ошибка
                </>
              )}
              {call.state === "cancelled" && (
                <>
                  <Ban size={12} strokeWidth={2.1} /> отменено
                </>
              )}
              {call.durationMs != null && call.state !== "running" && (
                <span className="tool-duration">{call.durationMs} ms</span>
              )}
            </span>
          </div>
          {call.detail && <div className="tool-target">«{call.detail}»</div>}
          {call.state === "failed" && call.error && <div className="tool-error">{call.error}</div>}
        </div>
      ))}
    </div>
  );
}

interface SourcesProps {
  sources: SourceItem[];
  onOpen: (url: string) => void;
}

/** Real search results — every row links to the page that was actually fetched. */
export function SourcesList({ sources, onOpen }: SourcesProps) {
  const [open, setOpen] = useState(false);
  if (sources.length === 0) return null;
  return (
    <div className="sources">
      <button className="sources-toggle" onClick={() => setOpen((v) => !v)}>
        <Globe size={13} strokeWidth={1.8} />
        <span>
          Источники · {sources.length}
        </span>
        <ChevronDown size={13} strokeWidth={1.8} className={"chevron" + (open ? " open" : "")} />
      </button>
      {open && (
        <ol className="sources-list">
          {sources.map((source) => (
            <li key={`${source.index}-${source.url}`}>
              <button className="source-row" onClick={() => onOpen(source.url)} title={source.url}>
                <span className="source-index">{source.index}</span>
                <span className="source-body">
                  <span className="source-title">{source.title || source.url}</span>
                  <span className="source-url">{source.url}</span>
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export function MessageError({ message, hint }: { message: string; hint: string | null }) {
  return (
    <div className="msg-error">
      <TriangleAlert size={15} strokeWidth={1.9} />
      <div>
        <div className="msg-error-title">{message}</div>
        {hint && <div className="msg-error-hint">{hint}</div>}
      </div>
    </div>
  );
}