"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { Fragment, useMemo, useState } from "react";

import { getErrorMessage, listEntityAuditLogs } from "../../lib/api";
import { queryKeys } from "../../lib/queryKeys";
import type { AuditRead } from "../../lib/types";
import { Button } from "../ui/button";
import { Spinner } from "../ui/spinner";
import { Table, Td, Th } from "../ui/table";

const PAGE_SIZE = 20;

function formatValue(value: unknown) {
  if (value === undefined) {
    return "undefined";
  }
  if (value === null) {
    return "null";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value);
}

function collectFieldDiff(before: Record<string, unknown> | null, after: Record<string, unknown> | null) {
  const beforeValue = before ?? {};
  const afterValue = after ?? {};
  const keys = Array.from(new Set([...Object.keys(beforeValue), ...Object.keys(afterValue)])).sort();
  const result: { key: string; kind: "new" | "removed" | "changed"; before: unknown; after: unknown }[] = [];

  keys.forEach((key) => {
    const prev = beforeValue[key];
    const next = afterValue[key];
    const prevExists = Object.prototype.hasOwnProperty.call(beforeValue, key);
    const nextExists = Object.prototype.hasOwnProperty.call(afterValue, key);

    if (!prevExists && nextExists) {
      result.push({ key, kind: "new", before: undefined, after: next });
      return;
    }
    if (prevExists && !nextExists) {
      result.push({ key, kind: "removed", before: prev, after: undefined });
      return;
    }
    if (JSON.stringify(prev) !== JSON.stringify(next)) {
      result.push({ key, kind: "changed", before: prev, after: next });
    }
  });

  return result;
}

interface AuditLogTableProps {
  entries: AuditRead[];
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  hasNextPage: boolean;
  isFetchingNextPage: boolean;
  onLoadMore: () => void;
}

export function AuditLogTable({
  entries,
  isLoading,
  isError,
  error,
  hasNextPage,
  isFetchingNextPage,
  onLoadMore
}: AuditLogTableProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  if (isLoading) {
    return <Spinner />;
  }

  if (isError) {
    return <p className="text-sm text-red-600">{getErrorMessage(error)}</p>;
  }

  if (entries.length === 0) {
    return <p className="text-sm text-slate-500">No audit entries.</p>;
  }

  return (
    <div className="space-y-3">
      <Table>
        <thead>
          <tr>
            <Th>Timestamp</Th>
            <Th>Actor</Th>
            <Th>Action</Th>
            <Th>Correlation ID</Th>
            <Th>Details</Th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {entries.map((entry) => {
            const isExpanded = Boolean(expanded[entry.id]);
            const diffs = collectFieldDiff(entry.before, entry.after);
            return (
              <Fragment key={entry.id}>
                <tr>
                  <Td>{new Date(entry.occurred_at).toLocaleString()}</Td>
                  <Td>{entry.actor_user_id}</Td>
                  <Td>{entry.action}</Td>
                  <Td>{entry.correlation_id ?? "-"}</Td>
                  <Td>
                    <button
                      type="button"
                      className="text-xs font-medium text-slate-700 underline"
                      onClick={() => setExpanded((current) => ({ ...current, [entry.id]: !isExpanded }))}
                    >
                      {isExpanded ? "Hide" : "Expand"}
                    </button>
                  </Td>
                </tr>
                {isExpanded ? (
                  <tr>
                    <td className="bg-slate-50 px-3 py-3" colSpan={5}>
                      <p className="mb-2 text-xs text-slate-600">
                        {entry.entity_type} · {entry.entity_id}
                      </p>
                      <div className="grid gap-3 lg:grid-cols-2">
                        <div>
                          <p className="mb-1 text-xs font-semibold uppercase text-slate-500">Before JSON</p>
                          <pre className="max-h-64 overflow-auto rounded-md border border-slate-200 bg-white p-2 text-xs text-slate-700">
                            {JSON.stringify(entry.before, null, 2) ?? "null"}
                          </pre>
                        </div>
                        <div>
                          <p className="mb-1 text-xs font-semibold uppercase text-slate-500">After JSON</p>
                          <pre className="max-h-64 overflow-auto rounded-md border border-slate-200 bg-white p-2 text-xs text-slate-700">
                            {JSON.stringify(entry.after, null, 2) ?? "null"}
                          </pre>
                        </div>
                      </div>

                      <div className="mt-3 space-y-2">
                        <p className="text-xs font-semibold uppercase text-slate-500">Field Diff</p>
                        {diffs.length === 0 ? (
                          <p className="text-xs text-slate-500">No changed fields.</p>
                        ) : (
                          <div className="space-y-1">
                            {diffs.map((diff) => (
                              <div
                                key={`${entry.id}-${diff.key}`}
                                className={`rounded-md border px-2 py-1 text-xs ${
                                  diff.kind === "new"
                                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                                    : diff.kind === "removed"
                                      ? "border-red-200 bg-red-50 text-red-800"
                                      : "border-amber-200 bg-amber-50 text-amber-800"
                                }`}
                              >
                                <span className="font-semibold">{diff.key}</span>: {formatValue(diff.before)} → {formatValue(diff.after)}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </Table>

      {hasNextPage ? (
        <Button variant="secondary" onClick={onLoadMore} disabled={isFetchingNextPage}>
          {isFetchingNextPage ? "Loading..." : "Load more"}
        </Button>
      ) : null}
    </div>
  );
}

export function EntityAuditTab({ entityType, entityId }: { entityType: string; entityId: string }) {
  const query = useInfiniteQuery({
    queryKey: queryKeys.entityAuditLogs(entityType, entityId, { limit: PAGE_SIZE }),
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      listEntityAuditLogs(entityType, entityId, {
        cursor: String(pageParam),
        limit: PAGE_SIZE
      }),
    getNextPageParam: (lastPage, allPages) => {
      if (lastPage.length < PAGE_SIZE) {
        return undefined;
      }
      return allPages.reduce((acc, page) => acc + page.length, 0);
    }
  });

  const entries = useMemo(() => query.data?.pages.flatMap((page) => page) ?? [], [query.data?.pages]);

  return (
    <AuditLogTable
      entries={entries}
      isLoading={query.isLoading}
      isError={query.isError}
      error={query.error}
      hasNextPage={Boolean(query.hasNextPage)}
      isFetchingNextPage={query.isFetchingNextPage}
      onLoadMore={() => void query.fetchNextPage()}
    />
  );
}
