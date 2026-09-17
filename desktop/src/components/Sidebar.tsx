import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { MessageSquarePlus, Search, Trash2, Settings2, Cpu } from "lucide-react";
import type { Conversation, ModelInfo } from "../types";

interface Props {
  open: boolean;
  width: number;
  onWidthChange: (w: number) => void;
  chats: Conversation[];
  activeChatId: string | null;
  search: string;
  onSearch: (q: string) => void;
  onNewChat: () => void;
  onOpenChat: (id: string) => void;
  onDeleteChat: (id: string) => void;
  onOpenSettings: () => void;
  onOpenModelMenu: (name: string) => void;
  models: ModelInfo[];
  activeModel: ModelInfo | null;
  busy: boolean;
}

interface Group {
  label: string;
  items: Conversation[];
}

function groupChats(chats: Conversation[]): Group[] {
  const now = Date.now() / 1000;
  const dayStart = new Date().setHours(0, 0, 0, 0) / 1000;
  const groups: Record<string, Conversation[]> = {
    "Сегодня": [],
    "Вчера": [],
    "Последние 7 дней": [],
    "Ранее": [],
  };
  for (const chat of chats) {
    const t = chat.updatedAt;
    if (t >= dayStart) groups["Сегодня"].push(chat);
    else if (t >= dayStart - 86400) groups["Вчера"].push(chat);
    else if (t >= now - 7 * 86400) groups["Последние 7 дней"].push(chat);
    else groups["Ранее"].push(chat);
  }
  return Object.entries(groups)
    .filter(([, items]) => items.length > 0)
    .map(([label, items]) => ({ label, items }));
}

export default function Sidebar(props: Props) {
  const {
    open, width, onWidthChange, chats, activeChatId, search, onSearch,
    onNewChat, onOpenChat, onDeleteChat, onOpenSettings, activeModel,
  } = props;
  const dragging = useRef(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      onWidthChange(Math.min(420, Math.max(200, e.clientX)));
    };
    const onUp = () => {
      dragging.current = false;
      document.body.classList.remove("resizing");
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [onWidthChange]);

  const startDrag = useCallback(() => {
    dragging.current = true;
    document.body.classList.add("resizing");
  }, []);

  const groups = groupChats(chats);

  return (
    <aside
      className={"sidebar" + (open ? " open" : "")}
      style={{ width: open ? width : 0, "--sidebar-w": `${width}px` } as CSSProperties}
    >
      <div className="sidebar-inner">
        <button className="new-chat" onClick={onNewChat}>
          <MessageSquarePlus size={16} strokeWidth={1.8} />
          <span>Новый чат</span>
          <kbd>Ctrl+N</kbd>
        </button>

        <div className="side-search">
          <Search size={14} strokeWidth={1.8} />
          <input
            id="chat-search"
            placeholder="Поиск чатов…  Ctrl+K"
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            spellCheck={false}
          />
        </div>

        <nav className="chat-list">
          {groups.length === 0 && (
            <div className="chat-list-empty">
              {search ? "Ничего не найдено" : "История пуста"}
            </div>
          )}
          {groups.map((group) => (
            <div key={group.label} className="chat-group">
              <div className="chat-group-label">{group.label}</div>
              {group.items.map((chat) => (
                <div
                  key={chat.id}
                  className={"chat-item" + (chat.id === activeChatId ? " active" : "")}
                  onClick={() => onOpenChat(chat.id)}
                  title={chat.title}
                >
                  <span className="chat-item-title">{chat.title}</span>
                  {confirmDelete === chat.id ? (
                    <span className="chat-item-confirm">
                      <button
                        className="mini-btn danger"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteChat(chat.id);
                          setConfirmDelete(null);
                        }}
                      >
                        Удалить
                      </button>
                      <button
                        className="mini-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          setConfirmDelete(null);
                        }}
                      >
                        Нет
                      </button>
                    </span>
                  ) : (
                    <button
                      className="chat-item-delete"
                      title="Удалить"
                      onClick={(e) => {
                        e.stopPropagation();
                        setConfirmDelete(chat.id);
                      }}
                    >
                      <Trash2 size={13} strokeWidth={1.8} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          ))}
        </nav>

        <div className="side-footer">
          <button className="side-action" onClick={onOpenSettings}>
            <Settings2 size={15} strokeWidth={1.8} />
            <span>Настройки</span>
          </button>
          <div className="side-model" title="Модель выбирается в шапке">
            <Cpu size={15} strokeWidth={1.8} />
            <span>{activeModel?.displayName ?? "Модель не выбрана"}</span>
          </div>
        </div>
      </div>
      <div className="sidebar-resizer" onMouseDown={startDrag} />
    </aside>
  );
}
