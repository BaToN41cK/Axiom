import { useState } from "react";
import { RefreshCw, X } from "lucide-react";
import type { TreeNode } from "../types";

interface Props {
  root: string | null;
  tree: TreeNode[];
  loading: boolean;
  openFile: { path: string; content: string } | null;
  onRefresh: () => void;
  onOpenFile: (path: string) => void;
  onCloseFile: () => void;
}

/** File explorer of the current project (§15). Real tree from the backend. */
export default function Explorer(props: Props) {
  const { root, tree, loading, openFile, onRefresh, onOpenFile, onCloseFile } = props;
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const toggle = (path: string) => setCollapsed((m) => ({ ...m, [path]: !m[path] }));
  const renderNodes = (nodes: TreeNode[], depth: number): React.ReactNode => (
    <>
      {nodes.map((n) => (
        <div key={n.path}>
          <button
            className={"ex-node" + (openFile?.path === n.path ? " active" : "")}
            style={{ paddingLeft: 8 + depth * 14 }}
            onClick={() => (n.dir ? toggle(n.path) : onOpenFile(n.path))}
            title={n.path}
          >
            <span className="ex-glyph">{n.dir ? (collapsed[n.path] ? "▸" : "▾") : "·"}</span>
            <span className="ex-name">{n.name}</span>
            {n.dir && <span className="ex-dir">/</span>}
          </button>
          {n.dir && !collapsed[n.path] && n.children && renderNodes(n.children, depth + 1)}
        </div>
      ))}
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
