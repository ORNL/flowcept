/** Agent detail: status strip + tabs (tasks, telemetry, dashboard, raw). */

import { useMemo, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQueries } from "@tanstack/react-query";
import { z } from "zod";
import { Eye, EyeOff } from "lucide-react";
import type { ColumnDef, SortingState } from "@tanstack/react-table";
import { useAgent, useResolveDashboard, useTask, useTasksQuery, useTaskSummary } from "../api/queries";
import type { ChartDataResult, Task } from "../api/types";
import { StatusStrip } from "../components/charts/StatusStrip";
import { TelemetryChart } from "../components/charts/TelemetryChart";
import { JsonTree } from "../components/JsonTree";
import { DataTable } from "../components/tables/DataTable";
import { TaskDrawer } from "../components/tasks/TaskDrawer";
import { apiPost } from "../api/client";
import { ChartRenderer } from "../components/dashboard/ChartRenderer";
import { chart, dashboardSpec, type DashboardSpec } from "../components/dashboard/spec";
import { fmtDuration, fmtTs, shortId, statusColor, taskDuration } from "../lib/format";

const TABS = ["tasks", "telemetry", "dashboard", "raw"] as const;

export const Route = createFileRoute("/agents/$agentId")({
  component: AgentDetail,
  validateSearch: z.object({
    tab: z.enum(TABS).default("tasks"),
    status: z.string().optional(),
    activity: z.string().optional(),
    task: z.string().optional(),
    sort: z.string().default("-started_at"),
  }),
});

