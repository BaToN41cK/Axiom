import type { ReactNode, RefObject } from "react";
import { useMemo, useEffect, useState } from "react";
import { ArrowUp, CornerDownLeft, Globe, Image as ImageIcon, Loader2, Square, X } from "lucide-react";
import type { AxiomConfig } from "../types";
import { matchingCommands, type SlashCommand } from "../lib/commands";
import { formatCount } from "../lib/format";

interface Props {
  generating: boolean;
  disabled: boolean;
  draft: string;
  onDraftChange: (value: string) => void;
  onSend: (text: string, forceSearch: boolean, images: string[]) => void;
  onCommand: (input: string) => void;
  onCancel: () => void;
  webSearchEnabled: boolean;
  onToggleWebSearch: () => void;
  config: AxiomConfig | null;
  modelName: string | null;
  modelSupportsVision: boolean | null;
  context: { used: number | null; window: number | null; ratio: number | null };
  onOpenContext: () => void;
  composerRef: RefObject<HTMLTextAreaElement>;
  /** Compact model selector rendered inside the composer row. */
  modelSelector?: ReactNode;
}


/** Read an image file as a data URL (rendered directly in the composer). */
function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error(`Не удалось прочитать ${file.name}`));
    reader.readAsDataURL(file);
  });
}

function imageFiles(list: FileList | null | undefined): File[] {
  return Array.from(list ?? []).filter((file) => file.type.startsWith("image/"));
}

