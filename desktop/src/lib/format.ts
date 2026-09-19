/** Small, dependency-free formatting helpers shared by the AXIOM components. */

const KB = 1024;
const MB = KB * 1024;
const GB = MB * 1024;

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return "";
  if (bytes >= GB) return `${(bytes / GB).toFixed(2)} GB`;
  if (bytes >= MB) return `${(bytes / MB).toFixed(0)} MB`;
  if (bytes >= KB) return `${(bytes / KB).toFixed(0)} KB`;
  return `${bytes} B`;
}

/** 12345 -> "12.3K" (used for token counters). */
export function formatCount(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
  return String(value);
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null || ms <= 0) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

/** Elapsed time of a running generation, e.g. "3.4s". */
export function formatElapsed(ms: number): string {
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60_000);
  return `${minutes}m ${String(Math.floor((ms % 60_000) / 1000)).padStart(2, "0")}s`;
}

export function formatRelativeTime(seconds: number): string {
  const delta = Math.max(0, Date.now() / 1000 - seconds);
  if (delta < 60) return "только что";
  if (delta < 3600) return `${Math.floor(delta / 60)} мин назад`;
  if (delta < 86400) return `${Math.floor(delta / 3600)} ч назад`;
  if (delta < 86400 * 7) return `${Math.floor(delta / 86400)} дн назад`;
  return new Date(seconds * 1000).toLocaleDateString();
}

export function formatTime(seconds: number): string {
  return new Date(seconds * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** "deepseek-r1:8b" -> "DeepSeek R1 8B" — a fallback when the bridge sends no label. */
export function prettyModelName(name: string): string {
  const [base, tag] = name.split(":");
  const words = base
    .split("/")
    .pop()!
    .replace(/[_-]/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((w) => (w.length <= 3 && /^[a-z]+$/i.test(w) ? w.toUpperCase() : w[0].toUpperCase() + w.slice(1)));
  return [words.join(" "), tag && tag !== "latest" ? tag.toUpperCase() : ""].filter(Boolean).join(" ");
}

/** Capability helpers — never optimistic: unknown capabilities are "unknown". */
export function supports(model: ModelInfoLike | null | undefined, capability: string): boolean | null {
  if (!model || !model.capabilities || model.capabilities.length === 0) return null;
  if (model.capabilities.includes(capability)) return true;
  return ["completion", "tools", "thinking", "vision"].includes(capability) ? false : null;
}

interface ModelInfoLike {
  capabilities: string[];
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/** Composer keeps data URLs for preview; Ollama wants raw base64. */
export function stripDataUrl(image: string): string {
  const comma = image.indexOf(",");
  return image.startsWith("data:") && comma >= 0 ? image.slice(comma + 1) : image;
}
