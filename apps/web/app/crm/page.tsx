"use client";

import { useMemo } from "react";
import Link from "next/link";

import { getCurrentRoles, hasPermission } from "../../lib/permissions";

export default function CrmPage() {
  const roles = useMemo(() => getCurrentRoles(), []);
  const canReadAudit = hasPermission("crm.audit.read", roles);
  const canReadCustomFields = hasPermission("crm.custom_fields.read", roles);
  const canReadWorkflows = hasPermission("crm.workflows.read", roles);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <h1 className="text-2xl font-semibold">CRM</h1>
      <p className="mt-2 text-sm text-slate-500">Accounts, contacts, opportunities, and lifecycle events.</p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Link href="/crm/accounts" className="inline-flex rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white">
          Accounts
        </Link>
        <Link href="/crm/leads" className="inline-flex rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white">
          Leads
        </Link>
        <Link href="/crm/opportunities" className="inline-flex rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white">
          Opportunities
        </Link>
        {canReadAudit ? (
          <Link href="/crm/audit" className="inline-flex rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white">
            Audit
          </Link>
        ) : null}
        {canReadCustomFields ? (
          <Link
            href="/crm/admin/custom-fields"
            className="inline-flex rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white"
          >
            Custom Fields
          </Link>
        ) : null}
        {canReadWorkflows ? (
          <Link
            href="/crm/admin/workflows"
            className="inline-flex rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white"
          >
            Workflows
          </Link>
        ) : null}
      </div>
    </div>
  );
}
