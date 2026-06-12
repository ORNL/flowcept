/** PROV-style dataflow graph: yellow-ellipse data entities, blue-rectangle task activities.
 *
 * Each task's inputs/outputs are packed into chunk entities; click nodes for details.
 */

import "@xyflow/react/dist/style.css";
import { useMemo, useState } from "react";
import { ReactFlow, Background, Controls, MarkerType, type Node, type Edge } from "@xyflow/react";
import { useDataflow, type DataflowGraph } from "../../api/queries";
import { useInspectorStore } from "../../stores/inspectorStore";
import { TASK_NODE_STYLE } from "./graphStyles";

interface Props {
  workflowId: string;
}

// W3C PROV diagram convention: Entity = yellow ellipse, Activity = blue rectangle.
const PROV = {
  entityBg: "#FFFC87",
  entityBorder: "#808080",
  activityBg: "#9FB1FC",
  activityBorder: "#0000FF",
  text: "#11111b",
};

/** Longest-path layered layout over the directed graph. */
function layout(graph: DataflowGraph) {
  const visibleNodes = graph.nodes;
  const visibleIds = new Set(visibleNodes.map((n) => n.id));
  const visibleEdges = graph.edges.filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target));

  const inDegree = new Map<string, number>(visibleNodes.map((n) => [n.id, 0]));
  const adj = new Map<string, string[]>(visibleNodes.map((n) => [n.id, []]));
  for (const e of visibleEdges) {
    adj.get(e.source)?.push(e.target);
    inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1);
  }

  const ranks = new Map<string, number>();
  const queue = visibleNodes.filter((n) => (inDegree.get(n.id) ?? 0) === 0).map((n) => n.id);
  for (const id of queue) ranks.set(id, 0);
  let head = 0;
  while (head < queue.length) {
    const curr = queue[head++];
    for (const next of adj.get(curr) ?? []) {
      const nextRank = (ranks.get(curr) ?? 0) + 1;
      if (!ranks.has(next)) {
        ranks.set(next, nextRank);
        queue.push(next);
      } else if (nextRank > (ranks.get(next) ?? 0) && nextRank < 50) {
        ranks.set(next, nextRank);
      }
    }
  }
  for (const n of visibleNodes) if (!ranks.has(n.id)) ranks.set(n.id, 0);

  const rankGroups = new Map<number, string[]>();
  for (const [id, r] of ranks) {
    if (!rankGroups.has(r)) rankGroups.set(r, []);
    rankGroups.get(r)!.push(id);
  }
  return { visibleNodes, visibleEdges, ranks, rankGroups };
}

export function DataflowView({ workflowId }: Props) {
  const [focus, setFocus] = useState<string | null>(null);

  const { data: graph, isLoading, error } = useDataflow(workflowId);

  const { nodes, edges } = useMemo(() => {
    if (!graph) return { nodes: [] as Node[], edges: [] as Edge[] };

    const { visibleNodes, visibleEdges, ranks, rankGroups } = layout(graph);

    // Lineage highlight: upstream + downstream reachable set from the focused node.
    let lineage: Set<string> | null = null;
    if (focus) {
      lineage = new Set([focus]);
      const fwd = new Map<string, string[]>();
      const back = new Map<string, string[]>();
      for (const e of visibleEdges) {
        if (!fwd.has(e.source)) fwd.set(e.source, []);
        fwd.get(e.source)!.push(e.target);
        if (!back.has(e.target)) back.set(e.target, []);
        back.get(e.target)!.push(e.source);
      }
      for (const dir of [fwd, back]) {
        const stack = [focus];
        while (stack.length) {
          const curr = stack.pop()!;
          for (const next of dir.get(curr) ?? []) {
            if (!lineage.has(next)) {
              lineage.add(next);
              stack.push(next);
            }
          }
        }
      }
    }

    const nodes: Node[] = visibleNodes.map((n) => {
      const rank = ranks.get(n.id) ?? 0;
      const siblings = rankGroups.get(rank) ?? [];
      const idx = siblings.indexOf(n.id);
      const dimmed = lineage !== null && !lineage.has(n.id);
      const isEntity = n.kind !== "task";

      return {
        id: n.id,
        position: { x: 230 * rank, y: 72 * idx },
        data: { label: n.label },
        style: isEntity
          ? {
              // PROV Entity: yellow ellipse.
              background: PROV.entityBg,
              color: PROV.text,
              border: `1.5px solid ${PROV.entityBorder}`,
              borderRadius: "50%",
              padding: "10px 18px",
              fontSize: 11,
              textAlign: "center" as const,
              opacity: dimmed ? 0.12 : 1,
            }
          : {
              ...TASK_NODE_STYLE,
              opacity: dimmed ? 0.12 : 1,
            },
      };
    });

    const edges: Edge[] = visibleEdges.map((e, i) => {
      const dimmed = lineage !== null && !(lineage.has(e.source) && lineage.has(e.target));
      return {
        id: `${e.source}->${e.target}-${i}`,
        source: e.source,
        target: e.target,
        type: "smoothstep",
        animated: !dimmed && lineage !== null,
        markerEnd: { type: MarkerType.ArrowClosed },
        style: {
          opacity: dimmed ? 0.06 : 0.85,
          strokeDasharray: e.relation === "derived" ? "5 4" : undefined,
        },
      };
    });

    return { nodes, edges };
  }, [graph, focus]);

  if (isLoading) return <div className="text-fg-muted text-xs">Loading dataflow…</div>;
  if (error) return <div className="text-fg-muted text-xs">No dataflow data captured for this workflow.</div>;
  if (!graph || nodes.length === 0) return <div className="text-fg-muted text-xs">No dataflow data captured.</div>;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-fg-muted text-[11px]">
          Inputs and outputs are packed into data chunks — click a task or chunk to inspect metadata.
        </span>
        {graph.truncated && (
          <span className="text-warn text-[11px]">Graph truncated — showing the first tasks only.</span>
        )}
      </div>

      <div style={{ height: 440 }} className="rounded border border-border bg-surface-2">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodesDraggable={false}
          nodesConnectable={false}
          onNodeClick={(_, node) => {
            setFocus((prev) => (prev === node.id ? null : node.id));
            const selectedNode = graph.nodes.find((n) => n.id === node.id) ?? null;
            if (selectedNode) {
              useInspectorStore.getState().set({
                kind: selectedNode.kind === "task" ? "task" : "dataflow",
                data: { label: selectedNode.label, stats: selectedNode.stats },
              });
            }
          }}
          fitView
          fitViewOptions={{ padding: 0.15 }}
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="text-fg-muted flex items-center gap-3 text-[11px]">
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block h-3 w-5 rounded-full"
              style={{ background: PROV.entityBg, border: `1px solid ${PROV.entityBorder}` }}
            />
            data (entity)
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block h-3 w-5"
              style={{ background: PROV.activityBg, border: `1px solid ${PROV.activityBorder}` }}
            />
            task (activity)
          </span>
          <span className="border-l border-border pl-3">┄ derived from</span>
        </div>
      </div>
    </div>
  );
}
