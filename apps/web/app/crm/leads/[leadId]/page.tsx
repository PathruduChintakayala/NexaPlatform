"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { CustomFieldsRenderer } from "../../../../components/crm/CustomFieldsRenderer";
import { EntityActivitiesTab } from "../../../../components/crm/EntityActivitiesTab";
import { EntityAuditTab } from "../../../../components/crm/EntityAuditTab";
import { EntityNotesTab } from "../../../../components/crm/EntityNotesTab";
import { LeadConvertWizard } from "../../../../components/crm/LeadConvertWizard";
import { LeadDisqualifyModal } from "../../../../components/crm/LeadDisqualifyModal";
import { Badge } from "../../../../components/ui/badge";
import { Button } from "../../../../components/ui/button";
import { Input } from "../../../../components/ui/input";
import { Spinner } from "../../../../components/ui/spinner";
import { Tabs } from "../../../../components/ui/tabs";
import { Toast, toastText, type ToastMessageValue } from "../../../../components/ui/toast";
import { normalizeCustomFieldPayload, zodErrorToFieldMap } from "../../../../lib/customFieldsZod";
import { getErrorMessage, getErrorToastMessage, getLead, listCustomFieldDefinitions, patchLead } from "../../../../lib/api";
import { queryKeys } from "../../../../lib/queryKeys";

const detailSchema = z.object({
  status: z.string().optional(),
  source: z.string().min(1, "Source is required"),
  owner_user_id: z.string().optional().or(z.literal("")),
  region_code: z.string().min(1, "Region code is required"),
  company_name: z.string().optional(),
  contact_first_name: z.string().optional(),
  contact_last_name: z.string().optional(),
  email: z.string().email("Invalid email").optional().or(z.literal("")),
  phone: z.string().optional(),
  qualification_notes: z.string().optional()
});

type DetailForm = z.infer<typeof detailSchema>;

