"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { CustomFieldsRenderer } from "../../../components/crm/CustomFieldsRenderer";
import { createAccount, exportAccounts, getErrorMessage, getJob, listAccounts, listCustomFieldDefinitions, patchAccount } from "../../../lib/api";
import { normalizeCustomFieldPayload, zodErrorToFieldMap } from "../../../lib/customFieldsZod";
import { queryKeys } from "../../../lib/queryKeys";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Modal } from "../../../components/ui/modal";
import { Select } from "../../../components/ui/select";
import { Spinner } from "../../../components/ui/spinner";
import { Table, Td, Th } from "../../../components/ui/table";
import { Toast } from "../../../components/ui/toast";

const createSchema = z.object({
  name: z.string().min(1, "Name is required"),
  status: z.enum(["Active", "Inactive"]),
  primary_region_code: z.string().optional().or(z.literal(""))
});

type CreateFormValues = z.infer<typeof createSchema>;

const terminalStatuses = new Set(["Succeeded", "Failed", "PartiallySucceeded"]);

export default function AccountsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

  const [nameFilter, setNameFilter] = useState(searchParams.get("name") ?? "");
  const [quickSearch, setQuickSearch] = useState(searchParams.get("q") ?? "");
  const [statusFilter, setStatusFilter] = useState(searchParams.get("status") ?? "");
  const [ownerFilter, setOwnerFilter] = useState(searchParams.get("owner_user_id") ?? "");
  const [openCreateModal, setOpenCreateModal] = useState(false);
  const [openExportModal, setOpenExportModal] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [customFieldValues, setCustomFieldValues] = useState<Record<string, unknown>>({});
  const [customFieldErrors, setCustomFieldErrors] = useState<Record<string, string>>({});

  const cursor = searchParams.get("cursor") ?? "0";
  const limit = 20;

  const accountParams = useMemo(
    () => ({
      name: nameFilter || quickSearch || undefined,
      status: statusFilter || undefined,
      owner_user_id: ownerFilter || undefined,
      cursor,
      limit
    }),
    [nameFilter, quickSearch, statusFilter, ownerFilter, cursor]
  );

  const accountsQuery = useQuery({
    queryKey: queryKeys.accounts(accountParams),
    queryFn: () => listAccounts(accountParams)
  });

  const createForm = useForm<CreateFormValues>({
    resolver: zodResolver(createSchema),
    defaultValues: { name: "", status: "Active", primary_region_code: "" }
  });

  const customFieldDefinitionsQuery = useQuery({
    queryKey: queryKeys.customFieldDefinitions("account"),
    queryFn: () => listCustomFieldDefinitions("account"),
    enabled: openCreateModal
  });

  const createMutation = useMutation({
    mutationFn: async ({
      values,
      customFields
    }: {
      values: CreateFormValues;
      customFields: Record<string, unknown>;
    }) => {
      const created = await createAccount({
        name: values.name,
        primary_region_code: values.primary_region_code || null,
        legal_entity_ids: [],
        custom_fields: customFields
      });
      if (values.status === "Inactive") {
        await patchAccount(created.id, { row_version: created.row_version, status: "Inactive" });
      }
      return created;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.accounts(accountParams) });
      createForm.reset();
      setCustomFieldValues({});
      setCustomFieldErrors({});
      setOpenCreateModal(false);
      setToastMessage("Account created.");
    },
    onError: (error) => setToastMessage(getErrorMessage(error))
  });

  const exportMutation = useMutation({
    mutationFn: () => exportAccounts({ name: nameFilter || quickSearch || undefined, status: statusFilter || undefined }, true),
    onSuccess: (job) => {
      setJobId(job.id);
      setOpenExportModal(true);
      setToastMessage("Export job created.");
    },
    onError: (error) => setToastMessage(getErrorMessage(error))
  });

  const jobQuery = useQuery({
    queryKey: jobId ? queryKeys.job(jobId) : ["job", "none"],
    queryFn: () => getJob(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status || terminalStatuses.has(status)) {
        return false;
      }
      return 1500;
    }
  });

  function setCursor(nextCursor: number) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("cursor", String(nextCursor));
    router.push(`/crm/accounts?${params.toString()}`);
  }

  function applyFilters() {
    const params = new URLSearchParams(searchParams.toString());
    if (nameFilter) {
      params.set("name", nameFilter);
    } else {
      params.delete("name");
    }
    if (quickSearch) {
      params.set("q", quickSearch);
    } else {
      params.delete("q");
    }
    if (statusFilter) {
      params.set("status", statusFilter);
    } else {
      params.delete("status");
    }
    if (ownerFilter) {
      params.set("owner_user_id", ownerFilter);
    } else {
      params.delete("owner_user_id");
    }
    params.set("cursor", "0");
    router.push(`/crm/accounts?${params.toString()}`);
  }

  const offset = Number.parseInt(cursor, 10) || 0;
  const rows = accountsQuery.data ?? [];
  const hasPrev = offset > 0;
  const hasNext = rows.length === limit;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Accounts</h1>
          <p className="text-sm text-slate-500">Manage customer accounts across legal entities.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => exportMutation.mutate()} disabled={exportMutation.isPending}>
            Export
          </Button>
          <Button onClick={() => setOpenCreateModal(true)}>Create Account</Button>
        </div>
      </div>

      <Toast message={toastMessage} tone={toastMessage?.toLowerCase().includes("created") ? "success" : "error"} />

      <div className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 md:grid-cols-5">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Name</label>
          <Input value={nameFilter} onChange={(event) => setNameFilter(event.target.value)} placeholder="Acme" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Quick search</label>
          <Input value={quickSearch} onChange={(event) => setQuickSearch(event.target.value)} placeholder="Type to search" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Status</label>
          <Select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">Any</option>
            <option value="Active">Active</option>
            <option value="Inactive">Inactive</option>
          </Select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Owner user ID</label>
          <Input value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value)} placeholder="UUID" />
        </div>
        <div className="flex items-end">
          <Button className="w-full" onClick={applyFilters}>
            Apply filters
          </Button>
        </div>
      </div>

      {accountsQuery.isLoading ? (
        <Spinner />
      ) : accountsQuery.isError ? (
        <p className="text-sm text-red-600">{getErrorMessage(accountsQuery.error)}</p>
      ) : (
        <>
          <Table>
            <thead>
              <tr>
                <Th>Name</Th>
                <Th>Status</Th>
                <Th>Owner</Th>
                <Th>Region</Th>
                <Th>Updated</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((account) => (
                <tr key={account.id}>
                  <Td>
                    <Link href={`/crm/accounts/${account.id}`} className="font-medium text-slate-900 hover:underline">
                      {account.name}
                    </Link>
                  </Td>
                  <Td>
                    <Badge tone={account.status === "Active" ? "success" : "warning"}>{account.status}</Badge>
                  </Td>
                  <Td>{account.owner_user_id ?? "-"}</Td>
                  <Td>{account.primary_region_code ?? "-"}</Td>
                  <Td>{new Date(account.updated_at).toLocaleString()}</Td>
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

      <Modal open={openCreateModal} title="Create Account" onClose={() => setOpenCreateModal(false)}>
        <form
          className="space-y-3"
          onSubmit={createForm.handleSubmit((values) => {
            try {
              const payload = normalizeCustomFieldPayload(customFieldDefinitionsQuery.data ?? [], customFieldValues);
              setCustomFieldErrors({});
              createMutation.mutate({ values, customFields: payload });
            } catch (error) {
              if (error instanceof z.ZodError) {
                setCustomFieldErrors(zodErrorToFieldMap(error));
                setToastMessage("Fix custom field validation errors.");
                return;
              }
              setToastMessage(getErrorMessage(error));
            }
          })}
        >
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Name</label>
            <Input {...createForm.register("name")} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Status</label>
            <Select {...createForm.register("status")}>
              <option value="Active">Active</option>
              <option value="Inactive">Inactive</option>
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Primary region code</label>
            <Input {...createForm.register("primary_region_code")} />
          </div>
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
          <Button type="submit" disabled={createMutation.isPending}>
            {createMutation.isPending ? "Saving..." : "Create"}
          </Button>
        </form>
      </Modal>

      <Modal open={openExportModal} title="Export Accounts" onClose={() => setOpenExportModal(false)}>
        {!jobId ? (
          <p className="text-sm text-slate-600">No export job.</p>
        ) : jobQuery.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-slate-600">
            <Spinner /> Checking job...
          </div>
        ) : jobQuery.isError ? (
          <p className="text-sm text-red-600">{getErrorMessage(jobQuery.error)}</p>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-slate-700">Status: {jobQuery.data?.status}</p>
            <p className="text-xs text-slate-500">Job ID: {jobId}</p>
            {jobQuery.data?.artifacts.find((artifact) => artifact.artifact_type === "EXPORT_CSV") ? (
              <a
                className="inline-flex rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white"
                href={`${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/api/crm/jobs/${jobId}/download/EXPORT_CSV`}
                target="_blank"
                rel="noreferrer"
              >
                Download CSV
              </a>
            ) : null}
          </div>
        )}
      </Modal>
    </div>
  );
}
