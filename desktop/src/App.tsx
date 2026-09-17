import Sidebar from "./components/Sidebar";
import MessageList from "./components/MessageList";
import Composer from "./components/Composer";
import ModelSelector from "./components/ModelSelector";
import SettingsModal from "./components/SettingsModal";
import { useAxiom } from "./hooks/useAxiom";

const WELCOME = "Чем Axiom может помочь?";

export default function App() {
  const s = useAxiom();

  return (
    <div className="app">
      <Sidebar
        open={s.sidebarOpen}
        width={s.sidebarWidth}
        onWidthChange={s.setSidebarWidth}
        chats={s.filteredChats}
        activeChatId={s.activeChatId}
        search={s.search}
        onSearch={s.setSearch}
        onNewChat={s.newChat}
        onOpenChat={s.openChat}
        onDeleteChat={s.deleteChat}
        onOpenSettings={() => s.setSettingsOpen(true)}
        onOpenModelMenu={s.selectModel}
        models={s.models}
        activeModel={s.activeModelInfo}
        busy={s.generating}
      />

      <div className="main">
        <header className="topbar">
          <button
            className="icon-btn"
            title="Sidebar (Ctrl+B)"
            onClick={() => s.setSidebarOpen(!s.sidebarOpen)}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <rect x="3" y="4" width="18" height="16" rx="2.5" />
              <line x1="9.5" y1="4" x2="9.5" y2="20" />
            </svg>
          </button>
          <div className="topbar-title">{s.activeConversation?.title ?? "Axiom"}</div>
          <div className="topbar-spacer" />
          <ModelSelector
            models={s.models}
            active={s.activeModelInfo}
            onSelect={s.selectModel}
          />
          <button className="icon-btn" title="Настройки (Ctrl+,)" onClick={() => s.setSettingsOpen(true)}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <circle cx="12" cy="12" r="3.2" />
              <path d="M12 2.8v2.4M12 18.8v2.4M4.6 4.6l1.7 1.7M17.7 17.7l1.7 1.7M2.8 12h2.4M18.8 12h2.4M4.6 19.4l1.7-1.7M17.7 6.3l1.7-1.7" />
            </svg>
          </button>
        </header>

        <div className={"conn-strip" + (s.connected ? " ok" : " bad")}>
          {s.connected
            ? `Ollama · ${s.activeModelInfo?.displayName ?? "модель не выбрана"}`
            : `Ollama недоступна · ${s.ollamaError ?? ""}`}
        </div>

        <MessageList
          messages={s.messages}
          generating={s.generating}
          statusText={s.statusText}
          welcome={WELCOME}
          showReasoning={s.config?.show_reasoning ?? true}
        />

        <Composer
          generating={s.generating}
          disabled={!s.connected}
          onSend={s.send}
          onCancel={s.cancel}
          webSearchEnabled={s.config?.web_search_enabled ?? true}
          onToggleWebSearch={() =>
            s.config && void s.saveConfig({ web_search_enabled: !s.config.web_search_enabled })
          }
        />
      </div>

      {s.settingsOpen && s.config && (
        <SettingsModal
          config={s.config}
          onClose={() => s.setSettingsOpen(false)}
          onSave={s.saveConfig}
          onRestartCore={s.restartBridge}
        />
      )}
      {s.toast && <div className="toast">{s.toast}</div>}
    </div>
  );
}
