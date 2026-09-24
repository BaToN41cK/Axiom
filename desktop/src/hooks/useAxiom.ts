/**
 * AXIOM workspace store — the single place where the GUI meets the real core.
 *
 * Everything the interface shows is derived from backend facts:
 *  - boot steps mirror real bridge probes (health → models → model selection);
 *  - streaming text is batched per animation frame (smooth, no per-token re-render);
 *  - reasoning appears only when the model really sends it;
 *  - tool activity, sources and metrics come from real events;
 *  - the model selector really calls `set_model` and the next request uses it.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  onCoreEvent,
  onCoreExit,
  onCoreStderr,
  openExternal,
  quitApp,
  request,
  restartCore,
} from "../bridge";
import { isPermissionGranted, requestPermission, sendNotification } from "@tauri-apps/plugin-notification";
import { commandByName, matchingCommands, parseCommand } from "../lib/commands";
import { stripDataUrl } from "../lib/format";
import type {
  AxiomConfig,
  ChatHit,
  Conversation,
  CoreEvent,
  DoneMetrics,
  HealthReport,
  LiveMessage,
  ModelInfo,
  ProjectInfo,
  SendResult,
  StartupReport,
  StatusReport,
  TerminalResult,
  ToolInfo,
  ProviderRow,
  ProviderModelRow,
  AgentRow,
  TrajectoryViewer,
  TreeNode,
  WorkspaceState,
} from "../types";

export type Phase = "booting" | "ready" | "unavailable" | "error";
export type Overlay = "help" | "status" | "tools" | "context" | "harness" | null;
export type SettingsSection =
  | "general"
  | "models"
  | "providers"
  | "chat"
  | "tools"
  | "appearance"
  | "shortcuts"
  | "about";

export interface BootStep {
  id: string;
  label: string;
  state: "pending" | "running" | "ok" | "failed";
  detail: string | null;
}

export interface Toast {
  id: number;
  text: string;
  kind: "info" | "ok" | "error";
}

/** Real boot sequence — each label is a probe that really runs. */
const BOOT_SEQUENCE: { id: string; label: string }[] = [
  { id: "ui", label: "Инициализация интерфейса" },
  { id: "detect", label: "Поиск Ollama" },
  { id: "connect", label: "Подключение к Ollama" },
  { id: "models", label: "Чтение установленных моделей" },
  { id: "select", label: "Выбор активной модели" },
  { id: "workspace", label: "Подготовка рабочего пространства" },
];

let liveId = 0;
let toastId = 0;

function freshSteps(): BootStep[] {
  return BOOT_SEQUENCE.map((step) => ({ ...step, state: "pending", detail: null }));
}

function liveAssistant(content = "", thinking = ""): LiveMessage {
  return {
    id: `live-${++liveId}`,
    role: "assistant",
    content,
    thinking,
    streaming: true,
    toolCalls: [],
    sources: [],
    createdAt: Date.now(),
  };
}

/** Mutate the trailing streaming assistant message, immutably. */
function updateLive(messages: LiveMessage[], mutate: (m: LiveMessage) => void): LiveMessage[] {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message.role === "assistant" && message.streaming) {
      const copy: LiveMessage = {
        ...message,
        toolCalls: message.toolCalls.map((tool) => ({ ...tool })),
      };
      mutate(copy);
      const next = [...messages];
      next[i] = copy;
      return next;
    }
  }
  return messages;
}

function errorText(err: unknown): string {
  const text = err instanceof Error ? err.message : String(err);
  return text.replace(/^Error:\s*/, "");
}

function activeProviderLabel(name: string, providerId: string): string {
  return providerId === "ollama" ? name : `${providerId}/${name}`;
}

/** Match a model by exact name, then by display label, then by substring. */
export function resolveModel(models: ModelInfo[], needle: string): ModelInfo | null {
  const query = needle.trim().toLowerCase();
  if (!query) return null;
  return (
    models.find((m) => m.name.toLowerCase() === query) ??
    models.find((m) => m.displayName.toLowerCase() === query) ??
    models.find((m) => m.name.toLowerCase().includes(query)) ??
    models.find((m) => m.displayName.toLowerCase().includes(query)) ??
    null
  );
}

/** Human label of a tool as shown in the UI. */
export function toolLabel(name: string): string {
  if (name === "web_search") return "Веб-поиск";
  if (name === "fetch_url") return "Чтение страницы";
  if (name === "list_files") return "Просмотр папки";
  if (name === "read_file") return "Чтение файла";
  if (name === "write_file") return "Запись файла";
  if (name === "edit_file") return "Редактирование";
  if (name === "search_text") return "Поиск по коду";
  if (name === "search_files") return "Поиск файлов";
  if (name === "run_command") return "Терминал";
  if (name === "inspect_project") return "Осмотр проекта";
  if (name.startsWith("git_")) return "Git";
  return name;
}

/** What a tool is actually working on (query, URL, ...). */
export function toolTarget(_name: string, args: Record<string, unknown>): string {
  const pick = (...keys: string[]): string => {
    for (const key of keys) {
      const value = args?.[key];
      if (typeof value === "string" && value.trim()) return value.trim();
    }
    return "";
  };
  const query = args?.query;
  const url = args?.url;
  if (typeof query === "string" && query.trim()) return query.trim();
  if (typeof url === "string" && url.trim()) return url.trim();
  return pick("command", "path", "pattern", "glob", "source", "destination");
}

function toolStatusText(name: string, args: Record<string, unknown>): string {
  const target = toolTarget(name, args);
  if (name === "web_search") return target ? `Ищет: «${target}»` : "Ищет в интернете…";
  if (name === "fetch_url") return target ? `Читает: ${target}` : "Читает страницу…";
  if (name === "list_files") return target ? `Смотрит папку: ${target}` : "Смотрит файлы…";
  if (name === "read_file") return target ? `Читает: ${target}` : "Читает файл…";
  if (name === "write_file") return target ? `Пишет: ${target}` : "Пишет файл…";
  if (name === "edit_file") return target ? `Правит: ${target}` : "Редактирует…";
  if (name === "search_text" || name === "search_files") return target ? `Ищет: «${target}»` : "Ищет по проекту…";
  if (name === "run_command") return target ? `Выполняет: ${target}` : "Выполняет команду…";
  if (name.startsWith("git_")) return "Git…";
  return toolLabel(name);
}

