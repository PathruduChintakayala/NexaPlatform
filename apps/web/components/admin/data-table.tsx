import React from "react";

import { Table, Td, Th } from "../ui/table";

interface DataTableColumn<TItem> {
  key: string;
  title: string;
  render: (item: TItem) => React.ReactNode;
}

interface DataTableProps<TItem> {
  columns: DataTableColumn<TItem>[];
  rows: TItem[];
  rowKey: (row: TItem) => string;
  emptyText?: string;
}

export function DataTable<TItem>({ columns, rows, rowKey, emptyText = "No records" }: DataTableProps<TItem>) {
  return (
    <Table>
      <thead>
        <tr>
          {columns.map((column) => (
            <Th key={column.key}>{column.title}</Th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr>
            <td className="px-3 py-3 align-top text-slate-700" colSpan={Math.max(columns.length, 1)}>
              <span className="text-sm text-slate-500">{emptyText}</span>
            </td>
          </tr>
        ) : (
          rows.map((row) => (
            <tr key={rowKey(row)} className="border-t border-slate-100">
              {columns.map((column) => (
                <Td key={column.key}>{column.render(row)}</Td>
              ))}
            </tr>
          ))
        )}
      </tbody>
    </Table>
  );
}
