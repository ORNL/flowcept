/** Formatting helpers for timestamps, durations, and bytes. */

export type TimeValue = number | string | null | undefined;

/** Tasks carry epoch-second floats OR ISO strings (DB-persisted datetimes); normalize to epoch seconds. */
export function toEpochSec(value: TimeValue): number | null {
  if (value === undefined || value === null) return null;
  if (typeof value === "number") return value > 1e12 ? value / 1000 : value;
  const text = value.trim();
  if (!text) return null;
  // ISO datetimes from the API are UTC but may lack a timezone suffix.
  const iso = /[zZ]|[+-]\d{2}:\d{2}$/.test(text) ? text : `${text}Z`;
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? null : ms / 1000;
}

export function fmtTs(ts?: TimeValue): string {
  const sec = toEpochSec(ts);
  if (sec === null) return "—";
  return new Date(sec * 1000).toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** "user · timestamp" omitting missing parts; never renders bare dashes. */
export function fmtUserTs(user?: string | null, ts?: TimeValue): string {
  const parts: string[] = [];
  if (user) parts.push(user);
  if (toEpochSec(ts) !== null) parts.push(fmtTs(ts));
  return parts.join(" · ");
}

export function fmtDuration(seconds?: number | null): string {
  if (seconds === undefined || seconds === null || Number.isNaN(seconds)) return "—";
  if (seconds < 0) return "—";
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)} ms`;
  if (seconds < 60) return `${seconds.toFixed(2)} s`;
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  if (m < 60) return `${m}m ${s.toFixed(0)}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m - h * 60}m`;
}

export function taskDuration(t: { started_at?: TimeValue; ended_at?: TimeValue }): number | null {
  const start = toEpochSec(t.started_at);
  const end = toEpochSec(t.ended_at);
  return start !== null && end !== null ? end - start : null;
}

export function shortId(id?: string | null, n = 8): string {
  if (!id) return "—";
  return id.length > n + 2 ? `${id.slice(0, n)}…` : id;
}

export const STATUS_COLORS: Record<string, string> = {
  FINISHED: "var(--color-ok)",
  ERROR: "var(--color-err)",
  RUNNING: "var(--color-running)",
  SUBMITTED: "var(--color-warn)",
  CREATED: "var(--color-fg-muted)",
  UNKNOWN: "var(--color-fg-muted)",
};

export function statusColor(status?: string | null): string {
  return STATUS_COLORS[status ?? "UNKNOWN"] ?? "var(--color-fg-muted)";
}

export function fmtBytes(bytes?: number | null): string {
  if (bytes === undefined || bytes === null || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

/** Deterministically returns one of 16 colors for an agent ID. */
export function agentColor(agentId?: string | null): string {
  if (!agentId) return "#7c3aed"; // Default accent color (e.g. violet)
  const colors = [
    "#f87171", "#fb923c", "#fbbf24", "#34d399", 
    "#2dd4bf", "#38bdf8", "#60a5fa", "#818cf8", 
    "#a78bfa", "#c084fc", "#f472b6", "#fb7185", 
    "#10b981", "#a3e635", "#e11d48", "#db2777"
  ];
  
  // Deterministic hash of agentId to index
  let hash = 0;
  for (let i = 0; i < agentId.length; i++) {
    hash = agentId.charCodeAt(i) + ((hash << 5) - hash);
  }
  const idx = Math.abs(hash) % colors.length;
  return colors[idx];
}

/** Merges custom node positions into a React Flow node list. */
export function applyNodePositions(
  nodes: any[],
  positions?: Record<string, { x: number; y: number }> | null
): any[] {
  if (!positions) return nodes;
  return nodes.map((n) => {
    const pos = positions[n.id];
    return pos ? { ...n, position: pos } : n;
  });
}
