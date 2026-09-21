// Shared types mirroring axiom.core.events / bridge payloads.

export type Role = "user" | "assistant" | "system" | "tool";

export type Capability = "completion" | "tools" | "thinking" | "vision";

export interface ProjectInfo {
  path: string;
  name: string;
  kind: string;
  git: boolean;
  branch: string | null;
  entries: string[];
  /** Whether this project is pinned */
  pinned?: boolean;
}

export interface ProjectManagerData {
  current: ProjectInfo | null;
  recent: ProjectInfo[];
  pinned: ProjectInfo[];
}

export interface CreateProjectOptions {
  path: string;
  name?: string;
  template?: string; // e.g., "empty", "node", "python", etc.
}

export interface ProjectSearchResult {
  matches: ProjectInfo[];
  query: string;
  total: number;
}

export interface WorkspaceState {
  current: ProjectInfo | null;
  recent: ProjectInfo[];
  pinned: ProjectInfo[];
}

export interface TreeNode {
  name: string;
  dir: boolean;
  path: string;
  children?: TreeNode[];
}

export interface TerminalResult {
  ok: boolean;
  content?: string;
  error?: string | null;
  exit_code?: number | null;
  cwd?: string | null;
  permission: "granted" | "ask" | "blocked";
  command?: string;
}

export interface ModelInfo {
  name: string;
  displayName: string;
  sizeGb: number;
  sizeBytes: number;
  parameterSize: string;
  quantization: string;
  family: string;
  capabilities: string[];
  contextLength: number | null;
  numCtx: number | null;
  /** Ollama reports the model as resident in memory (/api/ps). */
  loaded: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  model: string | null;
  createdAt: number;
  updatedAt: number;
  messageCount: number;
  messages?: StoredMessage[];
}

export interface StoredMessage {
  role: Role;
  content: string;
  thinking?: string | null;
  name?: string | null;
  images?: string[];
}

export type Density = "compact" | "comfortable" | "spacious";

export interface AxiomConfig {
  ollama_url: string;
  model: string | null;
  think: boolean | null;
  web_search_enabled: boolean;
  workspace_tools_enabled: boolean;
  workspace_root: string | null;
  access_mode: "read_only" | "workspace" | "full";
  terminal_enabled: boolean;
  search_max_sources: number;
  search_read_sources: number;
  search_timeout: number;
  history_limit: number;
  show_reasoning: boolean;
  reasoning_expanded: boolean;
  theme: string;
  animations: boolean;
  save_history: boolean;
  temperature: number | null;
  system_prompt: string | null;
  density: Density;
  font_size: number;
  sidebar_open: boolean;
  sidebar_width: number;
  render_markdown: boolean;
  auto_scroll: boolean;
  show_metrics: boolean;
  show_context: boolean;
}

export interface SourceItem {
  index: number;
  title: string;
  url: string;
  snippet: string;
}

export interface DoneMetrics {
  state: string;
  durationMs: number;
  tokensOut: number | null;
  tokensIn: number | null;
  tokensPerSecond: number | null;
}

export type CoreEvent =
  | { type: "reasoning"; text: string }
  | { type: "content"; text: string }
  | { type: "tool_call"; name: string; arguments: Record<string, unknown> }
  | { type: "tool_result"; name: string; ok: boolean; content: string; error: string | null; durationMs: number }
  | { type: "search_result"; query: string; sources: SourceItem[] }
  | { type: "status"; state: string; detail: string | null }
  | { type: "error"; message: string; kind: string; hint: string | null }
  | ({ type: "done" } & DoneMetrics);

export type ToolState = "running" | "ok" | "failed" | "cancelled";

export interface ToolActivity {
  name: string;
  /** Human readable target: the search query, the page URL, ... */
  detail: string;
  state: ToolState;
  durationMs?: number;
  error?: string | null;
  /** Real results of a search/fetch tool, when it produced any. */
  sources?: SourceItem[];
}

export interface LiveMessage {
  id: string;
  role: Role;
  content: string;
  thinking: string;
  streaming: boolean;
  error?: { message: string; hint: string | null } | null;
  toolCalls: ToolActivity[];
  sources: SourceItem[];
  metrics?: DoneMetrics | null;
  createdAt: number;
  /** Base64 images attached by the user (vision models). */
  images?: string[];
}

export interface HealthReport {
  available: boolean;
  version: string | null;
  url: string;
}

export interface StartupReport {
  available: boolean;
  version: string | null;
  error: string | null;
  hint: string | null;
  models: ModelInfo[];
  selected: ModelInfo | null;
  state: { state: string; model: string | null };
}

export interface StatusReport {
  state: string;
  model: string | null;
  lastMetrics: Partial<DoneMetrics>;
  ollamaUrl: string;
  version: string | null;
  activeModel: ModelInfo | null;
  historyCount: number;
  configPath: string;
  busy: boolean;
}

export interface ToolInfo {
  name: string;
  description: string;
  permission: string;
}

export interface SendResult {
  state: string;
  lastMetrics: Partial<DoneMetrics>;
  conversation: Conversation;
  activeModel: ModelInfo | null;
}
