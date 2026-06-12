/** Agents list derived from task agent ids. */

import { createFileRoute } from "@tanstack/react-router";
import { Bot } from "lucide-react";
import { useAgents } from "../api/queries";
import { fmtTs } from "../lib/format";

export const Route = createFileRoute("/agents/")({ component: AgentsPage });

function AgentsPage() {
  const { data, isLoading, error } = useAgents();

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <h1 className="text-xl font-semibold">Agents</h1>
      <p className="text-fg-muted text-xs">Agents observed in task provenance (agent_id / source_agent_id).</p>
      {isLoading && <div className="text-fg-muted text-xs">Loading…</div>}
      {error && <div className="text-err text-xs">{String(error)}</div>}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {(data?.items ?? []).map((a) => (
          <div key={a.agent_id} className="card p-4">
            <div className="flex flex-col">
              <div className="flex items-center gap-2">
                <Bot size={15} className="text-accent" />
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
              {a.activities.length > 0 && <div>activities: {a.activities.join(", ")}</div>}
              {a.source_agent_ids.length > 0 && <div>sources: {a.source_agent_ids.join(", ")}</div>}
            </div>
          </div>
        ))}
      </div>
      {data && data.count === 0 && (
        <div className="text-fg-muted text-xs">No agent activity recorded yet.</div>
      )}
    </div>
  );
}
