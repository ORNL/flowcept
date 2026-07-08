/** Campaign detail: summary, workflows, task summary, workflow card, dashboard. */

import { useMemo, useState } from "react";
import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { z } from "zod";
import { Eye, EyeOff, Trash2 } from "lucide-react";
import { useQueries } from "@tanstack/react-query";
import { useCampaign, useProvenanceCard, useResolveDashboard, useWorkflowsWithTasks } from "../api/queries";
import { apiDelete, apiPost } from "../api/client";
import type { ChartDataResult } from "../api/types";
import { DeleteConfirmModal } from "../components/DeleteConfirmModal";
import { ChartRenderer } from "../components/dashboard/ChartRenderer";
import { chart as chartSchema, dashboardSpec, type DashboardSpec } from "../components/dashboard/spec";
import { StatusStrip } from "../components/charts/StatusStrip";
import { Markdown } from "../components/markdown/Markdown";
import { fmtTs, fmtUserTs, getWorkflowTimestamp, shortId } from "../lib/format";


export const Route = createFileRoute("/campaigns/$campaignId")({
  component: CampaignDetail,
  validateSearch: z.object({ tab: z.enum(["workflows", "card", "dashboard"]).default("workflows") }),
});

function CampaignDetail() {
  const { campaignId } = Route.useParams();
  const { tab } = Route.useSearch();
  const navigate = Route.useNavigate();
  const router = useRouter();
  const [showDelete, setShowDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const { data, isLoading, error } = useCampaign(campaignId);
  const workflowsWithTasks = useWorkflowsWithTasks();
  const provCard = useProvenanceCard("campaigns", campaignId, tab === "card");

  async function handleDelete() {
    setDeleting(true);
    try {
      await apiDelete(`/campaigns/${campaignId}`);
      void router.invalidate();
      await navigate({ to: "/campaigns" });
    } finally {
      setDeleting(false);
      setShowDelete(false);
    }
  }

  if (isLoading) return <div className="text-fg-muted p-6 text-xs">Loading…</div>;
  if (error) return <div className="text-err p-6 text-xs">{String(error)}</div>;
  if (!data) return null;

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <header>
        <div className="text-fg-muted text-xs">
          <Link to="/campaigns" className="hover:text-fg hover:underline">Campaigns</Link>
        </div>
        <div className="flex items-center gap-3">
          <h1 className="font-mono text-lg font-semibold">{campaignId}</h1>
          <button
            onClick={() => setShowDelete(true)}
            className="ml-auto text-fg-muted hover:text-err"
            title="Delete campaign"
          >
            <Trash2 size={14} />
          </button>
        </div>
        <div className="text-fg-muted mt-1 text-xs">
          {data.campaign.workflow_count} workflows · {data.campaign.task_count} tasks · last activity{" "}
          {fmtTs(data.campaign.last_ts)}
        </div>
      </header>

      <div className="card p-4">
        <StatusStrip summary={data.task_summary} />
      </div>

      <div className="flex gap-1 border-b border-border">
        {(["workflows", "dashboard", "card"] as const).map((t) => (
          <button
            key={t}
            onClick={() => navigate({ search: { tab: t } })}
            className={`px-3 py-2 text-xs capitalize ${tab === t ? "border-accent text-fg border-b-2" : "text-fg-muted hover:text-fg"}`}
          >
            {t === "card" ? "Workflow Card" : t}
          </button>
        ))}
      </div>

      {tab === "workflows" && (
        <div className="card divide-y divide-border/50">
          {data.workflows
            .filter((w) => w.name && workflowsWithTasks.data?.has(w.workflow_id))
            .map((w) => (
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
                <span className="text-fg-muted">{fmtUserTs(w.user, getWorkflowTimestamp(w))}</span>
              </Link>
            ))}
        </div>
      )}

      {tab === "dashboard" && <CampaignDashboardTab campaignId={campaignId} />}

      {tab === "card" && (
        <div className="card p-5">
          {provCard.isLoading ? (
            <div className="text-fg-muted text-xs">Generating workflow card…</div>
          ) : provCard.error ? (
            <div className="text-err text-xs">{String(provCard.error)}</div>
          ) : (
            <Markdown stripInlineCode>{provCard.data ?? ""}</Markdown>
          )}
        </div>
      )}

      {showDelete && (
        <DeleteConfirmModal
          title="Delete campaign"
          description={`This will permanently delete campaign ${shortId(campaignId, 16)} and all its workflows, tasks, and artifacts. This cannot be undone.`}
          onConfirm={handleDelete}
          onCancel={() => setShowDelete(false)}
          loading={deleting}
        />
      )}
    </div>
  );
}

