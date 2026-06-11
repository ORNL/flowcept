/** Compact collapsible JSON viewer for used/generated/telemetry payloads. */

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

function Entry({ name, value, depth }: { name: string; value: unknown; depth: number }) {
  const [open, setOpen] = useState(depth < 1);
  const isObj = value !== null && typeof value === "object";

  if (!isObj) {
    return (
      <div className="flex gap-2 py-0.5" style={{ paddingLeft: depth * 14 }}>
        <span className="text-fg-muted shrink-0">{name}:</span>
        <span className="break-all font-mono">{value === null ? "null" : String(value)}</span>
      </div>
    );
  }

  const entries = Array.isArray(value)
    ? value.map((v, i) => [String(i), v] as [string, unknown])
    : Object.entries(value as Record<string, unknown>);

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="text-fg-muted hover:text-fg flex items-center gap-1 py-0.5"
        style={{ paddingLeft: depth * 14 }}
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <span>{name}</span>
        <span className="opacity-60">{Array.isArray(value) ? `[${entries.length}]` : `{${entries.length}}`}</span>
      </button>
      {open && entries.map(([k, v]) => <Entry key={k} name={k} value={v} depth={depth + 1} />)}
    </div>
  );
}

export function JsonTree({ data, name = "root" }: { data: unknown; name?: string }) {
  if (data === null || data === undefined) return <div className="text-fg-muted text-xs">—</div>;
  return (
    <div className="text-xs leading-5">
      <Entry name={name} value={data} depth={0} />
    </div>
  );
}
