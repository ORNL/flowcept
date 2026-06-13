/** Right slide-over with full task details; opened via the ?task= search param. */

import { Link } from "@tanstack/react-router";
import { ExternalLink, X } from "lucide-react";
import type { Task } from "../../api/types";
import { fmtDuration, fmtTs, statusColor, taskDuration } from "../../lib/format";
import { JsonTree } from "../JsonTree";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2 py-1 text-xs">
      <span className="text-fg-muted w-28 shrink-0">{label}</span>
      <span className="min-w-0 break-all">{children}</span>
    </div>
  );
}

export function TaskDrawer({ task, onClose }: { task: Task; onClose: () => void }) {
  return (
    <div className="fixed inset-y-0 right-0 z-40 flex w-[480px] max-w-[90vw] flex-col border-l border-border bg-surface shadow-2xl">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: statusColor(task.status) }} />
          <span className="font-medium">{task.activity_id ?? "task"}</span>
          <span className="text-fg-muted text-xs">{task.status}</span>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/tasks/$taskId"
            params={{ taskId: task.task_id }}
            className="text-fg-muted hover:text-fg"
            title="Open full page"
          >
            <ExternalLink size={15} />
          </Link>
          <button onClick={onClose} className="text-fg-muted hover:text-fg">
            <X size={16} />
          </button>
        </div>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        <div className="card p-3">
          <Field label="task_id">
            <span className="font-mono">{task.task_id}</span>
          </Field>
          {task.parent_task_id && (
            <Field label="parent_task_id">
              <span className="font-mono">{task.parent_task_id}</span>
            </Field>
          )}
          <Field label="workflow">
            {task.workflow_id ? (
              <Link
                to="/workflows/$workflowId"
                params={{ workflowId: task.workflow_id }}
                className="text-accent font-mono hover:underline"
              >
                {task.workflow_id}
              </Link>
            ) : (
              "—"
            )}
          </Field>
          <Field label="started">{fmtTs(task.started_at)}</Field>
          <Field label="ended">{fmtTs(task.ended_at)}</Field>
          <Field label="duration">{fmtDuration(taskDuration(task))}</Field>
          <Field label="host">{task.hostname ?? "—"}</Field>
          {task.agent_id && <Field label="agent">{task.agent_id}</Field>}
          {task.subtype && <Field label="subtype">{task.subtype}</Field>}
          {task.tags && task.tags.length > 0 && <Field label="tags">{task.tags.join(", ")}</Field>}
        </div>
        <section>
          <h3 className="text-fg-muted mb-1 text-xs font-semibold uppercase">Used (inputs)</h3>
          <div className="card p-3">
            <JsonTree data={task.used} name="used" />
          </div>
        </section>
        <section>
          <h3 className="text-fg-muted mb-1 text-xs font-semibold uppercase">Generated (outputs)</h3>
          <div className="card p-3">
            <JsonTree data={task.generated} name="generated" />
          </div>
        </section>
        {(task.telemetry_at_start || task.telemetry_at_end) && (
          <section>
            <h3 className="text-fg-muted mb-1 text-xs font-semibold uppercase">Telemetry</h3>
            <div className="card space-y-2 p-3">
              <JsonTree data={task.telemetry_at_start} name="at_start" />
              <JsonTree data={task.telemetry_at_end} name="at_end" />
            </div>
          </section>
        )}
        {(task.stdout || task.stderr) != null && (
          <section>
            <h3 className="text-fg-muted mb-1 text-xs font-semibold uppercase">Output</h3>
            {task.stdout != null && (
              <pre className="card overflow-x-auto p-3 text-xs">{String(task.stdout)}</pre>
            )}
            {task.stderr != null && (
              <pre className="card text-err mt-2 overflow-x-auto p-3 text-xs">{String(task.stderr)}</pre>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
