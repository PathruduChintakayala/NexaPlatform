"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { z } from "zod";

import { CustomFieldsRenderer } from "../../../../components/crm/CustomFieldsRenderer";
import { EntityActivitiesTab } from "../../../../components/crm/EntityActivitiesTab";
import { EntityAuditTab } from "../../../../components/crm/EntityAuditTab";
import { EntityAttachmentsTab } from "../../../../components/crm/EntityAttachmentsTab";
import { EntityNotesTab } from "../../../../components/crm/EntityNotesTab";
import { OpportunityChangeStageModal } from "../../../../components/crm/OpportunityChangeStageModal";
import { OpportunityCloseLostModal } from "../../../../components/crm/OpportunityCloseLostModal";
import { OpportunityCloseWonModal } from "../../../../components/crm/OpportunityCloseWonModal";
import { OpportunityReopenModal } from "../../../../components/crm/OpportunityReopenModal";
import { OpportunityRevenuePanel } from "../../../../components/crm/OpportunityRevenuePanel";
import { Badge } from "../../../../components/ui/badge";
import { Button } from "../../../../components/ui/button";
import { Spinner } from "../../../../components/ui/spinner";
import { Tabs } from "../../../../components/ui/tabs";
import { Toast, toastText, type ToastMessageValue } from "../../../../components/ui/toast";
import { normalizeCustomFieldPayload, zodErrorToFieldMap } from "../../../../lib/customFieldsZod";
import { getDefaultPipeline, getErrorMessage, getErrorToastMessage, getOpportunity, listCustomFieldDefinitions, patchOpportunity } from "../../../../lib/api";
import { queryKeys } from "../../../../lib/queryKeys";
import type { PipelineStageRead } from "../../../../lib/types";

function deriveStatus(opportunity: { closed_won_at: string | null; closed_lost_at: string | null }) {
  if (opportunity.closed_won_at) return "ClosedWon";
  if (opportunity.closed_lost_at) return "ClosedLost";
  return "Open";
}

