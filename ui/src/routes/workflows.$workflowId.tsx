/** Workflow detail: status strip + tabs (tasks table, timeline, telemetry, prov card, artifacts, raw). */

import { useMemo, useState } from "react";
import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { Eye, EyeOff, Radio, Trash2 } from "lucide-react";
import type { ColumnDef, SortingState } from "@tanstack/react-table";
import { useObjects, useProvenanceCard, useResolveDashboard, useTask, useTasksQuery, useTaskSummary, useWorkflow } from "../api/queries";
import { useEventStream } from "../api/sse";
import type { BlobObjectDoc, ListResponse, Task } from "../api/types";
import { DeleteConfirmModal } from "../components/DeleteConfirmModal";
import { DagView } from "../components/charts/DagView";
import { DataflowView } from "../components/charts/DataflowView";
import { GanttChart } from "../components/charts/GanttChart";
import { StatusStrip } from "../components/charts/StatusStrip";
import { TelemetryChart } from "../components/charts/TelemetryChart";
import { JsonTree } from "../components/JsonTree";
import { Markdown } from "../components/markdown/Markdown";
import { DataTable } from "../components/tables/DataTable";
import { TaskDrawer } from "../components/tasks/TaskDrawer";
import { apiDelete } from "../api/client";
import { fmtDuration, fmtTs, shortId, statusColor, taskDuration, toEpochSec, type TimeValue } from "../lib/format";
import { ChartRenderer } from "../components/dashboard/ChartRenderer";
import { chart, dashboardSpec, type DashboardSpec } from "../components/dashboard/spec";
import { useInspectorStore } from "../stores/inspectorStore";

const TABS = ["tasks", "graph", "timeline", "telemetry", "card", "artifacts", "dashboard", "raw"] as const;

export const Route = createFileRoute("/workflows/$workflowId")({
  component: WorkflowDetail,
  validateSearch: z.object({
    tab: z.enum(TABS).default("tasks"),
    status: z.string().optional(),
    activity: z.string().optional(),
    task: z.string().optional(),
    sort: z.string().default("-started_at"),
    live: z.boolean().default(false),
  }),
});

