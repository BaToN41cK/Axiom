import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { onCoreEvent, request, restartCore } from "../bridge";
import type {
  AxiomConfig,
  Conversation,
  CoreEvent,
  DoneMetrics,
  LiveMessage,
  ModelInfo,
} from "../types";

let liveId = 0;

function updateLive(
  messages: LiveMessage[],
  mutate: (m: LiveMessage) => void,
): LiveMessage[] {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === "assistant" && m.streaming) {
      const copy = { ...m, toolCalls: m.toolCalls.map((t) => ({ ...t })) };
      mutate(copy);
      const next = [...messages];
      next[i] = copy;
      return next;
    }
  }
  return messages;
}

export function useAxiom() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(264);
  const [search, setSearch] = useState("");
  const [chats, setChats] = useState<Conversation[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<LiveMessage[]>([]);
  const [generating, setGenerating] = useState(false);
  const [statusText, setStatusText] = useState<string | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [activeModel, setActiveModel] = useState<string | null>(null);
  const [config, setConfig] = useState<AxiomConfig | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [ollamaError, setOllamaError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const generatingRef = useRef(false);

  const activeConversation = useMemo(
    () => chats.find((c) => c.id === activeChatId) ?? null,
    [chats, activeChatId],
  );

  const showToast = useCallback((text: string) => {
    setToast(text);
    window.setTimeout(() => setToast((t) => (t === text ? null : t)), 3600);
  }, []);

  const refreshChats = useCallback(async () => {
    try {
      setChats(await request<Conversation[]>("list_chats"));
    } catch {
      /* bridge restarting */
    }
  }, []);

  // ------------------------------------------------------------ bootstrap
  useEffect(() => {
    let disposed = false;
    (async () => {
      try {
        const report = await request<{
          available: boolean;
          version: string;
          error: string | null;
          models: ModelInfo[];
          selected: ModelInfo | null;
        }>("startup");
        if (disposed) return;
        setConnected(report.available);
        if (!report.available) {
          setOllamaError(report.error || "Ollama is not reachable.");
          return;
        }
        setModels(report.models);
        setActiveModel(report.selected?.name ?? null);
        setConfig(await request<AxiomConfig>("get_config"));
        await refreshChats();
      } catch (err) {
        if (!disposed) setOllamaError(String(err));
      }
    })();
    return () => {
      disposed = true;
    };
  }, [refreshChats]);

  // ------------------------------------------------------- streaming events
  useEffect(() => {
    const off = onCoreEvent((raw) => {
      const event = raw as CoreEvent;
      switch (event.type) {
        case "reasoning":
          setStatusText("Думает…");
          setMessages((ms) => updateLive(ms, (m) => { m.thinking += event.text; }));
          break;
        case "content":
          setStatusText(null);
          setMessages((ms) => updateLive(ms, (m) => { m.content += event.text; }));
          break;
        case "tool_call":
          setMessages((ms) =>
            updateLive(ms, (m) => {
              m.toolCalls.push({
                name: event.name,
                detail: String(event.arguments?.query ?? event.name),
                state: "running",
              });
            }),
          );
          setStatusText(event.name === "web_search" ? "Ищет в интернете…" : event.name);
          break;
        case "tool_result":
          setMessages((ms) =>
            updateLive(ms, (m) => {
              const call = [...m.toolCalls]
                .reverse()
                .find((t) => t.name === event.name && t.state === "running");
              if (call) {
                call.state = event.ok ? "ok" : "failed";
                call.durationMs = event.durationMs;
              }
            }),
          );
          break;
        case "search_result":
          setMessages((ms) => updateLive(ms, (m) => { m.sources = event.sources; }));
          setStatusText(null);
          break;
        case "status":
          setStatusText(
            event.state === "thinking" ? "Думает…"
            : event.state === "receiving" ? null
            : event.state === "connecting" ? `Подключается к ${event.detail ?? "модели"}…`
            : event.state === "searching" ? "Ищет в интернете…"
            : event.state === "reading_source" ? "Читает источник…"
            : null,
          );
          break;
        case "error":
          setMessages((ms) =>
            updateLive(ms, (m) => {
              m.error = { message: event.message, hint: event.hint };
            }),
          );
          setStatusText(null);
          break;
        case "done":
          setMessages((ms) =>
            updateLive(ms, (m) => {
              m.streaming = false;
              m.metrics = event as DoneMetrics;
            }),
          );
          generatingRef.current = false;
          setGenerating(false);
          setStatusText(null);
          void refreshChats();
          break;
      }
    });
    return off;
  }, [refreshChats]);


  // ------------------------------------------------------------- actions
  const newChat = useCallback(() => {
    if (generatingRef.current) void request("cancel");
    setActiveChatId(null);
    setMessages([]);
    setStatusText(null);
  }, []);

  const openChat = useCallback(async (id: string) => {
    if (generatingRef.current) void request("cancel");
    try {
      const conv = await request<Conversation>("load_chat", { id });
      if (conv) {
        setActiveChatId(id);
        setMessages(
          (conv.messages ?? []).map((m) => ({
            id: `${id}-${m.role}-${Math.random().toString(36).slice(2, 8)}`,
            role: m.role,
            content: m.content,
            thinking: m.thinking ?? "",
            streaming: false,
            toolCalls: [],
            sources: [],
            images: Array.isArray(m.images) ? m.images.filter(Boolean) : [],
          })),
        );
      }
    } catch (err) {
      showToast(String(err));
    }
  }, [showToast]);

  const deleteChat = useCallback(async (id: string) => {
    try {
      await request("delete_chat", { id });
      if (id === activeChatId) {
        setActiveChatId(null);
        setMessages([]);
      }
      await refreshChats();
    } catch (err) {
      showToast(String(err));
    }
  }, [activeChatId, refreshChats, showToast]);

  const send = useCallback(
    async (text: string, forceSearch: boolean, images: string[] = []) => {
      const clean = text.trim();
      const imgs = (images || []).filter(Boolean);
      if ((!clean && imgs.length === 0) || generatingRef.current) return;
      generatingRef.current = true;
      setGenerating(true);
      setStatusText("Подключается…");
      setMessages((ms) => [
        ...ms,
        {
          id: `u-${Date.now()}`,
          role: "user",
          content: clean,
          thinking: "",
          streaming: false,
          toolCalls: [],
          sources: [],
          images: imgs,
        },
        {
          id: `live-${++liveId}`,
          role: "assistant",
          content: "",
          thinking: "",
          streaming: true,
          toolCalls: [],
          sources: [],
        },
      ]);
      try {
        await request("send", { text: clean, forceSearch, images: imgs });
      } catch (err) {
        setMessages((ms) =>
          updateLive(ms, (m) => {
            m.streaming = false;
            m.error = { message: String(err), hint: null };
          }),
        );
        generatingRef.current = false;
        setGenerating(false);
        setStatusText(null);
      }
    },
    [],
  );

  const cancel = useCallback(async () => {
    try {
      await request("cancel");
    } catch {
      /* nothing running */
    }
  }, []);

  const selectModel = useCallback(async (name: string) => {
    try {
      const model = await request<ModelInfo>("set_model", { name });
      setActiveModel(model.name);
      showToast(`Модель: ${model.displayName ?? model.name}`);
    } catch (err) {
      showToast(String(err));
    }
  }, [showToast]);

  const saveConfig = useCallback(async (patch: Partial<AxiomConfig>) => {
    try {
      setConfig(await request<AxiomConfig>("set_config", { patch }));
      showToast("Настройки сохранены");
    } catch (err) {
      showToast(String(err));
    }
  }, [showToast]);

  const restartBridge = useCallback(async () => {
    try {
      await restartCore();
      showToast("Ядро перезапускается…");
    } catch (err) {
      showToast(String(err));
    }
  }, [showToast]);

  // ---------------------------------------------------------- shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      const key = e.key.toLowerCase();
      if (key === "n") { e.preventDefault(); newChat(); }
      else if (key === "b") { e.preventDefault(); setSidebarOpen((v) => !v); }
      else if (key === "k") { e.preventDefault(); setSidebarOpen(true); window.setTimeout(() => document.getElementById("chat-search")?.focus(), 60); }
      else if (key === ",") { e.preventDefault(); setSettingsOpen(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [newChat]);

  const filteredChats = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return chats;
    return chats.filter((c) => c.title.toLowerCase().includes(q));
  }, [chats, search]);

  const activeModelInfo = models.find((m) => m.name === activeModel) ?? null;

  return {
    // state
    sidebarOpen, setSidebarOpen,
    sidebarWidth, setSidebarWidth,
    search, setSearch,
    filteredChats, activeChatId, activeConversation,
    messages, generating, statusText,
    models, activeModelInfo, config,
    settingsOpen, setSettingsOpen,
    ollamaError, connected, toast,
    // actions
    newChat, openChat, deleteChat, send, cancel,
    selectModel, saveConfig, restartBridge,
  };
}

export type AxiomStore = ReturnType<typeof useAxiom>;

