/** Overview: recent campaigns and workflows at a glance. */

import { createFileRoute, Link } from "@tanstack/react-router";
import { useCampaigns, useWorkflows } from "../api/queries";
import { fmtTs, shortId } from "../lib/format";

export const Route = createFileRoute("/")({ component: Overview });

function Overview() {
  const campaigns = useCampaigns();
  const workflows = useWorkflows();

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <header>
        <h1 className="text-xl font-semibold">Overview</h1>
        <p className="text-fg-muted text-xs">Provenance at a glance.</p>
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Stat label="Campaigns" value={campaigns.data?.count} />
        <Stat label="Workflows" value={workflows.data?.count} />
        <Stat
          label="Latest activity"
          value={workflows.data?.items?.length ? fmtTs(workflows.data.items.at(-1)?.utc_timestamp) : "—"}
        />
      </div>

      <section className="card">
        <h2 className="border-b border-border px-4 py-3 text-sm font-medium">Recent campaigns</h2>
        <div className="divide-y divide-border/50">
          {(campaigns.data?.items ?? []).slice(0, 8).map((c) => (
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
          {(workflows.data?.items ?? [])
            .slice(-8)
            .reverse()
            .map((w) => (
              <Link
                key={w.workflow_id}
                to="/workflows/$workflowId"
                params={{ workflowId: w.workflow_id }}
                className="hover:bg-surface-2 flex items-center justify-between px-4 py-2.5 text-xs"
              >
                <span>
                  <span className="font-medium">{w.name ?? "unnamed"}</span>{" "}
                  <span className="text-fg-muted font-mono">{shortId(w.workflow_id)}</span>
                </span>
                <span className="text-fg-muted">
                  {w.user ?? "—"} · {fmtTs(w.utc_timestamp)}
                </span>
              </Link>
            ))}
          {workflows.data && workflows.data.count === 0 && (
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