function AgentDetail() {
  const { agentId } = Route.useParams();
  const search = Route.useSearch();
  const navigate = Route.useNavigate();

  const agentQuery = useAgent(agentId);
  const summary = useTaskSummary({ agent_id: agentId });

  const filter: Record<string, unknown> = {
    $or: [{ agent_id: agentId }, { source_agent_id: agentId }],
  };
  if (search.status) filter["status"] = search.status;
  if (search.activity) filter["activity_id"] = search.activity;

  const sortField = search.sort.replace(/^-/, "");
  const sortOrder: 1 | -1 = search.sort.startsWith("-") ? -1 : 1;
  const tasksBody = useMemo(
    () => ({ filter, limit: 1000, sort: [{ field: sortField, order: sortOrder }] }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [agentId, search.status, search.activity, sortField, sortOrder],
  );
  const tasks = useTasksQuery(tasksBody);
  const taskItems: Task[] = tasks.data?.items ?? [];

  const openTask = useTask(search.task ?? "", !!search.task);

  const columns = useMemo<ColumnDef<Task, unknown>[]>(
    () => [
      {
        id: "status",
        header: "",
        size: 20,
        cell: ({ row }) => (
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: statusColor(row.original.status) }}
            title={row.original.status}
          />
        ),
      },
      {
        id: "activity_id",
        header: "Activity",
        size: 170,
        cell: ({ row }) => (
          <button
            className="text-accent hover:underline text-left truncate max-w-full"
            onClick={(e) => {
              e.stopPropagation();
              navigate({ search: (s) => ({ ...s, activity: row.original.activity_id || undefined }) });
            }}
            title={row.original.activity_id ?? ""}
          >
            {row.original.activity_id ?? "—"}
          </button>
        ),
      },
      {
        id: "task_id",
        header: "Task",
        size: 130,
        cell: ({ row }) => <span className="font-mono">{shortId(row.original.task_id, 12)}</span>,
      },
      {
        id: "started_at",
        header: "Started",
        size: 150,
        accessorKey: "started_at",
        cell: ({ row }) => fmtTs(row.original.started_at),
      },
      {
        id: "duration",
        header: "Duration",
        size: 100,
        accessorFn: (t: Task) => taskDuration(t) ?? -1,
        cell: ({ row }) => fmtDuration(taskDuration(row.original)),
      },
      { id: "hostname", header: "Host", size: 130, accessorKey: "hostname" },
      {
        id: "workflow_id",
        header: "Workflow",
        size: 130,
        cell: ({ row }) =>
          row.original.workflow_id ? (
            <Link
              to="/workflows/$workflowId"
              params={{ workflowId: row.original.workflow_id }}
              className="text-accent font-mono text-xs hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              {shortId(row.original.workflow_id, 10)}
            </Link>
          ) : (
            ""
          ),
      },
      {
        id: "tags",
        header: "Tags",
        size: 140,
        cell: ({ row }) => row.original.tags?.join(", ") ?? "",
      },
    ],
    [navigate],
  );

  const tableSorting: SortingState = [{ id: sortField === "started_at" ? "started_at" : sortField, desc: sortOrder === -1 }];

  const activities = useMemo(
    () => [...new Set((summary.data?.activity_stats ?? []).map((a) => a.activity_id).filter(Boolean))] as string[],
    [summary.data],
  );
  const statuses = useMemo(() => Object.keys(summary.data?.status_counts ?? {}), [summary.data]);

  const agent = agentQuery.data?.agent;

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <header>
        <div className="text-fg-muted flex items-center gap-2 text-xs">
          <Link to="/agents" className="hover:text-fg hover:underline">Agents</Link>
        </div>
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold">{agent?.name || shortId(agentId, 20)}</h1>
        </div>
        <div className="text-fg-muted mt-0.5 font-mono text-xs">{agentId}</div>
        {agent && (
          <div className="text-fg-muted mt-0.5 flex flex-wrap gap-4 text-xs">
            {agent.task_count != null && <span>{agent.task_count} tasks</span>}
            {agent.last_active && <span>Last active: {fmtTs(agent.last_active)}</span>}
            {agent.campaign_ids?.length > 0 && <span>Campaigns: {agent.campaign_ids.length}</span>}
            {agent.source_agent_ids?.length > 0 && (
              <span>Sources: {agent.source_agent_ids.map((id) => shortId(id, 10)).join(", ")}</span>
            )}
          </div>
        )}
      </header>

      {summary.data && (
        <div className="card p-4">
          <StatusStrip summary={summary.data} />
        </div>
      )}

      <div className="flex items-center justify-between border-b border-border">
        <div className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => navigate({ search: (s) => ({ ...s, tab: t }) })}
              className={`px-3 py-2 text-xs capitalize ${
                search.tab === t ? "border-accent text-fg border-b-2" : "text-fg-muted hover:text-fg"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
        {search.tab === "tasks" && (
          <div className="flex gap-2 pb-1">
            <select
              value={search.status ?? ""}
              onChange={(e) => navigate({ search: (s) => ({ ...s, status: e.target.value || undefined }) })}
              className="rounded border border-border bg-surface px-2 py-1 text-xs"
            >
              <option value="">all statuses</option>
              {statuses.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
            <select
              value={search.activity ?? ""}
              onChange={(e) => navigate({ search: (s) => ({ ...s, activity: e.target.value || undefined }) })}
              className="rounded border border-border bg-surface px-2 py-1 text-xs"
            >
              <option value="">all activities</option>
              {activities.map((a) => (
                <option key={a}>{a}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {search.tab === "tasks" &&
        (tasks.isLoading ? (
          <div className="text-fg-muted text-xs">Loading tasks…</div>
        ) : (
          <DataTable
            data={taskItems}
            columns={columns}
            sorting={tableSorting}
            onSortingChange={(updater) => {
              const next = typeof updater === "function" ? updater(tableSorting) : updater;
              if (next[0]) navigate({ search: (s) => ({ ...s, sort: `${next[0].desc ? "-" : ""}${next[0].id}` }) });
            }}
            onRowClick={(t) => navigate({ search: (s) => ({ ...s, task: t.task_id }) })}
          />
        ))}

      {search.tab === "telemetry" && (
        <div className="card p-4">
          <TelemetryChart filter={{ $or: [{ agent_id: agentId }, { source_agent_id: agentId }] }} />
        </div>
      )}

      {search.tab === "dashboard" && <AgentDashboardTab agentId={agentId} />}

      {search.tab === "raw" && (
        <div className="card p-4">
          <JsonTree data={agentQuery.data} name="agent" />
        </div>
      )}

      {search.task && openTask.data && (
        <TaskDrawer task={openTask.data} onClose={() => navigate({ search: (s) => ({ ...s, task: undefined }) })} />
      )}
    </div>
  );
}

function AgentDashboardTab({ agentId }: { agentId: string }) {
  const resolved = useResolveDashboard({ workflow_name: "agent" });
  const rawCharts = resolved.data ?? [];
  const charts = rawCharts.map((raw) => chart.parse({ ...raw, data: { filter: {}, ...(raw.data as object) } }));
  const context = useMemo(() => ({ agent_id: agentId }), [agentId]);

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
    type: "workflow",
    name: "Agent Dashboard",
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
        No agent dashboard charts configured. Add a <code className="text-xs">workflow_name: "agent"</code> config
        under <Link to="/dashboards" className="text-accent hover:underline">Dashboard configs</Link>.
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
