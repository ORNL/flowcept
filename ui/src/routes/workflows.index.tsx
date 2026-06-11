/** Workflows list with campaign filter. */

import { createFileRoute, Link } from "@tanstack/react-router";
import { z } from "zod";
import { useVisibleWorkflows } from "../api/queries";
import { fmtUserTs, shortId } from "../lib/format";

export const Route = createFileRoute("/workflows/")({
  component: WorkflowsPage,
  validateSearch: z.object({ campaign_id: z.string().optional() }),
});

function WorkflowsPage() {
  const { campaign_id } = Route.useSearch();
  const { items, isLoading, error } = useVisibleWorkflows({ campaign_id });

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
        {items.map((w) => (
          <Link
            key={w.workflow_id}
            to="/workflows/$workflowId"
            params={{ workflowId: w.workflow_id }}
            className="hover:bg-surface-2 flex items-center justify-between px-4 py-2.5 text-xs"
          >
            <span className="min-w-0">
              <span className="font-medium">{w.name}</span>{" "}
              <span className="text-fg-muted font-mono">{shortId(w.workflow_id)}</span>
              {w.campaign_id && (
                <span className="text-fg-muted ml-2">campaign {shortId(w.campaign_id, 10)}</span>
              )}
            </span>
            <span className="text-fg-muted shrink-0">{fmtUserTs(w.user, w.utc_timestamp)}</span>
          </Link>
        ))}
      </div>
      {!isLoading && items.length === 0 && (
        <div className="text-fg-muted text-xs">No workflows recorded yet.</div>
      )}
    </div>
  );
}
