/** Provenance lineage BFS — pure function, no React/DOM dependencies. */

export interface GraphEdge {
  source: string;
  target: string;
}

/**
 * Expand a set of seed node IDs to their full ancestor + descendant lineage
 * using two separate directed BFS passes (forward = descendants, backward =
 * ancestors). Keeping the passes separate prevents cross-contamination where a
 * single undirected traversal would visit the entire connected component.
 *
 * Returns a new Set containing the seeds and every reachable node in their lineage.
 * Returns an empty Set when seeds is empty.
 */
export function expandLineage(seeds: Iterable<string>, edges: GraphEdge[]): Set<string> {
  const result = new Set(seeds);
  if (result.size === 0) return result;

  // Capture seeds before either pass so both passes start from the same origin,
  // not from the growing result set (starting from result would pull in siblings
  // via descendants' ancestor edges — e.g. sibling C in a diamond A→B,A→C,B→D,C→D
  // when seeding B).
  const originalSeeds = [...result];

  const fwd = new Map<string, string[]>();
  const back = new Map<string, string[]>();
  for (const e of edges) {
    if (!fwd.has(e.source)) fwd.set(e.source, []);
    fwd.get(e.source)!.push(e.target);
    if (!back.has(e.target)) back.set(e.target, []);
    back.get(e.target)!.push(e.source);
  }

  for (const adj of [fwd, back]) {
    const stack = [...originalSeeds];
    while (stack.length) {
      const curr = stack.pop()!;
      for (const next of adj.get(curr) ?? []) {
        if (!result.has(next)) {
          result.add(next);
          stack.push(next);
        }
      }
    }
  }
  return result;
}
