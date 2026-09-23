import { Activity, AlertTriangle, Globe, Info, Loader2, RefreshCw, X, Wrench } from "lucide-react";
import type { AgentRow, ModelInfo, ProviderRow, StatusReport, ToolInfo, TrajectoryViewer } from "../types";
import { SHORTCUTS, COMMANDS } from "../lib/commands";
import { formatCount, formatDuration, formatBytes } from "../lib/format";
import type { Overlay } from "../hooks/useAxiom";

interface ContextInfo {
  window: number | null;
  numCtx: number | null;
  used: number | null;
  ratio: number | null;
  turns: number;
  images: number;
  toolCalls: number;
  sources: number;
}

interface Props {
  overlay: Overlay;
  onClose: () => void;
  model: ModelInfo | null;
  context: ContextInfo;
  status: StatusReport | null;
  statusError: string | null;
  tools: ToolInfo[] | null;
  toolsError: string | null;
  onReload: () => void;
  agents: AgentRow[];
  providers: ProviderRow[];
  trajectory: TrajectoryViewer | null;
}

const STATE_LABELS: Record<string, string> = {
  idle: "Ожидание",
  connecting: "Подключение",
  thinking: "Размышляет",
  tool_call: "Инструмент",
  searching: "Веб-поиск",
  receiving: "Генерация",
  completed: "Завершено",
  cancelled: "Остановлено",
  error: "Ошибка",
};

export default function OverlayPanel(props: Props) {
  const { overlay, onClose, model, context, status, statusError, tools, toolsError, onReload, agents, providers, trajectory } = props;
  if (!overlay) return null;

  const title =
    overlay === "help"
      ? "Справка"
      : overlay === "status"
        ? "Состояние AXIOM"
        : overlay === "tools"
          ? "Инструменты агента"
          : overlay === "harness"
            ? "Harness"
            : "Контекст";

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className={"modal panel-" + overlay} onClick={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <h2>{title}</h2>
          <div className="modal-head-actions">
            {(overlay === "status" || overlay === "tools" || overlay === "context") && (
              <button className="icon-btn" onClick={onReload} title="Обновить данные">
                <RefreshCw size={15} strokeWidth={1.8} />
              </button>
            )}
            <button className="icon-btn" onClick={onClose} title="Закрыть (Esc)">
              <X size={16} strokeWidth={1.8} />
            </button>
          </div>
        </div>
        <div className="modal-body">
          {overlay === "help" && <HelpBody />}
          {overlay === "status" && (
            <StatusBody status={status} error={statusError} model={model} />
          )}
          {overlay === "tools" && <ToolsBody tools={tools} error={toolsError} model={model} />}
          {overlay === "context" && <ContextBody context={context} model={model} />}
          {overlay === "harness" && <HarnessBody agents={agents} providers={providers} trajectory={trajectory} />}
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="info-row">
      <span className="info-label">{label}</span>
      <span className="info-value">{value}</span>
    </div>
  );
}

