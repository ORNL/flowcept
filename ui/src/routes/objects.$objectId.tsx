/** Artifact detail: metadata, version history, downloads. */

import { useState } from "react";
import { createFileRoute, Link, useRouter } from "@tanstack/react-router";
import { Download, Trash2 } from "lucide-react";
import { API_BASE, apiDelete } from "../api/client";
import { useObject, useObjectHistory } from "../api/queries";
import { DeleteConfirmModal } from "../components/DeleteConfirmModal";
import { JsonTree } from "../components/JsonTree";
import { shortId } from "../lib/format";

export const Route = createFileRoute("/objects/$objectId")({ component: ObjectPage });

function ObjectPage() {
  const { objectId } = Route.useParams();
  const router = useRouter();
  const { data: obj, isLoading, error } = useObject(objectId);
  const history = useObjectHistory(objectId);
  const [showDelete, setShowDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function handleDelete() {
    setDeleting(true);
    try {
      await apiDelete(`/objects/${objectId}`);
      void router.invalidate();
      await router.navigate({ to: "/objects" });
    } finally {
      setDeleting(false);
      setShowDelete(false);
    }
  }

  if (isLoading) return <div className="text-fg-muted p-6 text-xs">Loading…</div>;
  if (error) return <div className="text-err p-6 text-xs">{String(error)}</div>;
  if (!obj) return null;

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-6">
      <header className="flex items-start justify-between">
        <div>
          <div className="text-fg-muted text-xs">
            <Link to="/objects" className="hover:text-fg hover:underline">Artifacts</Link>
            {" · "}{obj.object_type ?? "object"}
          </div>
          <h1 className="font-mono text-lg font-semibold">{objectId}</h1>
          {obj.workflow_id && (
            <Link
              to="/workflows/$workflowId"
              params={{ workflowId: obj.workflow_id }}
              className="text-accent text-xs hover:underline"
            >
              workflow {shortId(obj.workflow_id, 14)}
            </Link>
          )}
        </div>
        <div className="flex items-center gap-2">
          <a
            href={`${API_BASE}/objects/${objectId}/download`}
            className="bg-accent-soft border-accent/40 hover:border-accent flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs"
          >
            <Download size={13} /> Download latest
          </a>
          <button
            onClick={() => setShowDelete(true)}
            className="text-fg-muted hover:text-err"
            title="Delete artifact"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </header>
      {showDelete && (
        <DeleteConfirmModal
          title="Delete artifact"
          description={`This will permanently delete artifact ${shortId(objectId, 16)} and all its versions. This cannot be undone.`}
          onConfirm={handleDelete}
          onCancel={() => setShowDelete(false)}
          loading={deleting}
        />
      )}

      <section>
        <h3 className="text-fg-muted mb-1 text-xs font-semibold uppercase">Metadata</h3>
        <div className="card p-3">
          <JsonTree data={obj} name="object" />
        </div>
      </section>

      <section>
        <h3 className="text-fg-muted mb-1 text-xs font-semibold uppercase">Version history</h3>
        <div className="card divide-y divide-border/50">
          {(history.data?.items ?? []).map((v) => (
            <div key={String(v.version)} className="flex items-center justify-between px-4 py-2.5 text-xs">
              <span>
                <span className="font-medium">v{v.version}</span>
                {v.created_at && <span className="text-fg-muted ml-2">{String(v.created_at)}</span>}
                {v.custom_metadata && (
                  <span className="text-fg-muted ml-2 truncate">
                    {JSON.stringify(v.custom_metadata).slice(0, 80)}
                  </span>
                )}
              </span>
              <a
                href={`${API_BASE}/objects/${objectId}/versions/${v.version}/download`}
                className="text-accent flex items-center gap-1 hover:underline"
              >
                <Download size={12} /> download
              </a>
            </div>
          ))}
          {history.data && history.data.count === 0 && (
            <div className="text-fg-muted px-4 py-4 text-xs">No version history (single unversioned object).</div>
          )}
        </div>
      </section>
    </div>
  );
}
