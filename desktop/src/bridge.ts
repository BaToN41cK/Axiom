import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

type Resolver = { resolve: (v: unknown) => void; reject: (e: Error) => void };

const pending = new Map<number, Resolver>();

export type CoreEventHandler = (event: unknown) => void;
const eventHandlers = new Set<CoreEventHandler>();

let initialized = false;

async function ensureListener() {
  if (initialized) return;
  initialized = true;
  await listen<unknown>("bridge://line", (event) => {
    const payload = event.payload as {
      type?: string;
      req?: number;
      ok?: boolean;
      data?: unknown;
      error?: string;
      event?: unknown;
    };
    if (payload.type === "event" && payload.event) {
      for (const handler of eventHandlers) handler(payload.event);
      return;
    }
    if (payload.type === "reply" && typeof payload.req === "number") {
      const resolver = pending.get(payload.req);
      if (!resolver) return;
      pending.delete(payload.req);
      if (payload.ok) resolver.resolve(payload.data);
      else resolver.reject(new Error(payload.error || "bridge error"));
    }
  });
}

/** Fire-and-await JSONL request to the Python core. */
export async function request<T = unknown>(
  cmd: string,
  args: Record<string, unknown> = {},
): Promise<T> {
  await ensureListener();
  const req = Date.now() * 1000 + Math.floor(Math.random() * 1000);
  return await new Promise<T>((resolve, reject) => {
    pending.set(req, {
      resolve: resolve as (v: unknown) => void,
      reject,
    });
    void invoke("bridge_request", { payload: { req, cmd, args } }).catch(reject);
  });
}

/** Restart the Python core subprocess (used after Ollama restarts). */
export async function restartCore(): Promise<void> {
  await invoke("bridge_restart");
}

/** Subscribe to async core events (streaming, status, done...). */
export function onCoreEvent(handler: CoreEventHandler): () => void {
  eventHandlers.add(handler);
  return () => {
    eventHandlers.delete(handler);
  };
}