export default function LeadDetailPage({ params }: { params: { leadId: string } }) {
  const leadId = params.leadId;
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<ToastMessageValue>(null);
  const [openConvert, setOpenConvert] = useState(false);
  const [openDisqualify, setOpenDisqualify] = useState(false);
  const [customFieldValues, setCustomFieldValues] = useState<Record<string, unknown>>({});
  const [customFieldErrors, setCustomFieldErrors] = useState<Record<string, string>>({});

  const leadQuery = useQuery({
    queryKey: queryKeys.lead(leadId),
    queryFn: () => getLead(leadId)
  });

  const customFieldDefinitionsQuery = useQuery({
    queryKey: queryKeys.customFieldDefinitions("lead", leadQuery.data?.selling_legal_entity_id),
    queryFn: () => listCustomFieldDefinitions("lead", leadQuery.data?.selling_legal_entity_id),
    enabled: Boolean(leadQuery.data)
  });

  useEffect(() => {
    if (!leadQuery.data) {
      return;
    }
    setCustomFieldValues(leadQuery.data.custom_fields ?? {});
    setCustomFieldErrors({});
  }, [leadQuery.data]);

  const form = useForm<DetailForm>({
    resolver: zodResolver(detailSchema),
    values: leadQuery.data
      ? {
          status: leadQuery.data.status,
          source: leadQuery.data.source,
          owner_user_id: leadQuery.data.owner_user_id ?? "",
          region_code: leadQuery.data.region_code,
          company_name: leadQuery.data.company_name ?? "",
          contact_first_name: leadQuery.data.contact_first_name ?? "",
          contact_last_name: leadQuery.data.contact_last_name ?? "",
          email: leadQuery.data.email ?? "",
          phone: leadQuery.data.phone ?? "",
          qualification_notes: leadQuery.data.qualification_notes ?? ""
        }
      : undefined
  });

  const updateMutation = useMutation({
    mutationFn: ({ values, customFields }: { values: DetailForm; customFields: Record<string, unknown> }) => {
      if (!leadQuery.data) {
        throw new Error("Lead not loaded");
      }
      return patchLead(leadId, {
        row_version: leadQuery.data.row_version,
        status: values.status || null,
        source: values.source,
        owner_user_id: values.owner_user_id || null,
        region_code: values.region_code,
        company_name: values.company_name || null,
        contact_first_name: values.contact_first_name || null,
        contact_last_name: values.contact_last_name || null,
        email: values.email || null,
        phone: values.phone || null,
        qualification_notes: values.qualification_notes || null,
        custom_fields: customFields
      });
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.lead(leadId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.leads({}) })
      ]);
      setMessage("Lead updated.");
    },
    onError: (error) => setMessage(getErrorToastMessage(error))
  });

  if (leadQuery.isLoading) {
    return <Spinner />;
  }

  if (leadQuery.isError || !leadQuery.data) {
    return <p className="text-sm text-red-600">{getErrorMessage(leadQuery.error)}</p>;
  }

  const lead = leadQuery.data;
  const disabledConvert = lead.status === "Converted" || lead.status === "Disqualified";
  const disabledDisqualify = lead.status === "Converted";

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">{lead.company_name || `${lead.contact_first_name ?? ""} ${lead.contact_last_name ?? ""}`.trim() || "Lead"}</h1>
            <p className="mt-1 text-sm text-slate-500">Lead detail and conversion workflow.</p>
          </div>
          <Badge
            tone={lead.status === "Converted" ? "success" : lead.status === "Disqualified" ? "danger" : "default"}
          >
            {lead.status}
          </Badge>
        </div>

        <div className="mt-3 grid gap-2 text-sm text-slate-700 md:grid-cols-2">
          <p>
            <span className="font-medium">Source:</span> {lead.source}
          </p>
          <p>
            <span className="font-medium">Selling legal entity:</span> {lead.selling_legal_entity_id}
          </p>
          <p>
            <span className="font-medium">Region:</span> {lead.region_code}
          </p>
          <p>
            <span className="font-medium">Owner:</span> {lead.owner_user_id ?? "-"}
          </p>
          <p>
            <span className="font-medium">Created:</span> {new Date(lead.created_at).toLocaleString()}
          </p>
          <p>
            <span className="font-medium">Updated:</span> {new Date(lead.updated_at).toLocaleString()}
          </p>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Button
            onClick={() => setOpenConvert(true)}
            disabled={disabledConvert}
            title={lead.status === "Disqualified" ? "Disqualified" : undefined}
          >
            Convert
          </Button>
          <Button variant="secondary" onClick={() => setOpenDisqualify(true)} disabled={disabledDisqualify}>
            Disqualify
          </Button>
        </div>
      </div>

      <Toast message={message} tone={toastText(message).toLowerCase().includes("updated") ? "success" : "error"} />

      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <Tabs
          items={[
            {
              id: "details",
              label: "Details",
              content: (
                <form
                  className="grid gap-3 md:grid-cols-2"
                  onSubmit={form.handleSubmit((values) => {
                    try {
                      const payload = normalizeCustomFieldPayload(customFieldDefinitionsQuery.data ?? [], customFieldValues);
                      setCustomFieldErrors({});
                      updateMutation.mutate({ values, customFields: payload });
                    } catch (error) {
                      if (error instanceof z.ZodError) {
                        setCustomFieldErrors(zodErrorToFieldMap(error));
                        setMessage("Fix custom field validation errors.");
                        return;
                      }
                      setMessage(getErrorToastMessage(error));
                    }
                  })}
                >
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-600">Status</label>
                    <Input {...form.register("status")} />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-600">Source</label>
                    <Input {...form.register("source")} />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-600">Owner user ID</label>
                    <Input {...form.register("owner_user_id")} />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-600">Region code</label>
                    <Input {...form.register("region_code")} />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-600">Company</label>
                    <Input {...form.register("company_name")} />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-600">Contact first name</label>
                    <Input {...form.register("contact_first_name")} />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-600">Contact last name</label>
                    <Input {...form.register("contact_last_name")} />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-600">Email</label>
                    <Input {...form.register("email")} />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-600">Phone</label>
                    <Input {...form.register("phone")} />
                  </div>
                  <div className="md:col-span-2">
                    <label className="mb-1 block text-xs font-medium text-slate-600">Qualification notes</label>
                    <textarea
                      className="min-h-20 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                      {...form.register("qualification_notes")}
                    />
                  </div>
                  <div className="md:col-span-2">
                    {customFieldDefinitionsQuery.isLoading ? (
                      <Spinner />
                    ) : customFieldDefinitionsQuery.isError ? (
                      <p className="text-sm text-red-600">{getErrorMessage(customFieldDefinitionsQuery.error)}</p>
                    ) : (
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
                    )}
                  </div>
                  <div className="md:col-span-2">
                    <Button type="submit" disabled={updateMutation.isPending}>
                      {updateMutation.isPending ? "Saving..." : "Save changes"}
                    </Button>
                  </div>
                </form>
              )
            },
            {
              id: "activities",
              label: "Activities",
              content: <EntityActivitiesTab entityType="lead" entityId={leadId} />
            },
            {
              id: "notes",
              label: "Notes",
              content: <EntityNotesTab entityType="lead" entityId={leadId} />
            },
            {
              id: "audit",
              label: "Audit",
              content: <EntityAuditTab entityType="lead" entityId={leadId} />
            }
          ]}
        />
      </div>

      <LeadConvertWizard open={openConvert} lead={lead} onClose={() => setOpenConvert(false)} />
      <LeadDisqualifyModal
        open={openDisqualify}
        leadId={leadId}
        rowVersion={lead.row_version}
        onClose={() => setOpenDisqualify(false)}
      />
    </div>
  );
}
