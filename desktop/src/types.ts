// Shared types mirroring axiom.core.events / bridge payloads.

export type Role = "user" | "assistant" | "system" | "tool";

export interface ModelInfo {
  name: string;
  displayName: string;
  sizeGb: number;
  parameterSize: string;
  capabilities: string[];
  contextLength: number | null;
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

export interface AxiomConfig {
  ollama_url: string;
  model: string | null;
  think: boolean | null;
  web_search_enabled: boolean;
  search_max_sources: number;
  search_read_sources: number;
  show_reasoning: boolean;
  reasoning_expanded: boolean;
  theme: string;
  animations: boolean;
  save_history: boolean;
  temperature: number | null;
  system_prompt: string | null;
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
  /** Base64 images attached by the user (vision models). */
  images?: string[];
}

export interface ToolActivity {
  name: string;
  detail: string;
  state: "running" | "ok" | "failed";
  durationMs?: number;
}
