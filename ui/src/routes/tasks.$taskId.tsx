/** Task permalink page reusing the drawer content layout. */

import { createFileRoute, Link } from "@tanstack/react-router";
import { useTask } from "../api/queries";
import { JsonTree } from "../components/JsonTree";
import { fmtDuration, fmtTs, statusColor, taskDuration } from "../lib/format";

export const Route = createFileRoute("/tasks/$taskId")({ component: TaskPage });

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2 py-1 text-xs">
      <span className="text-fg-muted w-32 shrink-0">{label}</span>
      <span className="min-w-0 break-all">{children}</span>
    </div>
  );
}

function TaskPage() {
  const { taskId } = Route.useParams();
  const { data: task, isLoading, error } = useTask(taskId);

  if (isLoading) return <div className="text-fg-muted p-6 text-xs">Loading…</div>;
  if (error) return <div className="text-err p-6 text-xs">{String(error)}</div>;
  if (!task) return null;

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-6">
      <header>
        <div className="text-fg-muted text-xs">Task</div>
        <h1 className="flex items-center gap-2 text-lg font-semibold">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: statusColor(task.status) }} />
          {task.activity_id ?? "task"}
          <span className="text-fg-muted text-xs font-normal">{task.status}</span>
        </h1>
        <div className="text-fg-muted mt-0.5 font-mono text-xs">{task.task_id}</div>
      </header>

      <div className="card p-4">
        <Row label="workflow">
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
        </Row>
        {task.parent_task_id && (
          <Row label="parent task">
            <Link
              to="/tasks/$taskId"
              params={{ taskId: task.parent_task_id }}
              className="text-accent font-mono hover:underline"
            >
              {task.parent_task_id}
            </Link>
          </Row>
        )}
        {task.campaign_id && (
          <Row label="campaign">
            <Link
              to="/campaigns/$campaignId"
              params={{ campaignId: task.campaign_id }}
              className="text-accent font-mono hover:underline"
            >
              {task.campaign_id}
            </Link>
          </Row>
        )}
        <Row label="started">{fmtTs(task.started_at)}</Row>
        <Row label="ended">{fmtTs(task.ended_at)}</Row>
        <Row label="duration">{fmtDuration(taskDuration(task))}</Row>
        <Row label="host">{task.hostname ?? "—"}</Row>
        <Row label="user">{task.user ?? "—"}</Row>
        {task.agent_id && <Row label="agent">{task.agent_id}</Row>}
        {task.subtype && <Row label="subtype">{task.subtype}</Row>}
        {task.tags && task.tags.length > 0 && <Row label="tags">{task.tags.join(", ")}</Row>}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
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
      </div>

      {(task.telemetry_at_start || task.telemetry_at_end) && (
        <section>
          <h3 className="text-fg-muted mb-1 text-xs font-semibold uppercase">Telemetry</h3>
          <div className="card grid grid-cols-1 gap-4 p-4 md:grid-cols-2">
            <JsonTree data={task.telemetry_at_start} name="at_start" />
            <JsonTree data={task.telemetry_at_end} name="at_end" />
          </div>
        </section>
      )}

      {(task.stdout != null || task.stderr != null) && (
        <section className="space-y-2">
          <h3 className="text-fg-muted text-xs font-semibold uppercase">Output</h3>
          {task.stdout != null && <pre className="card overflow-x-auto p-3 text-xs">{String(task.stdout)}</pre>}
          {task.stderr != null && (
            <pre className="card text-err overflow-x-auto p-3 text-xs">{String(task.stderr)}</pre>
          )}
        </section>
      )}
    </div>
  );
}
