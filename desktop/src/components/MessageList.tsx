import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ChevronDown,
  Cpu,
  Pencil,
  RefreshCw,
  Sparkles,
  Square,
} from "lucide-react";
import type { AxiomConfig, LiveMessage } from "../types";
import { MessageError, SourcesList, ToolActivityList } from "./ToolBits";
import CodeBlock, { CopyIconButton } from "./CodeBlock";
import { formatElapsed } from "../lib/format";

interface Props {
  messages: LiveMessage[];
  generating: boolean;
  statusText: string | null;
  liveState: string;
  elapsedMs: number;
  config: AxiomConfig | null;
  modelName: string | null;
  modelCapabilities: string[];
  canContinue: boolean;
  canRegenerate: boolean;
  onRegenerate: () => void;
  onContinue: () => void;
  onEdit: (text: string) => void;
  onOpen: (url: string) => void;
  onSuggestion: (text: string, forceSearch?: boolean) => void;
  onStop: () => void;
}

const SUGGESTIONS: { text: string; search?: boolean }[] = [
  { text: "Что ты умеешь?" },
  { text: "Напиши на Python функцию с обработкой ошибок" },
  { text: "Разбери этот код и предложи улучшения" },
  { text: "Какая сейчас последняя стабильная версия Python?", search: true },
];

/** Human wording of the live backend state (never invented). */
function liveStateLabel(state: string): string {
  switch (state) {
    case "connecting":
      return "Подключение";
    case "thinking":
      return "Размышляет";
    case "tool_call":
      return "Инструмент";
    case "searching":
      return "Веб-поиск";
    case "receiving":
      return "Генерация";
    case "cancelled":
      return "Остановлено";
    case "error":
      return "Ошибка";
    default:
      return "Генерация";
  }
}

