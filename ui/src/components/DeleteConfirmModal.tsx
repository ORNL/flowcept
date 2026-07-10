/** Modal that requires the user to type "DELETE" before confirming destructive removal. */

import { useState } from "react";

interface DeleteConfirmModalProps {
  title: string;
  description: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}

export function DeleteConfirmModal({ title, description, onConfirm, onCancel, loading }: DeleteConfirmModalProps) {
  const [input, setInput] = useState("");
  const ready = input === "DELETE";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-surface border border-border rounded-lg p-6 w-full max-w-md shadow-xl space-y-4">
        <h2 className="text-sm font-semibold text-err">{title}</h2>
        <p className="text-xs text-fg-muted">{description}</p>
        <p className="text-xs text-fg-muted">
          Type <span className="font-mono font-bold text-fg">DELETE</span> to confirm.
        </p>
        <input
          className="w-full rounded border border-border bg-surface-2 px-3 py-2 text-xs font-mono focus:outline-none focus:border-err"
          placeholder="DELETE"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          autoFocus
        />
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="px-3 py-1.5 rounded border border-border text-xs text-fg-muted hover:text-fg"
            disabled={loading}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!ready || loading}
            className="px-3 py-1.5 rounded text-xs font-medium bg-err text-white disabled:opacity-40 hover:opacity-90"
          >
            {loading ? "Deleting…" : "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}
