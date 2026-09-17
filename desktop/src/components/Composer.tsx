import { useEffect, useRef, useState } from "react";
import { ArrowUp, Square, Globe, Plus, X } from "lucide-react";

interface Props {
  generating: boolean;
  disabled: boolean;
  onSend: (text: string, forceSearch: boolean, images?: string[]) => void;
  onCancel: () => void;
  webSearchEnabled: boolean;
  onToggleWebSearch: () => void;
}

const MAX_IMAGES = 4;
const MAX_FILE_BYTES = 10 * 1024 * 1024;

/** Read an image file as base64 (no data: prefix — Ollama wants raw base64). */
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(new Error(`Не удалось прочитать ${file.name}`));
    reader.readAsDataURL(file);
  });
}

/** Collect image files from a clipboard/drag event payload. */
function imageFiles(list: FileList | null | undefined): File[] {
  return Array.from(list ?? []).filter((f) => f.type.startsWith("image/"));
}

export default function Composer(props: Props) {
  const { generating, disabled, onSend, onCancel, webSearchEnabled, onToggleWebSearch } = props;
  const [text, setText] = useState("");
  const [images, setImages] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 220)}px`;
  }, [text]);

  useEffect(() => {
    const focus = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "/") {
        e.preventDefault();
        taRef.current?.focus();
      }
    };
    window.addEventListener("keydown", focus);
    return () => window.removeEventListener("keydown", focus);
  }, []);

  const flash = (message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice((n) => (n === message ? null : n)), 3200);
  };

  const addFiles = async (files: File[]) => {
    if (!files.length) return;
    const room = MAX_IMAGES - images.length;
    if (room <= 0) {
      flash(`Максимум ${MAX_IMAGES} изображения`);
      return;
    }
    const encoded: string[] = [];
    for (const file of files.slice(0, room)) {
      if (file.size > MAX_FILE_BYTES) {
        flash(`${file.name || "изображение"}: больше 10 МБ`);
        continue;
      }
      try {
        encoded.push(await fileToBase64(file));
      } catch (err) {
        flash(String(err));
      }
    }
    if (encoded.length) setImages((prev) => [...prev, ...encoded].slice(0, MAX_IMAGES));
  };

  /** Ctrl+V: images from the clipboard land directly in the composer. */
  const onPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const files = imageFiles(e.clipboardData?.files);
    if (files.length) {
      e.preventDefault();
      void addFiles(files);
    }
  };

  /** Drag & drop images onto the composer. */
  const onDrop = (e: React.DragEvent<HTMLTextAreaElement>) => {
    const files = imageFiles(e.dataTransfer?.files);
    if (files.length) {
      e.preventDefault();
      void addFiles(files);
    }
  };

  const submit = (forceSearch = false) => {
    const clean = text.trim();
    if ((!clean && images.length === 0) || generating || disabled) return;
    onSend(clean, forceSearch, images);
    setText("");
    setImages([]);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.altKey) {
      e.preventDefault();
      submit();
    }
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      submit(true);
    }
  };

  const estimate = Math.max(1, Math.round((text.length + images.length * 1200) / 4));

  return (
    <div className="composer-area">
      <div className={"composer" + (images.length > 0 ? " has-attach" : "")}>
        {notice && <div className="composer-notice">{notice}</div>}
        <textarea
          ref={taRef}
          rows={1}
          placeholder={disabled ? "Ollama недоступна…" : "Спросите Axiom… Ctrl+V — вставить изображение"}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          onDrop={onDrop}
          disabled={disabled}
          spellCheck={false}
        />
        {images.length > 0 && (
          <div className="attach-row inline">
            {images.map((img, i) => (
              <div className="attach-thumb" key={i}>
                <img src={`data:image;base64,${img}`} alt={`вложение ${i + 1}`} />
                <button
                  className="attach-remove"
                  onClick={() => setImages((prev) => prev.filter((_, j) => j !== i))}
                  title="Убрать изображение"
                >
                  <X size={12} strokeWidth={2.2} />
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="composer-row">
          <div className="composer-left">
            <button
              className={"chip" + (webSearchEnabled ? " on" : "")}
              onClick={onToggleWebSearch}
              title="Web Search (Ollama + DuckDuckGo)"
            >
              <Globe size={13} strokeWidth={1.8} />
              <span>Web Search</span>
              <span className={"chip-dot" + (webSearchEnabled ? " on" : "")} />
            </button>
            <button
              className="chip ghost"
              onClick={() => submit(true)}
              disabled={generating || disabled || !text.trim()}
              title="Отправить с принудительным поиском (Ctrl+Enter)"
            >
              <Plus size={13} strokeWidth={1.8} />
              <span>С поиском</span>
            </button>
          </div>
          <div className="composer-right">
            <span className="token-counter" title="Оценка токенов запроса">
              ~{estimate} tok
            </span>
            {generating ? (
              <button className="send-btn stop" onClick={onCancel} title="Остановить (Esc)">
                <Square size={13} strokeWidth={2} fill="currentColor" />
              </button>
            ) : (
              <button
                className="send-btn"
                onClick={() => submit()}
                disabled={(!text.trim() && images.length === 0) || disabled}
                title="Отправить (Enter)"
              >
                <ArrowUp size={16} strokeWidth={2.2} />
              </button>
            )}
          </div>
        </div>
      </div>
      <div className="composer-note">
        Axiom может ошибаться · локальные модели через Ollama · Ctrl+Enter — принудительный web search
      </div>
    </div>
  );
}