export default function MessageList(props: Props) {
  const {
    messages,
    generating,
    statusText,
    liveState,
    elapsedMs,
    config,
    modelName,
    modelCapabilities,
    canContinue,
    canRegenerate,
    onRegenerate,
    onContinue,
    onEdit,
    onOpen,
    onSuggestion,
    onStop,
  } = props;

  const scrollRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);

  const lastUserId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "user") return messages[i].id;
    }
    return null;
  }, [messages]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 140;
  };

  useEffect(() => {
    if (!config?.auto_scroll) return;
    if (!stickRef.current) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, config?.auto_scroll]);

  if (messages.length === 0) {
    return (
      <div className="chat-scroll" ref={scrollRef}>
        <div className="chat-inner welcome-wrap">
          <div className="welcome">
            <div className="welcome-mark">
              <Sparkles size={30} strokeWidth={1.4} />
            </div>
            <h1 className="welcome-title">AXIOM</h1>
            <p className="welcome-sub">Чем Axiom может помочь?</p>
            <div className="welcome-model">
              <Cpu size={13} strokeWidth={1.8} />
              <span>{modelName ?? "модель не выбрана"}</span>
              {modelCapabilities.length > 0 && (
                <span className="welcome-caps">{modelCapabilities.join(" · ")}</span>
              )}
            </div>
            <div className="welcome-suggestions">
              {SUGGESTIONS.map((item) => (
                <button
                  key={item.text}
                  className="suggestion"
                  onClick={() => onSuggestion(item.text, item.search)}
                  title={item.search ? "Отправит с принудительным веб-поиском" : "Отправить этот запрос"}
                >
                  {item.search && <Sparkles size={12} strokeWidth={1.8} />}
                  {item.text}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-scroll" ref={scrollRef} onScroll={onScroll}>
      <div className="chat-inner">
        {messages.map((message) =>
          message.role === "user" ? (
            <UserMessage
              key={message.id}
              message={message}
              editable={message.id === lastUserId && !generating}
              onEdit={onEdit}
            />
          ) : (
            <AssistantMessage
              key={message.id}
              message={message}
              config={config}
              generating={generating}
              liveState={liveState}
              statusText={statusText}
              elapsedMs={elapsedMs}
              canContinue={canContinue}
              canRegenerate={canRegenerate}
              onRegenerate={onRegenerate}
              onContinue={onContinue}
              onOpen={onOpen}
              onStop={onStop}
            />
          ),
        )}
      </div>
    </div>
  );
}

function UserMessage({
  message,
  editable,
  onEdit,
}: {
  message: LiveMessage;
  editable: boolean;
  onEdit: (text: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(message.content);
  const areaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!editing) return;
    const area = areaRef.current;
    if (!area) return;
    area.focus();
    area.style.height = "auto";
    area.style.height = `${area.scrollHeight}px`;
  }, [editing]);

  return (
    <div className={"msg user" + (editing ? " editing" : "")}>
      {!editing && (
        <div className="msg-head">
          <span className="msg-role">YOU</span>
          {editable && (
            <div className="msg-tools">
              <button
                className="msg-action"
                title="Изменить и отправить заново"
                onClick={() => {
                  setDraft(message.content);
                  setEditing(true);
                }}
              >
                <Pencil size={13} strokeWidth={1.9} />
                <span>Изменить</span>
              </button>
            </div>
          )}
        </div>
      )}

      {message.images && message.images.length > 0 && (
        <div className="msg-images">
          {message.images.map((image, index) => (
            <img key={index} src={image} alt={`вложение ${index + 1}`} />
          ))}
        </div>
      )}

      {editing ? (
        <div className="edit-box">
          <div className="edit-label">
            <Pencil size={12} strokeWidth={2} />
            <span>Редактирование сообщения</span>
            <span className="edit-label-note">ответ ниже будет сгенерирован заново</span>
          </div>
          <textarea
            ref={areaRef}
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value);
              const area = event.target;
              area.style.height = "auto";
              area.style.height = `${area.scrollHeight}px`;
            }}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                event.preventDefault();
                setEditing(false);
              }
              if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                event.preventDefault();
                if (draft.trim()) {
                  setEditing(false);
                  onEdit(draft);
                }
              }
            }}
            spellCheck={false}
          />
          <div className="edit-actions">
            <span className="edit-hint">
              <kbd>Ctrl+Enter</kbd> — отправить · <kbd>Esc</kbd> — отмена
            </span>
            <div className="edit-actions-btns">
              <button className="btn ghost small" onClick={() => setEditing(false)}>
                Отмена
              </button>
              <button
                className="btn primary small"
                disabled={!draft.trim()}
                onClick={() => {
                  setEditing(false);
                  onEdit(draft);
                }}
              >
                Отправить заново
              </button>
            </div>
          </div>
        </div>
      ) : (
        message.content && <div className="msg-user-bubble">{message.content}</div>
      )}
    </div>
  );
}

