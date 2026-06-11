/** Activity-level DAG view for a workflow's tasks. */

import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import { ReactFlow, Background, Controls, type Node, type Edge } from "@xyflow/react";
import type { Task } from "../../api/types";
import { statusColor, toEpochSec } from "../../lib/format";

interface Props {
  tasks: Task[];
}

export function DagView({ tasks }: Props) {
  const { nodes, edges } = useMemo(() => {
    // Group tasks by activity_id
    const byActivity = new Map<string, Task[]>();
    for (const t of tasks) {
      const id = t.activity_id ?? "unknown";
      if (!byActivity.has(id)) byActivity.set(id, []);
      byActivity.get(id)!.push(t);
    }

    const activities = [...byActivity.keys()];

    // Derive edge connections from task dependencies, falling back to time-ordered chain
    const hasDeps = tasks.some((t) => Array.isArray((t as any).dependencies) && (t as any).dependencies.length > 0);

    const activityEdges = new Set<string>();
    if (hasDeps) {
      for (const t of tasks) {
        const deps: string[] = (t as any).dependencies ?? [];
        for (const depId of deps) {
          const depTask = tasks.find((x) => x.task_id === depId);
          if (depTask?.activity_id && t.activity_id && depTask.activity_id !== t.activity_id) {
            activityEdges.add(`${depTask.activity_id}__${t.activity_id}`);
          }
        }
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

    const nodes: Node[] = activities.map((activity) => {
      const actTasks = byActivity.get(activity) ?? [];
      const statuses = actTasks.map((t) => t.status ?? "");
      const aggStatus = statuses.includes("error") || statuses.includes("failed")
        ? "failed"
        : statuses.some((s) => s === "started" || s === "running")
        ? "running"
        : "finished";
      const rank = ranks.get(activity) ?? 0;
      const siblings = rankGroups.get(rank) ?? [];
      const idx = siblings.indexOf(activity);
      return {
        id: activity,
        position: { x: 220 * rank, y: 90 * idx },
        data: { label: `${activity}\n(${actTasks.length})` },
        style: {
          background: "#1e1e2e",
          color: "#cdd6f4",
          border: `2px solid ${statusColor(aggStatus)}`,
          borderRadius: 6,
          padding: "6px 12px",
          fontSize: 12,
          whiteSpace: "pre",
        },
      };
    });

    const edges: Edge[] = [...activityEdges].map((key) => {
      const [source, target] = key.split("__");
      return { id: key, source, target, type: "smoothstep" };
    });

    return { nodes, edges };
  }, [tasks]);

  if (nodes.length === 0) return null;

  return (
    <div style={{ height: 320 }} className="rounded border border-border bg-surface-2">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        fitView
        fitViewOptions={{ padding: 0.2 }}
      >
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
