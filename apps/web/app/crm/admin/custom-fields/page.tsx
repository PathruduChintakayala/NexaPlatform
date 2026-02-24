"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  listCustomFieldDefinitions,
  getErrorMessage,
  type CustomFieldEntityType
} from "../../../../lib/api";
import { getCurrentRoles, hasPermission } from "../../../../lib/permissions";
import { queryKeys } from "../../../../lib/queryKeys";
import { Button } from "../../../../components/ui/button";
import { Input } from "../../../../components/ui/input";
import { Select } from "../../../../components/ui/select";
import { Spinner } from "../../../../components/ui/spinner";
import { Toast, type ToastMessageValue } from "../../../../components/ui/toast";
import { CustomFieldDefinitionFormModal } from "../../../../components/crm/admin/CustomFieldDefinitionFormModal";
import { CustomFieldDefinitionsTable } from "../../../../components/crm/admin/CustomFieldDefinitionsTable";
import type { CustomFieldDefinitionRead } from "../../../../lib/types";

const entityTypes: CustomFieldEntityType[] = ["account", "contact", "lead", "opportunity"];

export default function CustomFieldsAdminPage() {
  const roles = useMemo(() => getCurrentRoles(), []);
  const canRead = hasPermission("crm.custom_fields.read", roles);
  const canManage = hasPermission("crm.custom_fields.manage", roles);

  const [entityType, setEntityType] = useState<CustomFieldEntityType>("account");
  const [scopeMode, setScopeMode] = useState<"global" | "legal_entity">("global");
  const [legalEntityId, setLegalEntityId] = useState("");
  const [toast, setToast] = useState<ToastMessageValue>(null);
  const [openCreate, setOpenCreate] = useState(false);
  const [editingDefinition, setEditingDefinition] = useState<CustomFieldDefinitionRead | null>(null);

  const activeLegalEntityId = scopeMode === "legal_entity" && legalEntityId ? legalEntityId : undefined;

  const definitionsQuery = useQuery({
    queryKey: queryKeys.customFieldDefinitions(entityType, activeLegalEntityId),
    queryFn: () => listCustomFieldDefinitions(entityType, activeLegalEntityId),
    enabled: canRead
  });

  const rows = definitionsQuery.data ?? [];

  if (!canRead) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-red-800">
        <h1 className="text-xl font-semibold">Custom Fields</h1>
        <p className="mt-2 text-sm">You do not have permission to view custom fields.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Custom Fields</h1>
            <p className="mt-1 text-sm text-slate-500">Define and manage CRM custom fields by entity and scope.</p>
          </div>
          {canManage ? <Button onClick={() => setOpenCreate(true)}>Create</Button> : null}
        </div>

        <Toast message={toast} tone={typeof toast === "string" ? "success" : toast?.message ? "error" : "info"} />

        <div className="mt-4 grid gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 md:grid-cols-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Entity type</label>
            <Select value={entityType} onChange={(event) => setEntityType(event.target.value as CustomFieldEntityType)}>
              {entityTypes.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </Select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Scope</label>
            <Select value={scopeMode} onChange={(event) => setScopeMode(event.target.value as "global" | "legal_entity")}>
              <option value="global">Global</option>
              <option value="legal_entity">Legal entity scoped</option>
            </Select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Legal entity ID</label>
            <Input
              placeholder="UUID"
              value={legalEntityId}
              disabled={scopeMode === "global"}
              onChange={(event) => setLegalEntityId(event.target.value)}
            />
          </div>
        </div>
      </div>

      {definitionsQuery.isLoading ? (
        <Spinner />
      ) : definitionsQuery.isError ? (
        <p className="text-sm text-red-600">{getErrorMessage(definitionsQuery.error)}</p>
      ) : (
        <CustomFieldDefinitionsTable
          definitions={rows}
          canManage={canManage}
          onEdit={(definition) => setEditingDefinition(definition)}
        />
      )}

      {canManage ? (
        <CustomFieldDefinitionFormModal
          open={openCreate}
          mode="create"
          entityType={entityType}
          legalEntityId={activeLegalEntityId}
          onClose={() => setOpenCreate(false)}
          onSuccess={(message) => setToast(message)}
          onError={(message) => setToast(message)}
        />
      ) : null}

      {canManage ? (
        <CustomFieldDefinitionFormModal
          open={Boolean(editingDefinition)}
          mode="edit"
          entityType={entityType}
          legalEntityId={activeLegalEntityId}
          initialDefinition={editingDefinition}
          onClose={() => setEditingDefinition(null)}
          onSuccess={(message) => setToast(message)}
          onError={(message) => setToast(message)}
        />
      ) : null}
    </div>
  );
}