function CampaignDashboardTab({ campaignId }: { campaignId: string }) {
  const resolved = useResolveDashboard({ campaign_id: campaignId });
  const rawCharts = resolved.data ?? [];
  const charts = rawCharts.map((raw) => chartSchema.parse({ ...raw, data: { filter: {}, ...(raw.data as object) } }));
  const context = useMemo(() => ({ campaign_id: campaignId }), [campaignId]);

  const prefetch = useQueries({
    queries: charts.map((c) => ({
      queryKey: ["chartData", c.data, context],
      queryFn: () => apiPost<ChartDataResult>("/stats/chart_data", { data: c.data, context }),
      enabled: c.data != null,
    })),
  });

  const [userToggles, setUserToggles] = useState<Map<string, boolean>>(() => new Map());

  const allLoaded = charts.length > 0 && prefetch.every((r) => !r.isLoading);

  const hiddenChartIds: Set<string> = (() => {
    if (!allLoaded) return new Set();
    const result = new Set<string>();
    charts.forEach((c, i) => {
      const hasData = (prefetch[i]?.data?.rows?.length ?? 0) > 0;
      const override = userToggles.get(c.chart_id);
      const hidden = override !== undefined ? !override : !hasData;
      if (hidden) result.add(c.chart_id);
    });
    return result;
  })();

  const visibleCharts = charts.filter((c) => !hiddenChartIds.has(c.chart_id));
  const spec: DashboardSpec = dashboardSpec.parse({
    type: "campaign",
    name: "Campaign Dashboard",
    context,
    charts: visibleCharts,
    layout: [],
  });

  function toggleChart(chartId: string) {
    const willBeVisible = hiddenChartIds.has(chartId);
    setUserToggles((prev) => new Map(prev).set(chartId, willBeVisible));
  }

  if (resolved.isLoading) return <div className="text-fg-muted text-xs">Loading…</div>;

  if (!charts.length) {
    return (
      <p className="text-fg-muted text-sm">
        No charts configured. Visit <span className="font-medium">Dashboard configs</span> to add charts for this campaign.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {charts.map((c) => {
          const hidden = hiddenChartIds.has(c.chart_id);
          return (
            <button
              key={c.chart_id}
              onClick={() => toggleChart(c.chart_id)}
              className={`flex items-center gap-1 rounded border px-2 py-1 text-[11px] ${
                hidden ? "border-border text-fg-muted" : "border-accent/50 text-fg"
              }`}
              title={hidden ? "Show chart" : "Hide chart"}
            >
              {hidden ? <EyeOff size={11} /> : <Eye size={11} />}
              {c.title || c.chart_id}
            </button>
          );
        })}
      </div>
      {!visibleCharts.length && <p className="text-fg-muted text-sm">All dashboard charts are hidden.</p>}
      <div className="grid grid-cols-2 gap-4">
        {visibleCharts.map((c) => (
          <div key={c.chart_id} className="card p-3" style={{ height: 280 }}>
            <div className="text-fg-muted mb-2 text-xs font-medium">{c.title}</div>
            <div className="h-[calc(100%-1.5rem)]">
              <ChartRenderer chart={c} spec={spec} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
