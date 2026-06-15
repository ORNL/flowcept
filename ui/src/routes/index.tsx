/** Overview: recent campaigns and workflows at a glance. */

import { useMemo, useState } from "react";
import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { Trash2 } from "lucide-react";
import { useCampaigns, useVisibleWorkflows, useAgents } from "../api/queries";
import { apiDelete } from "../api/client";
import { DeleteConfirmModal } from "../components/DeleteConfirmModal";
import { fmtTs, fmtUserTs, shortId, toEpochSec } from "../lib/format";

export const Route = createFileRoute("/")({ component: Overview });

function Overview() {
  const campaigns = useCampaigns();
  const workflows = useVisibleWorkflows();
  const agents = useAgents();
  const router = useRouter();
  const [deleteTarget, setDeleteTarget] = useState<{ kind: "workflow" | "campaign"; id: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const path = deleteTarget.kind === "workflow" ? `/workflows/${deleteTarget.id}` : `/campaigns/${deleteTarget.id}`;
      await apiDelete(path);
      void router.invalidate();
    } finally {
      setDeleting(false);
      setDeleteTarget(null);
    }
  }

  const latestTs = useMemo(() => {
    const campTs = (campaigns.data?.items ?? [])
      .map((c) => c.last_ts)
      .filter((t): t is number => t != null && t > 0);
    if (campTs.length) return Math.max(...campTs);
    const ts = workflows.items
      .map((w) => toEpochSec(w.utc_timestamp))
      .filter((t): t is number => t != null);
    return ts.length ? Math.max(...ts) : undefined;
  }, [campaigns.data, workflows.items]);

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <header>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="text-fg-muted text-xs">Provenance at a glance.</p>
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <Stat label="Campaigns" value={campaigns.data?.count} />
        <Stat label="Workflows" value={workflows.isLoading ? undefined : workflows.items.length} />
        <Stat label="Agents" value={agents.data?.count} />
        <Stat label="Latest activity" value={fmtTs(latestTs)} />
      </div>

      <section className="card">
        <h2 className="border-b border-border px-4 py-3 text-sm font-medium">Recent campaigns</h2>
        <div className="divide-y divide-border/50">
          {(campaigns.data?.items ?? [])
            .filter((c) => c.workflow_count > 0 && c.task_count > 0)
            .slice(0, 8)
            .map((c) => (
              <div key={c.campaign_id} className="group flex items-center justify-between hover:bg-surface-2 px-4 py-2.5 text-xs">
                <Link
                  to="/campaigns/$campaignId"
                  params={{ campaignId: c.campaign_id }}
                  className="flex flex-1 items-center gap-2 min-w-0"
                >
                  <span className="font-mono">{shortId(c.campaign_id, 24)}</span>
                </Link>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="text-fg-muted">
                    {c.workflow_count} workflows · {c.task_count} tasks · {fmtTs(c.last_ts)}
                  </span>
                  <button
                    onClick={() => setDeleteTarget({ kind: "campaign", id: c.campaign_id })}
                    className="text-fg-muted opacity-0 group-hover:opacity-100 hover:text-err ml-1"
                    title="Delete campaign"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))}
          {campaigns.data && campaigns.data.count === 0 && (
            <div className="text-fg-muted px-4 py-6 text-center text-xs">No campaigns recorded yet.</div>
          )}
        </div>
      </section>

      <section className="card">
        <h2 className="border-b border-border px-4 py-3 text-sm font-medium">Recent workflows</h2>
        <div className="divide-y divide-border/50">
          {workflows.isLoading ? (
            <div className="text-fg-muted px-4 py-4 text-center text-xs">Loading…</div>
          ) : (
            workflows.items.slice(0, 8).map((w) => (
              <div key={w.workflow_id} className="group flex items-center justify-between hover:bg-surface-2 px-4 py-2.5 text-xs">
                <Link
                  to="/workflows/$workflowId"
                  params={{ workflowId: w.workflow_id }}
                  className="flex flex-1 items-center gap-1.5 min-w-0"
                >
                  <span className="font-medium">{w.name}</span>
                  <span className="text-fg-muted font-mono">{shortId(w.workflow_id)}</span>
                </Link>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="text-fg-muted">{fmtUserTs(w.user, w.utc_timestamp)}</span>
                  <button
                    onClick={() => setDeleteTarget({ kind: "workflow", id: w.workflow_id })}
                    className="text-fg-muted opacity-0 group-hover:opacity-100 hover:text-err ml-1"
                    title="Delete workflow"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))
          )}
          {!workflows.isLoading && workflows.items.length === 0 && (
            <div className="text-fg-muted px-4 py-6 text-center text-xs">No workflows recorded yet.</div>
          )}
        </div>
      </section>

      {deleteTarget && (
        <DeleteConfirmModal
          title={`Delete ${deleteTarget.kind}`}
          description={`This will permanently delete this ${deleteTarget.kind} and all its data. This cannot be undone.`}
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
          loading={deleting}
        />
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="card px-4 py-3">
      <div className="text-fg-muted text-xs">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value ?? "…"}</div>
    </div>
  );
}
