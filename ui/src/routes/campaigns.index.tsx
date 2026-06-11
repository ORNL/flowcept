/** Campaigns list. */

import { createFileRoute, Link } from "@tanstack/react-router";
import { useCampaigns } from "../api/queries";
import { fmtTs, shortId } from "../lib/format";

export const Route = createFileRoute("/campaigns/")({ component: CampaignsPage });

function CampaignsPage() {
  const { data, isLoading, error } = useCampaigns();

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <h1 className="text-xl font-semibold">Campaigns</h1>
      {isLoading && <div className="text-fg-muted text-xs">Loading…</div>}
      {error && <div className="text-err text-xs">{String(error)}</div>}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {(data?.items ?? [])
          .filter((c) => c.task_count > 0)
          .sort((a, b) => (b.last_ts ?? 0) - (a.last_ts ?? 0))
          .map((c) => (
          <Link
            key={c.campaign_id}
            to="/campaigns/$campaignId"
            params={{ campaignId: c.campaign_id }}
            className="card hover:border-accent/60 block p-4"
          >
            <div className="font-mono text-sm">{shortId(c.campaign_id, 28)}</div>
            <div className="text-fg-muted mt-2 space-y-1 text-xs">
              <div>
                {c.workflow_count} workflows · {c.task_count} tasks
              </div>
              {c.workflow_names.length > 0 && <div className="truncate">{c.workflow_names.join(", ")}</div>}
              <div>
                {c.users.join(", ") || "unknown user"} · last: {fmtTs(c.last_ts)}
              </div>
            </div>
          </Link>
        ))}
      </div>
      {data && data.count === 0 && <div className="text-fg-muted text-xs">No campaigns recorded yet.</div>}
    </div>
  );
}
