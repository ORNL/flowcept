/**
 * Coarse Provenance Graph: task nodes grouped by activity_id, chunk nodes
 * grouped by their generating activity.  Nodes with count > 1 show a ×N
 * badge and a double-border outline.  Edges with count > 1 are rendered as
 * two offset parallel bezier curves with a ×N label.
 */

import "@xyflow/react/dist/style.css";
import { useEffect } from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  MarkerType,
  useNodesState,
  useEdgesState,
  Position,
  getBezierPath,
  type Node,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";
import { Bot } from "lucide-react";
import { useDataflow } from "../../api/queries";
import { useInspectorStore } from "../../stores/inspectorStore";
import { coarsenGraph, type CoarseNode } from "../../lib/coarsenGraph";
import { agentIconStyle, buildAgentNameColorMap } from "../../lib/format";

// W3C PROV colours — same palette as DataflowView for visual consistency.
const PROV = {
  entityBg: "#FFFC87",
  entityBorder: "#808080",
  activityBg: "#9FB1FC",
  activityBorder: "#0000FF",
  text: "#11111b",
};

// ---------------------------------------------------------------------------
// Custom edge: double-line for aggregated connections
// ---------------------------------------------------------------------------

function AggregatedEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  style,
  data,
}: EdgeProps) {
  const count = (data as Record<string, unknown>)?.count as number ?? 1;
  const color = (style?.stroke as string) ?? "#666";
  const opacity = (style?.opacity as number) ?? 0.85;

  const baseProps = { sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition };
  const [pathMid, lx, ly] = getBezierPath(baseProps);

  if (count <= 1) {
    return (
      <path
        id={id}
        d={pathMid}
        stroke={color}
        strokeWidth={1.5}
        fill="none"
        opacity={opacity}
        markerEnd={markerEnd ?? undefined}
      />
    );
  }

  // Two parallel bezier curves with ±3.5 px vertical offset → rail-track effect.
  const [pathTop] = getBezierPath({ ...baseProps, sourceY: sourceY - 3.5, targetY: targetY - 3.5 });
  const [pathBot] = getBezierPath({ ...baseProps, sourceY: sourceY + 3.5, targetY: targetY + 3.5 });

  return (
    <g opacity={opacity}>
      <path id={id} d={pathTop} stroke={color} strokeWidth={1.5} fill="none" />
      <path d={pathBot} stroke={color} strokeWidth={1.5} fill="none" markerEnd={markerEnd ?? undefined} />
      {/* Invisible wide hit area for pointer events */}
      <path d={pathMid} stroke="transparent" strokeWidth={12} fill="none" />
      <text
        x={lx}
        y={ly - 10}
        textAnchor="middle"
        fontSize={9}
        fill={color}
        style={{ userSelect: "none", pointerEvents: "none" }}
      >
        ×{count}
      </text>
    </g>
  );
}

// Defined outside the component so the reference is stable across renders.
const EDGE_TYPES = { aggregated: AggregatedEdge };

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

function fmtDur(sec: number): string {
  if (sec < 1) return `${(sec * 1000).toFixed(0)}ms`;
  if (sec < 60) return `${sec.toFixed(1)}s`;
  return `${(sec / 60).toFixed(1)}m`;
}

interface CoarseLike {
  nodes: { id: string }[];
  edges: { source: string; target: string }[];
}

function layoutCoarse(g: CoarseLike) {
  const inDegree = new Map(g.nodes.map((n) => [n.id, 0]));
  const adj = new Map<string, string[]>(g.nodes.map((n) => [n.id, []]));
  for (const e of g.edges) {
    adj.get(e.source)?.push(e.target);
    inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1);
  }
  const ranks = new Map<string, number>();
  const queue = g.nodes.filter((n) => (inDegree.get(n.id) ?? 0) === 0).map((n) => n.id);
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
        queue.push(next);
      }
    }
  }
  for (const n of g.nodes) if (!ranks.has(n.id)) ranks.set(n.id, 0);
  const rankGroups = new Map<number, string[]>();
  for (const [id, r] of ranks) {
    if (!rankGroups.has(r)) rankGroups.set(r, []);
    rankGroups.get(r)!.push(id);
  }
  return { ranks, rankGroups };
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface Props {
  workflowId: string;
  height?: string | number;
}