function WorkflowDetail() {
  const { workflowId } = Route.useParams();
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  const router = useRouter();
  const [showDelete, setShowDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const workflow = useWorkflow(workflowId);
  const summary = useTaskSummary({ workflow_id: workflowId });

  const filter: Record<string, unknown> = { workflow_id: workflowId };
  if (search.status) filter["status"] = search.status;
  if (search.activity) filter["activity_id"] = search.activity;

  const sortField = search.sort.replace(/^-/, "");
  const sortOrder: 1 | -1 = search.sort.startsWith("-") ? -1 : 1;
  const tasksBody = useMemo(
    () => ({ filter, limit: 1000, sort: [{ field: sortField, order: sortOrder }] }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(filter), sortField, sortOrder],
  );
  const tasks = useTasksQuery(tasksBody);

  const queryClient = useQueryClient();
  useEventStream<Task>({
    path: "/stream/tasks",
    params: { workflow_id: workflowId },
    event: "tasks",
    enabled: search.live,
    onBatch: (docs) => {
      queryClient.setQueryData<ListResponse<Task>>(["tasks", tasksBody], (prev) => {
        if (!prev) return prev;
        const byId = new Map(prev.items.map((t) => [t.task_id, t]));
        for (const doc of docs) byId.set(doc.task_id, { ...byId.get(doc.task_id), ...doc });
        const items = [...byId.values()];
        return { ...prev, items, count: items.length };
      });
      void queryClient.invalidateQueries({ queryKey: ["taskSummary", { workflow_id: workflowId }] });
    },
  });

  const openTask = useTask(search.task ?? "", !!search.task);
  const taskItems = useMemo(() => tasks.data?.items ?? [], [tasks.data]);

  const columns = useMemo<ColumnDef<Task, any>[]>(
    () => [
      {
        id: "status",
        header: "",
        size: 36,
        enableSorting: false,
        cell: ({ row }) => (
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: statusColor(row.original.status) }}
            title={row.original.status}
          />
        ),
      },
      { id: "activity_id", header: "Activity", size: 170, accessorKey: "activity_id" },
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
        id: "parent",
        header: "Parent",
        size: 120,
        cell: ({ row }) =>
          row.original.parent_task_id ? (
            <span className="font-mono">{shortId(row.original.parent_task_id, 10)}</span>
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
    [],
  );

  const tableSorting: SortingState = [{ id: sortField === "started_at" ? "started_at" : sortField, desc: sortOrder === -1 }];

  const activities = useMemo(
    () => [...new Set((summary.data?.activity_stats ?? []).map((a) => a.activity_id).filter(Boolean))] as string[],
    [summary.data],
  );
  const statuses = useMemo(() => Object.keys(summary.data?.status_counts ?? {}), [summary.data]);

  const newestTaskEnd = useMemo(() => {
    const ends = taskItems.map((t) => t.ended_at).filter((v): v is number | string => Boolean(v));
    if (!ends.length) return null;
    return ends.reduce<number | string>((best, cur) => ((toEpochSec(cur) ?? 0) > (toEpochSec(best) ?? 0) ? cur : best), ends[0]);
  }, [taskItems]);

  const nowSec = Date.now() / 1000;
  const isFinished = Boolean(newestTaskEnd && ((toEpochSec(newestTaskEnd) ?? 0) > 0) && nowSec - (toEpochSec(newestTaskEnd) ?? 0) > 600);

  async function handleDelete() {
    setDeleting(true);
    try {
      await apiDelete(`/workflows/${workflowId}`);
      void router.invalidate();
      await navigate({ to: "/workflows" });
    } finally {
      setDeleting(false);
      setShowDelete(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <header>
        <div className="text-fg-muted flex items-center gap-2 text-xs">
          <Link to="/workflows" className="hover:text-fg hover:underline">Workflows</Link>
          {workflow.data?.campaign_id && (
            <>
              <span>·</span>
              <Link
                to="/campaigns/$campaignId"
                params={{ campaignId: workflow.data.campaign_id }}
                className="text-accent hover:underline"
              >
                campaign {shortId(workflow.data.campaign_id, 12)}
              </Link>
            </>
          )}
        </div>
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold">{workflow.data?.name ?? shortId(workflowId, 20)}</h1>
          {isFinished ? (
            <span className="rounded-full border border-ok/60 px-2.5 py-1 text-[11px] text-ok">Finished</span>
          ) : (
            <button
              onClick={() => navigate({ search: (s) => ({ ...s, live: !search.live }) })}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] ${
                search.live
                  ? "border-ok/60 text-ok animate-pulse"
                  : "border-border text-fg-muted hover:text-fg"
              }`}
              title="Toggle live updates (SSE)"
            >
              <Radio size={11} />
              {search.live ? "LIVE" : "Go live"}
            </button>
          )}
          <button
            onClick={() => setShowDelete(true)}
            className="ml-auto text-fg-muted hover:text-err"
            title="Delete workflow"
          >
            <Trash2 size={14} />
          </button>
        </div>
        <div className="text-fg-muted mt-0.5 font-mono text-xs">{workflowId}</div>
        {summary.data?.time_range && (summary.data.time_range.min_started_at || summary.data.time_range.max_ended_at) && (
          <div className="text-fg-muted mt-0.5 flex gap-4 text-xs">
            {summary.data.time_range.min_started_at && (
              <span>Started: {fmtTs(summary.data.time_range.min_started_at)}</span>
            )}
            {summary.data.time_range.max_ended_at && (
              <span>Ended: {fmtTs(summary.data.time_range.max_ended_at)}</span>
            )}
            {(() => {
              const s = toEpochSec(summary.data.time_range.min_started_at as TimeValue);
              const e = toEpochSec(summary.data.time_range.max_ended_at as TimeValue);
              return s && e ? <span>Duration: {fmtDuration(e - s)}</span> : null;
            })()}
          </div>
        )}
        {workflow.data?.workflow_description && (
          <p className="text-fg-muted mt-1 text-sm">{workflow.data.workflow_description}</p>
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
              {t === "card" ? "Workflow Card" : t === "dashboard" ? "Dashboard" : t === "graph" ? "Graphs" : t}
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

      {search.tab === "graph" && <GraphTab tasks={taskItems} workflowId={workflowId} />}

      {search.tab === "timeline" && (
        <div className="card p-4">
          <GanttChart
            tasks={taskItems}
            onTaskClick={(taskId) => navigate({ search: (s) => ({ ...s, task: taskId }) })}
          />
        </div>
      )}

      {search.tab === "telemetry" && (
        <div className="card p-4">
          {taskItems.length > 0 && !taskItems.some((t) => t.telemetry_at_start || t.telemetry_at_end) ? (
            <p className="text-fg-muted text-sm">Telemetry capture was disabled for this workflow.</p>
          ) : (
            <TelemetryChart filter={{ workflow_id: workflowId }} />
          )}
        </div>
      )}

      {search.tab === "card" && <ProvCardTab workflowId={workflowId} />}

      {search.tab === "artifacts" && <ArtifactsTab workflowId={workflowId} />}

      {search.tab === "dashboard" && <WorkflowDashboardTab workflowId={workflowId} workflowName={workflow.data?.name} />}

      {search.tab === "raw" && (
        <div className="card p-4">
          <JsonTree data={workflow.data} name="workflow" />
        </div>
      )}

      {search.task && openTask.data && (
        <TaskDrawer task={openTask.data} onClose={() => navigate({ search: (s) => ({ ...s, task: undefined }) })} />
      )}

      {showDelete && (
        <DeleteConfirmModal
          title="Delete workflow"
          description={`This will permanently delete workflow ${shortId(workflowId, 16)} and all its tasks and artifacts. This cannot be undone.`}
          onConfirm={handleDelete}
          onCancel={() => setShowDelete(false)}
          loading={deleting}
        />
      )}
    </div>
  );
}

function ProvCardTab({ workflowId }: { workflowId: string }) {
  const card = useProvenanceCard("workflows", workflowId);

  function downloadMd() {
    const blob = new Blob([card.data ?? ""], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `workflow_card_${workflowId}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function downloadPdf() {
    const a = document.createElement("a");
    a.href = `/api/v1/workflows/${workflowId}/workflow_card?format=pdf`;
    a.download = `workflow_card_${workflowId}.pdf`;
    a.click();
  }

  return (
    <div className="card p-5 space-y-4">
      {!card.isLoading && !card.error && card.data && (
        <div className="flex gap-2 justify-end">
          <button onClick={downloadMd} className="text-xs text-fg-muted hover:text-fg border border-border rounded px-2.5 py-1">
            Download Card
          </button>
          <button onClick={downloadPdf} className="text-xs text-fg-muted hover:text-fg border border-border rounded px-2.5 py-1">
            Download PDF
          </button>
        </div>
      )}
      {card.isLoading ? (
        <div className="text-fg-muted text-xs">Generating workflow card…</div>
      ) : card.error ? (
        <div className="text-err text-xs">{String(card.error)}</div>
      ) : (
        <Markdown stripInlineCode>{card.data ?? ""}</Markdown>
      )}
    </div>
  );
}

const OBJECT_COLS: ColumnDef<BlobObjectDoc, any>[] = [
  { id: "object_type", header: "Type", size: 100, cell: ({ row }) => (
    <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px]">{row.original.object_type ?? "—"}</span>
  )},
  { id: "object_id", header: "Object ID", size: 200, cell: ({ row }) => (
    <Link to="/objects/$objectId" params={{ objectId: row.original.object_id }} className="text-accent font-mono text-xs hover:underline">
      {shortId(row.original.object_id, 16)}
    </Link>
  )},
  { id: "version", header: "Version", size: 80, accessorKey: "version" },
  { id: "created_at", header: "Created", size: 150, cell: ({ row }) => <span>{fmtTs(row.original.created_at)}</span> },
];

function ArtifactsTab({ workflowId }: { workflowId: string }) {
  const objects = useObjects({ workflow_id: workflowId });
  const items = objects.data?.items ?? [];
  if (objects.isLoading) return <div className="text-fg-muted text-xs">Loading artifacts…</div>;
  if (!items.length) return <p className="text-fg-muted text-sm">No artifacts recorded for this workflow.</p>;
  return (
    <div className="card p-4">
      <DataTable data={items} columns={OBJECT_COLS} onRowClick={(obj) => useInspectorStore.getState().set({ kind: "object", data: obj })} />
    </div>
  );
}

function GraphTab({ tasks, workflowId }: { tasks: Task[]; workflowId: string }) {
  const [graphType, setGraphType] = useState<"activity" | "task" | "dataflow">("activity");
  return (
    <div className="card space-y-3 p-4">
      <div className="flex items-center gap-2">
        <div className="flex rounded border border-border text-xs">
          {(
            [
              ["activity", "Activity Graph"],
              ["task", "Task Graph"],
              ["dataflow", "Dataflow Graph"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setGraphType(key)}
              className={`px-3 py-1.5 ${graphType === key ? "bg-accent-soft text-fg" : "text-fg-muted hover:text-fg"}`}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="text-fg-muted text-[11px]">
          {graphType === "activity" && "Activities and their execution order."}
          {graphType === "task" && "Individual task executions."}
          {graphType === "dataflow" && "How data flows between tasks, derived from inputs and outputs."}
        </span>
      </div>
      {graphType === "dataflow" ? (
        <DataflowView workflowId={workflowId} />
      ) : (
        <DagView tasks={tasks} mode={graphType} />
      )}
    </div>
  );
}

function WorkflowDashboardTab({ workflowId, workflowName }: { workflowId: string; workflowName?: string | null }) {
  const [hiddenChartIds, setHiddenChartIds] = useState<Set<string>>(() => new Set());
  const resolved = useResolveDashboard({ workflow_name: workflowName ?? undefined });
  const rawCharts = resolved.data ?? [];
  const charts = rawCharts.map((raw) => chart.parse({ ...raw, data: { filter: {}, ...(raw.data as object) } }));
  const visibleCharts = charts.filter((c) => !hiddenChartIds.has(c.chart_id));
  const spec: DashboardSpec = dashboardSpec.parse({
    type: "workflow",
    name: "Workflow Dashboard",
    context: { workflow_id: workflowId },
    charts: visibleCharts,
    layout: [],
  });

  function toggleChart(chartId: string) {
    setHiddenChartIds((prev) => {
      const next = new Set(prev);
      if (next.has(chartId)) next.delete(chartId);
      else next.add(chartId);
      return next;
    });
  }

  if (resolved.isLoading) return <div className="text-fg-muted text-xs">Loading…</div>;

  if (!charts.length) {
    return (
      <p className="text-fg-muted text-sm">
        No charts configured. Visit{" "}
        <span className="font-medium">Dashboard configs</span> to add charts for this workflow.
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
