import { useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  FileCode2,
  FileJson,
  FileText,
  Folder,
  RefreshCw,
  X,
} from "lucide-react";
import type { TreeNode } from "../types";

interface Props {
  root: string | null;
  tree: TreeNode[];
  loading: boolean;
  /** Raw `git status --short` output of the active project (null = no repo). */
  gitStatus: string | null;
  openFile: { path: string; content: string } | null;
  onRefresh: () => void;
  onOpenFile: (path: string) => void;
  onCloseFile: () => void;
}

const CODE_EXT = new Set([
  "ts", "tsx", "js", "jsx", "py", "rs", "go", "java", "kt", "c", "h", "cpp",
  "cs", "rb", "php", "swift", "sh", "ps1", "css", "scss", "html", "vue", "sql",
]);
const TEXT_EXT = new Set(["md", "txt", "rst", "adoc", "log", "csv"]);
const DATA_EXT = new Set(["json", "jsonc", "yaml", "yml", "toml", "ini", "env", "lock"]);

/** Small, consistent file-type glyphs (lucide) — no emoji (§13). */
function fileIcon(name: string) {
  const ext = name.includes(".") ? name.split(".").pop()!.toLowerCase() : "";
  if (DATA_EXT.has(ext)) return <FileJson size={13} strokeWidth={1.8} className="ex-icon data" />;
  if (CODE_EXT.has(ext)) return <FileCode2 size={13} strokeWidth={1.8} className="ex-icon code" />;
  if (TEXT_EXT.has(ext)) return <FileText size={13} strokeWidth={1.8} className="ex-icon text" />;
  return <FileText size={13} strokeWidth={1.8} className="ex-icon" />;
}

/**
 * Parse `git status --short` into `relative path -> letter` (§5).
 * Both columns are inspected: `XY path`, where X is the index state and Y the
 * worktree state. The most visible letter for the GUI wins (M/A/D/?).
 */
function parseGitStatus(raw: string | null): Map<string, string> {
  const map = new Map<string, string>();
  if (!raw) return map;
  for (const line of raw.split("\n")) {
    if (line.length < 4 || line.startsWith("##")) continue;
    const [x, y] = [line[0], line[1]];
    const path = line.slice(3).trim().replace(/"/g, "");
    if (!path) continue;
    const code = y !== " " ? y : x;
    map.set(path.replace(/\\/g, "/"), code === "?" ? "?" : code);
  }
  return map;
}

/** File explorer of the current project (§15). Real tree from the backend. */
export default function Explorer(props: Props) {
  const { root, tree, loading, gitStatus, openFile, onRefresh, onOpenFile, onCloseFile } = props;
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const toggle = (path: string) => setCollapsed((m) => ({ ...m, [path]: !m[path] }));
  const git = useMemo(() => parseGitStatus(gitStatus), [gitStatus]);
  const renderNodes = (nodes: TreeNode[], depth: number): React.ReactNode => (
    <>
      {nodes.map((n) => {
        const rel = n.path.replace(/\\/g, "/");
        const mark = git.get(rel);
        return (
          <div key={n.path}>
            <button
              className={"ex-node" + (openFile?.path === n.path ? " active" : "")}
              style={{ paddingLeft: 6 + depth * 14 }}
              onClick={() => (n.dir ? toggle(n.path) : onOpenFile(n.path))}
              title={n.path}
            >
              <span className="ex-caret">
                {n.dir ? (
                  collapsed[n.path] ? (
                    <ChevronRight size={13} strokeWidth={2} />
                  ) : (
                    <ChevronDown size={13} strokeWidth={2} />
                  )
                ) : null}
              </span>
              {n.dir ? (
                <Folder size={13} strokeWidth={1.8} className="ex-icon folder" />
              ) : (
                fileIcon(n.name)
              )}
              <span className="ex-name">{n.name}</span>
              {mark && (
                <span className={"ex-git ex-git-" + mark.toLowerCase()} title={"git: " + mark}>
                  {mark}
                </span>
              )}
            </button>
            {n.dir && !collapsed[n.path] && n.children && renderNodes(n.children, depth + 1)}
          </div>
        );
      })}
    </>
  );
  return (
    <aside className="explorer">
      <div className="ex-head">
        <span className="ex-title">Explorer</span>
        <button className="icon-btn tiny" title="Обновить" onClick={onRefresh}>
          <RefreshCw size={12} strokeWidth={1.8} />
        </button>
      </div>
      <div className="ex-root" title={root ?? ""}>
        {root ? (root.split(/[\\/]/).pop() ?? root) : "нет активного проекта"}
      </div>
      <div className="ex-tree">
        {!root ? (
          <div className="ex-empty">Откройте проект, чтобы видеть его файлы</div>
        ) : loading ? (
          <div className="ex-empty">Читаю файлы…</div>
        ) : tree.length === 0 ? (
          <div className="ex-empty">Пустая папка</div>
        ) : (
          renderNodes(tree, 0)
        )}
      </div>
      {openFile && (
        <div className="ex-file">
          <div className="ex-file-head">
            <span className="ex-file-name">{openFile.path}</span>
            <button className="icon-btn tiny" onClick={onCloseFile} title="Закрыть">
              <X size={12} strokeWidth={1.8} />
            </button>
          </div>
          <pre className="ex-file-body">{openFile.content}</pre>
        </div>
      )}
    </aside>
  );
}
