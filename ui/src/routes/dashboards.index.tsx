/** Dashboards: schema/configuration view for workflow and campaign dashboards. */

import { createFileRoute, Link } from "@tanstack/react-router";
import { LayoutDashboard, ChevronRight } from "lucide-react";
import { useInfo, useWorkflows, useWorkflowsWithTasks, useCampaigns } from "../api/queries";
import { chart as chartSchema } from "../components/dashboard/spec";
import { fmtTs, shortId, toEpochSec } from "../lib/format";

export const Route = createFileRoute("/dashboards/")({ component: DashboardsPage });

function DashboardsPage() {
  const { data: info } = useInfo();
  const workflows = useWorkflows({ limit: 200 } as any);
  const workflowsWithTasks = useWorkflowsWithTasks();
  const campaigns = useCampaigns();

  const rawWorkflowCharts = info?.workflow_dashboard ?? [];
  const rawCampaignCharts = info?.campaign_dashboard ?? [];

  const wfCharts = rawWorkflowCharts.map((raw) =>
    chartSchema.parse({ ...raw, data: { filter: {}, ...(raw.data as object) } }),
  );
  const campCharts = rawCampaignCharts.map((raw) =>
    chartSchema.parse({ ...raw, data: { filter: {}, ...(raw.data as object) } }),
  );

  const recentWorkflows = (workflows.data?.items ?? [])
    .filter((w) => w.name && (toEpochSec(w.utc_timestamp) ?? 0) > 0)
    .filter((w) => !workflowsWithTasks.data || workflowsWithTasks.data.has(w.workflow_id))
    .sort((a, b) => (toEpochSec(b.utc_timestamp) ?? 0) - (toEpochSec(a.utc_timestamp) ?? 0))
    .slice(0, 6);

  const recentCampaigns = (campaigns.data?.items ?? [])
    .filter((c) => c.task_count > 0)
    .slice(0, 6);

  return (
    <div className="mx-auto max-w-5xl space-y-8 p-6">
      <header>
        <h1 className="text-xl font-semibold">Dashboards</h1>
        <p className="text-fg-muted text-xs mt-1">
          Dashboard schemas define which charts appear in every workflow's and campaign's Dashboard tab.
          Configure them under <code className="bg-surface-2 px-1 rounded">web_server.workflow_dashboard</code> /
          <code className="bg-surface-2 px-1 rounded ml-1">campaign_dashboard</code> in your settings.yaml.
        </p>
      </header>

      {/* Workflow Dashboard Schema */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <LayoutDashboard size={15} className="text-accent" />
          <h2 className="text-sm font-semibold">Workflow Dashboard</h2>
          <span className="text-fg-muted text-xs">· {wfCharts.length} chart{wfCharts.length !== 1 ? "s" : ""} configured</span>
        </div>

        {wfCharts.length === 0 ? (
          <div className="card p-4 text-fg-muted text-xs">
            No charts configured. Add <code>workflow_dashboard</code> under <code>web_server</code> in settings.yaml.
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
            {wfCharts.map((c) => (
              <div key={c.chart_id} className="card px-3 py-2.5 flex items-start gap-2">
                <span className="text-[10px] rounded border border-border px-1.5 py-0.5 text-fg-muted mt-0.5 shrink-0 uppercase tracking-wide">{c.type}</span>
                <div className="min-w-0">
                  <div className="text-xs font-medium truncate">{c.title}</div>
                  {c.data?.group_by && (
                    <div className="text-fg-muted text-[10px] truncate">grouped by {c.data.group_by}</div>
                  )}
                  {c.data?.x && c.data?.y && (
                    <div className="text-fg-muted text-[10px] truncate">{c.data.x} → {c.data.y.join(", ")}</div>
                  )}
                  {c.viz?.kind && (
                    <div className="text-fg-muted text-[10px]">{c.viz.kind} chart</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {recentWorkflows.length > 0 && (
          <div className="card divide-y divide-border/50">
            <div className="px-4 py-2 text-[11px] font-medium text-fg-muted uppercase tracking-wider">Recent workflows</div>
            {recentWorkflows.map((w) => (
              <Link
                key={w.workflow_id}
                to="/workflows/$workflowId"
                params={{ workflowId: w.workflow_id }}
                search={{ tab: "dashboard" } as any}
                className="hover:bg-surface-2 flex items-center justify-between px-4 py-2 text-xs"
              >
                <span>
                  <span className="font-medium">{w.name}</span>{" "}
                  <span className="text-fg-muted font-mono">{shortId(w.workflow_id)}</span>
                </span>
                <span className="flex items-center gap-1 text-fg-muted">
                  {fmtTs(w.utc_timestamp)}
                  <ChevronRight size={12} />
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>

      {/* Campaign Dashboard Schema */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <LayoutDashboard size={15} className="text-accent" />
          <h2 className="text-sm font-semibold">Campaign Dashboard</h2>
          <span className="text-fg-muted text-xs">· {campCharts.length} chart{campCharts.length !== 1 ? "s" : ""} configured</span>
        </div>

        {campCharts.length === 0 ? (
          <div className="card p-4 text-fg-muted text-xs">
            No charts configured. Add <code>campaign_dashboard</code> under <code>web_server</code> in settings.yaml.
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
            {campCharts.map((c) => (
              <div key={c.chart_id} className="card px-3 py-2.5 flex items-start gap-2">
                <span className="text-[10px] rounded border border-border px-1.5 py-0.5 text-fg-muted mt-0.5 shrink-0 uppercase tracking-wide">{c.type}</span>
                <div className="min-w-0">
                  <div className="text-xs font-medium truncate">{c.title}</div>
                  {c.data?.group_by && (
                    <div className="text-fg-muted text-[10px] truncate">grouped by {c.data.group_by}</div>
                  )}
                  {c.viz?.kind && (
                    <div className="text-fg-muted text-[10px]">{c.viz.kind} chart</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {recentCampaigns.length > 0 && (
          <div className="card divide-y divide-border/50">
            <div className="px-4 py-2 text-[11px] font-medium text-fg-muted uppercase tracking-wider">Recent campaigns</div>
            {recentCampaigns.map((c) => (
              <Link
                key={c.campaign_id}
                to="/campaigns/$campaignId"
                params={{ campaignId: c.campaign_id }}
                search={{ tab: "dashboard" } as any}
                className="hover:bg-surface-2 flex items-center justify-between px-4 py-2 text-xs"
              >
                <span className="font-mono">{shortId(c.campaign_id, 24)}</span>
                <span className="flex items-center gap-1 text-fg-muted">
                  {c.task_count} tasks
                  <ChevronRight size={12} />
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