function AssistantMessage({
  message,
  config,
  generating,
  liveState,
  statusText,
  elapsedMs,
  canContinue,
  canRegenerate,
  onRegenerate,
  onContinue,
  onOpen,
  onStop,
}: {
  message: LiveMessage;
  config: AxiomConfig | null;
  generating: boolean;
  liveState: string;
  statusText: string | null;
  elapsedMs: number;
  canContinue: boolean;
  canRegenerate: boolean;
  onRegenerate: () => void;
  onContinue: () => void;
  onOpen: (url: string) => void;
  onStop: () => void;
}) {
  const streaming = message.streaming;
  const cancelled = message.metrics?.state === "cancelled";
  const failed = message.metrics?.state === "error" || !!message.error;

  return (
    <div className="msg assistant">
      <div className="msg-head">
        <span className="msg-role">AXIOM</span>
        <div className="msg-tools">
          {message.content && <CopyIconButton text={message.content} title="Копировать ответ" />}
        </div>
      </div>

      <ThinkingSection
        thinking={message.thinking}
        streaming={streaming}
        visible={config?.show_reasoning ?? true}
        expandedByDefault={config?.reasoning_expanded ?? false}
      />

      <ToolActivityList calls={message.toolCalls} />

      {message.sources.length > 0 && <SourcesList sources={message.sources} onOpen={onOpen} />}

      {message.content &&
        (config?.render_markdown ?? true ? (
          <div className={"markdown" + (streaming ? " streaming" : "")}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code: MarkdownCode,
                a: ({ href, children }) => (
                  <a
                    href={href}
                    title={href}
                    onClick={(event) => {
                      event.preventDefault();
                      if (href) onOpen(href);
                    }}
                  >
                    {children}
                  </a>
                ),
                table: ({ children }) => (
                  <div className="table-wrap">
                    <table>{children}</table>
                  </div>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
            {streaming && <span className="caret" />}
          </div>
        ) : (
          <div className={"markdown plain" + (streaming ? " streaming" : "")}>
            {message.content}
            {streaming && <span className="caret" />}
          </div>
        ))}

      {streaming && (
        <div className="msg-live">
          <span className="live-dot" />
          {statusText ? (
            <span className="live-label">{statusText}</span>
          ) : (
            <span className="live-label">{liveStateLabel(liveState)}</span>
          )}
          <span className="live-sep" />
          <span className="live-time">{formatElapsed(elapsedMs)}</span>
          {generating && (
            <button className="stop-inline" onClick={onStop} title="Остановить (Esc)">
              <Square size={10} strokeWidth={2.2} fill="currentColor" />
              <span>Стоп</span>
            </button>
          )}
        </div>
      )}

      {!streaming && cancelled && !message.content && (
        <div className="msg-note">
          <Square size={12} strokeWidth={2} />
          <span>Генерация остановлена</span>
        </div>
      )}

      {message.error && <MessageError message={message.error.message} hint={message.error.hint} />}

      {!streaming && !failed && (config?.show_metrics ?? true) && message.metrics && (
        <div className="msg-metrics">
          {message.metrics.tokensOut != null && <span>{message.metrics.tokensOut} tok out</span>}
          {message.metrics.tokensIn != null && <span>{message.metrics.tokensIn} tok in</span>}
          {message.metrics.tokensPerSecond != null && (
            <span>{message.metrics.tokensPerSecond.toFixed(1)} tok/s</span>
          )}
          {message.metrics.durationMs > 0 && <span>{formatElapsed(message.metrics.durationMs)}</span>}
        </div>
      )}
    </div>
  );
}

/** Markdown `code` renderer: fenced blocks get the AXIOM code card. */
function MarkdownCode(props: { className?: string; children?: ReactNode }) {
  const { className, children } = props;
  const language = /language-([\w+#-]+)/.exec(className ?? "")?.[1];
  const text = Array.isArray(children) ? children.join("") : String(children ?? "");
  const trimmed = text.replace(/\n$/, "");
  if (!language && !trimmed.includes("\n")) {
    return <code className="md-inline">{children}</code>;
  }
  return <CodeBlock code={trimmed} language={language} />;
}

/** Real reasoning only: hidden when the model sends none, collapsible always. */
function ThinkingSection({
  thinking,
  streaming,
  visible,
  expandedByDefault,
}: {
  thinking: string;
  streaming: boolean;
  visible: boolean;
  expandedByDefault: boolean;
}) {
  const active = streaming && thinking.length > 0;
  const [open, setOpen] = useState(expandedByDefault);

  useEffect(() => {
    setOpen(active ? true : expandedByDefault);
  }, [active, expandedByDefault]);

  if (!visible || !thinking) return null;

  return (
    <div className={"thinking" + (active ? " live" : "")}>
      <button className="thinking-toggle" onClick={() => setOpen((v) => !v)} title="Размышления модели">
        {active ? <span className="think-glyph live" /> : <span className="think-glyph done">✓</span>}
        <span>{active ? "Размышляет…" : "Размышление ✓"}</span>
        <span className="thinking-meta">
          {thinking.split("\n").filter(Boolean).length} строк
        </span>
        <ChevronDown size={14} strokeWidth={1.8} className={"chevron" + (open ? " open" : "")} />
      </button>
      {(open || active) && <div className="thinking-body">{thinking}</div>}
    </div>
  );
}