export default function OpportunityDetailPage({ params }: { params: { opportunityId: string } }) {
  const opportunityId = params.opportunityId;
  const queryClient = useQueryClient();
  const [openChangeStage, setOpenChangeStage] = useState(false);
  const [openCloseWon, setOpenCloseWon] = useState(false);
  const [openCloseLost, setOpenCloseLost] = useState(false);
  const [openReopen, setOpenReopen] = useState(false);
  const [message, setMessage] = useState<ToastMessageValue>(null);
  const [customFieldValues, setCustomFieldValues] = useState<Record<string, unknown>>({});
  const [customFieldErrors, setCustomFieldErrors] = useState<Record<string, string>>({});

  const opportunityQuery = useQuery({
    queryKey: queryKeys.opportunity(opportunityId),
    queryFn: () => getOpportunity(opportunityId)
  });

  const defaultPipelineQuery = useQuery({
    queryKey: queryKeys.pipelineDefault(opportunityQuery.data?.selling_legal_entity_id),
    queryFn: () =>
      getDefaultPipeline({
        selling_legal_entity_id: opportunityQuery.data?.selling_legal_entity_id
      }),
    enabled: Boolean(opportunityQuery.data)
  });

  const customFieldDefinitionsQuery = useQuery({
    queryKey: queryKeys.customFieldDefinitions("opportunity", opportunityQuery.data?.selling_legal_entity_id),
    queryFn: () => listCustomFieldDefinitions("opportunity", opportunityQuery.data?.selling_legal_entity_id),
    enabled: Boolean(opportunityQuery.data)
  });

  useEffect(() => {
    if (!opportunityQuery.data) {
      return;
    }
    setCustomFieldValues(opportunityQuery.data.custom_fields ?? {});
    setCustomFieldErrors({});
  }, [opportunityQuery.data]);

  const saveCustomFieldsMutation = useMutation({
    mutationFn: (customFields: Record<string, unknown>) => {
      const opportunity = opportunityQuery.data;
      if (!opportunity) {
        throw new Error("Opportunity not loaded");
      }
      return patchOpportunity(opportunity.id, {
        row_version: opportunity.row_version,
        custom_fields: customFields
      });
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.opportunity(opportunityId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.opportunities({}) })
      ]);
      setMessage("Custom fields updated.");
    },
    onError: (error) => setMessage(getErrorToastMessage(error))
  });

  const stages: PipelineStageRead[] = useMemo(
    () => [...(defaultPipelineQuery.data?.stages ?? [])].sort((left, right) => left.position - right.position),
    [defaultPipelineQuery.data?.stages]
  );

  if (opportunityQuery.isLoading) {
    return <Spinner />;
  }

  if (opportunityQuery.isError || !opportunityQuery.data) {
    return <p className="text-sm text-red-600">{getErrorMessage(opportunityQuery.error)}</p>;
  }

  const opportunity = opportunityQuery.data;
  const currentStage = stages.find((stage) => stage.id === opportunity.stage_id);
  const stageType = currentStage?.stage_type;
  const statusFromStageType =
    stageType === "ClosedWon" ? "ClosedWon" : stageType === "ClosedLost" ? "ClosedLost" : "Open";
  const status = statusFromStageType === "Open" ? deriveStatus(opportunity) : statusFromStageType;
  const isClosed = status === "ClosedWon" || status === "ClosedLost";
  const stageLabel = currentStage?.name ?? "Other / Inactive";
  const openStages = stages.filter((stage) => stage.stage_type === "Open");

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">{opportunity.name}</h1>
            <p className="mt-1 text-sm text-slate-500">Opportunity lifecycle and collaboration.</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge tone="default">{stageLabel}</Badge>
            <Badge tone={status === "ClosedWon" ? "success" : status === "ClosedLost" ? "danger" : "default"}>{status}</Badge>
          </div>
        </div>

        <div className="mt-4 grid gap-2 text-sm text-slate-700 md:grid-cols-2">
          <p>
            <span className="font-medium">Amount:</span> {opportunity.amount} {opportunity.currency_code}
          </p>
          <p>
            <span className="font-medium">Expected close:</span> {opportunity.expected_close_date ?? "-"}
          </p>
          <p>
            <span className="font-medium">Owner:</span> {opportunity.owner_user_id ?? "-"}
          </p>
          <p>
            <span className="font-medium">Account:</span> {opportunity.account_id}
          </p>
          <p>
            <span className="font-medium">Closed won at:</span> {opportunity.closed_won_at ?? "-"}
          </p>
          <p>
            <span className="font-medium">Closed lost at:</span> {opportunity.closed_lost_at ?? "-"}
          </p>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Button onClick={() => setOpenChangeStage(true)} disabled={isClosed} title={isClosed ? "Closed opportunity" : undefined}>
            Change Stage
          </Button>
          <Button onClick={() => setOpenCloseWon(true)} disabled={isClosed}>
            Close Won
          </Button>
          <Button onClick={() => setOpenCloseLost(true)} disabled={isClosed}>
            Close Lost
          </Button>
          <Button variant="secondary" onClick={() => setOpenReopen(true)} disabled={!isClosed}>
            Reopen
          </Button>
        </div>
      </div>

      <OpportunityRevenuePanel opportunity={opportunity} />

      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3">
        <Toast message={message} tone={toastText(message).toLowerCase().includes("updated") ? "success" : "error"} />
        {customFieldDefinitionsQuery.isLoading ? (
          <Spinner />
        ) : customFieldDefinitionsQuery.isError ? (
          <p className="text-sm text-red-600">{getErrorMessage(customFieldDefinitionsQuery.error)}</p>
        ) : (
          <>
            <CustomFieldsRenderer
              definitions={customFieldDefinitionsQuery.data ?? []}
              values={customFieldValues}
              errors={customFieldErrors}
              onChange={(fieldKey, value) => {
                setCustomFieldValues((current) => ({ ...current, [fieldKey]: value }));
                setCustomFieldErrors((current) => {
                  if (!current[fieldKey]) {
                    return current;
                  }
                  const next = { ...current };
                  delete next[fieldKey];
                  return next;
                });
              }}
            />
            <Button
              onClick={() => {
                try {
                  const payload = normalizeCustomFieldPayload(customFieldDefinitionsQuery.data ?? [], customFieldValues);
                  setCustomFieldErrors({});
                  saveCustomFieldsMutation.mutate(payload);
                } catch (error) {
                  if (error instanceof z.ZodError) {
                    setCustomFieldErrors(zodErrorToFieldMap(error));
                    setMessage("Fix custom field validation errors.");
                    return;
                  }
                  setMessage(getErrorToastMessage(error));
                }
              }}
              disabled={saveCustomFieldsMutation.isPending}
            >
              {saveCustomFieldsMutation.isPending ? "Saving..." : "Save custom fields"}
            </Button>
          </>
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <Tabs
          items={[
            {
              id: "activities",
              label: "Activities",
              content: <EntityActivitiesTab entityType="opportunity" entityId={opportunityId} />
            },
            {
              id: "notes",
              label: "Notes",
              content: <EntityNotesTab entityType="opportunity" entityId={opportunityId} />
            },
            {
              id: "attachments",
              label: "Attachments",
              content: <EntityAttachmentsTab entityType="opportunity" entityId={opportunityId} />
            },
            {
              id: "audit",
              label: "Audit",
              content: <EntityAuditTab entityType="opportunity" entityId={opportunityId} />
            }
          ]}
        />
      </div>

      <OpportunityChangeStageModal
        open={openChangeStage}
        opportunity={opportunity}
        stages={stages}
        onClose={() => setOpenChangeStage(false)}
      />
      <OpportunityCloseWonModal
        open={openCloseWon}
        opportunity={opportunity}
        customFieldDefinitions={customFieldDefinitionsQuery.data ?? []}
        onClose={() => setOpenCloseWon(false)}
      />
      <OpportunityCloseLostModal
        open={openCloseLost}
        opportunity={opportunity}
        customFieldDefinitions={customFieldDefinitionsQuery.data ?? []}
        onClose={() => setOpenCloseLost(false)}
      />
      <OpportunityReopenModal
        open={openReopen}
        opportunity={opportunity}
        openStages={openStages.length > 0 ? openStages : stages}
        onClose={() => setOpenReopen(false)}
      />
    </div>
  );
}
