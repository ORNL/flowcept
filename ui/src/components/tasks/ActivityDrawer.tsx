/** Slide-over with activity summary stats; opened via the ?activity= search param. */

import { X } from "lucide-react";
import type { ActivityStat } from "../../api/types";
import { fmtDuration } from "../../lib/format";
import { statusColor } from "../../lib/format";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2 py-1 text-xs">
      <span className="text-fg-muted w-28 shrink-0">{label}</span>
      <span className="min-w-0 break-all">{children}</span>
    </div>
  );
}

export function ActivityDrawer({
  activity,
  onClose,
}: {
  activity: ActivityStat;
  onClose: () => void;
}) {
  return (
    <div
      data-testid="activity-drawer"
      className="fixed inset-y-0 right-0 z-40 flex w-[420px] max-w-[90vw] flex-col border-l border-border bg-surface shadow-2xl"
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="font-medium">{activity.activity_id ?? "activity"}</span>
        <button onClick={onClose} className="text-fg-muted hover:text-fg">
          <X size={16} />
        </button>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        <div className="card p-3">
          <Field label="tasks">{activity.count}</Field>
          {activity.avg_duration != null && (
            <Field label="avg duration">{fmtDuration(activity.avg_duration)}</Field>
          )}
          {activity.min_duration != null && (
            <Field label="min duration">{fmtDuration(activity.min_duration)}</Field>
          )}
          {activity.max_duration != null && (
            <Field label="max duration">{fmtDuration(activity.max_duration)}</Field>
          )}
        </div>
        {Object.keys(activity.status_counts ?? {}).length > 0 && (
          <section>
            <h3 className="text-fg-muted mb-1 text-xs font-semibold uppercase">Status breakdown</h3>
            <div className="card p-3">
              {Object.entries(activity.status_counts).map(([status, count]) => (
                <div key={status} className="flex items-center gap-2 py-0.5 text-xs">
                  <span
                    className="inline-block h-2 w-2 shrink-0 rounded-full"
                    style={{ background: statusColor(status) }}
                  />
                  <span className="text-fg-muted">{status}</span>
                  <span className="ml-auto font-mono">{count}</span>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
