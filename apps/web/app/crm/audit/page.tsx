"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { AuditLogTable } from "../../../components/crm/EntityAuditTab";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Select } from "../../../components/ui/select";
import { listAuditLogs } from "../../../lib/api";
import { getCurrentRoles, hasPermission } from "../../../lib/permissions";
import { queryKeys } from "../../../lib/queryKeys";

const PAGE_SIZE = 20;

export default function CrmAuditPage() {
  const roles = useMemo(() => getCurrentRoles(), []);
  const canReadAudit = hasPermission("crm.audit.read", roles);

  const [entityType, setEntityType] = useState("");
  const [actorUserId, setActorUserId] = useState("");
  const [action, setAction] = useState("");
  const [correlationId, setCorrelationId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const filters = useMemo(
    () => ({
      entity_type: entityType || undefined,
      actor_user_id: actorUserId || undefined,
      action: action || undefined,
      correlation_id: correlationId || undefined,
      date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
      date_to: dateTo ? new Date(dateTo).toISOString() : undefined
    }),
    [action, actorUserId, correlationId, dateFrom, dateTo, entityType]
  );

  const query = useInfiniteQuery({
    queryKey: queryKeys.auditLogs({ ...filters, limit: PAGE_SIZE }),
    initialPageParam: 0,
    enabled: canReadAudit,
    queryFn: ({ pageParam }) =>
      listAuditLogs({
        ...filters,
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

  if (!canReadAudit) {
    return <p className="text-sm text-red-600">Missing permission: crm.audit.read</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Audit</h1>
        <p className="text-sm text-slate-500">Global CRM audit log with filters and pagination.</p>
      </div>

      <div className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 md:grid-cols-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Entity type</label>
          <Select value={entityType} onChange={(event) => setEntityType(event.target.value)}>
            <option value="">Any</option>
            <option value="account">account</option>
            <option value="contact">contact</option>
            <option value="lead">lead</option>
            <option value="opportunity">opportunity</option>
          </Select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Actor user ID</label>
          <Input value={actorUserId} onChange={(event) => setActorUserId(event.target.value)} placeholder="user-1" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Action</label>
          <Input value={action} onChange={(event) => setAction(event.target.value)} placeholder="update" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Correlation ID</label>
          <Input value={correlationId} onChange={(event) => setCorrelationId(event.target.value)} placeholder="corr-123" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Date from</label>
          <Input type="datetime-local" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Date to</label>
          <Input type="datetime-local" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
        </div>
        <div className="md:col-span-3">
          <Button
            variant="secondary"
            onClick={() => {
              setEntityType("");
              setActorUserId("");
              setAction("");
              setCorrelationId("");
              setDateFrom("");
              setDateTo("");
            }}
          >
            Reset filters
          </Button>
        </div>
      </div>

      <AuditLogTable
        entries={entries}
        isLoading={query.isLoading}
        isError={query.isError}
        error={query.error}
        hasNextPage={Boolean(query.hasNextPage)}
        isFetchingNextPage={query.isFetchingNextPage}
        onLoadMore={() => void query.fetchNextPage()}
      />
    </div>
  );
}
