/** Artifacts browser with type filter pills. */

import { useMemo } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { z } from "zod";
import { useObjects } from "../api/queries";
import { fmtBytes, shortId } from "../lib/format";

export const Route = createFileRoute("/objects/")({
  component: ObjectsPage,
  validateSearch: z.object({ type: z.enum(["all", "ml_model", "dataset"]).default("all") }),
});

function ObjectsPage() {
  const { type } = Route.useSearch();
  const navigate = Route.useNavigate();
  const { data, isLoading, error } = useObjects(type === "all" ? {} : { type });

  const sizeByType = useMemo(() => {
    const items = data?.items ?? [];
    const map = new Map<string, number>();
    for (const o of items) {
      const t = o.object_type ?? "unknown";
      map.set(t, (map.get(t) ?? 0) + (o.object_size_bytes ?? 0));
    }
    return [...map.entries()].sort((a, b) => b[1] - a[1]);
  }, [data]);

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <h1 className="text-xl font-semibold">Artifacts</h1>
      <div className="flex gap-1.5">
        {(["all", "ml_model", "dataset"] as const).map((t) => (
          <button
            key={t}
            onClick={() => navigate({ search: { type: t } })}
            className={`rounded-full border px-3 py-1 text-xs ${
              type === t ? "border-accent bg-accent-soft" : "border-border text-fg-muted hover:text-fg"
            }`}
          >
            {t === "all" ? "All" : t === "ml_model" ? "Models" : "Datasets"}
          </button>
        ))}
      </div>
      {isLoading && <div className="text-fg-muted text-xs">Loading…</div>}
      {error && <div className="text-err text-xs">{String(error)}</div>}
      {sizeByType.length > 0 && (
        <div className="card flex flex-wrap gap-4 px-4 py-3">
          {sizeByType.map(([t, sz]) => (
            <div key={t} className="text-xs">
              <span className="text-fg-muted">{t}</span>
              {" "}
              <span className="font-medium">{fmtBytes(sz)}</span>
            </div>
          ))}
        </div>
      )}
      <div className="card divide-y divide-border/50">
        {(data?.items ?? []).map((o) => (
          <Link
            key={o.object_id}
            to="/objects/$objectId"
            params={{ objectId: o.object_id }}
            className="hover:bg-surface-2 flex items-center justify-between px-4 py-2.5 text-xs"
          >
            <span className="min-w-0">
              <span className="font-mono">{shortId(o.object_id, 16)}</span>
              <span className="text-accent ml-2 rounded bg-accent-soft px-1.5 py-0.5 text-[10px]">
                {o.object_type ?? "object"}
              </span>
              {o.version !== undefined && <span className="text-fg-muted ml-2">v{o.version}</span>}
            </span>
            <span className="text-fg-muted flex shrink-0 items-center gap-3 pl-4">
              {o.object_size_bytes !== undefined && (
                <span className="font-medium">{fmtBytes(o.object_size_bytes)}</span>
              )}
              <span className="truncate">
                {o.workflow_id ? `wf ${shortId(o.workflow_id, 10)}` : ""}
                {o.custom_metadata ? ` · ${JSON.stringify(o.custom_metadata).slice(0, 80)}` : ""}
              </span>
            </span>
          </Link>
        ))}
      </div>
      {data && data.count === 0 && <div className="text-fg-muted text-xs">No artifacts recorded yet.</div>}
    </div>
  );
}
