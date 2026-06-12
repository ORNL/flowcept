/** Activity- or task-level DAG view for a workflow's tasks. */

import "@xyflow/react/dist/style.css";
import { useEffect, useMemo } from "react";
import { ReactFlow, ReactFlowProvider, useReactFlow, Background, Controls, MarkerType, type Node, type Edge } from "@xyflow/react";
import type { Task } from "../../api/types";
import { fmtDuration, shortId, toEpochSec } from "../../lib/format";
import { useInspectorStore, type GraphInspectorDoc } from "../../stores/inspectorStore";
import { useHighlightStore } from "../../stores/highlightStore";
import { TASK_NODE_STYLE } from "./graphStyles";
import { Bot } from "lucide-react";

const MAX_TASK_NODES = 150;

interface Props {
  tasks: Task[];
  /** "activity" groups tasks by activity_id (default); "task" shows one node per task. */
  mode?: "activity" | "task";
  height?: string | number;
}

function FitViewHelper({ trigger }: { trigger: any }) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    const timer = setTimeout(() => {
      void fitView({ duration: 250, padding: 0.2 });
    }, 100);
    return () => clearTimeout(timer);
  }, [trigger, fitView]);
  return null;
}

export function DagView({ tasks: allTasks, mode = "activity", height }: Props) {
  const tasks = useMemo(() => {
    if (mode !== "task" || allTasks.length <= MAX_TASK_NODES) return allTasks;
    return [...allTasks]
      .sort((a, b) => (toEpochSec(a.started_at) ?? 0) - (toEpochSec(b.started_at) ?? 0))
      .slice(0, MAX_TASK_NODES);
  }, [allTasks, mode]);

  const agentHighlight = useHighlightStore((s) => s.taskIds);

  const { nodes, edges } = useMemo(() => {
    // Group tasks by node key: activity_id, or task_id in task mode.
    const byActivity = new Map<string, Task[]>();
    for (const t of tasks) {
      const id = (mode === "task" ? t.task_id : t.activity_id) ?? "unknown";
      if (!byActivity.has(id)) byActivity.set(id, []);
      byActivity.get(id)!.push(t);
    }

    const activities = [...byActivity.keys()];

    // Derive edge connections from task dependencies, falling back to time-ordered chain
    const hasDeps = tasks.some((t) => Array.isArray((t as any).dependencies) && (t as any).dependencies.length > 0);

    const nodeKey = (t: Task) => ((mode === "task" ? t.task_id : t.activity_id) ?? "unknown");

    const activityEdges = new Set<string>();
    if (hasDeps) {
      for (const t of tasks) {
        const deps: string[] = (t as any).dependencies ?? [];
        for (const depId of deps) {
          const depTask = tasks.find((x) => x.task_id === depId);
          if (depTask && nodeKey(depTask) !== nodeKey(t)) {
            activityEdges.add(`${nodeKey(depTask)}__${nodeKey(t)}`);
          }
        }
      }
    }
    if (mode === "task" && activityEdges.size === 0) {
      // Parent links as a secondary structure source in task mode.
      for (const t of tasks) {
        const parent = (t as any).parent_task_id;
        if (parent && byActivity.has(parent)) activityEdges.add(`${parent}__${t.task_id}`);
      }
    }

    if (!hasDeps || activityEdges.size === 0) {
      // Fallback: sort activities by min started_at and chain linearly
      const sorted = activities.slice().sort((a, b) => {
        const minA = Math.min(...(byActivity.get(a) ?? []).map((t) => toEpochSec(t.started_at) ?? Infinity));
        const minB = Math.min(...(byActivity.get(b) ?? []).map((t) => toEpochSec(t.started_at) ?? Infinity));
        return minA - minB;
      });
      for (let i = 0; i < sorted.length - 1; i++) {
        activityEdges.add(`${sorted[i]}__${sorted[i + 1]}`);
      }
    }

    // Build rank tiers: BFS from sources
    const inDegree = new Map<string, number>(activities.map((a) => [a, 0]));
    const adj = new Map<string, string[]>(activities.map((a) => [a, []]));
    for (const edge of activityEdges) {
      const [from, to] = edge.split("__");
      adj.get(from)?.push(to);
      inDegree.set(to, (inDegree.get(to) ?? 0) + 1);
    }
    const ranks = new Map<string, number>();
    const queue = activities.filter((a) => (inDegree.get(a) ?? 0) === 0);
    for (const a of queue) ranks.set(a, 0);
    let head = 0;
    while (head < queue.length) {
      const curr = queue[head++];
      for (const next of adj.get(curr) ?? []) {
        const nextRank = (ranks.get(curr) ?? 0) + 1;
        if (!ranks.has(next)) {
          ranks.set(next, nextRank);
          queue.push(next);
        } else if (nextRank > (ranks.get(next) ?? 0)) {
          ranks.set(next, nextRank);
        }
      }
    }
    // Assign position: x = 220 * rank, y = 90 * index within rank
    const rankGroups = new Map<number, string[]>();
    for (const [a, r] of ranks) {
      if (!rankGroups.has(r)) rankGroups.set(r, []);
      rankGroups.get(r)!.push(a);
    }

    // Task mode without structural edges: grid columns per activity, rows per task.
    const gridFallback = mode === "task" && activityEdges.size === 0;
    const activityColumns = new Map<string, number>();
    const rowWithinActivity = new Map<string, number>();
    if (gridFallback) {
      const perActivityCount = new Map<string, number>();
      const sortedTasks = [...tasks].sort(
        (a, b) => (toEpochSec(a.started_at) ?? 0) - (toEpochSec(b.started_at) ?? 0),
      );
      for (const t of sortedTasks) {
        const act = t.activity_id ?? "unknown";
        if (!activityColumns.has(act)) activityColumns.set(act, activityColumns.size);
        const row = perActivityCount.get(act) ?? 0;
        perActivityCount.set(act, row + 1);
        rowWithinActivity.set(t.task_id, row);
      }
    }

    const nodes: Node[] = activities.map((activity) => {
      const actTasks = byActivity.get(activity) ?? [];
      const statuses = actTasks.map((t) => t.status ?? "");
      let rank = ranks.get(activity) ?? 0;
      const siblings = rankGroups.get(rank) ?? [];
      let idx = siblings.indexOf(activity);
      const labelText =
        mode === "task"
          ? `${actTasks[0]?.activity_id ?? "task"}\n${shortId(activity, 12)}`
          : `${activity}\n(${actTasks.length})`;
      const hasAgent = !!(actTasks[0]?.agent_id || actTasks[0]?.source_agent_id);
      const label = hasAgent ? (
        <div className="relative w-full h-full flex items-center justify-center">
          <Bot size={13} className="absolute -top-1.5 -right-1.5 text-accent bg-surface rounded-full p-0.5 border border-border" />
          <span className="whitespace-pre">{labelText}</span>
        </div>
      ) : (
        labelText
      );
      const start = Math.min(...actTasks.map((t) => toEpochSec(t.started_at) ?? Infinity));
      const end = Math.max(...actTasks.map((t) => toEpochSec(t.ended_at) ?? -Infinity));
      const duration = start !== Infinity && end !== -Infinity ? fmtDuration(end - start) : null;
      if (gridFallback) {
        rank = activityColumns.get(actTasks[0]?.activity_id ?? "unknown") ?? 0;
        idx = rowWithinActivity.get(activity) ?? 0;
      }
      const stats: Record<string, unknown> =
        mode === "task"
          ? {
              activity_id: actTasks[0]?.activity_id ?? null,
              task_id: activity,
              status: actTasks[0]?.status ?? null,
              started_at: actTasks[0]?.started_at ?? null,
              ended_at: actTasks[0]?.ended_at ?? null,
              duration,
              hostname: actTasks[0]?.hostname ?? null,
              parent_task_id: actTasks[0]?.parent_task_id ?? null,
              used: actTasks[0]?.used ?? null,
              generated: actTasks[0]?.generated ?? null,
              agent_id: actTasks[0]?.agent_id ?? null,
              source_agent_id: actTasks[0]?.source_agent_id ?? null,
            }
          : {
              activity_id: activity,
              task_count: actTasks.length,
              status_counts: statuses.reduce<Record<string, number>>((acc, status) => {
                if (!status) return acc;
                acc[status] = (acc[status] ?? 0) + 1;
                return acc;
              }, {}),
              started_at: start === Infinity ? null : start,
              ended_at: end === -Infinity ? null : end,
              duration,
              task_ids: actTasks.map((t) => t.task_id),
              agent_id: actTasks[0]?.agent_id ?? null,
              source_agent_id: actTasks[0]?.source_agent_id ?? null,
            };
      // Dim when the agent has highlighted specific tasks and this node is not among them.
      const dimmed =
        agentHighlight.size > 0 &&
        (mode === "task"
          ? !agentHighlight.has(activity)
          : !actTasks.some((t) => agentHighlight.has(t.task_id)));

      return {
        id: activity,
        position: { x: 220 * rank, y: (mode === "task" ? 70 : 90) * idx },
        data: { label, stats } as GraphInspectorDoc,
        style: {
          ...TASK_NODE_STYLE,
          fontSize: mode === "task" ? 10 : 12,
          whiteSpace: "pre",
          opacity: dimmed ? 0.15 : 1,
        },
      };
    });

    const edges: Edge[] = [...activityEdges].map((key) => {
      const [source, target] = key.split("__");
      return { id: key, source, target, type: "smoothstep", markerEnd: { type: MarkerType.ArrowClosed } };
    });

    return { nodes, edges };
  }, [tasks, mode, agentHighlight]);

  if (nodes.length === 0) return null;

  return (
    <div className={`space-y-1 ${height === "100%" ? "flex-1 flex flex-col h-full" : ""}`}>
      {mode === "task" && allTasks.length > MAX_TASK_NODES && (
        <div className="text-warn text-[11px]">
          Showing the first {MAX_TASK_NODES} of {allTasks.length} tasks.
        </div>
      )}
      <div
        style={{ height: height ?? (mode === "task" ? 420 : 320) }}
        className={`rounded border border-border bg-surface-2 ${height === "100%" ? "flex-1" : ""}`}
      >
        <ReactFlowProvider>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            onNodeClick={(_, node) => {
              const stats = node.data as unknown as GraphInspectorDoc;
              useInspectorStore.getState().set({
                kind: mode === "task" ? "task" : "activity",
                data: stats,
              });
            }}
            fitView
            fitViewOptions={{ padding: 0.2 }}
          >
            <Background />
            <Controls showInteractive={false} />
            <FitViewHelper trigger={height} />
          </ReactFlow>
        </ReactFlowProvider>
      </div>
    </div>
  );
}
