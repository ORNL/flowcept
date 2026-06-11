/** Dashboards list with create/delete. */

import { useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LayoutDashboard, Plus, Trash2 } from "lucide-react";
import { apiDelete, apiGet, apiPost } from "../api/client";
import type { ListResponse } from "../api/types";

export const Route = createFileRoute("/dashboards/")({ component: DashboardsPage });

interface DashboardDoc {
  dashboard_id: string;
  name: string;
  description?: string;
  cards?: unknown[];
  updated_at?: string;
}

function DashboardsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboards"],
    queryFn: () => apiGet<ListResponse<DashboardDoc>>("/dashboards"),
  });

  const create = useMutation({
    mutationFn: () => apiPost<DashboardDoc>("/dashboards", { name: name || "New dashboard", cards: [], layout: [] }),
    onSuccess: (d) => {
      void queryClient.invalidateQueries({ queryKey: ["dashboards"] });
      void navigate({ to: "/dashboards/$dashboardId", params: { dashboardId: d.dashboard_id } });
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => apiDelete(`/dashboards/${id}`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["dashboards"] }),
  });

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Dashboards</h1>
        <div className="flex gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="dashboard name"
            className="rounded border border-border bg-surface px-2 py-1 text-xs"
          />
          <button
            onClick={() => create.mutate()}
            className="bg-accent-soft border-accent/40 flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs"
          >
            <Plus size={13} /> New dashboard
          </button>
        </div>
      </header>
      {isLoading && <div className="text-fg-muted text-xs">Loading…</div>}
      {error && <div className="text-err text-xs">{String(error)}</div>}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {(data?.items ?? []).map((d) => (
          <div key={d.dashboard_id} className="card hover:border-accent/60 relative p-4">
            <Link to="/dashboards/$dashboardId" params={{ dashboardId: d.dashboard_id }} className="block">
              <div className="flex items-center gap-2">
                <LayoutDashboard size={15} className="text-accent" />
                <span className="text-sm font-medium">{d.name}</span>
              </div>
              <div className="text-fg-muted mt-2 text-xs">
                {d.description || "No description."} · {(d.cards ?? []).length} cards
              </div>
            </Link>
            <button
              onClick={() => remove.mutate(d.dashboard_id)}
              className="text-fg-muted hover:text-err absolute right-3 top-3"
              title="Delete dashboard"
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>
      {data && data.count === 0 && (
        <div className="text-fg-muted text-xs">No dashboards yet — create one above.</div>
      )}
    </div>
  );
}
