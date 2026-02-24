"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { CustomFieldsRenderer } from "../../../components/crm/CustomFieldsRenderer";
import { createLead, getErrorMessage, getErrorToastMessage, listCustomFieldDefinitions, listLeads } from "../../../lib/api";
import { normalizeCustomFieldPayload, zodErrorToFieldMap } from "../../../lib/customFieldsZod";
import { queryKeys } from "../../../lib/queryKeys";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Modal } from "../../../components/ui/modal";
import { Select } from "../../../components/ui/select";
import { Spinner } from "../../../components/ui/spinner";
import { Table, Td, Th } from "../../../components/ui/table";
import { Toast, toastText, type ToastMessageValue } from "../../../components/ui/toast";

const statuses = ["New", "Working", "Qualified", "Disqualified", "Converted"] as const;

const createSchema = z.object({
  status: z.enum(statuses),
  source: z.string().min(1, "Source is required"),
  selling_legal_entity_id: z.string().uuid("Selling legal entity ID must be UUID"),
  region_code: z.string().min(1, "Region code is required"),
  owner_user_id: z.string().optional().or(z.literal("")),
  company_name: z.string().optional(),
  contact_first_name: z.string().optional(),
  contact_last_name: z.string().optional(),
  email: z.string().email("Invalid email").optional().or(z.literal("")),
  phone: z.string().optional(),
  qualification_notes: z.string().optional()
});

type CreateLeadForm = z.infer<typeof createSchema>;