export function useAxiom() {
  // ------------------------------------------------------------------- boot
  const [phase, setPhase] = useState<Phase>("booting");
  const [bootSteps, setBootSteps] = useState<BootStep[]>(freshSteps);
  const [bootError, setBootError] = useState<{ message: string; hint: string | null; url: string } | null>(
    null,
  );

  // ------------------------------------------------------------- connection
  const [health, setHealth] = useState<HealthReport | null>(null);
  const [connected, setConnected] = useState(false);
  const [coreLost, setCoreLost] = useState(false);

  // ----------------------------------------------------------------- models
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [activeModel, setActiveModel] = useState<string | null>(null);
  const [activeModelProvider, setActiveModelProvider] = useState("ollama");
  const [modelDetail, setModelDetail] = useState<ModelInfo | null>(null);
  const [switchingModel, setSwitchingModel] = useState<string | null>(null);
  const [modelMenuSignal, setModelMenuSignal] = useState(0);

  // ------------------------------------------------------------------- chat
  const [chats, setChats] = useState<Conversation[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<LiveMessage[]>([]);
  const [chatSearch, setChatSearch] = useState("");
  const [generating, setGenerating] = useState(false);
  const [liveState, setLiveState] = useState("idle");
  const [statusText, setStatusText] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [lastMetrics, setLastMetrics] = useState<DoneMetrics | null>(null);

  // ----------------------------------------------------------------- config
  const [config, setConfig] = useState<AxiomConfig | null>(null);
  const [providerRows, setProviderRows] = useState<ProviderRow[]>([]);
  const [providerModels, setProviderModels] = useState<ProviderModelRow[]>([]);
  const [providerLoading, setProviderLoading] = useState(false);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [profiles, setProfiles] = useState<{ active: string; items: { id: string; name: string; prompt: string }[] }>({ active: "", items: [] });
  const [trajectory, setTrajectory] = useState<TrajectoryViewer | null>(null);

  // ------------------------------------------------- full-text chat search
  const [chatHits, setChatHits] = useState<Record<string, string>>({});

  // ------------------------------------------------------- model warm-up UI
  const [warming, setWarming] = useState(false);

  // ------------------------------------------------ command palette (Ctrl+Shift+P)
  const [paletteOpen, setPaletteOpen] = useState(false);

  // ---------------------------------------------- interactive shell session
  const [shellRunning, setShellRunning] = useState(false);
  const [shellOutput, setShellOutput] = useState("");

  // ------------------------------------------------------- project workspace
  const [workspace, setWorkspace] = useState<WorkspaceState | null>(null);
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [treeLoading, setTreeLoading] = useState(false);
  const [openFile, setOpenFile] = useState<{ path: string; content: string } | null>(null);
  const [termHistory, setTermHistory] = useState<{ command: string; result: TerminalResult }[]>([]);
  const [pendingTerm, setPendingTerm] = useState<string | null>(null);
  const [gitStatus, setGitStatus] = useState<{ ok: boolean; content: string; error: string | null } | null>(null);
  const [gitLog, setGitLog] = useState<{ ok: boolean; content: string; error: string | null } | null>(null);

  // --------------------------------------------------------------------- ui
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(268);
  // Right workbench panel (Files/Terminal/Git) — session UI state, not config.
  const [rightPanelOpen, setRightPanelOpen] = useState<boolean>(() => {
    try {
      return localStorage.getItem("axiom.rightPanel") !== "closed";
    } catch {
      return true;
    }
  });
  // Resizable width of the same panel (§8): persisted next to the open/closed
  // flag so a restored session keeps the user's layout.
  const [rightPanelWidth, setRightPanelWidth] = useState<number>(() => {
    try {
      const saved = Number(localStorage.getItem("axiom.rightPanelWidth"));
      return Number.isFinite(saved) && saved >= 240 && saved <= 680 ? saved : 340;
    } catch {
      return 340;
    }
  });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsSection, setSettingsSection] = useState<SettingsSection>("general");
  const [overlay, setOverlay] = useState<Overlay>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [tools, setTools] = useState<ToolInfo[] | null>(null);
  const [toolsError, setToolsError] = useState<string | null>(null);
  const [status, setStatus] = useState<StatusReport | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [debugLog, setDebugLog] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const composerRef = useRef<HTMLTextAreaElement>(null);

  function onOpenModels() {
    setModelMenuSignal((n) => n + 1);
  }

  const generatingRef = useRef(false);
  const startedAtRef = useRef(0);
  const pendingTextRef = useRef({ content: "", thinking: "" });
  const rafRef = useRef<number | null>(null);
  const bootedRef = useRef(false);
  /** Tokens that cancel superseded background tasks (warm-up, chat search). */
  const warmupTokenRef = useRef(0);
  const searchSeqRef = useRef(0);

  // ---------------------------------------------------------------- toasts
  function notify(text: string, kind: Toast["kind"] = "info") {
    const id = ++toastId;
    setToasts((list) => [...list.slice(-2), { id, text, kind }]);
    window.setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)), 4200);
  }

  /**
   * Desktop toast when a real answer finishes while the window is away.
   * Best-effort: OS notifications need the Tauri notification plugin and the
   * user's permission — any failure must never disturb the session.
   */
  function notifyAnswerReady(metrics: DoneMetrics) {
    if (metrics.state !== "completed") return;
    // The user is already looking at the answer — no toast needed.
    if (document.hasFocus()) return;
    void (async () => {
      try {
        let granted = await isPermissionGranted();
        if (!granted) granted = (await requestPermission()) === "granted";
        if (granted) sendNotification({ title: "AXIOM", body: "Ответ готов" });
      } catch {
        /* notifications are optional (plugin/permission unavailable) */
      }
    })();
  }

  // ------------------------------------------------- streaming text batching
  // Chunks arrive far faster than a frame; accumulate and flush once per frame
  // so long answers stay smooth instead of re-rendering per token.
  const flushText = useCallback(() => {
    rafRef.current = null;
    const { content, thinking } = pendingTextRef.current;
    if (!content && !thinking) return;
    pendingTextRef.current = { content: "", thinking: "" };
    setMessages((list) =>
      updateLive(list, (m) => {
        if (thinking) m.thinking += thinking;
        if (content) m.content += content;
      }),
    );
  }, []);

  function queueText(kind: "content" | "reasoning", text: string) {
    const pending = pendingTextRef.current;
    pendingTextRef.current =
      kind === "content" ? { ...pending, content: pending.content + text } : { ...pending, thinking: pending.thinking + text };
    if (rafRef.current == null) rafRef.current = window.requestAnimationFrame(flushText);
  }

  // --------------------------------------------------------------- elapsed
  useEffect(() => {
    if (!generating) return;
    const timer = window.setInterval(() => setElapsedMs(Date.now() - startedAtRef.current), 120);
    return () => window.clearInterval(timer);
  }, [generating]);

  // ------------------------------------------------------------ boot probes
  function setStep(id: string, state: BootStep["state"], detail: string | null = null) {
    setBootSteps((steps) => steps.map((step) => (step.id === id ? { ...step, state, detail } : step)));
  }

  async function loadModelDetail(name: string) {
    try {
      const detail = await request<ModelInfo | null>("model_info", { name });
      if (detail) setModelDetail(detail);
    } catch {
      setModelDetail(null);
    }
  }

  const refreshChats = useCallback(async () => {
    try {
      setChats(await request<Conversation[]>("list_chats"));
    } catch {
      /* the core may be restarting — the list stays as it is */
    }
  }, []);

  async function loadWorkspace() {
    try {
      const state = await request<{ current: ProjectInfo | null }>("workspace_info");
      setWorkspace((w) => ({
        current: state.current,
        recent: w?.recent ?? [],
        pinned: w?.pinned ?? [],
      }));
      return state;
    } catch (err) {
      notify(errorText(err), "error");
      return null;
    }
  }

  async function loadProjectList() {
    try {
      const [recent, pinned] = await Promise.all([
        request<{ recent: ProjectInfo[] }>("recent_workspaces"),
        request<{ pinned: ProjectInfo[] }>("pinned_workspaces"),
      ]);
      setWorkspace((w) => ({
        current: w?.current ?? null,
        recent: recent.recent,
        pinned: pinned.pinned,
      }));
    } catch {
      /* ignore */
    }
  }

  async function toggleWorkspacePin(path: string) {
    const isPinned = await request<{ pinned: boolean }>("is_pinned", { path });
    const success = isPinned.pinned
      ? await request<boolean>("unpin_workspace", { path })
      : await request<boolean>("pin_workspace", { path });
    if (success) {
      // Update local state optimistically
      setWorkspace((w) => ({
        current: w?.current ?? null,
        recent: w?.recent?.map((p) =>
          p.path === path ? { ...p, pinned: !p.pinned } : p
        ) ?? [],
        pinned: w?.pinned?.map((p) =>
          p.path === path ? { ...p, pinned: !p.pinned } : p
        ) ?? [],
      }));
      // Refresh project list to ensure consistency
      void loadProjectList();
    }
  }

  async function loadTree() {
    setTreeLoading(true);
    try {
      const data = await request<{ tree: TreeNode[] }>("workspace_tree", { depth: 3 });
      setTree(data.tree ?? []);
    } catch {
      setTree([]);
    } finally {
      setTreeLoading(false);
    }
  }

  async function loadGit() {
    try {
      const data = await request<{
        project: ProjectInfo | null;
        status: { ok: boolean; content: string; error: string | null } | null;
        log: { ok: boolean; content: string; error: string | null } | null;
      }>("git_panel");
      setGitStatus(data.status);
      setGitLog(data.log);
    } catch {
      setGitStatus(null);
      setGitLog(null);
    }
  }

  // ------------------------------------------------------ git write ops (§17)
  /** Run a user-initiated git write op and refresh the panel (never agent-driven). */
  async function gitWrite(cmd: string, args: Record<string, unknown>): Promise<boolean> {
    try {
      const res = await request<{ ok: boolean; error?: string; output?: string }>(cmd, args);
      if (!res.ok) {
        notify(res.error ?? "Операция Git не выполнена", "error");
        return false;
      }
      void loadGit();
      return true;
    } catch (err) {
      notify(errorText(err), "error");
      return false;
    }
  }

  /** Stage files (empty list = everything). */
  async function gitStage(paths: string[]): Promise<boolean> {
    return gitWrite("git_stage", { paths });
  }

  /** Unstage files (empty list = all staged). */
  async function gitUnstage(paths: string[]): Promise<boolean> {
    return gitWrite("git_unstage", { paths });
  }

  async function gitCommit(message: string, all = false): Promise<boolean> {
    const ok = await gitWrite("git_commit", { message, all });
    if (ok) notify("Коммит создан", "ok");
    return ok;
  }

  /** Unified diff of one file ("" when there are no changes). */
  async function gitShowDiff(path: string): Promise<string | null> {
    try {
      const res = await request<{ ok: boolean; diff?: string; error?: string }>("git_diff_file", { path });
      if (!res.ok) {
        notify(res.error ?? "Не удалось получить diff", "error");
        return null;
      }
      return res.diff ?? "";
    } catch (err) {
      notify(errorText(err), "error");
      return null;
    }
  }

  /** Switch the workspace repo to an existing local branch. */
  async function switchBranch(branch: string): Promise<boolean> {
    try {
      const res = await request<{ ok: boolean; error?: string; output?: string }>("git_switch", { branch });
      if (!res.ok) {
        notify(res.error ?? `Не удалось переключиться на ${branch}`, "error");
        return false;
      }
      notify(`Ветка: ${branch}`, "ok");
      void loadGit();
      void loadWorkspace(); // the branch is shown in the project header
      return true;
    } catch (err) {
      notify(errorText(err), "error");
      return false;
    }
  }

  async function runBoot() {
    setPhase("booting");
    setBootSteps(freshSteps());
    setBootError(null);
    let current = "ui";
    try {
      setStep("ui", "running");
      await Promise.resolve();
      setStep("ui", "ok", "AXIOM desktop");

      // The local config read and the Ollama probe do not depend on each other,
      // so they run together instead of as a chain of round trips.
      setStep("detect", "running");
      current = "detect";
      const [probe, cfg] = await Promise.all([
        request<HealthReport>("health"),
        request<AxiomConfig>("get_config"),
      ]);
      setHealth(probe);
      setConfig(cfg);
      setSidebarOpen(cfg.sidebar_open);
      setSidebarWidth(cfg.sidebar_width);
      if (!probe.available) {
        setStep("detect", "failed", probe.url);
        setConnected(false);
        setBootError({
          message: "Ollama недоступна",
          hint: `AXIOM не смог подключиться к ${probe.url}`,
          url: probe.url,
        });
        setPhase("unavailable");
        return;
      }
      setStep("detect", "ok", probe.url);

      setStep("connect", "running");
      setStep("connect", "ok", probe.version ? `Ollama ${probe.version}` : "соединение установлено");

      // The model list and the saved history are independent as well.
      setStep("models", "running");
      current = "models";
      // /api/tags can briefly answer with an empty list (or fail) while Ollama
      // is still starting / loading a model — retry before believing it.
      const chatsLoaded = refreshChats();
      let list: ModelInfo[] = [];
      let lastModelsError: string | null = null;
      for (let attempt = 0; attempt < 3 && list.length === 0; attempt += 1) {
        if (attempt > 0) await new Promise((resolve) => setTimeout(resolve, 700));
        try {
          list = await request<ModelInfo[]>("models");
          lastModelsError = null;
        } catch (err) {
          lastModelsError = errorText(err);
        }
      }
      await chatsLoaded;
      setModels(list);
      setStep(
        "models",
        "ok",
        list.length
          ? `${list.length} модел${list.length === 1 ? "ь" : "и"}`
          : lastModelsError
            ? "нет данных — повторим позже"
            : "моделей пока нет",
      );

      if (list.length === 0) {
        // An empty model list is NOT an error (API providers are coming):
        // boot continues to the main screen and the list is re-probed later.
        setStep("select", "ok", "модель не выбрана");
      } else {
        setStep("select", "running");
        current = "select";
        const configuredRoute = cfg.router_primary;
        const routeModel = configuredRoute
          ? list.find((m) => m.name === configuredRoute.model && (m.providerId ?? "ollama") === configuredRoute.provider_id)
          : null;
        const preferred = cfg.model ? list.find((m) => m.name === cfg.model && (m.providerId ?? "ollama") === "ollama") : null;
        const chosen = routeModel ?? preferred ?? list.find((m) => (m.providerId ?? "ollama") === "ollama") ?? list[0];
        const selected = await request<ModelInfo>("set_model", { name: chosen.name, providerId: chosen.providerId ?? "ollama" });
        setActiveModelProvider(selected.providerId ?? "ollama");
        setActiveModel(selected.name);
        setModels((known) => known.map((m) => {
          const same = m.name === selected.name && (m.providerId ?? "ollama") === (selected.providerId ?? "ollama");
          return same ? { ...m, ...selected } : m;
        }));
        void loadModelDetail(selected.name);
        setStep("select", "ok", selected.displayName);
        if (cfg.warmup_model && (selected.providerId ?? "ollama") === "ollama") trackWarmup(selected.name);
        if (cfg.model && !preferred) {
          notify(`Модель ${cfg.model} не найдена в Ollama — выбрана ${selected.displayName}`, "error");
        }
      }

      setStep("workspace", "running");
      try {
        const ws = await request<{ current: ProjectInfo | null }>("workspace_info");
        setWorkspace((prev) => ({
          current: ws.current,
          recent: prev?.recent ?? [],
          pinned: prev?.pinned ?? [],
        }));
        setStep("workspace", "ok", ws.current ? `${ws.current.name} · ${ws.current.kind}` : "без проекта");
        void loadTree();
        void loadGit();
        // Load recent/pinned projects after boot completes to avoid blocking startup
        void loadProjectList();
      } catch {
        setStep("workspace", "ok", "готово");
      }
      setConnected(true);
      setCoreLost(false);
      setPhase("ready");
      // Background model warm-up: fire-and-forget, never blocks the GUI.
      void request<{ warmed: boolean; pending: boolean }>("warmup", {}).catch(() => {});
      if (list.length === 0) {
        // The list often appears seconds later (Ollama still loading a model):
        // re-probe quietly in the background and select a model if it showed up.
        window.setTimeout(() => {
          void refreshModels()
            .then((fresh) => {
              if (fresh.length === 0) return;
              const configured = cfg.router_primary;
              const preferred = configured
                ? fresh.find((m) => m.name === configured.model
                  && (m.providerId ?? "ollama") === configured.provider_id)
                : cfg.model
                  ? fresh.find((m) => m.name === cfg.model && (m.providerId ?? "ollama") === "ollama")
                  : null;
              const fallback = fresh.find((m) => (m.providerId ?? "ollama") === "ollama") ?? fresh[0];
              const chosen = preferred ?? fallback;
              void selectModel(chosen.name, chosen.providerId ?? "ollama", true);
            })
            .catch(() => {});
        }, 3000);
      }
    } catch (err) {
      setStep(current, "failed", errorText(err));
      setBootError({ message: errorText(err), hint: null, url: health?.url ?? "" });
      setPhase("error");
    }
  }

  // ------------------------------------------------------------ status text
  function applyStatus(state: string, detail: string | null) {
    setLiveState(state);
    switch (state) {
      case "thinking":
        setStatusText("Размышляет…");
        break;
      case "connecting":
        setStatusText(detail ? `Подключается к ${detail}…` : "Подключается…");
        break;
      case "searching":
        setStatusText("Ищет в интернете…");
        break;
      case "tool_call":
        setStatusText(detail ?? "Инструмент");
        break;
      case "receiving":
        setStatusText(null);
        break;
      default:
        break;
    }
  }

  function finishGeneration(metrics: DoneMetrics) {
    flushText();
    setMessages((list) =>
      updateLive(list, (m) => {
        m.streaming = false;
        m.metrics = metrics;
        if (metrics.state === "cancelled") {
          m.toolCalls = m.toolCalls.map((tool) =>
            tool.state === "running" ? { ...tool, state: "cancelled" as const } : tool,
          );
        }
      }),
    );
    generatingRef.current = false;
    setGenerating(false);
    setStatusText(null);
    setLiveState(metrics.state);
    setLastMetrics(metrics);
    notifyAnswerReady(metrics);
    void refreshChats();
  }

  // ------------------------------------------------------- streaming events
  useEffect(() => {
    const off = onCoreEvent((raw) => {
      const event = raw as CoreEvent;
      switch (event.type) {
        case "reasoning":
          setLiveState("thinking");
          queueText("reasoning", event.text);
          break;
        case "content":
          setLiveState("receiving");
          setStatusText(null);
          queueText("content", event.text);
          break;
        case "tool_call":
          setLiveState(event.name === "web_search" ? "searching" : "tool_call");
          setStatusText(toolStatusText(event.name, event.arguments ?? {}));
          setMessages((list) =>
            updateLive(list, (m) => {
              m.toolCalls.push({
                name: event.name,
                detail: toolTarget(event.name, event.arguments ?? {}),
                state: "running",
              });
            }),
          );
          break;
        case "tool_result":
          setMessages((list) =>
            updateLive(list, (m) => {
              const call = [...m.toolCalls]
                .reverse()
                .find((tool) => tool.name === event.name && tool.state === "running");
              if (call) {
                call.state = event.ok ? "ok" : "failed";
                call.durationMs = event.durationMs;
                call.error = event.error;
              }
            }),
          );
          break;
        case "search_result":
          setMessages((list) =>
            updateLive(list, (m) => {
              m.sources = event.sources;
            }),
          );
          break;
        case "status":
          applyStatus(event.state, event.detail);
          break;
        case "error":
          setMessages((list) =>
            updateLive(list, (m) => {
              m.error = { message: event.message, hint: event.hint };
            }),
          );
          setStatusText(null);
          break;
        case "done":
          finishGeneration(event as DoneMetrics);
          break;
      }
    });
    return off;
  }, [flushText, refreshChats]);

  // ---------------------------------------------------------- generation API
  function beginGeneration() {
    generatingRef.current = true;
    startedAtRef.current = Date.now();
    pendingTextRef.current = { content: "", thinking: "" };
    setElapsedMs(0);
    setGenerating(true);
    setLiveState("connecting");
    setStatusText("Подключается…");
  }

  function failGeneration(err: unknown) {
    flushText();
    setMessages((list) =>
      updateLive(list, (m) => {
        m.streaming = false;
        m.error = { message: errorText(err), hint: null };
        m.toolCalls = m.toolCalls.map((tool) =>
          tool.state === "running" ? { ...tool, state: "cancelled" as const } : tool,
        );
      }),
    );
    generatingRef.current = false;
    setGenerating(false);
    setStatusText(null);
    setLiveState("error");
    const text = errorText(err);
    if (/ядро остановлено/i.test(text)) setCoreLost(true);
    notify(text, "error");
    void refreshChats();
  }

  /** Run a real turn through the bridge and follow its event stream. */
  async function streamTurn(cmd: string, args: Record<string, unknown>, before?: () => void) {
    beginGeneration();
    before?.();
    try {
      const result = await request<SendResult>(cmd, args);
      if (result?.conversation) {
        const conversation = result.conversation;
        setActiveChatId(conversation.id);
        setChats((list) => [conversation, ...list.filter((c) => c.id !== conversation.id)]);
      }
      if (result?.activeModel) {
        const model = result.activeModel;
        setModels((list) => list.map((m) => (m.name === model.name ? { ...m, ...model } : m)));
      }
    } catch (err) {
      failGeneration(err);
    }
  }

  async function send(text: string, forceSearch = false, images: string[] = []) {
    const clean = text.trim();
    const attached = (images || []).filter(Boolean);
    if (!clean && attached.length === 0) return;
    if (generatingRef.current) {
      notify("Генерация уже идёт — остановите её (Esc)", "error");
      return;
    }
    if (!connected) {
      notify("Ollama недоступна — проверьте подключение", "error");
      return;
    }
    const userMessage: LiveMessage = {
      id: `u-${++liveId}`,
      role: "user",
      content: clean,
      thinking: "",
      streaming: false,
      toolCalls: [],
      sources: [],
      createdAt: Date.now(),
      images: attached,
    };
    await streamTurn("send", { text: clean, forceSearch, images: attached.map(stripDataUrl) }, () => {
      setMessages((list) => [...list, userMessage, liveAssistant()]);
    });
  }

  async function cancel() {
    if (!generatingRef.current) return;
    setStatusText("Останавливаю…");
    try {
      await request<{ cancelled: boolean }>("cancel");
    } catch {
      /* nothing was running on the backend side */
    }
  }

  async function regenerate(forceSearch = false) {
    if (generatingRef.current) {
      notify("Генерация уже идёт — остановите её (Esc)", "error");
      return;
    }
    if (!messages.some((m) => m.role === "user")) {
      notify("Нечего перегенерировать — сначала отправьте сообщение", "error");
      return;
    }
    await streamTurn("regenerate", { forceSearch }, () => {
      setMessages((list) => {
        const trimmed = [...list];
        while (trimmed.length && trimmed[trimmed.length - 1].role === "assistant") trimmed.pop();
        return [...trimmed, liveAssistant()];
      });
    });
  }

  async function continueGeneration() {
    if (generatingRef.current) {
      notify("Генерация уже идёт — остановите её (Esc)", "error");
      return;
    }
    if (!connected) {
      notify("Ollama недоступна — проверьте подключение", "error");
      return;
    }
    const hasPartial = messages.some((m) => m.role === "assistant" && m.content);
    if (!hasPartial) {
      notify("Продолжать нечего — в этом чате ещё нет ответа", "error");
      return;
    }
    // Resume in place: the backend nudges the model with the partial answer
    // (prefill-only) and new text is appended to the same assistant message.
    await streamTurn("continue_last", { forceSearch: false }, () => {
      setMessages((list) => {
        const target = [...list].reverse().find((m) => m.role === "assistant" && m.content);
        if (!target) return [...list, liveAssistant()];
        return list.map((m) =>
          m.id === target.id
            ? { ...m, streaming: true, metrics: undefined, error: undefined }
            : m,
        );
      });
    });
  }

  async function editLastUser(text: string, forceSearch = false) {
    const clean = text.trim();
    if (!clean) {
      notify("Сообщение не может быть пустым", "error");
      return;
    }
    if (generatingRef.current) {
      notify("Генерация уже идёт — остановите её (Esc)", "error");
      return;
    }
    let index = -1;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        index = i;
        break;
      }
    }
    if (index === -1) {
      notify("Нет сообщения для правки", "error");
      return;
    }
    const images = messages[index].images ?? [];
    await streamTurn(
      "edit_message",
      { text: clean, forceSearch, images: images.map(stripDataUrl) },
      () => {
        setMessages((list) => [...list.slice(0, index), { ...list[index], content: clean }, liveAssistant()]);
      },
    );
  }

    // ------------------------------------------------------------ chat actions
  async function newChat() {
    if (generatingRef.current) void cancel();
    try {
      const conversation = await request<Conversation>("new_chat");
      setActiveChatId(conversation.id);
    } catch {
      setActiveChatId(null);
    }
    setMessages([]);
    setStatusText(null);
    setLiveState("idle");
    setLastMetrics(null);
    void refreshChats();
  }

  async function openChat(id: string) {
    if (generatingRef.current) void cancel();
    try {
      const conversation = await request<Conversation | null>("load_chat", { id });
      if (!conversation) {
        notify("Разговор не найден", "error");
        void refreshChats();
        return;
      }
      setActiveChatId(id);
      setMessages(
        (conversation.messages ?? []).map((message, index) => ({
          id: `${id}-${index}`,
          role: message.role,
          content: message.content,
          thinking: message.thinking ?? "",
          streaming: false,
          toolCalls: [],
          sources: [],
          createdAt: conversation.updatedAt,
          images: Array.isArray(message.images) ? message.images.filter(Boolean) : [],
        })),
      );
      setStatusText(null);
      setLiveState("idle");
      setLastMetrics(null);
    } catch (err) {
      notify(errorText(err), "error");
    }
  }

  async function deleteChat(id: string) {
    try {
      await request("delete_chat", { id });
      if (id === activeChatId) {
        setActiveChatId(null);
        setMessages([]);
      }
      await refreshChats();
      notify("Разговор удалён");
    } catch (err) {
      notify(errorText(err), "error");
    }
  }

  /** Delete every conversation in history — one button, real core calls. */
  async function deleteAllChats() {
    const ids = chats.map((c) => c.id);
    if (ids.length === 0) return;
    const failed: string[] = [];
    for (const id of ids) {
      try {
        await request("delete_chat", { id });
      } catch {
        failed.push(id);
      }
    }
    if (activeChatId && !failed.includes(activeChatId)) {
      setActiveChatId(null);
      setMessages([]);
      setLastMetrics(null);
    }
    await refreshChats();
    if (failed.length > 0) {
      notify(`Не удалось удалить ${failed.length} из ${ids.length} разговоров`, "error");
    } else {
      notify(`История очищена — удалено ${ids.length}`, "ok");
    }
  }

  async function renameChat(id: string, title: string) {
    try {
      const result = await request<{ renamed: boolean }>("rename_chat", { id, title });
      if (!result.renamed) {
        notify("Не удалось переименовать разговор", "error");
        return;
      }
      setChats((list) => list.map((c) => (c.id === id ? { ...c, title: title.trim() } : c)));
      notify("Разговор переименован", "ok");
    } catch (err) {
      notify(errorText(err), "error");
    }
  }

  // --------------------------------------------- sidebar search / organisation
  /** Full-text search over stored messages (debounced by the sidebar query). */
  async function searchChats(query: string) {
    const token = ++searchSeqRef.current;
    try {
      const data = await request<{ hits: ChatHit[] }>("search_chats", { query });
      if (searchSeqRef.current !== token) return; // a newer query already won
      const map: Record<string, string> = {};
      for (const hit of data.hits ?? []) map[hit.id] = hit.snippet;
      setChatHits(map);
    } catch {
      /* the core may be restarting — the previous hits stay visible */
    }
  }

  /** Pin/unpin a chat to the top of the sidebar (persisted in history). */
  async function pinChat(id: string, pinned?: boolean) {
    const next = pinned ?? !(chats.find((c) => c.id === id)?.pinned ?? false);
    try {
      const res = await request<{ ok: boolean }>("chat_meta", { id, pin: next });
      if (!res.ok) {
        notify("Не удалось закрепить разговор", "error");
        return;
      }
      setChats((list) => list.map((c) => (c.id === id ? { ...c, pinned: next } : c)));
    } catch (err) {
      notify(errorText(err), "error");
    }
  }

  /** File a chat under a sidebar folder (null = no folder). */
  async function setChatFolder(id: string, folder: string | null) {
    try {
      const res = await request<{ ok: boolean }>("chat_meta", { id, folder });
      if (!res.ok) {
        notify("Не удалось изменить папку разговора", "error");
        return;
      }
      setChats((list) => list.map((c) => (c.id === id ? { ...c, folder } : c)));
    } catch (err) {
      notify(errorText(err), "error");
    }
  }

  // ---------------------------------------------------------- model actions
  async function refreshModels(): Promise<ModelInfo[]> {
    setModelsLoading(true);
    setModelsError(null);
    try {
      const list = await request<ModelInfo[]>("models");
      setModels(list);
      // An empty list is a normal state (API providers are coming) — never an
      // error banner; real transport failures still land in the catch below.
      // A model can disappear from Ollama while AXIOM is running: adapt for real.
      const activeExists = list.some(
        (m) => m.name === activeModel
          && (m.providerId ?? "ollama") === activeModelProvider,
      );
      if (activeModel && !activeExists) {
        const fallback = list.find((m) => (m.providerId ?? "ollama") === activeModelProvider)
          ?? list.find((m) => (m.providerId ?? "ollama") === "ollama")
          ?? list[0];
        if (fallback) {
          const fallbackProvider = fallback.providerId ?? "ollama";
          notify(`Модель ${activeProviderLabel(activeModel, activeModelProvider)} больше не доступна — выбрана ${fallback.displayName}`, "error");
          await selectModel(fallback.name, fallbackProvider);
        } else {
          setActiveModel(null);
          setActiveModelProvider("ollama");
        }
      }
      return list;
    } catch (err) {
      setModelsError(errorText(err));
      return [];
    } finally {
      setModelsLoading(false);
    }
  }

  async function selectModel(name: string, providerId: string | boolean = "ollama", silent = false): Promise<boolean> {
    if (typeof providerId === "boolean") {
      silent = providerId;
      providerId = "ollama";
    }
    if (generatingRef.current) {
      notify("Нельзя переключить модель во время генерации — остановите её (Esc)", "error");
      return false;
    }
    if (name === activeModel && providerId === activeModelProvider) return true;
    setSwitchingModel(`${providerId}/${name}`);
    try {
      const model = await request<ModelInfo>("set_model", { name, providerId });
      setActiveModel(model.name);
      setActiveModelProvider(model.providerId ?? providerId);
      setModels((list) => list.map((m) => {
        const same = m.name === model.name && (m.providerId ?? "ollama") === (model.providerId ?? "ollama");
        return same ? { ...m, ...model } : m;
      }));
      void loadModelDetail(model.name);
      if (providerId === "ollama" && config?.warmup_model) trackWarmup(name);
      if (!silent) notify(`Активная модель: ${model.displayName}`, "ok");
      return true;
    } catch (err) {
      notify(errorText(err), "error");
      void refreshModels();
      return false;
    } finally {
      setSwitchingModel(null);
    }
  }

  // ------------------------------------------------------- model warm-up UI
  /** Watch the real residency of `name` (Ollama /api/ps) until the weights are in memory. */
  function trackWarmup(name: string) {
    const token = ++warmupTokenRef.current;
    setWarming(true);
    void (async () => {
      try {
        // The core warms the model in the background; `models` reports the
        // truth via /api/ps — poll until it is resident (≤5 minutes).
        for (let attempt = 0; attempt < 150; attempt += 1) {
          if (warmupTokenRef.current !== token) return;
          const list = await request<ModelInfo[]>("models");
          if (warmupTokenRef.current !== token) return;
          setModels(list);
          if (list.find((m) => m.name === name)?.loaded) return;
          await new Promise((resolve) => setTimeout(resolve, 2000));
        }
      } catch {
        /* the core may be restarting — the indicator simply turns off */
      } finally {
        if (warmupTokenRef.current === token) setWarming(false);
      }
    })();
  }

  /** Apply a new Ollama URL and re-probe everything (real reconnect). */
  async function reconnect(url?: string) {
    setPhase("booting");
    setBootSteps(freshSteps());
    try {
      setStep("ui", "ok", "AXIOM desktop");
      setStep("detect", "running");
      const report = await request<StartupReport>("reconnect", url ? { url } : {});
      setHealth({ available: report.available, version: report.version, url: url ?? health?.url ?? "" });
      if (!report.available) {
        setStep("detect", "failed", url ?? health?.url ?? "");
        setConnected(false);
        setBootError({ message: report.error ?? "Ollama недоступна", hint: report.hint, url: url ?? "" });
        setPhase("unavailable");
        return;
      }
      setStep("detect", "ok", url ?? health?.url ?? "");
      setStep("connect", "ok", report.version ? `Ollama ${report.version}` : "соединение установлено");
      setModels(report.models);
      setStep(
        "models",
        "ok",
        report.models.length
          ? `${report.models.length} модел${report.models.length === 1 ? "ь" : "и"}`
          : "моделей пока нет",
      );
      if (report.selected) {
        setActiveModel(report.selected.name);
        void loadModelDetail(report.selected.name);
        setStep("select", "ok", report.selected.displayName);
      } else {
        // No selected model is not a failure — the list may fill in later.
        setStep("select", "ok", "модель не выбрана");
      }
      setConfig(await request<AxiomConfig>("get_config"));
      await refreshChats();
      setStep("workspace", "ok", "готово");
      setConnected(true);
      setCoreLost(false);
      setPhase("ready");
      notify(
        report.selected ? "Ollama подключена" : "Ollama подключена — список моделей пока пуст",
        report.selected ? "ok" : "info",
      );
    } catch (err) {
      setStep("detect", "failed", errorText(err));
      setConnected(false);
      setBootError({ message: errorText(err), hint: null, url: url ?? "" });
      setPhase("error");
    }
  }

  // ---------------------------------------------------------------- config
  async function saveConfig(patch: Partial<AxiomConfig>): Promise<boolean> {
    try {
      const next = await request<AxiomConfig>("set_config", { patch });
      setConfig(next);
      setSidebarOpen(next.sidebar_open);
      setSidebarWidth(next.sidebar_width);
      return true;
    } catch (err) {
      notify(errorText(err), "error");
      return false;
    }
  }

  function toggleSidebar() {
    const next = !sidebarOpen;
    setSidebarOpen(next);
    if (config) void saveConfig({ sidebar_open: next });
  }

  function toggleRightPanel() {
    setRightPanelOpen((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("axiom.rightPanel", next ? "open" : "closed");
      } catch {
        /* storage unavailable — session-only state */
      }
      return next;
    });
  }

  function commitRightPanelWidth(width: number) {
    setRightPanelWidth(width);
    try {
      localStorage.setItem("axiom.rightPanelWidth", String(width));
    } catch {
      /* storage unavailable — session-only state */
    }
  }

  function commitSidebarWidth(width: number) {
    setSidebarWidth(width);
    if (config && config.sidebar_width !== width) void saveConfig({ sidebar_width: width });
  }

  // --------------------------------------------------------------------- ui
  function openSettings(section: SettingsSection = "general") {
    setSettingsSection(section);
    setSettingsOpen(true);
  }

  function openOverlay(next: Overlay) {
    setOverlay(next);
    if (next === "tools") void loadTools();
    if (next === "status") void loadStatus();
  }

  async function loadTools() {
    setToolsError(null);
    try {
      setTools(await request<ToolInfo[]>("tools"));
    } catch (err) {
      setToolsError(errorText(err));
    }
  }

  async function loadStatus() {
    setStatusError(null);
    try {
      setStatus(await request<StatusReport>("status"));
    } catch (err) {
      setStatusError(errorText(err));
    }
  }

  async function loadProviders() {
    setProviderLoading(true);
    try {
      setProviderRows(await request<ProviderRow[]>("providers"));
    } catch (err) { notify(errorText(err), "error"); }
    finally { setProviderLoading(false); }
  }
  async function providerTest(id: string) { try { const status = await request<string>("provider_test", { provider_id: id }); notify(`${id}: ${status}`, status === "error" ? "error" : "ok"); await loadProviders(); } catch (err) { notify(errorText(err), "error"); } }
  async function providerSaveKey(id: string, apiKey: string) { try { await request("provider_set_key", { provider_id: id, api_key: apiKey }); notify(`Ключ ${id} сохранён локально`, "ok"); await loadProviders(); } catch (err) { notify(errorText(err), "error"); } }
  async function providerSetBaseUrl(id: string, baseUrl: string) { try { await request("provider_set_base_url", { provider_id: id, base_url: baseUrl }); notify(`Endpoint ${id} сохранён`, "ok"); await loadProviders(); } catch (err) { notify(errorText(err), "error"); } }
  async function providerDiscover(id: string) { setProviderLoading(true); try { setProviderModels(await request<ProviderModelRow[]>("provider_discover", { provider_id: id })); notify(`Модели ${id} обновлены`, "ok"); } catch (err) { notify(errorText(err), "error"); } finally { setProviderLoading(false); } }
  async function providerPickModel(providerId: string, model: string) {
    try {
      await request("provider_pick_model", { provider_id: providerId, model });
      const selected = await request<ModelInfo>("set_model", { name: model, provider_id: providerId });
      setActiveModel(selected.name);
      setActiveModelProvider(selected.providerId ?? providerId);
      await refreshModels();
      notify(`Маршрут: ${providerId}/${model}`, "ok");
    } catch (err) { notify(errorText(err), "error"); }
  }
  async function loadHarness() { try { setAgents(await request<AgentRow[]>("agents")); setProfiles(await request<{ active: string; items: { id: string; name: string; prompt: string }[] }>("profiles")); setTrajectory(await request<TrajectoryViewer>("trajectory")); } catch (err) { notify(errorText(err), "error"); } }

  function focusComposer() {
    composerRef.current?.focus();
  }

  function focusChatSearch() {
    setSidebarOpen(true);
    window.setTimeout(() => document.getElementById("chat-search")?.focus(), 90);
  }

  // ---------------------------------------------------------- slash commands
  /** Runs a slash command. Returns true when the input was consumed by one. */
  async function runCommand(input: string): Promise<boolean> {
    const { name, args } = parseCommand(input);
    const command = commandByName(name);
    if (!command) return false;
    switch (command.name) {
      case "/help":
        openOverlay("help");
        return true;
      case "/new":
      case "/clear":
        await newChat();
        notify("Новый разговор");
        return true;
      case "/history":
        focusChatSearch();
        return true;
      case "/models":
        setModelMenuSignal((n) => n + 1);
        return true;
      case "/model": {
        if (!args) {
          setModelMenuSignal((n) => n + 1);
          return true;
        }
        const match = resolveModel(models, args);
        if (!match) {
          notify(`Модель «${args}» не найдена в Ollama или среди подключённых провайдеров`, "error");
          return true;
        }
        await selectModel(match.name, match.providerId ?? "ollama");
        return true;
      }
      case "/context":
        openOverlay("context");
        return true;
      case "/tools":
        openOverlay("tools");
        return true;
      case "/status":
        openOverlay("status");
        return true;
      case "/settings":
        openSettings("general");
        return true;
      case "/providers":
        openSettings("providers");
        await loadProviders();
        return true;
      case "/permissions":
        openSettings("tools");
        return true;
      case "/profiles":
        openOverlay("harness");
        await loadHarness();
        return true;
      case "/trajectory":
        openOverlay("harness");
        await loadHarness();
        return true;
      case "/agents":
        openOverlay("harness");
        await loadHarness();
        return true;
      case "/search": {
        if (!args) {
          notify("Укажите запрос: /search <запрос>", "error");
          return true;
        }
        await send(args, true);
        return true;
      }
      case "/exit":
        await quitApp();
        return true;
      case "/workspace":
        await loadWorkspace();
        return true;
      default:
        return false;
    }
  }

  // ---------------------------------------------------------------- effects
  useEffect(() => {
    if (bootedRef.current) return;
    bootedRef.current = true;
    void runBoot();
  }, []);

  useEffect(
    () =>
      onCoreExit(() => {
        generatingRef.current = false;
        setGenerating(false);
        setConnected(false);
        setCoreLost(true);
        setStatusText(null);
        setBootError({
          message: "Ядро AXIOM остановлено",
          hint: "Перезапустите ядро кнопкой ниже или перезапустите приложение.",
          url: "",
        });
        setPhase("error");
      }),
    [],
  );

  useEffect(
    () =>
      onCoreStderr((text) => {
        const clean = text.replace(/\s+$/, "");
        if (!clean) return;
        setDebugLog((log) => [...log.slice(-199), clean]);
      }),
    [],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      if (e.ctrlKey || e.metaKey) {
        if (key === "n") {
          e.preventDefault();
          void newChat();
        } else if (key === "b") {
          e.preventDefault();
          toggleSidebar();
        } else if (key === "k") {
          e.preventDefault();
          focusChatSearch();
        } else if (key === ",") {
          e.preventDefault();
          openSettings("general");
        } else if (key === "/") {
          e.preventDefault();
          focusComposer();
        }
        return;
      }
      if (e.key === "Escape") {
        if (overlay) {
          setOverlay(null);
          return;
        }
        if (settingsOpen) {
          setSettingsOpen(false);
          return;
        }
        if (generatingRef.current) {
          e.preventDefault();
          void cancel();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  /** Restart the Python core and re-run the whole boot probe. */
  async function restartCoreAndBoot() {
    notify("Перезапуск ядра AXIOM…");
    try {
      await restartCore();
      await new Promise((resolve) => window.setTimeout(resolve, 900));
      await runBoot();
      notify("Ядро перезапущено", "ok");
    } catch (err) {
      notify(errorText(err), "error");
    }
  }

  async function switchWorkspace(path: string) {
    try {
      const info = await request<ProjectInfo>("set_workspace", { path });
      setWorkspace((w) => ({ current: info, recent: w?.recent ?? [], pinned: w?.pinned ?? [] }));
      setOpenFile(null);
      setTermHistory([]);
      setPendingTerm(null);
      await Promise.all([loadWorkspace(), loadTree(), loadGit(), refreshChats(), loadProjectList()]);
      await newChat();
      notify(`Проект: ${info.name} (${info.kind})`, "ok");
    } catch (err) {
      notify(errorText(err), "error");
    }
  }

  async function openWorkspaceDialog() {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      const picked = await invoke<string | null>("pick_folder");
      if (picked) await switchWorkspace(picked);
    } catch (err) {
      notify(errorText(err), "error");
    }
  }

  /** Global Chat: drop the active project — no file/terminal tools, global history. */
  async function clearWorkspace() {
    try {
      await request("clear_workspace");
      setOpenFile(null);
      setTermHistory([]);
      setPendingTerm(null);
      setTree([]);
      setGitStatus(null);
      setGitLog(null);
      setConfig(await request<AxiomConfig>("get_config"));
      await Promise.all([loadWorkspace(), refreshChats(), loadProjectList()]);
      await newChat();
      notify("Глобальный чат: проект не активен", "ok");
    } catch (err) {
      notify(errorText(err), "error");
    }
  }

  async function removeWorkspace(path: string) {
    try {
      await request("remove_workspace", { path });
      // The backend store changed (recent + pinned) — refresh both the current
      // workspace and the selector lists, otherwise the removed project keeps
      // rendering from the stale `recent` state.
      await Promise.all([loadWorkspace(), loadProjectList()]);
    } catch (err) {
      notify(errorText(err), "error");
    }
  }

  async function openWorkspaceFile(path: string) {
    try {
      const data = await request<{ ok: boolean; content?: string; error?: string }>("workspace_file", { path });
      if (!data.ok) {
        notify(data.error ?? "Не удалось прочитать файл", "error");
        return;
      }
      setOpenFile({ path, content: data.content ?? "" });
    } catch (err) {
      notify(errorText(err), "error");
    }
  }

  /** Apply a ```diff block from an answer to a workspace file (§17). */
  async function applyPatch(path: string, patch: string): Promise<boolean> {
    try {
      const res = await request<{ ok: boolean; error?: string; path?: string }>("apply_patch", { path, patch });
      if (!res.ok) {
        notify(res.error ?? "Не удалось применить патч", "error");
        return false;
      }
      notify(`Файл обновлён: ${res.path ?? path}`, "ok");
      if (openFile?.path === path) void openWorkspaceFile(path);
      void loadGit(); // the file may now show up as modified
      return true;
    } catch (err) {
      notify(errorText(err), "error");
      return false;
    }
  }

  async function runTerminal(command: string, confirmed = false) {
    try {
      const result = await request<TerminalResult>("run_terminal", { command, confirmed });
      if (result.permission === "ask" && !confirmed) {
        setPendingTerm(command);
        return;
      }
      setPendingTerm(null);
      setTermHistory((h) => [...h.slice(-99), { command, result }]);
      if (!result.ok && result.permission === "granted") {
        notify(result.error ?? "Команда завершилась с ошибкой", "error");
      }
    } catch (err) {
      notify(errorText(err), "error");
    }
  }

  async function confirmTerminal(allow: boolean) {
    const cmd = pendingTerm;
    setPendingTerm(null);
    if (allow && cmd) await runTerminal(cmd, true);
  }

  // ---------------------------------------------- interactive shell session
  async function startShell() {
    try {
      const res = await request<{ running: boolean; output: string }>("shell_start", {});
      setShellRunning(res.running);
      setShellOutput(res.output ?? "");
      if (!res.running) notify("Терминал не запустился", "error");
    } catch (err) {
      notify(errorText(err), "error");
    }
  }

  async function writeShell(line: string) {
    try {
      const res = await request<{ running: boolean; ok: boolean }>("shell_write", { line });
      setShellRunning(res.running);
      if (res.ok) {
        await pollShell();
      } else {
        notify("Не удалось отправить команду в терминал", "error");
      }
    } catch (err) {
      notify(errorText(err), "error");
    }
  }

  /** Drain the shell transcript (the backend returns the whole buffer). */
  async function pollShell() {
    try {
      const res = await request<{ running: boolean; output: string }>("shell_read", {});
      setShellRunning(res.running);
      setShellOutput(res.output ?? "");
    } catch {
      /* the core may be restarting — keep the last output on screen */
    }
  }

  async function stopShell() {
    try {
      const res = await request<{ running: boolean; output: string }>("shell_stop", {});
      setShellRunning(res.running);
      setShellOutput(res.output ?? "");
    } catch {
      setShellRunning(false);
    }
  }

  const accessLabel =
    config?.access_mode === "read_only" ? "R/O" : config?.access_mode === "full" ? "FULL" : "WS";
  const accessTitle =
    config?.access_mode === "read_only"
      ? "AI: только чтение файлов, без изменений и терминала"
      : config?.access_mode === "full"
        ? "AI: полный доступ (осторожно)"
        : "AI: разрешена работа внутри проекта";

  // ------------------------------------------------------------- derived state
  const activeModelInfo = useMemo(
    () => models.find((m) => m.name === activeModel
      && (m.providerId ?? "ollama") === activeModelProvider) ?? null,
    [models, activeModel, activeModelProvider],
  );

  const activeConversation = useMemo(
    () => chats.find((c) => c.id === activeChatId) ?? null,
    [chats, activeChatId],
  );

  const filteredChats = useMemo(() => {
    const query = chatSearch.trim().toLowerCase();
    if (!query) return chats;
    // Title matches first; full-text hits (by id) still show with their snippet.
    return chats.filter(
      (c) => c.title.toLowerCase().includes(query) || chatHits[c.id] !== undefined,
    );
  }, [chats, chatSearch, chatHits]);

  // Debounced full-text search while the sidebar query changes.
  useEffect(() => {
    if (!chatSearch.trim()) {
      setChatHits({});
      return;
    }
    const timer = window.setTimeout(() => void searchChats(chatSearch), 260);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatSearch]);

  const context = useMemo(() => {
    const window = modelDetail?.contextLength ?? activeModelInfo?.contextLength ?? null;
    const numCtx = modelDetail?.numCtx ?? activeModelInfo?.numCtx ?? null;
    const used = lastMetrics?.tokensIn ?? null;
    const ratio = used != null && window ? Math.min(1, used / window) : null;
    let turns = 0;
    let images = 0;
    let toolCalls = 0;
    let sources = 0;
    for (const message of messages) {
      if (message.role === "user" || message.role === "assistant") turns += 1;
      images += message.images?.length ?? 0;
      toolCalls += message.toolCalls.length;
      sources += message.sources.length;
    }
    return { window, numCtx, used, ratio, turns, images, toolCalls, sources };
  }, [messages, lastMetrics, modelDetail, activeModelInfo]);

  const canContinue = useMemo(
    () => messages.some((m) => m.role === "assistant" && m.content.length > 0),
    [messages],
  );
  const canRegenerate = useMemo(() => messages.some((m) => m.role === "user"), [messages]);

  /** A stored chat remembers its model — surface a real mismatch instead of hiding it. */
  const chatModelMismatch =
    activeConversation?.model && activeModel && activeConversation.model !== activeModel
      ? activeConversation.model
      : null;

  // ---------------------------------------------------------------- commands
  return {
    // boot
    phase,
    bootSteps,
    bootError,
    runBoot,
    reconnect,
    restartCore: restartCoreAndBoot,
    // connection
    connected,
    health,
    coreLost,
    // models
    models,
    modelsLoading,
    modelsError,
    activeModel,
    activeModelProvider,
    activeModelInfo,
    modelDetail,
    switchingModel,
    modelMenuSignal,
    refreshModels,
    selectModel,
    // chat
    chats,
    filteredChats,
    activeChatId,
    activeConversation,
    chatSearch,
    setChatSearch,
    chatHits,
    pinChat,
    setChatFolder,
    applyPatch,
    gitStage,
    gitUnstage,
    gitCommit,
    gitShowDiff,
    shellRunning,
    shellOutput,
    startShell,
    writeShell,
    pollShell,
    stopShell,
    warming,
    paletteOpen,
    setPaletteOpen,
    switchBranch,
    messages,
    generating,
    liveState,
    statusText,
    elapsedMs,
    lastMetrics,
    context,
    canContinue,
    canRegenerate,
    chatModelMismatch,
    draft,
    setDraft,
    onOpenModels,
    send,
    cancel,
    regenerate,
    continueGeneration,
    editLastUser,
    newChat,
    openChat,
    deleteChat,
    deleteAllChats,
    renameChat,
    // config
    config,
    saveConfig,
    providerRows,
    providerModels,
    providerLoading,
    loadProviders,
    providerTest,
    providerSaveKey,
    providerSetBaseUrl,
    providerDiscover,
    providerPickModel,
    agents,
    profiles,
    trajectory,
    // workspace
    workspace,
    tree,
    treeLoading,
    openFile,
    setOpenFile,
    loadWorkspace,
    loadTree,
    loadGit,
    switchWorkspace,
    clearWorkspace,
    openWorkspaceDialog,
    removeWorkspace,
    toggleWorkspacePin,
    openWorkspaceFile,
    termHistory,
    pendingTerm,
    runTerminal,
    confirmTerminal,
    gitStatus,
    gitLog,
    accessLabel,
    accessTitle,
    // ui
    sidebarOpen,
    toggleSidebar,
    sidebarWidth,
    setSidebarWidth,
    commitSidebarWidth,
    rightPanelOpen,
    toggleRightPanel,
    rightPanelWidth,
    setRightPanelWidth,
    commitRightPanelWidth,
    settingsOpen,
    setSettingsOpen,
    settingsSection,
    setSettingsSection,
    openSettings,
    overlay,
    openOverlay,
    setOverlay,
    toasts,
    notify,
    tools,
    toolsError,
    status,
    statusError,
    loadTools,
    loadStatus,
    debugLog,
    composerRef,
    runCommand,
    focusComposer,
    // helper exposed for components
    matchingCommands,
    openExternal,
  };
}

export type AxiomStore = ReturnType<typeof useAxiom>;