export default function Composer(props: Props) {
  const {
    generating,
    disabled,
    draft,
    onDraftChange,
    onSend,
    onCommand,
    onCancel,
    webSearchEnabled,
    onToggleWebSearch,
    modelSupportsVision,
    context,
    onOpenContext,
    composerRef,
  } = props;

  const MAX_IMAGES = 3;
  const MAX_FILE_BYTES = 10 * 1024 * 1024;

  const [images, setImages] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [paletteIndex, setPaletteIndex] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const commands = useMemo<SlashCommand[]>(() => {
    const trimmed = draft.trim();
    if (!trimmed.startsWith("/")) return [];
    return matchingCommands(trimmed);
  }, [draft]);

  useEffect(() => {
    setPaletteOpen(commands.length > 0);
    setPaletteIndex(0);
  }, [commands]);

  // Auto-grow the textarea up to a sane ceiling.
  useEffect(() => {
    const area = composerRef.current;
    if (!area) return;
    area.style.height = "auto";
    area.style.height = `${Math.min(area.scrollHeight, 232)}px`;
  }, [draft, composerRef]);

  const flash = (message: string) => {
    setNotice(message);
    window.setTimeout(() => setNotice((current) => (current === message ? null : current)), 3400);
  };

  const addFiles = async (files: File[]) => {
    if (!files.length) return;
    if (modelSupportsVision === false) {
      flash("Текущая модель не поддерживает изображения — переключитесь на vision-модель");
      return;
    }
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
        encoded.push(await fileToDataUrl(file));
      } catch (err) {
        flash(String(err));
      }
    }
    if (encoded.length) setImages((current) => [...current, ...encoded].slice(0, MAX_IMAGES));
  };

  const submit = (forceSearch = false) => {
    if (generating || disabled) return;
    const text = draft.trim();
    if (!text && images.length === 0) return;
    onSend(text, forceSearch, images);
    onDraftChange("");
    setImages([]);
  };

  const acceptCommand = (command: SlashCommand) => {
    const needsArgument = command.argumentHint != null;
    onDraftChange(`${command.name} `);
    setPaletteOpen(false);
    if (!needsArgument) {
      void onCommand(command.name);
      onDraftChange("");
    }
    composerRef.current?.focus();
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (paletteOpen && commands.length > 0) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setPaletteIndex((index) => Math.min(commands.length - 1, index + 1));
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setPaletteIndex((index) => Math.max(0, index - 1));
        return;
      }
      if (event.key === "Tab" || (event.key === "Enter" && !event.shiftKey)) {
        event.preventDefault();
        const selected = commands[paletteIndex];
        if (selected) acceptCommand(selected);
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setPaletteOpen(false);
        return;
      }
    }
    if (event.key === "Enter" && !event.shiftKey && !event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault();
      if (draft.trim().startsWith("/") && !images.length) {
        onCommand(draft.trim());
        onDraftChange("");
        return;
      }
      submit(false);
    }
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      submit(true);
    }
  };

  const estimate = Math.max(1, Math.round((draft.length + images.length * 1200) / 4));

  return (
    <div className="composer-area">
      {paletteOpen && (
        <div className="palette" role="listbox">
          <div className="palette-head">COMMANDS</div>
          {commands.map((command, index) => (
            <button
              key={command.name}
              role="option"
              aria-selected={index === paletteIndex}
              className={"palette-item" + (index === paletteIndex ? " cursor" : "")}
              onMouseEnter={() => setPaletteIndex(index)}
              onClick={() => acceptCommand(command)}
            >
              <span className="palette-name">
                {command.name}
                {command.argumentHint ? <span className="palette-arg"> {command.argumentHint}</span> : null}
              </span>
              <span className="palette-desc">{command.description}</span>
            </button>
          ))}
          <div className="palette-foot">
            <CornerDownLeft size={11} strokeWidth={2} /> выбрать · ↑↓ навигация · Esc закрыть
          </div>
        </div>
      )}

      <div className={"composer" + (images.length > 0 ? " has-attach" : "")}>
        {notice && <div className="composer-notice">{notice}</div>}

        {images.length > 0 && (
          <div className="attach-row inline">
            {images.map((image, index) => (
              <div className="attach-thumb" key={index}>
                <img src={image} alt={`вложение ${index + 1}`} />
                <button
                  className="attach-remove"
                  onClick={() => setImages((prev) => prev.filter((_, i) => i !== index))}
                  title="Убрать изображение"
                >
                  <X size={12} strokeWidth={2.2} />
                </button>
              </div>
            ))}
          </div>
        )}

        <textarea
          ref={composerRef}
          rows={1}
          placeholder={
            disabled ? "Ollama недоступна — проверьте подключение" : "Спросите Axiom…  / — команды, Ctrl+V — изображение"
          }
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={onKeyDown}
          onPaste={(event) => {
            const files = imageFiles(event.clipboardData?.files);
            if (files.length) {
              event.preventDefault();
              void addFiles(files);
            }
          }}
          onDrop={(event) => {
            const files = imageFiles(event.dataTransfer?.files);
            if (files.length) {
              event.preventDefault();
              void addFiles(files);
            }
          }}
          disabled={disabled}
          spellCheck={false}
        />

        <div className="composer-row">
          <div className="composer-left">
            {props.modelSelector}
            <button
              className={"chip" + (webSearchEnabled ? " on" : "")}
              onClick={onToggleWebSearch}
              title="Веб-поиск: агент ищет в интернете, если нужно"
            >
              <Globe size={13} strokeWidth={1.8} />
              <span>Web Search</span>
              <span className={"chip-dot" + (webSearchEnabled ? " on" : "")} />
            </button>
            {modelSupportsVision !== false && (
              <label className="chip ghost" title="Прикрепить изображение (Ctrl+V или drag & drop)">
                <ImageIcon size={13} strokeWidth={1.8} />
                <span>Фото</span>
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  hidden
                  onChange={(event) => {
                    void addFiles(imageFiles(event.target.files));
                    event.target.value = "";
                  }}
                />
              </label>
            )}
          </div>

          <div className="composer-right">
            <button className="ctx-chip" onClick={onOpenContext} title="Контекст: токены, сообщения, инструменты">
              {context.used != null || context.window != null ? (
                <span>
                  {formatCount(context.used)} / {formatCount(context.window)} tok
                </span>
              ) : (
                <span>ctx —</span>
              )}
            </button>
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
                disabled={(!draft.trim() && images.length === 0) || disabled}
                title="Отправить (Enter)"
              >
                {disabled ? <Loader2 size={15} className="spin" /> : <ArrowUp size={16} strokeWidth={2.2} />}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}