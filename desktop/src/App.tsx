import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { Moon, PanelRightClose, PanelRightOpen, Sun } from "lucide-react";
import BootScreen from "./components/BootScreen";
import ProjectSelector from "./components/ProjectSelector";
import OverlayPanel from "./components/OverlayPanel";
import SettingsModal from "./components/SettingsModal";
import Sidebar from "./components/Sidebar";
import MessageList from "./components/MessageList";
import Composer from "./components/Composer";
import ModelSelector from "./components/ModelSelector";
import { useAxiom } from "./hooks/useAxiom";

import Explorer from "./components/Explorer";
import GitPanel from "./components/GitPanel";
import TerminalPanel from "./components/TerminalPanel";
import type { AxiomStore } from "./hooks/useAxiom";

function WorkbenchSide({ store: s }: { store: AxiomStore }) {
  const [tab, setTab] = useState<"files" | "terminal" | "git">("files");
  // Drag-to-resize of the tools panel (§8). Width lives in the store and is
  // persisted; the CSS transition is switched off while dragging (body.resizing).
  const dragging = useRef(false);
  const lastWidth = useRef(s.rightPanelWidth);
  useEffect(() => {
    const onMove = (event: MouseEvent) => {
      if (!dragging.current) return;
      const next = Math.min(680, Math.max(240, window.innerWidth - event.clientX));
      lastWidth.current = next;
      s.setRightPanelWidth(next);
    };
    const onUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.classList.remove("resizing");
      s.commitRightPanelWidth(lastWidth.current);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [s]);
  const startDrag = () => {
    dragging.current = true;
    document.body.classList.add("resizing");
  };
  return (
    <aside
      className="workbench-side"
      style={{ "--side-w": `${s.rightPanelWidth}px` } as CSSProperties}
    >
      <div className="side-resizer" onMouseDown={startDrag} title="Изменить размер панели" />
      <div className="side-tabs">
        <button className={tab === "files" ? "active" : ""} onClick={() => setTab("files")}>Файлы</button>
        <button className={tab === "terminal" ? "active" : ""} onClick={() => setTab("terminal")}>Терминал</button>
        <button className={tab === "git" ? "active" : ""} onClick={() => setTab("git")}>Git</button>
      </div>
      {tab === "files" && (
        <Explorer
          root={s.workspace?.current?.path ?? null}
          tree={s.tree}
          loading={s.treeLoading}
          gitStatus={s.gitStatus?.ok ? s.gitStatus.content : null}
          openFile={s.openFile}
          onRefresh={() => void s.loadTree()}
          onOpenFile={(p) => void s.openWorkspaceFile(p)}
          onCloseFile={() => s.setOpenFile(null)}
        />
      )}
      {tab === "terminal" && (
        <TerminalPanel
          cwd={s.workspace?.current?.path ?? null}
          enabled={
            !!s.workspace?.current &&
            s.config?.terminal_enabled !== false &&
            s.config?.access_mode !== "read_only"
          }
          history={s.termHistory}
          pendingConfirm={s.pendingTerm}
          onRun={(c) => void s.runTerminal(c)}
          onConfirm={(ok) => void s.confirmTerminal(ok)}
        />
      )}
      {tab === "git" && (
        <GitPanel
          project={s.workspace?.current ?? null}
          status={s.gitStatus}
          log={s.gitLog}
          onRefresh={() => void s.loadGit()}
        />
      )}
    </aside>
  );
}

export default function App() {
  const s = useAxiom();

  // Reflect the configured theme on <html> (light/dark palettes in styles.css).
  // The coordinated fade is enabled only for the duration of a theme switch.
  const theme = s.config?.theme === "light" ? "light" : "dark";
  useEffect(() => {
    const root = document.documentElement;
    root.classList.add("theme-anim");
    root.dataset.theme = theme;
    const timer = window.setTimeout(() => root.classList.remove("theme-anim"), 480);
    return () => window.clearTimeout(timer);
  }, [theme]);

  // Settings → General → animations off silences every transition at once.
  useEffect(() => {
    document.documentElement.classList.toggle("no-anim", s.config?.animations === false);
  }, [s.config?.animations]);

  const toasts = s.toasts.map((toast) => (
    <div key={toast.id} className={"toast toast-" + toast.kind}>
      {toast.text}
    </div>
  ));

  // The boot sequence is a real screen: it shows while the probes run and
  // explains a failure instead of leaving an empty window behind.
  if (s.phase !== "ready") {
    return (
      <div className="app">
        <BootScreen
          phase={s.phase}
          steps={s.bootSteps}
          error={s.bootError}
          onRetry={() => void s.runBoot()}
          onRestartCore={() => void s.restartCore()}
          onOpenSettings={() => s.openSettings()}
        />
        {s.settingsOpen && s.config && (
          <SettingsModal
            config={s.config}
            section={s.settingsSection}
            setSection={s.setSettingsSection}
            onClose={() => s.setSettingsOpen(false)}
            onSave={s.saveConfig}
            onRestartCore={s.restartCore}
          />
        )}
        {toasts}
      </div>
    );
  }

  return (
    <div className="app">
      <Sidebar
        open={s.sidebarOpen}
        drawer={false}
        width={s.sidebarWidth}
        onWidthChange={s.setSidebarWidth}
        onWidthCommit={s.commitSidebarWidth}
        chats={s.filteredChats}
        totalChats={s.chats.length}
        activeChatId={s.activeChatId}
        search={s.chatSearch}
        onSearch={s.setChatSearch}
        onNewChat={s.newChat}
        onOpenChat={s.openChat}
        onDeleteChat={s.deleteChat}
        onRenameChat={s.renameChat}
        onDeleteAllChats={s.deleteAllChats}
        onOpenSettings={() => s.openSettings()}
        onOpenModels={() => void s.openOverlay("status")}
        onClose={() => s.toggleSidebar()}
        activeModel={s.modelDetail}
      />

      <div className="main">
        <header className="topbar">
          <button
            className="icon-btn"
            title="Sidebar (Ctrl+B)"
            onClick={() => s.toggleSidebar()}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <rect x="3" y="4" width="18" height="16" rx="2.5" />
              <line x1="9.5" y1="4" x2="9.5" y2="20" />
            </svg>
          </button>
          <ProjectSelector
            current={s.workspace?.current ?? null}
            recent={s.workspace?.recent ?? []}
            pinned={s.workspace?.pinned ?? []}
            onOpen={s.openWorkspaceDialog}
            onSwitch={(path) => void s.switchWorkspace(path)}
            onClear={() => void s.clearWorkspace()}
            onRemove={(path) => void s.removeWorkspace(path)}
            onTogglePin={(path) => void s.toggleWorkspacePin(path)}
          />
          <div className="topbar-spacer" />
          <div className="access-dot" title={s.accessTitle}>{s.accessLabel}</div>
          <button
            className="icon-btn"
            title={theme === "light" ? "Тёмная тема" : "Светлая тема"}
            aria-label={theme === "light" ? "Включить тёмную тему" : "Включить светлую тему"}
            onClick={() =>
              s.config && void s.saveConfig({ theme: theme === "light" ? "obsidian" : "light" })
            }
          >
            {theme === "light" ? (
              <Moon size={17} strokeWidth={1.8} />
            ) : (
              <Sun size={17} strokeWidth={1.8} />
            )}
          </button>
          <button
            className="icon-btn"
            title={s.rightPanelOpen ? "Скрыть панель" : "Показать панель"}
            aria-label={s.rightPanelOpen ? "Скрыть панель" : "Показать панель"}
            aria-pressed={s.rightPanelOpen}
            onClick={s.toggleRightPanel}
          >
            {s.rightPanelOpen ? (
              <PanelRightClose size={17} strokeWidth={1.8} />
            ) : (
              <PanelRightOpen size={17} strokeWidth={1.8} />
            )}
          </button>
        </header>

        <div className={"workbench" + (s.rightPanelOpen ? "" : " panel-closed")}>
          <div className="workbench-chat">
            <MessageList
              messages={s.messages}
              generating={s.generating}
              statusText={s.statusText}
              liveState={s.liveState}
              elapsedMs={s.elapsedMs}
              config={s.config}
              modelName={s.activeModel}
              modelCapabilities={s.activeModelInfo?.capabilities ?? []}
              globalChat={!s.workspace?.current}
              onEdit={s.editLastUser}
              onOpen={s.openExternal}
              onSuggestion={s.send}
              onStop={s.cancel}
            />

            <Composer
              generating={s.generating}
              disabled={!s.connected}
              draft={s.draft}
              onDraftChange={s.setDraft}
              onSend={s.send}
              onCommand={s.runCommand}
              onCancel={s.cancel}
              webSearchEnabled={s.config?.web_search_enabled ?? true}
              onToggleWebSearch={() =>
                s.config && void s.saveConfig({ web_search_enabled: !s.config.web_search_enabled })
              }
              config={s.config}
              modelName={s.activeModel}
              modelSupportsVision={s.activeModelInfo?.capabilities.includes("vision") ?? null}
              context={s.context}
              onOpenContext={() => s.openOverlay("context")}
              composerRef={s.composerRef}
              modelSelector={
                <ModelSelector
                  models={s.models}
                  active={s.activeModelInfo}
                  loading={s.modelsLoading}
                  error={s.modelsError}
                  switching={s.switchingModel}
                  disabled={!s.connected}
                  openSignal={s.modelMenuSignal}
                  onSelect={s.selectModel}
                  onRefresh={s.refreshModels}
                />
              }
            />
          </div>
          <WorkbenchSide store={s} />
        </div>
      </div>

      {s.settingsOpen && s.config && (
        <SettingsModal
          config={s.config}
          section={s.settingsSection}
          setSection={s.setSettingsSection}
          onClose={() => s.setSettingsOpen(false)}
          onSave={s.saveConfig}
          onRestartCore={s.restartCore}
        />
      )}

      <OverlayPanel
        overlay={s.overlay}
        onClose={() => s.setOverlay(null)}
        model={s.modelDetail}
        context={s.context}
        status={s.status}
        statusError={s.statusError}
        tools={s.tools}
        toolsError={s.toolsError}
        onReload={() => void s.loadStatus()}
      />

      {toasts}
    </div>
  );
}
