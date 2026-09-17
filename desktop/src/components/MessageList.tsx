import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Brain, ChevronDown, Sparkles, AlertTriangle } from "lucide-react";
import type { LiveMessage } from "../types";
import { SourcesRow, ToolStatus } from "./ToolBits";

interface Props {
  messages: LiveMessage[];
  generating: boolean;
  statusText: string | null;
  welcome: string;
  showReasoning: boolean;
}

export default function MessageList(props: Props) {
  const { messages, generating, statusText, welcome, showReasoning } = props;
  const bottomRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  const onScroll = () => {
    const el = document.querySelector(".chat-scroll");
    if (!el) return;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  };

  useEffect(() => {
    if (stickToBottom.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  });

  if (messages.length === 0) {
    return (
      <div className="chat-scroll">
        <div className="chat-inner welcome-wrap">
          <div className="welcome">
            <div className="welcome-mark">
              <Sparkles size={34} strokeWidth={1.4} />
            </div>
            <h1 className="welcome-title">AXIOM</h1>
            <p className="welcome-sub">{welcome}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-scroll" onScroll={onScroll}>
      <div className="chat-inner">
        {messages.map((m) => (
          <MessageRow key={m.id} message={m} showReasoning={showReasoning} />
        ))}
        {generating && statusText && (
          <div className="status-line">
            <span className="status-dot" />
            {statusText}
          </div>
        )}
        <div ref={bottomRef} className="chat-bottom-anchor" />
      </div>
    </div>
  );
}

function MessageRow({ message, showReasoning }: { message: LiveMessage; showReasoning: boolean }) {
  if (message.role === "user") {
    return (
      <div className="msg user">
        {message.images && message.images.length > 0 && (
          <div className="msg-images">
            {message.images.map((img, i) => (
              <img key={i} src={`data:image;base64,${img}`} alt={`вложение ${i + 1}`} />
            ))}
          </div>
        )}
        {message.content && <div className="msg-user-bubble">{message.content}</div>}
      </div>
    );
  }
  return (
    <div className="msg assistant">
      <ThinkingSection
        thinking={message.thinking}
        streaming={message.streaming}
        visible={showReasoning}
      />
      <ToolStatus calls={message.toolCalls} />
      {message.sources.length > 0 && <SourcesRow sources={message.sources} />}
      {(message.content || message.streaming) && (
        <div className={"markdown" + (message.streaming ? " streaming" : "")}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {message.content}
          </ReactMarkdown>
        </div>
      )}
      {message.error && (
        <div className="msg-error">
          <AlertTriangle size={15} strokeWidth={1.8} />
          <div>
            <div className="msg-error-title">{message.error.message}</div>
            {message.error.hint && <div className="msg-error-hint">{message.error.hint}</div>}
          </div>
        </div>
      )}
      {message.metrics && (
        <div className="msg-metrics">
          {message.metrics.tokensOut != null && <span>{message.metrics.tokensOut} tok</span>}
          {message.metrics.tokensPerSecond != null && (
            <span>{message.metrics.tokensPerSecond.toFixed(1)} tok/s</span>
          )}
          {message.metrics.durationMs > 0 && (
            <span>{(message.metrics.durationMs / 1000).toFixed(1)}s</span>
          )}
        </div>
      )}
    </div>
  );
}

function ThinkingSection({
  thinking,
  streaming,
  visible,
}: {
  thinking: string;
  streaming: boolean;
  visible: boolean;
}) {
  const [open, setOpen] = useState(false);
  const thinkingActive = streaming && thinking.length > 0;

  useEffect(() => {
    if (!streaming) setOpen(false); // collapse after completion
  }, [streaming]);

  if (!visible || !thinking) return null;

  return (
    <div className={"thinking" + (thinkingActive ? " live" : "")}>
      <button className="thinking-toggle" onClick={() => setOpen((v) => !v)}>
        <Brain size={14} strokeWidth={1.8} />
        <span>{thinkingActive ? "Размышляет…" : "Процесс размышления"}</span>
        <ChevronDown
          size={14}
          strokeWidth={1.8}
          className={"chevron" + (open ? " open" : "")}
        />
      </button>
      {(open || thinkingActive) && <div className="thinking-body">{thinking}</div>}
    </div>
  );
}
