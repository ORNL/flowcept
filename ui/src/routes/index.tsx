/** Overview: recent campaigns and workflows at a glance. */

import { useMemo } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useCampaigns, useVisibleWorkflows } from "../api/queries";
import { fmtTs, fmtUserTs, shortId, toEpochSec } from "../lib/format";

export const Route = createFileRoute("/")({ component: Overview });

function Overview() {
  const campaigns = useCampaigns();
  const workflows = useVisibleWorkflows();

  const latestTs = useMemo(() => {
    const campTs = (campaigns.data?.items ?? [])
      .map((c) => c.last_ts)
      .filter((t): t is number => t != null && t > 0);
    if (campTs.length) return Math.max(...campTs);
    // Fall back to most recent visible workflow (items are sorted newest first).
    const ts = workflows.items.map((w) => toEpochSec(w.utc_timestamp)).find((t) => t != null);
    return ts ?? undefined;
  }, [campaigns.data, workflows.items]);

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <header>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="text-fg-muted text-xs">Provenance at a glance.</p>
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Stat label="Campaigns" value={campaigns.data?.count} />
        <Stat label="Workflows" value={workflows.isLoading ? undefined : workflows.items.length} />
        <Stat label="Latest activity" value={fmtTs(latestTs)} />
      </div>

      <section className="card">
        <h2 className="border-b border-border px-4 py-3 text-sm font-medium">Recent campaigns</h2>
        <div className="divide-y divide-border/50">
          {(campaigns.data?.items ?? [])
            .filter((c) => c.workflow_count > 0 && c.task_count > 0)
            .slice(0, 8)
            .map((c) => (
              <Link
                key={c.campaign_id}
                to="/campaigns/$campaignId"
                params={{ campaignId: c.campaign_id }}
                className="hover:bg-surface-2 flex items-center justify-between px-4 py-2.5 text-xs"
              >
                <span className="font-mono">{shortId(c.campaign_id, 24)}</span>
                <span className="text-fg-muted">
                  {c.workflow_count} workflows · {c.task_count} tasks · {fmtTs(c.last_ts)}
                </span>
              </Link>
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
              <Link
                key={w.workflow_id}
                to="/workflows/$workflowId"
                params={{ workflowId: w.workflow_id }}
                className="hover:bg-surface-2 flex items-center justify-between px-4 py-2.5 text-xs"
              >
                <span>
                  <span className="font-medium">{w.name}</span>{" "}
                  <span className="text-fg-muted font-mono">{shortId(w.workflow_id)}</span>
                </span>
                <span className="text-fg-muted">{fmtUserTs(w.user, w.utc_timestamp)}</span>
              </Link>
            ))
          )}
          {!workflows.isLoading && workflows.items.length === 0 && (
            <div className="text-fg-muted px-4 py-6 text-center text-xs">No workflows recorded yet.</div>
          )}
        </div>
      </section>
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
