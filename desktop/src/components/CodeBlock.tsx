import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { copyText } from "../lib/format";

interface Props {
  code: string;
  language?: string;
}

/** Fenced code block with a real copy action and the detected language. */
export default function CodeBlock({ code, language }: Props) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    const ok = await copyText(code);
    if (!ok) return;
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <div className="code-block">
      <div className="code-head">
        <span className="code-lang">{language || "text"}</span>
        <button className="code-copy" onClick={copy} title="Скопировать код">
          {copied ? <Check size={12} strokeWidth={2.2} /> : <Copy size={12} strokeWidth={1.9} />}
          <span>{copied ? "Скопировано" : "Копировать"}</span>
        </button>
      </div>
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  );
}

/** Small icon-only copy button (used for whole answers). */
export function CopyIconButton({
  text,
  title = "Копировать",
  className = "",
}: {
  text: string;
  title?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className={"msg-action " + className}
      title={copied ? "Скопировано" : title}
      onClick={async () => {
        if (await copyText(text)) {
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1400);
        }
      }}
    >
      {copied ? <Check size={13} strokeWidth={2.2} /> : <Copy size={13} strokeWidth={1.9} />}
      <span>{copied ? "Скопировано" : title}</span>
    </button>
  );
}