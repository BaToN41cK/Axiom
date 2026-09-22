import { GitBranch, RefreshCw } from "lucide-react";
import type { ProjectInfo } from "../types";

interface GitState {
  ok: boolean;
  content: string;
  error: string | null;
}

interface Props {
  project: ProjectInfo | null;
  status: GitState | null;
  log: GitState | null;
  onRefresh: () => void;
}

/** Git panel: branch / status / log (§17). Read-only facts from the backend. */
export default function GitPanel(props: Props) {
  const { project, status, log, onRefresh } = props;
  // Global Chat: no project → no git state to show. Keep an explicit empty
  // state so the tab never looks broken/blank.
  if (!project) {
    return (
      <section className="gitpanel">
        <div className="git-empty ex-empty">Проект не открыт — Git недоступен</div>
      </section>
    );
  }
  if (!project.git) {
    return (
      <section className="gitpanel">
        <div className="git-empty ex-empty">Папка не является git-репозиторием</div>
      </section>
    );
  }
  return (
    <section className="gitpanel">
      <div className="ex-head">
        <GitBranch size={13} strokeWidth={1.8} />
        <span className="ex-title">{project.branch ?? "git"}</span>
        <span className="side-action-label" />
        <button className="icon-btn tiny" title="Обновить" onClick={onRefresh}>
          <RefreshCw size={12} strokeWidth={1.8} />
        </button>
      </div>
      <pre className="git-body">{status?.ok ? status.content || "(clean)" : status?.error ?? "…"}</pre>
      {log?.ok && log.content && <pre className="git-log">{log.content}</pre>}
    </section>
  );
}
