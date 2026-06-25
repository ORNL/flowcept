/** Provenance lineage highlight state — set by the Flowcept Agent to focus graphs. */

import { create } from "zustand";

interface HighlightState {
  taskIds: Set<string>;
  setHighlight: (ids: string[]) => void;
  clearHighlight: () => void;
}

export const useHighlightStore = create<HighlightState>((set) => ({
  taskIds: new Set(),
  setHighlight: (ids) => set({ taskIds: new Set(ids) }),
  clearHighlight: () => set({ taskIds: new Set() }),
}));
