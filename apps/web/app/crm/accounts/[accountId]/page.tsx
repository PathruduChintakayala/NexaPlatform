"use client";

import { useQuery } from "@tanstack/react-query";

import { AccountContactsTab } from "../../../../components/crm/AccountContactsTab";
import { CustomFieldsReadOnly } from "../../../../components/crm/CustomFieldsReadOnly";
import { AccountOpportunitiesTab } from "../../../../components/crm/AccountOpportunitiesTab";
import { EntityActivitiesTab } from "../../../../components/crm/EntityActivitiesTab";
import { EntityAuditTab } from "../../../../components/crm/EntityAuditTab";
import { EntityAttachmentsTab } from "../../../../components/crm/EntityAttachmentsTab";
import { EntityNotesTab } from "../../../../components/crm/EntityNotesTab";
import { Badge } from "../../../../components/ui/badge";
import { Spinner } from "../../../../components/ui/spinner";
import { Tabs } from "../../../../components/ui/tabs";
import { getAccount, getErrorMessage, listCustomFieldDefinitions } from "../../../../lib/api";
import { queryKeys } from "../../../../lib/queryKeys";

export default function AccountDetailPage({ params }: { params: { accountId: string } }) {
  const accountId = params.accountId;

  const accountQuery = useQuery({
    queryKey: queryKeys.account(accountId),
    queryFn: () => getAccount(accountId)
  });

  const accountLegalEntityId = accountQuery.data?.legal_entity_ids?.[0];
  const customFieldDefinitionsQuery = useQuery({
    queryKey: queryKeys.customFieldDefinitions("account", accountLegalEntityId),
    queryFn: () => listCustomFieldDefinitions("account", accountLegalEntityId),
    enabled: Boolean(accountQuery.data)
  });

  if (accountQuery.isLoading) {
    return <Spinner />;
  }

  if (accountQuery.isError) {
    return <p className="text-sm text-red-600">{getErrorMessage(accountQuery.error)}</p>;
  }

  const account = accountQuery.data;
  if (!account) {
    return <p className="text-sm text-slate-600">Account not found.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">{account.name}</h1>
            <p className="mt-1 text-sm text-slate-500">Account details and related CRM records.</p>
          </div>
          <Badge tone={account.status === "Active" ? "success" : "warning"}>{account.status}</Badge>
        </div>
        <div className="mt-4 grid gap-2 text-sm text-slate-700 md:grid-cols-2">
          <p>
            <span className="font-medium">Owner:</span> {account.owner_user_id ?? "-"}
          </p>
          <p>
            <span className="font-medium">Region:</span> {account.primary_region_code ?? "-"}
          </p>
          <p className="md:col-span-2">
            <span className="font-medium">Legal entities:</span> {account.legal_entity_ids.join(", ") || "-"}
          </p>
          <div className="md:col-span-2">
            <p className="mb-1 font-medium">Custom fields</p>
            <CustomFieldsReadOnly definitions={customFieldDefinitionsQuery.data ?? []} values={account.custom_fields} />
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <Tabs
          items={[
            { id: "contacts", label: "Contacts", content: <AccountContactsTab accountId={accountId} /> },
            { id: "opportunities", label: "Opportunities", content: <AccountOpportunitiesTab accountId={accountId} /> },
            { id: "activities", label: "Activities", content: <EntityActivitiesTab entityType="account" entityId={accountId} /> },
            { id: "notes", label: "Notes", content: <EntityNotesTab entityType="account" entityId={accountId} /> },
            { id: "attachments", label: "Attachments", content: <EntityAttachmentsTab entityType="account" entityId={accountId} /> },
            { id: "audit", label: "Audit", content: <EntityAuditTab entityType="account" entityId={accountId} /> }
          ]}
        />
      </div>
    </div>
  );
}