function HelpBody() {
  return (
    <div className="help">
      <div className="help-section">
        <div className="help-title">
          <Info size={14} strokeWidth={1.8} /> Команды
        </div>
        <div className="help-grid">
          {COMMANDS.map((command) => (
            <div key={command.name} className="help-row">
              <code>
                {command.name}
                {command.argumentHint ? ` ${command.argumentHint}` : ""}
              </code>
              <span>{command.description}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="help-section">
        <div className="help-title">
          <Activity size={14} strokeWidth={1.8} /> Клавиши
        </div>
        <div className="help-grid">
          {SHORTCUTS.map((shortcut) => (
            <div key={shortcut.keys} className="help-row">
              <kbd>{shortcut.keys}</kbd>
              <span>{shortcut.label}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="help-note">
        AXIOM работает локально через Ollama: reasoning, инструменты, источники и метрики показываются
        только тогда, когда их действительно вернул бэкенд.
      </div>
    </div>
  );
}

function StatusBody({
  status,
  error,
  model,
}: {
  status: StatusReport | null;
  error: string | null;
  model: ModelInfo | null;
}) {
  if (error) {
    return (
      <div className="panel-error">
        <AlertTriangle size={15} strokeWidth={1.9} />
        <span>{error}</span>
      </div>
    );
  }
  if (!status) {
    return (
      <div className="panel-loading">
        <Loader2 size={15} className="spin" /> Читаю состояние ядра…
      </div>
    );
  }
  const metrics = status.lastMetrics ?? {};
  return (
    <div className="info-list">
      <Row label="Ollama" value={status.ollamaUrl} />
      <Row label="Версия Ollama" value={status.version ?? "недоступна"} />
      <Row label="Состояние" value={STATE_LABELS[status.state] ?? status.state} />
      <Row label="Активная модель" value={status.activeModel?.displayName ?? model?.displayName ?? "—"} />
      <Row label="Генерация" value={status.busy ? "выполняется" : "не выполняется"} />
      <Row label="Разговоров в истории" value={String(status.historyCount)} />
      <Row label="Конфигурация" value={<code>{status.configPath}</code>} />
      {metrics.tokensOut != null && <Row label="Токенов (последний ответ)" value={String(metrics.tokensOut)} />}
      {metrics.tokensIn != null && <Row label="Токенов промпта" value={String(metrics.tokensIn)} />}
      {metrics.tokensPerSecond != null && (
        <Row label="Скорость" value={`${metrics.tokensPerSecond.toFixed(1)} tok/s`} />
      )}
      {metrics.durationMs != null && <Row label="Длительность" value={formatDuration(metrics.durationMs)} />}
    </div>
  );
}

function ToolsBody({
  tools,
  error,
  model,
}: {
  tools: ToolInfo[] | null;
  error: string | null;
  model: ModelInfo | null;
}) {
  const canUseTools = model ? model.capabilities.includes("tools") : null;
  return (
    <div className="info-list">
      {canUseTools === false && (
        <div className="panel-note">
          <AlertTriangle size={14} strokeWidth={1.9} />
          <span>
            {model?.displayName ?? "Текущая модель"} не сообщает о поддержке инструментов — вызовы через
            неё недоступны, но веб-поиск всегда можно запустить принудительно.
          </span>
        </div>
      )}
      {error && (
        <div className="panel-error">
          <AlertTriangle size={15} strokeWidth={1.9} />
          <span>{error}</span>
        </div>
      )}
      {!error && !tools && (
        <div className="panel-loading">
          <Loader2 size={15} className="spin" /> Читаю инструменты агента…
        </div>
      )}
      {tools?.map((tool) => (
        <div key={tool.name} className="tool-row">
          <div className="tool-row-head">
            <Wrench size={14} strokeWidth={1.8} />
            <code>{tool.name}</code>
            <span className="tool-perm">{tool.permission}</span>
          </div>
          <div className="tool-desc">{tool.description}</div>
        </div>
      ))}
      {tools && tools.length === 0 && <Row label="Инструменты" value="агент не сообщает ни об одном" />}
    </div>
  );
}

function ContextBody({ context, model }: { context: ContextInfo; model: ModelInfo | null }) {
  const bar = context.ratio == null ? null : Math.round(context.ratio * 100);
  return (
    <div className="info-list">
      <Row label="Модель" value={model?.displayName ?? "—"} />
      <Row
        label="Окно контекста"
        value={context.window != null ? `${formatCount(context.window)} токенов` : "модель не сообщает"}
      />
      {context.numCtx != null && <Row label="num_ctx" value={formatCount(context.numCtx)} />}
      <Row
        label="Использовано (промпт)"
        value={context.used != null ? `${formatCount(context.used)} токенов` : "—"}
      />
      {bar != null && (
        <div className="ctx-bar-row">
          <div className="ctx-bar">
            <div className="ctx-bar-fill" style={{ width: `${bar}%` }} />
          </div>
          <span className="ctx-bar-label">{bar}%</span>
        </div>
      )}
      <Row label="Сообщений" value={String(context.turns)} />
      <Row label="Файлов/изображений" value={String(context.images)} />
      <Row label="Вызовов инструментов" value={String(context.toolCalls)} />
      <Row label="Источников поиска" value={String(context.sources)} />
      {context.used == null && (
        <div className="panel-note">
          <Globe size={14} strokeWidth={1.8} />
          <span>Точное потребление токенов появится после первой генерации — AXIOM не выдумывает цифры.</span>

        </div>
      )}
      <Row label="Размер модели" value={formatBytes(model?.sizeBytes ?? null) || "—"} />
      <Row label="Параметры" value={model?.parameterSize || "—"} />
      <Row label="Квантование" value={model?.quantization || "—"} />
    </div>
  );
}

function HarnessBody({ agents, providers, trajectory }: { agents: AgentRow[]; providers: ProviderRow[]; trajectory: TrajectoryViewer | null }) {
  return <div className="info-list">
    <div className="help-section"><div className="help-title">Permissions</div><div className="panel-note">ask · auto_approve_safe · auto_approve_all</div></div>
    <div className="help-section"><div className="help-title">Providers</div>{providers.map((p) => <div className="info-row" key={p.id}><span className="info-label">{p.label}</span><span className="info-value">{p.status}</span></div>)}</div>
    <div className="help-section"><div className="help-title">Agents</div>{agents.map((a) => <div className="info-row" key={a.id}><span className="info-label">{a.label}</span><span className="info-value">{a.provider_id}/{a.model || "auto"}</span></div>)}</div>
    <div className="help-section"><div className="help-title">Trajectory</div>{(trajectory?.lines ?? []).slice(-30).map((e) => <div className="info-row" key={e.seq}><span className="info-label">{e.time} · {e.kind}</span><span className="info-value">{e.summary}</span></div>)}</div>
  </div>;
}
