/** Horizontal stacked status counts + per-activity stats table. */

import type { TaskSummary } from "../../api/types";
import { fmtDuration, statusColor } from "../../lib/format";

export function StatusStrip({ summary }: { summary: TaskSummary }) {
  const total = summary.count || 1;
  const entries = Object.entries(summary.status_counts);
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <div className="flex h-2.5 flex-1 overflow-hidden rounded-full bg-surface-2">
          {entries.map(([status, count]) => (
            <div
              key={status}
              title={`${status}: ${count}`}
              style={{ width: `${(count / total) * 100}%`, background: statusColor(status) }}
            />
          ))}
        </div>
        <div className="text-fg-muted text-xs whitespace-nowrap">{summary.count} tasks</div>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {entries.map(([status, count]) => (
          <span key={status} className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: statusColor(status) }} />
            {status} <span className="text-fg-muted">{count}</span>
          </span>
        ))}
      </div>
      {summary.activity_stats.length > 0 && (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-fg-muted border-b border-border text-left">
              <th className="py-1.5 pr-2 font-medium">Activity</th>
              <th className="py-1.5 pr-2 font-medium">Count</th>
              <th className="py-1.5 pr-2 font-medium">Avg</th>
              <th className="py-1.5 pr-2 font-medium">Min</th>
              <th className="py-1.5 pr-2 font-medium">Max</th>
              <th className="py-1.5 font-medium">Errors</th>
            </tr>
          </thead>
          <tbody>
            {summary.activity_stats.map((a) => (
              <tr key={String(a.activity_id)} className="border-b border-border/50">
                <td className="py-1.5 pr-2 font-mono">{a.activity_id ?? "—"}</td>
                <td className="py-1.5 pr-2">{a.count}</td>
                <td className="py-1.5 pr-2">{fmtDuration(a.avg_duration)}</td>
                <td className="py-1.5 pr-2">{fmtDuration(a.min_duration)}</td>
                <td className="py-1.5 pr-2">{fmtDuration(a.max_duration)}</td>
                <td className="py-1.5" style={{ color: a.status_counts["ERROR"] ? "var(--color-err)" : undefined }}>
                  {a.status_counts["ERROR"] ?? 0}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
