/** Campaign detail: summary, workflows, task summary, provenance card. */

import { createFileRoute, Link } from "@tanstack/react-router";
import { z } from "zod";
import { useCampaign, useProvenanceCard } from "../api/queries";
import { StatusStrip } from "../components/charts/StatusStrip";
import { Markdown } from "../components/markdown/Markdown";
import { fmtTs, shortId } from "../lib/format";

export const Route = createFileRoute("/campaigns/$campaignId")({
  component: CampaignDetail,
  validateSearch: z.object({ tab: z.enum(["workflows", "card"]).default("workflows") }),
});

function CampaignDetail() {
  const { campaignId } = Route.useParams();
  const { tab } = Route.useSearch();
  const navigate = Route.useNavigate();
  const { data, isLoading, error } = useCampaign(campaignId);
  const card = useProvenanceCard("campaigns", campaignId, tab === "card");

  if (isLoading) return <div className="text-fg-muted p-6 text-xs">Loading…</div>;
  if (error) return <div className="text-err p-6 text-xs">{String(error)}</div>;
  if (!data) return null;

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <header>
        <div className="text-fg-muted text-xs">Campaign</div>
        <h1 className="font-mono text-lg font-semibold">{campaignId}</h1>
        <div className="text-fg-muted mt-1 text-xs">
          {data.campaign.workflow_count} workflows · {data.campaign.task_count} tasks · last activity{" "}
          {fmtTs(data.campaign.last_ts)}
        </div>
      </header>

      <div className="card p-4">
        <StatusStrip summary={data.task_summary} />
      </div>

      <div className="flex gap-1 border-b border-border">
        {(["workflows", "card"] as const).map((t) => (
          <button
            key={t}
            onClick={() => navigate({ search: { tab: t } })}
            className={`px-3 py-2 text-xs ${tab === t ? "border-accent text-fg border-b-2" : "text-fg-muted hover:text-fg"}`}
          >
            {t === "workflows" ? "Workflows" : "Provenance card"}
          </button>
        ))}
      </div>

      {tab === "workflows" && (
        <div className="card divide-y divide-border/50">
          {data.workflows.map((w) => (
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
        </div>
      )}

      {tab === "card" && (
        <div className="card p-5">
          {card.isLoading ? (
            <div className="text-fg-muted text-xs">Generating provenance card…</div>
          ) : card.error ? (
            <div className="text-err text-xs">{String(card.error)}</div>
          ) : (
            <Markdown>{card.data ?? ""}</Markdown>
          )}
        </div>
      )}
    </div>
  );
}
