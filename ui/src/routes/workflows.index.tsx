/** Workflows list with campaign filter. */

import { useState } from "react";
import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { z } from "zod";
import { ChevronLeft, ChevronRight, Trash2 } from "lucide-react";
import { useVisibleWorkflows } from "../api/queries";
import { apiDelete } from "../api/client";
import { DeleteConfirmModal } from "../components/DeleteConfirmModal";
import { fmtUserTs, shortId } from "../lib/format";

const PAGE_SIZE = 30;

export const Route = createFileRoute("/workflows/")({
  component: WorkflowsPage,
  validateSearch: z.object({ campaign_id: z.string().optional() }),
});

function WorkflowsPage() {
  const { campaign_id } = Route.useSearch();
  const { items, isLoading, error } = useVisibleWorkflows({ campaign_id });
  const router = useRouter();
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [page, setPage] = useState(0);
  const totalPages = Math.ceil(items.length / PAGE_SIZE);
  const pageItems = items.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  async function handleDelete() {
    if (!deleteId) return;
    setDeleting(true);
    try {
      await apiDelete(`/workflows/${deleteId}`);
      void router.invalidate();
    } finally {
      setDeleting(false);
      setDeleteId(null);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <header className="flex items-baseline gap-3">
        <h1 className="text-xl font-semibold">Workflows</h1>
        {campaign_id && (
          <span className="text-fg-muted text-xs">
            campaign <span className="font-mono">{shortId(campaign_id, 16)}</span>
          </span>
        )}
      </header>
      {isLoading && <div className="text-fg-muted text-xs">Loading…</div>}
      {error && <div className="text-err text-xs">{String(error)}</div>}
      <div className="card divide-y divide-border/50">
        {pageItems.map((w) => (
          <div key={w.workflow_id} className="group flex items-center justify-between hover:bg-surface-2 px-4 py-2.5 text-xs">
            <Link
              to="/workflows/$workflowId"
              params={{ workflowId: w.workflow_id }}
              className="flex flex-1 items-center gap-1.5 min-w-0"
            >
              <span className="font-medium">{w.name}</span>
              <span className="text-fg-muted font-mono">{shortId(w.workflow_id)}</span>
              {w.campaign_id && (
                <span className="text-fg-muted">campaign {shortId(w.campaign_id, 10)}</span>
              )}
            </Link>
            <div className="flex shrink-0 items-center gap-2">
              <span className="text-fg-muted">{fmtUserTs(w.user, w.utc_timestamp)}</span>
              <button
                onClick={() => setDeleteId(w.workflow_id)}
                className="text-fg-muted opacity-0 group-hover:opacity-100 hover:text-err ml-1"
                title="Delete workflow"
              >
                <Trash2 size={12} />
              </button>
            </div>
          </div>
        ))}
      </div>
      {!isLoading && items.length === 0 && (
        <div className="text-fg-muted text-xs">No workflows recorded yet.</div>
      )}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <button
            data-testid="pagination-prev"
            onClick={() => setPage((p) => p - 1)}
            disabled={page === 0}
            className="flex items-center gap-1 rounded border border-border px-2.5 py-1.5 text-xs disabled:opacity-40"
          >
            <ChevronLeft size={13} /> Prev
          </button>
          <span className="text-fg-muted text-xs">Page {page + 1} of {totalPages}</span>
          <button
            data-testid="pagination-next"
            onClick={() => setPage((p) => p + 1)}
            disabled={page >= totalPages - 1}
            className="flex items-center gap-1 rounded border border-border px-2.5 py-1.5 text-xs disabled:opacity-40"
          >
            Next <ChevronRight size={13} />
          </button>
        </div>
      )}

      {deleteId && (
        <DeleteConfirmModal
          title="Delete workflow"
          description={`This will permanently delete workflow ${shortId(deleteId, 16)} and all its tasks and artifacts. This cannot be undone.`}
          onConfirm={handleDelete}
          onCancel={() => setDeleteId(null)}
          loading={deleting}
        />
      )}
    </div>
  );
}
