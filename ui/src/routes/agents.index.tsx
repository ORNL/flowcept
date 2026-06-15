/** Agents list derived from task agent ids. */

import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Bot, ChevronLeft, ChevronRight } from "lucide-react";
import { useAgents } from "../api/queries";
import { fmtTs, sortAgents, filterActiveAgents, agentIconStyle, agentColor } from "../lib/format";

const PAGE_SIZE = 30;

export const Route = createFileRoute("/agents/")({ component: AgentsPage });

function AgentsPage() {
  const { data, isLoading, error } = useAgents();
  const [page, setPage] = useState(0);

  const visible = sortAgents(filterActiveAgents(data?.items ?? []));
  const totalPages = Math.ceil(visible.length / PAGE_SIZE);
  const pageItems = visible.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  // Key the color map by the real agent name (from backend), not the extracted ID-based name.
  // This ensures same-name agents (e.g. two "HPCAgent" instances with different ID formats)
  // always get the same icon color regardless of whether the ID is a plain UUID or named-UUID.
  const colorMap = new Map(
    visible.map((a) => {
      const label = a.name || a.agent_id;
      return [label, agentColor(undefined, label)];
    }),
  );

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <h1 className="text-xl font-semibold">Agents</h1>
      <p className="text-fg-muted text-xs">Agents observed in task provenance (agent_id / source_agent_id).</p>
      {isLoading && <div className="text-fg-muted text-xs">Loading…</div>}
      {error && <div className="text-err text-xs">{String(error)}</div>}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {pageItems.map((a) => (
          <Link
            key={a.agent_id}
            to="/agents/$agentId"
            params={{ agentId: a.agent_id }}
            className="card p-4 block hover:border-accent/60 transition-colors"
          >
            <div className="flex flex-col">
              <div className="flex items-center gap-2">
                <Bot size={15} data-testid="agent-icon" {...agentIconStyle(a.agent_id, colorMap, a.name)} />
                <span className="font-semibold text-sm">{a.name || a.agent_id}</span>
              </div>
              {a.name && (
                <div className="font-mono text-[10px] text-fg-muted mt-1 pl-6">
                  {a.agent_id}
                </div>
              )}
            </div>
            <div className="text-fg-muted mt-2 space-y-1 text-xs">
              <div>
                {a.task_count} tasks
                {a.registered_at && ` · registered ${fmtTs(a.registered_at)}`}
              </div>
              {a.activities.length > 0 && (
                <div>activities: {a.activities.join(", ")}</div>
              )}
              {a.workflow_ids?.length > 0 && (
                <div className="flex flex-wrap gap-1 items-center">
                  <span>workflows:</span>
                  {a.workflow_ids.map((wid: string) => (
                    <Link
                      key={wid}
                      to="/workflows/$workflowId"
                      params={{ workflowId: wid }}
                      className="font-mono text-accent hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {wid.slice(0, 8)}
                    </Link>
                  ))}
                </div>
              )}
              {a.source_agent_ids.length > 0 && (
                <div className="flex flex-wrap gap-1 items-center">
                  <span>source agents:</span>
                  {a.source_agent_ids.map((sid: string) => (
                    <Link
                      key={sid}
                      to="/agents/$agentId"
                      params={{ agentId: sid }}
                      className="font-mono text-accent hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {sid.slice(0, 8)}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </Link>
        ))}
      </div>
      {data && data.count === 0 && (
        <div className="text-fg-muted text-xs">No agent activity recorded yet.</div>
      )}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <button
            data-testid="pagination-prev"
            onClick={() => setPage((p) => p - 1)}
            disabled={page === 0}
            className="flex items-center gap-1 rounded border border-border px-2.5 py-1.5 text-xs disabled:opacity-40"
          >
            <ChevronLeft size={13} /> Prev
          </button>
          <span className="text-fg-muted text-xs">Page {page + 1} of {totalPages}</span>
          <button
            data-testid="pagination-next"
            onClick={() => setPage((p) => p + 1)}
            disabled={page >= totalPages - 1}
            className="flex items-center gap-1 rounded border border-border px-2.5 py-1.5 text-xs disabled:opacity-40"
          >
            Next <ChevronRight size={13} />
          </button>
        </div>
      )}
    </div>
  );
}
