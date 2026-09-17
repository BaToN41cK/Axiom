import { useState } from "react";
import { ChevronDown, FileSearch, Globe } from "lucide-react";
import type { LiveMessage, SourceItem } from "../types";

export function ToolStatus({ calls }: { calls: LiveMessage["toolCalls"] }) {
  if (calls.length === 0) return null;
  return (
    <div className="tool-status">
      {calls.map((call, i) => (
        <span key={i} className={"tool-chip " + call.state}>
          {call.name === "web_search" ? <Globe size={12} /> : <FileSearch size={12} />}
          <span>
            {call.name === "web_search" ? "Web search" : call.name}
            {call.detail ? `: ${call.detail}` : ""}
          </span>
          {call.state === "running" && <span className="spin" />}
          {call.state === "ok" && <span className="tool-ok">✓</span>}
          {call.state === "failed" && <span className="tool-failed">✗</span>}
        </span>
      ))}
    </div>
  );
}

export function SourcesRow({ sources }: { sources: SourceItem[] }) {
  const [open, setOpen] = useState(false);
  if (sources.length === 0) return null;
  return (
    <div className="sources">
      <button className="sources-toggle" onClick={() => setOpen((v) => !v)}>
        <Globe size={13} strokeWidth={1.8} />
        <span>Веб-поиск · {sources.length}</span>
        <ChevronDown size={13} strokeWidth={1.8} className={"chevron" + (open ? " open" : "")} />
      </button>
      {open && (
        <ol className="sources-list">
          {sources.map((s) => (
            <li key={s.index}>
              <a href={s.url} target="_blank" rel="noreferrer">
                <span className="source-index">{s.index}</span>
                <span className="source-title">{s.title}</span>
                <span className="source-url">{s.url}</span>
              </a>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