export function CoarseDataflowView({ workflowId, height }: Props) {
  const { data: graph, isLoading, error } = useDataflow(workflowId);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    if (!graph) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const coarse = coarsenGraph(graph);
    const { ranks, rankGroups } = layoutCoarse(coarse);

    // Build agent color map from ALL original task node agent IDs — same scheme as DataflowView.
    const agentColorMap = buildAgentNameColorMap(
      graph.nodes
        .filter((n) => n.kind === "task")
        .map((n) => (n.stats?.agent_id || n.stats?.source_agent_id) as string | null | undefined),
    );
    // Quick lookup from original node ID → node (for agent_id extraction).
    const nodeMap = new Map(graph.nodes.map((n) => [n.id, n]));

    const nextNodes: Node[] = coarse.nodes.map((n) => {
      const rank = ranks.get(n.id) ?? 0;
      const siblings = rankGroups.get(rank) ?? [];
      const idx = siblings.indexOf(n.id);
      const isEntity = n.kind !== "task";
      const isAggregated = n.count > 1;

      // Use the first original node's agent_id (matches DagView's actTasks[0] approach).
      const firstOrig = nodeMap.get(n.originalIds[0]);
      const agentId = n.kind === "task"
        ? ((firstOrig?.stats?.agent_id || firstOrig?.stats?.source_agent_id) as string | null | undefined)
        : undefined;
      const hasAgent = !!agentId;

      let labelContent: React.ReactNode;
      if (n.kind === "task" && isAggregated) {
        const mean = n.durationStats?.mean;
        labelContent = (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
            <span style={{ fontWeight: 500 }}>{n.label}</span>
            <span style={{ fontSize: 9, opacity: 0.7 }}>
              ×{n.count}{mean != null ? ` · avg ${fmtDur(mean)}` : ""}
            </span>
          </div>
        );
      } else if (isEntity && isAggregated) {
        labelContent = (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
            <span>{n.label}</span>
            <span style={{ fontSize: 9, opacity: 0.7 }}>×{n.count} chunks</span>
          </div>
        );
      } else {
        labelContent = n.label;
      }

      // Wrap task label with the agent icon (same position as DataflowView / DagView).
      if (hasAgent) {
        labelContent = (
          <div className="relative w-full h-full flex items-center justify-center">
            <Bot
              size={13}
              data-testid="coarse-agent-icon"
              {...agentIconStyle(agentId, agentColorMap)}
              className="absolute -top-1.5 -right-1.5 bg-surface rounded-full p-0.5 border border-border"
            />
            {labelContent}
          </div>
        );
      }

      const baseStyle = isEntity
        ? {
            background: PROV.entityBg,
            color: PROV.text,
            border: `1.5px solid ${PROV.entityBorder}`,
            borderRadius: "50%",
            padding: "10px 18px",
            fontSize: 11,
            textAlign: "center" as const,
          }
        : {
            background: PROV.activityBg,
            color: PROV.text,
            border: `1.5px solid ${PROV.activityBorder}`,
            borderRadius: 4,
            padding: "8px 14px",
            fontSize: 11,
            textAlign: "center" as const,
          };

      return {
        id: n.id,
        position: { x: 250 * rank, y: 80 * idx },
        data: { label: labelContent, coarseNode: n },
        targetPosition: Position.Left,
        sourcePosition: Position.Right,
        style: isAggregated
          ? {
              ...baseStyle,
              outline: `2px solid ${isEntity ? PROV.entityBorder : PROV.activityBorder}`,
              outlineOffset: "3px",
            }
          : baseStyle,
      };
    });

    const nextEdges: Edge[] = coarse.edges.map((e, i) => ({
      id: `${e.source}->${e.target}-${i}`,
      source: e.source,
      target: e.target,
      type: "aggregated",
      data: { count: e.count },
      markerEnd: { type: MarkerType.ArrowClosed },
      style: {
        opacity: 0.85,
        strokeDasharray: e.relation === "derived" ? "5 4" : undefined,
      },
    }));

    setNodes(nextNodes);
    setEdges(nextEdges);
  }, [graph, setNodes, setEdges]);

  if (isLoading) return <div className="text-fg-muted text-xs">Loading coarse provenance graph…</div>;
  if (error) return <div className="text-fg-muted text-xs">No dataflow data captured for this workflow.</div>;
  if (!graph || nodes.length === 0) return <div className="text-fg-muted text-xs">No dataflow data captured.</div>;

  return (
    <div className={`space-y-2 ${height === "100%" ? "flex-1 flex flex-col h-full justify-between" : ""}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-fg-muted text-[11px]">
          Tasks with the same activity are condensed into one node — ×N shows how many were aggregated.
          {graph.truncated && (
            <span className="text-warn ml-2">Graph truncated — showing the first tasks only.</span>
          )}
        </span>
      </div>

      <div
        style={{ height: height ?? 440 }}
        className={`rounded border border-border bg-surface-2 ${height === "100%" ? "flex-1" : ""}`}
      >
        <ReactFlowProvider>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            edgeTypes={EDGE_TYPES}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodesDraggable
            nodesConnectable={false}
            onNodeClick={(_, node) => {
              const cn = (node.data as Record<string, unknown>)?.coarseNode as CoarseNode | undefined;
              if (!cn) return;

              // Single node: pass original DataflowNode data, same as DataflowView.
              if (cn.count === 1) {
                const orig = graph.nodes.find((n) => n.id === cn.originalIds[0]);
                if (orig) {
                  useInspectorStore.getState().set({
                    kind: orig.kind === "task" ? "task" : "dataflow",
                    data: { label: orig.label, stats: orig.stats },
                  });
                }
                return;
              }

              // Aggregated task: show duration stats summary.
              if (cn.kind === "task") {
                useInspectorStore.getState().set({
                  kind: "activity",
                  data: {
                    label: cn.label,
                    stats: {
                      task_count: cn.count,
                      task_ids: cn.originalIds,
                      duration_stats: cn.durationStats ?? null,
                    },
                  },
                });
                return;
              }

              // Aggregated chunk: show per-key item stats if available.
              useInspectorStore.getState().set({
                kind: "dataflow",
                data: {
                  label: cn.label,
                  stats: {
                    chunk_count: cn.count,
                    activities: cn.activities,
                    original_ids: cn.originalIds,
                    item_stats: cn.itemStats ?? null,
                  },
                },
              });
            }}
            fitView
            fitViewOptions={{ padding: 0.15 }}
          >
            <Background />
            <Controls showInteractive={false} />
          </ReactFlow>
        </ReactFlowProvider>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="text-fg-muted flex flex-wrap items-center gap-3 text-[11px]">
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block h-3 w-5 rounded-full"
              style={{
                background: PROV.entityBg,
                border: `1px solid ${PROV.entityBorder}`,
                outline: `2px solid ${PROV.entityBorder}`,
                outlineOffset: "2px",
              }}
            />
            data (aggregated)
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block h-3 w-5 rounded-sm"
              style={{
                background: PROV.activityBg,
                border: `1px solid ${PROV.activityBorder}`,
                outline: `2px solid ${PROV.activityBorder}`,
                outlineOffset: "2px",
              }}
            />
            task activity (aggregated)
          </span>
          <span className="border-l border-border pl-3">double edge = multiple parallel connections</span>
          <span className="border-l border-border pl-3">×N = number of original instances</span>
        </div>
      </div>
    </div>
  );
}
