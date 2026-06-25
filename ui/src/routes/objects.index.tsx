/** Artifacts browser with type filter pills. */

import { useMemo, useState } from "react";
import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { Trash2 } from "lucide-react";
import { z } from "zod";
import { useObjects } from "../api/queries";
import { apiDelete } from "../api/client";
import { DeleteConfirmModal } from "../components/DeleteConfirmModal";
import { fmtBytes, shortId } from "../lib/format";

export const Route = createFileRoute("/objects/")({
  component: ObjectsPage,
  validateSearch: z.object({ type: z.enum(["all", "ml_model", "dataset"]).default("all") }),
});

function ObjectsPage() {
  const { type } = Route.useSearch();
  const navigate = Route.useNavigate();
  const router = useRouter();
  const { data, isLoading, error } = useObjects(type === "all" ? {} : { type });
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!deleteId) return;
    setDeleting(true);
    try {
      await apiDelete(`/objects/${deleteId}`);
      void router.invalidate();
    } finally {
      setDeleting(false);
      setDeleteId(null);
    }
  }

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
          <div key={o.object_id} className="group flex items-center justify-between hover:bg-surface-2 px-4 py-2.5 text-xs">
            <Link
              to="/objects/$objectId"
              params={{ objectId: o.object_id }}
              className="flex flex-1 items-center gap-2 min-w-0"
            >
              <span className="font-mono">{shortId(o.object_id, 16)}</span>
              <span className="text-accent rounded bg-accent-soft px-1.5 py-0.5 text-[10px]">
                {o.object_type ?? "object"}
              </span>
              {o.version !== undefined && <span className="text-fg-muted">v{o.version}</span>}
            </Link>
            <div className="flex shrink-0 items-center gap-3 pl-4">
              <span className="text-fg-muted flex items-center gap-3">
                {o.object_size_bytes !== undefined && (
                  <span className="font-medium">{fmtBytes(o.object_size_bytes)}</span>
                )}
                <span className="truncate">
                  {o.workflow_id ? `wf ${shortId(o.workflow_id, 10)}` : ""}
                  {o.custom_metadata ? ` · ${JSON.stringify(o.custom_metadata).slice(0, 80)}` : ""}
                </span>
              </span>
              <button
                onClick={() => setDeleteId(o.object_id)}
                className="text-fg-muted opacity-0 group-hover:opacity-100 hover:text-err ml-1"
                title="Delete artifact"
              >
                <Trash2 size={12} />
              </button>
            </div>
          </div>
        ))}
      </div>
      {data && data.count === 0 && <div className="text-fg-muted text-xs">No artifacts recorded yet.</div>}
      {deleteId && (
        <DeleteConfirmModal
          title="Delete artifact"
          description={`This will permanently delete artifact ${shortId(deleteId, 16)} and all its versions. This cannot be undone.`}
          onConfirm={handleDelete}
          onCancel={() => setDeleteId(null)}
          loading={deleting}
        />
      )}
    </div>
  );
}
