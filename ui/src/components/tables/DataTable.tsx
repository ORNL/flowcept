/** Generic virtualized data table built on TanStack Table + Virtual. */

import { useRef } from "react";
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
  type OnChangeFn,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowDown, ArrowUp } from "lucide-react";

interface Props<T> {
  data: T[];
  columns: ColumnDef<T, any>[];
  onRowClick?: (row: T) => void;
  sorting?: SortingState;
  onSortingChange?: OnChangeFn<SortingState>;
  maxHeight?: number;
  emptyMessage?: string;
}

export function DataTable<T>({
  data,
  columns,
  onRowClick,
  sorting,
  onSortingChange,
  maxHeight = 560,
  emptyMessage = "No records.",
}: Props<T>) {
  const table = useReactTable({
    data,
    columns,
    state: sorting ? { sorting } : undefined,
    onSortingChange,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const parentRef = useRef<HTMLDivElement>(null);
  const rows = table.getRowModel().rows;
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 33,
    overscan: 12,
  });

  if (data.length === 0) {
    return <div className="text-fg-muted py-10 text-center text-xs">{emptyMessage}</div>;
  }

  return (
    <div ref={parentRef} className="overflow-auto rounded-md border border-border" style={{ maxHeight }}>
      <div className="text-xs" style={{ minWidth: table.getTotalSize() }}>
        <div className="bg-surface-2 sticky top-0 z-10">
          {table.getHeaderGroups().map((hg) => (
            <div key={hg.id} className="flex border-b border-border">
              {hg.headers.map((header) => (
                <div
                  key={header.id}
                  onClick={header.column.getToggleSortingHandler()}
                  className={`text-fg-muted px-3 py-2 text-left font-medium ${
                    header.column.getCanSort() ? "cursor-pointer select-none hover:text-fg" : ""
                  }`}
                  style={{ width: header.getSize(), flexShrink: 0 }}
                >
                  <span className="inline-flex items-center gap-1">
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {header.column.getIsSorted() === "asc" && <ArrowUp size={12} />}
                    {header.column.getIsSorted() === "desc" && <ArrowDown size={12} />}
                  </span>
                </div>
              ))}
            </div>
          ))}
        </div>
        <div style={{ height: virtualizer.getTotalSize() }} className="relative">
          {virtualizer.getVirtualItems().map((vi) => {
            const row = rows[vi.index];
            return (
              <div
                key={row.id}
                onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                className={`absolute left-0 top-0 flex w-full border-b border-border/40 ${
                  onRowClick ? "hover:bg-surface-2 cursor-pointer" : ""
                }`}
                style={{ transform: `translateY(${vi.start}px)` }}
              >
                {row.getVisibleCells().map((cell) => (
                  <div
                    key={cell.id}
                    className="overflow-hidden text-ellipsis whitespace-nowrap px-3 py-2"
                    style={{ width: cell.column.getSize(), flexShrink: 0 }}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