export default function LeadsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

  const [statusFilter, setStatusFilter] = useState(searchParams.get("status") ?? "");
  const [ownerFilter, setOwnerFilter] = useState(searchParams.get("owner_user_id") ?? "");
  const [sourceFilter, setSourceFilter] = useState(searchParams.get("source") ?? "");
  const [searchFilter, setSearchFilter] = useState(searchParams.get("q") ?? "");
  const [openCreate, setOpenCreate] = useState(false);
  const [message, setMessage] = useState<ToastMessageValue>(null);
  const [customFieldValues, setCustomFieldValues] = useState<Record<string, unknown>>({});
  const [customFieldErrors, setCustomFieldErrors] = useState<Record<string, string>>({});

  const cursor = searchParams.get("cursor") ?? "0";
  const limit = 20;

  const leadParams = useMemo(
    () => ({
      status: statusFilter || undefined,
      owner_user_id: ownerFilter || undefined,
      source: sourceFilter || undefined,
      q: searchFilter || undefined,
      cursor,
      limit
    }),
    [statusFilter, ownerFilter, sourceFilter, searchFilter, cursor]
  );

  const leadsQuery = useQuery({
    queryKey: queryKeys.leads(leadParams),
    queryFn: () => listLeads(leadParams)
  });

  const form = useForm<CreateLeadForm>({
    resolver: zodResolver(createSchema),
    defaultValues: {
      status: "New",
      source: "Web",
      selling_legal_entity_id: "",
      region_code: "US",
      owner_user_id: "",
      company_name: "",
      contact_first_name: "",
      contact_last_name: "",
      email: "",
      phone: "",
      qualification_notes: ""
    }
  });

  const sellingLegalEntityId = form.watch("selling_legal_entity_id");

  const customFieldDefinitionsQuery = useQuery({
    queryKey: queryKeys.customFieldDefinitions("lead", sellingLegalEntityId || undefined),
    queryFn: () => listCustomFieldDefinitions("lead", sellingLegalEntityId || undefined),
    enabled: openCreate
  });

  const createMutation = useMutation({
    mutationFn: ({ values, customFields }: { values: CreateLeadForm; customFields: Record<string, unknown> }) =>
      createLead({
        status: values.status,
        source: values.source,
        selling_legal_entity_id: values.selling_legal_entity_id,
        region_code: values.region_code,
        owner_user_id: values.owner_user_id || null,
        company_name: values.company_name || null,
        contact_first_name: values.contact_first_name || null,
        contact_last_name: values.contact_last_name || null,
        email: values.email || null,
        phone: values.phone || null,
        qualification_notes: values.qualification_notes || null,
        custom_fields: customFields
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.leads(leadParams) });
      form.reset();
      setCustomFieldValues({});
      setCustomFieldErrors({});
      setOpenCreate(false);
      setMessage("Lead created.");
    },
    onError: (error) => setMessage(getErrorToastMessage(error))
  });

  const rows = leadsQuery.data ?? [];
  const offset = Number.parseInt(cursor, 10) || 0;
  const hasPrev = offset > 0;
  const hasNext = rows.length === limit;

  function applyFilters() {
    const params = new URLSearchParams(searchParams.toString());
    if (statusFilter) params.set("status", statusFilter);
    else params.delete("status");

    if (ownerFilter) params.set("owner_user_id", ownerFilter);
    else params.delete("owner_user_id");

    if (sourceFilter) params.set("source", sourceFilter);
    else params.delete("source");

    if (searchFilter) params.set("q", searchFilter);
    else params.delete("q");

    params.set("cursor", "0");
    router.push(`/crm/leads?${params.toString()}`);
  }

  function setCursor(nextCursor: number) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("cursor", String(nextCursor));
    router.push(`/crm/leads?${params.toString()}`);
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Leads</h1>
          <p className="text-sm text-slate-500">Track and convert leads through qualification stages.</p>
        </div>
        <Button onClick={() => setOpenCreate(true)}>Create Lead</Button>
      </div>

      <Toast message={message} tone={toastText(message).toLowerCase().includes("created") ? "success" : "error"} />

      <div className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 md:grid-cols-5">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Status</label>
          <Select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">Any</option>
            {statuses.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Owner user ID</label>
          <Input value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value)} placeholder="UUID" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Source</label>
          <Input value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)} placeholder="Web" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Search (company/email)</label>
          <Input value={searchFilter} onChange={(event) => setSearchFilter(event.target.value)} placeholder="Acme" />
        </div>
        <div className="flex items-end">
          <Button className="w-full" onClick={applyFilters}>
            Apply filters
          </Button>
        </div>
      </div>

      {leadsQuery.isLoading ? (
        <Spinner />
      ) : leadsQuery.isError ? (
        <p className="text-sm text-red-600">{getErrorMessage(leadsQuery.error)}</p>
      ) : (
        <>
          <Table>
            <thead>
              <tr>
                <Th>Company / Contact</Th>
                <Th>Status</Th>
                <Th>Source</Th>
                <Th>Owner</Th>
                <Th>Created</Th>
                <Th>Updated</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((lead) => (
                <tr key={lead.id}>
                  <Td>
                    <Link href={`/crm/leads/${lead.id}`} className="font-medium text-slate-900 hover:underline">
                      {lead.company_name || `${lead.contact_first_name ?? ""} ${lead.contact_last_name ?? ""}`.trim() || "Lead"}
                    </Link>
                  </Td>
                  <Td>
                    <Badge
                      tone={
                        lead.status === "Converted"
                          ? "success"
                          : lead.status === "Disqualified"
                            ? "danger"
                            : "default"
                      }
                    >
                      {lead.status}
                    </Badge>
                  </Td>
                  <Td>{lead.source}</Td>
                  <Td>{lead.owner_user_id ?? "-"}</Td>
                  <Td>{new Date(lead.created_at).toLocaleString()}</Td>
                  <Td>{new Date(lead.updated_at).toLocaleString()}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <div className="flex items-center justify-end gap-2">
            <Button variant="secondary" disabled={!hasPrev} onClick={() => setCursor(Math.max(0, offset - limit))}>
              Previous
            </Button>
            <Button variant="secondary" disabled={!hasNext} onClick={() => setCursor(offset + limit)}>
              Next
            </Button>
          </div>
        </>
      )}

      <Modal open={openCreate} title="Create Lead" onClose={() => setOpenCreate(false)}>
        <form
          className="grid gap-3 md:grid-cols-2"
          onSubmit={form.handleSubmit((values) => {
            try {
              const payload = normalizeCustomFieldPayload(customFieldDefinitionsQuery.data ?? [], customFieldValues);
              setCustomFieldErrors({});
              createMutation.mutate({ values, customFields: payload });
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
            <label className="mb-1 block text-xs font-medium text-slate-600">Status *</label>
            <Select {...form.register("status")}>
              {statuses.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Source *</label>
            <Input {...form.register("source")} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Selling legal entity ID *</label>
            <Input {...form.register("selling_legal_entity_id")} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Region code *</label>
            <Input {...form.register("region_code")} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Company</label>
            <Input {...form.register("company_name")} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Owner user ID</label>
            <Input {...form.register("owner_user_id")} />
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
            <textarea className="min-h-20 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" {...form.register("qualification_notes")} />
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
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Saving..." : "Create"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
