/** PROV-style dataflow graph: yellow-ellipse data entities, blue-rectangle task activities.
 *
 * Each task's inputs/outputs are packed into chunk entities; click nodes for details.
 */

import "@xyflow/react/dist/style.css";
import { useEffect, useState } from "react";
import { ReactFlow, ReactFlowProvider, useReactFlow, Background, Controls, MarkerType, useNodesState, useEdgesState, Position, type Node, type Edge } from "@xyflow/react";
import { useDataflow, type DataflowGraph } from "../../api/queries";
import { useInspectorStore } from "../../stores/inspectorStore";
import { useHighlightStore } from "../../stores/highlightStore";
import { TASK_NODE_STYLE } from "./graphStyles";
import { Bot } from "lucide-react";

interface Props {
  workflowId: string;
  height?: string | number;
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
        queue.push(next);
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

function FitViewHelper({ trigger }: { trigger: any }) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    const timer = setTimeout(() => {
      void fitView({ duration: 250, padding: 0.15 });
    }, 100);
    return () => clearTimeout(timer);
  }, [trigger, fitView]);
  return null;
}

export function DataflowView({ workflowId, height }: Props) {
  const [focus, setFocus] = useState<string | null>(null);
  const agentHighlight = useHighlightStore((s) => s.taskIds);

  const { data: graph, isLoading, error } = useDataflow(workflowId);

  const [prevWfId, setPrevWfId] = useState<string>(workflowId);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  if (prevWfId !== workflowId) {
    setPrevWfId(workflowId);
    setNodes([]);
    setEdges([]);
  }

  useEffect(() => {
    if (!graph) {
      setNodes([]);
      setEdges([]);
      return;
    }

    const { visibleNodes, visibleEdges, ranks, rankGroups } = layout(graph);

    // Seed lineage from: agent-highlighted task nodes + local click focus (combined).
    const seeds = new Set<string>();
    if (focus) seeds.add(focus);
    for (const tid of agentHighlight) seeds.add(`task:${tid}`);

    let lineage: Set<string> | null = null;
    if (seeds.size > 0) {
      // 1. Build a map of values for each node in the graph.
      const getValues = (n: any) => {
        const vals = new Set<string>();
        const addVal = (v: any) => {
          if (v === null || v === undefined) return;
          if (Array.isArray(v)) {
            for (const item of v) addVal(item);
          } else if (typeof v === "object") {
            for (const k of Object.keys(v)) addVal(v[k]);
          } else {
            const s = String(v);
            if (s.length > 2 && s !== "true" && s !== "false") {
              vals.add(s);
            }
          }
        };
        if (n.kind === "chunk") {
          addVal(n.stats?.items);
        } else {
          addVal(n.stats?.used);
          addVal(n.stats?.generated);
        }
        return vals;
      };

      const nodeValuesMap = new Map<string, Set<string>>();
      const nodeMap = new Map<string, any>();
      for (const n of visibleNodes) {
        nodeValuesMap.set(n.id, getValues(n));
        nodeMap.set(n.id, n);
      }

      // 2. Collect the union of all primitive values from the seed nodes.
      const V_seed = new Set<string>();
      for (const seed of seeds) {
        const vals = nodeValuesMap.get(seed);
        if (vals) {
          for (const v of vals) V_seed.add(v);
        }
      }

      // 3. Run standard BFS/DFS guided by V_seed intersection on derived edges only.
      lineage = new Set(seeds);
      const fwd = new Map<string, { node: string; relation: string }[]>();
      const back = new Map<string, { node: string; relation: string }[]>();
      for (const e of visibleEdges) {
        if (!fwd.has(e.source)) fwd.set(e.source, []);
        fwd.get(e.source)!.push({ node: e.target, relation: e.relation });
        if (!back.has(e.target)) back.set(e.target, []);
        back.get(e.target)!.push({ node: e.source, relation: e.relation });
      }
      // Two separate passes to avoid cross-contamination: forward (descendants) then backward (ancestors).
      for (const adj of [fwd, back]) {
        const stack = [...seeds];
        while (stack.length) {
          const curr = stack.pop()!;
          for (const edge of adj.get(curr) ?? []) {
            const next = edge.node;
            const rel = edge.relation;

            let shouldTraverse = true;
            if (rel === "derived") {
              const nextVals = nodeValuesMap.get(next) ?? new Set();
              const intersection = new Set([...V_seed].filter((x) => nextVals.has(x)));
              shouldTraverse = V_seed.size === 0 || nextVals.size === 0 || intersection.size > 0;
            }

            if (shouldTraverse) {
              if (!lineage.has(next)) {
                lineage.add(next);

                // Add next node's values to V_seed dynamically if it's a chunk node and NOT a selector node.
                const isChunk = next.startsWith("chunk:");
                if (isChunk) {
                  const incomingDerived = (back.get(next) ?? []).filter((e) => e.relation === "derived");
                  let isSelectorChunk = false;
                  if (incomingDerived.length > 1) {
                    const sourceActivities = new Set<string>();
                    for (const e of incomingDerived) {
                      const srcNode = nodeMap.get(e.node);
                      if (srcNode && srcNode.stats?.generated_by) {
                        for (const g of srcNode.stats.generated_by) {
                          if (g.activity) {
                            sourceActivities.add(g.activity);
                          }
                        }
                      }
                    }
                    if (sourceActivities.size === 1) {
                      isSelectorChunk = true;
                    }
                  }

                  if (!isSelectorChunk) {
                    const nextVals = nodeValuesMap.get(next);
                    if (nextVals) {
                      for (const v of nextVals) V_seed.add(v);
                    }
                  }
                }

                stack.push(next);
              }
            }
          }
        }
      }
    }

    const nextNodes: Node[] = visibleNodes.map((n) => {
      const rank = ranks.get(n.id) ?? 0;
      const siblings = rankGroups.get(rank) ?? [];
      const idx = siblings.indexOf(n.id);
      const dimmed = lineage !== null && !lineage.has(n.id);
      const isEntity = n.kind !== "task";

      const hasAgent = !!(n.stats?.agent_id || n.stats?.source_agent_id);
      const label = hasAgent ? (
        <div className="relative w-full h-full flex items-center justify-center">
          <Bot size={13} className="absolute -top-1.5 -right-1.5 text-accent bg-surface rounded-full p-0.5 border border-border" />
          <span className="whitespace-pre">{n.label}</span>
        </div>
      ) : (
        n.label
      );

      return {
        id: n.id,
        position: { x: 230 * rank, y: 72 * idx },
        data: { label },
        targetPosition: Position.Left,
        sourcePosition: Position.Right,
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

    const nextEdges: Edge[] = visibleEdges.map((e, i) => {
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

    // Update nodes state preserving previously dragged positions.
    setNodes((prevNodes) => {
      const prevPositions = new Map(prevNodes.map((n) => [n.id, n.position]));
      return nextNodes.map((n) => ({
        ...n,
        position: prevPositions.get(n.id) || n.position,
      }));
    });
    setEdges(nextEdges);
  }, [graph, focus, agentHighlight]);

  if (isLoading) return <div className="text-fg-muted text-xs">Loading dataflow…</div>;
  if (error) return <div className="text-fg-muted text-xs">No dataflow data captured for this workflow.</div>;
  if (!graph || nodes.length === 0) return <div className="text-fg-muted text-xs">No dataflow data captured.</div>;

  return (
    <div className={`space-y-2 ${height === "100%" ? "flex-1 flex flex-col h-full justify-between" : ""}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-fg-muted text-[11px]">
          Inputs and outputs are packed into data chunks — click a task or chunk to inspect metadata.
        </span>
        {graph.truncated && (
          <span className="text-warn text-[11px]">Graph truncated — showing the first tasks only.</span>
        )}
      </div>

      <div
        style={{ height: height ?? 440 }}
        className={`rounded border border-border bg-surface-2 ${height === "100%" ? "flex-1" : ""}`}
      >
        <ReactFlowProvider>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            nodesDraggable={true}
            nodesConnectable={false}
            onNodeClick={(_, node) => {
              useHighlightStore.getState().clearHighlight();
              setFocus((prev) => (prev === node.id ? null : node.id));
              const selectedNode = graph.nodes.find((n) => n.id === node.id) ?? null;
              if (selectedNode) {
                useInspectorStore.getState().set({
                  kind: selectedNode.kind === "task" ? "task" : "dataflow",
                  data: { label: selectedNode.label, stats: selectedNode.stats },
                });
              }
            }}
            onPaneClick={(e) => {
              if ((e.target as HTMLElement).closest(".react-flow__node")) return;
              setFocus(null);
              useHighlightStore.getState().clearHighlight();
            }}
            fitView
            fitViewOptions={{ padding: 0.15 }}
          >
            <Background />
            <Controls showInteractive={false} />
            <FitViewHelper trigger={height} />
          </ReactFlow>
        </ReactFlowProvider>
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
