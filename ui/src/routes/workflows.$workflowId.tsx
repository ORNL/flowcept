/** Workflow detail: status strip + tabs (tasks table, timeline, telemetry, prov card, raw). */

import { useMemo } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { Radio } from "lucide-react";
import type { ColumnDef, SortingState } from "@tanstack/react-table";
import { useProvenanceCard, useTask, useTasksQuery, useTaskSummary, useWorkflow } from "../api/queries";
import { useEventStream } from "../api/sse";
import type { ListResponse, Task } from "../api/types";
import { GanttChart } from "../components/charts/GanttChart";
import { StatusStrip } from "../components/charts/StatusStrip";
import { TelemetryChart } from "../components/charts/TelemetryChart";
import { JsonTree } from "../components/JsonTree";
import { Markdown } from "../components/markdown/Markdown";
import { DataTable } from "../components/tables/DataTable";
import { TaskDrawer } from "../components/tasks/TaskDrawer";
import { fmtDuration, fmtTs, shortId, statusColor, taskDuration } from "../lib/format";

const TABS = ["tasks", "timeline", "telemetry", "card", "raw"] as const;

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

  const openTask = useTask(search.task ?? "");
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

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <header>
        <div className="text-fg-muted flex items-center gap-2 text-xs">
          <span>Workflow</span>
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
        </div>
        <div className="text-fg-muted mt-0.5 font-mono text-xs">{workflowId}</div>
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
              {t === "card" ? "Provenance card" : t}
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
          <TelemetryChart filter={{ workflow_id: workflowId }} />
        </div>
      )}

      {search.tab === "card" && <ProvCardTab workflowId={workflowId} />}

      {search.tab === "raw" && (
        <div className="card p-4">
          <JsonTree data={workflow.data} name="workflow" />
        </div>
      )}

      {search.task && openTask.data && (
        <TaskDrawer task={openTask.data} onClose={() => navigate({ search: (s) => ({ ...s, task: undefined }) })} />
      )}
    </div>
  );
}

function ProvCardTab({ workflowId }: { workflowId: string }) {
  const card = useProvenanceCard("workflows", workflowId);
  return (
    <div className="card p-5">
      {card.isLoading ? (
        <div className="text-fg-muted text-xs">Generating provenance card…</div>
      ) : card.error ? (
        <div className="text-err text-xs">{String(card.error)}</div>
      ) : (
        <Markdown>{card.data ?? ""}</Markdown>
      )}
    </div>
  );
}
