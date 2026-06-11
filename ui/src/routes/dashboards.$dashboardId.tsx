/** Dashboard detail: react-grid-layout grid of cards with edit mode (drag/resize/add/remove). */

import { useCallback, useMemo, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GridLayout, useContainerWidth, type Layout, type LayoutItem as RGLItem } from "react-grid-layout";
import { Pencil, Plus, Trash2, X } from "lucide-react";
import { apiGet, apiPut } from "../api/client";
import { CardRenderer } from "../components/dashboard/CardRenderer";
import { dashboardSpec, type Card, type DashboardSpec } from "../components/dashboard/spec";

import "react-grid-layout/css/styles.css";

export const Route = createFileRoute("/dashboards/$dashboardId")({ component: DashboardDetail });

function DashboardDetail() {
  const { dashboardId } = Route.useParams();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [adding, setAdding] = useState(false);
  const { width, containerRef } = useContainerWidth();

  const { data: spec, isLoading, error } = useQuery({
    queryKey: ["dashboard", dashboardId],
    queryFn: async () => dashboardSpec.parse(await apiGet<unknown>(`/dashboards/${dashboardId}`)),
  });

  const save = useMutation({
    mutationFn: (next: DashboardSpec) => apiPut<DashboardSpec>(`/dashboards/${dashboardId}`, next),
    onSuccess: (saved) => queryClient.setQueryData(["dashboard", dashboardId], dashboardSpec.parse(saved)),
  });

  const onLayoutChange = useCallback(
    (layout: Layout) => {
      if (!editing || !spec) return;
      const next = {
        ...spec,
        layout: layout.map((l: RGLItem) => ({ card_id: l.i, x: l.x, y: l.y, w: l.w, h: l.h })),
      };
      save.mutate(next);
    },
    [editing, spec, save],
  );

  const gridLayout: Layout = useMemo(() => {
    if (!spec) return [];
    const placed = new Map(spec.layout.map((l) => [l.card_id, l]));
    return spec.cards.map((c, i) => {
      const l = placed.get(c.card_id);
      return l
        ? { i: c.card_id, x: l.x, y: l.y, w: l.w, h: l.h }
        : { i: c.card_id, x: (i % 2) * 6, y: Math.floor(i / 2) * 4, w: 6, h: 4 };
    });
  }, [spec]);

  if (isLoading) return <div className="text-fg-muted p-6 text-xs">Loading…</div>;
  if (error) return <div className="text-err p-6 text-xs">{String(error)}</div>;
  if (!spec) return null;

  const removeCard = (cardId: string) => {
    save.mutate({
      ...spec,
      cards: spec.cards.filter((c) => c.card_id !== cardId),
      layout: spec.layout.filter((l) => l.card_id !== cardId),
    });
  };

  return (
    <div className="space-y-4 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">{spec.name}</h1>
          {spec.description && <p className="text-fg-muted text-xs">{spec.description}</p>}
        </div>
        <div className="flex gap-2">
          {editing && (
            <button
              onClick={() => setAdding(true)}
              className="bg-accent-soft border-accent/40 flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs"
            >
              <Plus size={13} /> Add card
            </button>
          )}
          <button
            onClick={() => setEditing(!editing)}
            className={`flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs ${
              editing ? "border-accent bg-accent-soft" : "border-border text-fg-muted hover:text-fg"
            }`}
          >
            <Pencil size={13} /> {editing ? "Done" : "Edit"}
          </button>
        </div>
      </header>

      {/* RGL v2 types target React 19 nullable refs; cast for the React 18 type defs. */}
      <div ref={containerRef as React.RefObject<HTMLDivElement>}>
        <GridLayout
          layout={gridLayout}
          width={width || 1200}
          gridConfig={{ cols: 12, rowHeight: 64, margin: [12, 12] }}
          dragConfig={{ enabled: editing, cancel: ".card-content" }}
          resizeConfig={{ enabled: editing }}
          onLayoutChange={onLayoutChange}
        >
          {spec.cards.map((card) => (
            <div key={card.card_id} className="card flex flex-col overflow-hidden">
              <div
                className={`flex items-center justify-between border-b border-border px-3 py-1.5 ${editing ? "cursor-move" : ""}`}
              >
                <span className="text-xs font-medium">
                  {card.title || card.type}
                  {card.live && <span className="text-ok ml-2 text-[10px]">● live</span>}
                </span>
                {editing && (
                  <button onClick={() => removeCard(card.card_id)} className="text-fg-muted hover:text-err">
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
              <div className="card-content min-h-0 flex-1">
                <CardRenderer card={card} spec={spec} />
              </div>
            </div>
          ))}
        </GridLayout>
      </div>
      {spec.cards.length === 0 && (
        <div className="text-fg-muted py-16 text-center text-xs">
          Empty dashboard — switch to Edit and add a card.
        </div>
      )}

      {adding && (
        <AddCardDialog
          onClose={() => setAdding(false)}
          onAdd={(card) => {
            save.mutate({ ...spec, cards: [...spec.cards, card] });
            setAdding(false);
          }}
        />
      )}
    </div>
  );
}

function AddCardDialog({ onAdd, onClose }: { onAdd: (card: Card) => void; onClose: () => void }) {
  const [type, setType] = useState<Card["type"]>("chart");
  const [title, setTitle] = useState("");
  const [groupBy, setGroupBy] = useState("activity_id");
  const [agg, setAgg] = useState<"count" | "avg" | "sum" | "min" | "max">("count");
  const [field, setField] = useState("");
  const [kind, setKind] = useState<"bar" | "line" | "pie" | "scatter" | "area">("bar");
  const [filterJson, setFilterJson] = useState("{}");
  const [content, setContent] = useState("");
  const [scopeId, setScopeId] = useState("");
  const [live, setLive] = useState(false);
  const [err, setErr] = useState("");

  const submit = () => {
    let filter: Record<string, unknown>;
    try {
      filter = JSON.parse(filterJson || "{}");
    } catch {
      setErr("Filter must be valid JSON.");
      return;
    }
    const cardId = `c-${Date.now().toString(36)}`;
    if (type === "markdown") {
      onAdd({ card_id: cardId, type, title, live: false, content } as Card);
      return;
    }
    if (type === "prov_card") {
      onAdd({ card_id: cardId, type, title, live: false, workflow_id: scopeId || null } as Card);
      return;
    }
    onAdd({
      card_id: cardId,
      type,
      title,
      live,
      data: {
        source: "tasks",
        filter,
        group_by: groupBy || null,
        metrics: [{ field, agg }],
        limit: 500,
      },
      viz: { kind, stacked: false },
    } as Card);
  };

  const labelCls = "text-fg-muted text-xs w-24 shrink-0";
  const inputCls = "flex-1 rounded border border-border bg-surface-2 px-2 py-1 text-xs";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="card w-[440px] p-4" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium">Add card</h2>
          <button onClick={onClose} className="text-fg-muted hover:text-fg">
            <X size={15} />
          </button>
        </div>
        <div className="space-y-2.5">
          <label className="flex items-center gap-2">
            <span className={labelCls}>Type</span>
            <select value={type} onChange={(e) => setType(e.target.value as Card["type"])} className={inputCls}>
              <option value="chart">chart</option>
              <option value="metric">metric</option>
              <option value="table">table</option>
              <option value="markdown">markdown</option>
              <option value="prov_card">prov_card</option>
            </select>
          </label>
          <label className="flex items-center gap-2">
            <span className={labelCls}>Title</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} className={inputCls} />
          </label>
          {type === "markdown" && (
            <label className="flex items-start gap-2">
              <span className={labelCls}>Content</span>
              <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={4} className={inputCls} />
            </label>
          )}
          {type === "prov_card" && (
            <label className="flex items-center gap-2">
              <span className={labelCls}>Workflow id</span>
              <input value={scopeId} onChange={(e) => setScopeId(e.target.value)} className={inputCls} />
            </label>
          )}
          {(type === "chart" || type === "metric" || type === "table") && (
            <>
              <label className="flex items-center gap-2">
                <span className={labelCls}>Group by</span>
                <input value={groupBy} onChange={(e) => setGroupBy(e.target.value)} className={inputCls} />
              </label>
              <label className="flex items-center gap-2">
                <span className={labelCls}>Aggregation</span>
                <select value={agg} onChange={(e) => setAgg(e.target.value as typeof agg)} className={inputCls}>
                  {["count", "avg", "sum", "min", "max"].map((a) => (
                    <option key={a}>{a}</option>
                  ))}
                </select>
              </label>
              {agg !== "count" && (
                <label className="flex items-center gap-2">
                  <span className={labelCls}>Field</span>
                  <input
                    value={field}
                    onChange={(e) => setField(e.target.value)}
                    placeholder="e.g. ended_at"
                    className={inputCls}
                  />
                </label>
              )}
              {type === "chart" && (
                <label className="flex items-center gap-2">
                  <span className={labelCls}>Chart kind</span>
                  <select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)} className={inputCls}>
                    {["bar", "line", "pie", "scatter", "area"].map((k) => (
                      <option key={k}>{k}</option>
                    ))}
                  </select>
                </label>
              )}
              <label className="flex items-start gap-2">
                <span className={labelCls}>Filter (JSON)</span>
                <textarea
                  value={filterJson}
                  onChange={(e) => setFilterJson(e.target.value)}
                  rows={2}
                  className={`${inputCls} font-mono`}
                />
              </label>
              <label className="flex items-center gap-2">
                <span className={labelCls}>Live refresh</span>
                <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
              </label>
            </>
          )}
          {err && <div className="text-err text-xs">{err}</div>}
          <div className="flex justify-end gap-2 pt-2">
            <button onClick={onClose} className="text-fg-muted rounded-md border border-border px-3 py-1.5 text-xs">
              Cancel
            </button>
            <button onClick={submit} className="bg-accent-soft border-accent/40 rounded-md border px-3 py-1.5 text-xs">
              Add
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
