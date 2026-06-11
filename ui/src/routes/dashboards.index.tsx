/** Dashboard configs: manage the four types of dashboard chart configurations. */

import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Plus, Trash2, X } from "lucide-react";
import { useCampaigns, useDashboardConfigs, useVisibleWorkflows } from "../api/queries";
import { apiDelete, apiPost, apiPut } from "../api/client";
import { chart as chartSchema, type Chart } from "../components/dashboard/spec";

export const Route = createFileRoute("/dashboards/")({ component: DashboardConfigsPage });

type DashboardType = "common_workflow" | "common_campaign" | "custom_workflow" | "custom_campaign";

const TYPE_LABELS: Record<DashboardType, { title: string; sub: string }> = {
  common_workflow: { title: "Common Workflow Charts", sub: "Shown on every workflow's Dashboard tab" },
  common_campaign: { title: "Common Campaign Charts", sub: "Shown on every campaign's Dashboard tab" },
  custom_workflow: { title: "Custom Workflow Charts", sub: "Per workflow name — only shown for matching workflows" },
  custom_campaign: { title: "Custom Campaign Charts", sub: "Per campaign ID — only shown for matching campaigns" },
};

function DashboardConfigsPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [addingTo, setAddingTo] = useState<string | null>(null);
  const [newTargetFor, setNewTargetFor] = useState<DashboardType | null>(null);

  const allConfigs = useDashboardConfigs();
  const configs: Record<string, unknown>[] = allConfigs.data?.items ?? [];

  const byType = (t: DashboardType) => configs.filter((c) => c["dashboard_type"] === t);

  const deleteChart = useMutation({
    mutationFn: async ({ configId, chartId }: { configId: string; chartId: string }) => {
      const cfg = configs.find((c) => c["dashboard_id"] === configId);
      if (!cfg) return;
      const updated = { ...cfg, charts: (cfg["charts"] as Chart[]).filter((ch) => ch.chart_id !== chartId) };
      return apiPut(`/dashboards/${configId}`, updated);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboardConfigs"] }),
  });

  const addChart = useMutation({
    mutationFn: async ({ configId, chart }: { configId: string; chart: Chart }) => {
      const cfg = configs.find((c) => c["dashboard_id"] === configId);
      if (!cfg) return;
      const updated = { ...cfg, charts: [...(cfg["charts"] as Chart[]), chart] };
      return apiPut(`/dashboards/${configId}`, updated);
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["dashboardConfigs"] }); setAddingTo(null); },
  });

  const createConfig = useMutation({
    mutationFn: (payload: { dashboard_type: DashboardType; target: string; name: string }) =>
      apiPost("/dashboards", { ...payload, charts: [] }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["dashboardConfigs"] }); setNewTargetFor(null); },
  });

  const deleteConfig = useMutation({
    mutationFn: (configId: string) => apiDelete(`/dashboards/${configId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["dashboardConfigs"] }),
  });

  function toggle(id: string) {
    setOpen((p) => ({ ...p, [id]: !p[id] }));
  }

  if (allConfigs.isLoading) return <div className="text-fg-muted p-6 text-xs">Loading…</div>;

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <header>
        <h1 className="text-xl font-semibold">Dashboard configs</h1>
        <p className="text-fg-muted mt-1 text-xs">
          Configure which charts appear in workflow and campaign Dashboard tabs.
        </p>
      </header>

      {(["common_workflow", "common_campaign", "custom_workflow", "custom_campaign"] as DashboardType[]).map((type) => {
        const { title, sub } = TYPE_LABELS[type];
        const isCustom = type.startsWith("custom");
        const typeConfigs = byType(type);

        return (
          <section key={type} className="card">
            <div className="border-b border-border px-4 py-3">
              <h2 className="text-sm font-semibold">{title}</h2>
              <p className="text-fg-muted text-xs">{sub}</p>
            </div>

            <div className="divide-y divide-border/50">
              {typeConfigs.map((cfg) => {
                const id = cfg["dashboard_id"] as string;
                const target = cfg["target"] as string | null;
                const charts = (cfg["charts"] as Chart[]) ?? [];
                const isOpen = open[id] ?? true;

                return (
                  <div key={id}>
                    <button
                      onClick={() => toggle(id)}
                      className="hover:bg-surface-2 flex w-full items-center justify-between px-4 py-2.5 text-left"
                    >
                      <div className="flex items-center gap-2 text-xs">
                        {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                        <span className="font-medium">
                          {isCustom ? (target ?? "—") : (cfg["name"] as string)}
                        </span>
                        <span className="text-fg-muted">{charts.length} chart{charts.length !== 1 ? "s" : ""}</span>
                      </div>
                      {isCustom && (
                        <button
                          onClick={(e) => { e.stopPropagation(); deleteConfig.mutate(id); }}
                          className="text-fg-muted hover:text-err p-1"
                          title="Delete this config"
                        >
                          <Trash2 size={12} />
                        </button>
                      )}
                    </button>

                    {isOpen && (
                      <div className="bg-surface-2/40 space-y-1 px-4 py-2">
                        {charts.map((c) => (
                          <div key={c.chart_id} className="flex items-center justify-between rounded px-2 py-1 text-xs">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="border-border text-fg-muted shrink-0 rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
                                {c.type}
                              </span>
                              <span className="truncate font-medium">{c.title || c.chart_id}</span>
                              {c.data?.group_by && (
                                <span className="text-fg-muted truncate">· grouped by {c.data.group_by}</span>
                              )}
                              {c.viz?.kind && (
                                <span className="text-fg-muted shrink-0">· {c.viz.kind}</span>
                              )}
                            </div>
                            <button
                              onClick={() => deleteChart.mutate({ configId: id, chartId: c.chart_id })}
                              className="text-fg-muted hover:text-err ml-2 shrink-0 p-1"
                            >
                              <Trash2 size={11} />
                            </button>
                          </div>
                        ))}
                        <button
                          onClick={() => setAddingTo(id)}
                          className="text-fg-muted hover:text-fg mt-1 flex items-center gap-1 px-2 py-1 text-xs"
                        >
                          <Plus size={12} /> Add chart
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}

              {isCustom && (
                <div className="px-4 py-2.5">
                  <button
                    onClick={() => setNewTargetFor(type)}
                    className="text-fg-muted hover:text-fg flex items-center gap-1 text-xs"
                  >
                    <Plus size={12} />
                    {type === "custom_workflow" ? "Add config for a workflow name" : "Add config for a campaign ID"}
                  </button>
                </div>
              )}
            </div>
          </section>
        );
      })}

      {addingTo && (
        <AddChartDialog
          onClose={() => setAddingTo(null)}
          onAdd={(c) => addChart.mutate({ configId: addingTo, chart: c })}
        />
      )}

      {newTargetFor && (
        <NewTargetDialog
          type={newTargetFor}
          existingTargets={byType(newTargetFor).map((c) => c["target"] as string).filter(Boolean)}
          onClose={() => setNewTargetFor(null)}
          onCreate={(target) =>
            createConfig.mutate({
              dashboard_type: newTargetFor,
              target,
              name: `${target} Charts`,
            })
          }
        />
      )}
    </div>
  );
}

function NewTargetDialog({
  type,
  existingTargets,
  onCreate,
  onClose,
}: {
  type: DashboardType;
  existingTargets: string[];
  onCreate: (t: string) => void;
  onClose: () => void;
}) {
  const isWorkflow = type === "custom_workflow";
  const workflows = useVisibleWorkflows();
  const campaigns = useCampaigns();

  const options: string[] = isWorkflow
    ? [...new Set((workflows.items ?? []).map((w) => w.name).filter((n): n is string => !!n))]
        .filter((n) => !existingTargets.includes(n))
        .sort()
    : (campaigns.data?.items ?? [])
        .map((c) => c.campaign_id)
        .filter((id) => !existingTargets.includes(id))
        .sort();

  const loading = isWorkflow ? workflows.isLoading : campaigns.isLoading;
  const [value, setValue] = useState("");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="card w-80 p-4 space-y-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium">New custom config</h2>
          <button onClick={onClose} className="text-fg-muted hover:text-fg"><X size={15} /></button>
        </div>
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-fg-muted">{isWorkflow ? "Workflow name" : "Campaign ID"}</span>
          {loading ? (
            <div className="text-fg-muted py-1">Loading…</div>
          ) : options.length === 0 ? (
            <div className="text-fg-muted py-1">All available {isWorkflow ? "workflows" : "campaigns"} already have a custom config.</div>
          ) : (
            <select
              autoFocus
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="rounded border border-border bg-surface-2 px-2 py-1.5 text-xs"
            >
              <option value="">— select —</option>
              {options.map((o) => (
                <option key={o} value={o}>{o}</option>
              ))}
            </select>
          )}
        </label>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="text-fg-muted rounded border border-border px-3 py-1.5 text-xs">Cancel</button>
          <button
            onClick={() => { if (value) onCreate(value); }}
            disabled={!value}
            className="bg-accent-soft border-accent/40 rounded border px-3 py-1.5 text-xs disabled:opacity-50"
          >
            Create
          </button>
        </div>
      </div>
    </div>
  );
}

function AddChartDialog({ onAdd, onClose }: { onAdd: (c: Chart) => void; onClose: () => void }) {
  const [type, setType] = useState<Chart["type"]>("chart");
  const [title, setTitle] = useState("");
  const [groupBy, setGroupBy] = useState("activity_id");
  const [agg, setAgg] = useState<"count" | "avg" | "sum" | "min" | "max">("count");
  const [field, setField] = useState("");
  const [kind, setKind] = useState<"bar" | "line" | "pie" | "scatter" | "area">("bar");
  const [filterJson, setFilterJson] = useState("{}");
  const [content, setContent] = useState("");
  const [err, setErr] = useState("");

  const submit = () => {
    let filter: Record<string, unknown>;
    try { filter = JSON.parse(filterJson || "{}"); } catch { setErr("Filter must be valid JSON."); return; }
    const chartId = `c-${Math.random().toString(36).slice(2, 9)}`;
    if (type === "markdown") {
      onAdd(chartSchema.parse({ chart_id: chartId, type, title, content }));
      return;
    }
    onAdd(chartSchema.parse({
      chart_id: chartId, type, title,
      data: { source: "tasks", filter, group_by: groupBy || null, metrics: [{ field, agg }], limit: 500 },
      viz: { kind, stacked: false },
    }));
  };

  const lbl = "text-fg-muted text-xs w-24 shrink-0";
  const inp = "flex-1 rounded border border-border bg-surface-2 px-2 py-1 text-xs";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="card w-[420px] p-4" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium">Add chart</h2>
          <button onClick={onClose} className="text-fg-muted hover:text-fg"><X size={15} /></button>
        </div>
        <div className="space-y-2.5">
          <label className="flex items-center gap-2">
            <span className={lbl}>Type</span>
            <select value={type} onChange={(e) => setType(e.target.value as Chart["type"])} className={inp}>
              {["chart", "metric", "table", "markdown"].map((t) => <option key={t}>{t}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2">
            <span className={lbl}>Title</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} className={inp} />
          </label>
          {type === "markdown" ? (
            <label className="flex items-start gap-2">
              <span className={lbl}>Content</span>
              <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={4} className={inp} />
            </label>
          ) : (
            <>
              <label className="flex items-center gap-2">
                <span className={lbl}>Group by</span>
                <input value={groupBy} onChange={(e) => setGroupBy(e.target.value)} placeholder="e.g. activity_id" className={inp} />
              </label>
              <label className="flex items-center gap-2">
                <span className={lbl}>Aggregation</span>
                <select value={agg} onChange={(e) => setAgg(e.target.value as typeof agg)} className={inp}>
                  {["count", "avg", "sum", "min", "max"].map((a) => <option key={a}>{a}</option>)}
                </select>
              </label>
              {agg !== "count" && (
                <label className="flex items-center gap-2">
                  <span className={lbl}>Field</span>
                  <input value={field} onChange={(e) => setField(e.target.value)} placeholder="e.g. generated.val_loss" className={inp} />
                </label>
              )}
              {type === "chart" && (
                <label className="flex items-center gap-2">
                  <span className={lbl}>Chart kind</span>
                  <select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)} className={inp}>
                    {["bar", "line", "pie", "scatter", "area"].map((k) => <option key={k}>{k}</option>)}
                  </select>
                </label>
              )}
              <label className="flex items-start gap-2">
                <span className={lbl}>Filter (JSON)</span>
                <textarea value={filterJson} onChange={(e) => setFilterJson(e.target.value)} rows={2} className={`${inp} font-mono`} />
              </label>
            </>
          )}
          {err && <div className="text-err text-xs">{err}</div>}
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={onClose} className="text-fg-muted rounded border border-border px-3 py-1.5 text-xs">Cancel</button>
            <button onClick={submit} className="bg-accent-soft border-accent/40 rounded border px-3 py-1.5 text-xs">Add</button>
          </div>
        </div>
      </div>
    </div>
  );
}
