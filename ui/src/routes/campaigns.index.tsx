/** Campaigns list. */

import { useState } from "react";
import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { Trash2 } from "lucide-react";
import { useCampaigns } from "../api/queries";
import { apiDelete } from "../api/client";
import { DeleteConfirmModal } from "../components/DeleteConfirmModal";
import { fmtTs, shortId, sortCampaigns } from "../lib/format";

export const Route = createFileRoute("/campaigns/")({ component: CampaignsPage });

function CampaignsPage() {
  const { data, isLoading, error } = useCampaigns();
  const router = useRouter();
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    if (!deleteId) return;
    setDeleting(true);
    try {
      await apiDelete(`/campaigns/${deleteId}`);
      void router.invalidate();
    } finally {
      setDeleting(false);
      setDeleteId(null);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-6">
      <h1 className="text-xl font-semibold">Campaigns</h1>
      {isLoading && <div className="text-fg-muted text-xs">Loading…</div>}
      {error && <div className="text-err text-xs">{String(error)}</div>}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {sortCampaigns((data?.items ?? []).filter((c) => c.task_count > 0)).map((c) => (
          <div key={c.campaign_id} className="card hover:border-accent/60 relative group p-4">
            <Link
              to="/campaigns/$campaignId"
              params={{ campaignId: c.campaign_id }}
              className="block"
            >
              <div className="font-mono text-sm">{shortId(c.campaign_id, 28)}</div>
              <div className="text-fg-muted mt-2 space-y-1 text-xs">
                <div>
                  {c.workflow_count} workflows · {c.task_count} tasks
                </div>
                {c.workflow_names.length > 0 && <div className="truncate">{c.workflow_names.join(", ")}</div>}
                <div>
                  {c.users.join(", ") || "unknown user"} · last: {fmtTs(c.last_ts)}
                </div>
              </div>
            </Link>
            <button
              onClick={(e) => { e.preventDefault(); setDeleteId(c.campaign_id); }}
              className="absolute top-3 right-3 text-fg-muted opacity-0 group-hover:opacity-100 hover:text-err"
              title="Delete campaign"
            >
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>
      {data && data.count === 0 && <div className="text-fg-muted text-xs">No campaigns recorded yet.</div>}

      {deleteId && (
        <DeleteConfirmModal
          title="Delete campaign"
          description={`This will permanently delete campaign ${shortId(deleteId, 16)} and all its workflows, tasks, and artifacts. This cannot be undone.`}
          onConfirm={handleDelete}
          onCancel={() => setDeleteId(null)}
          loading={deleting}
        />
      )}
    </div>
  );
}
