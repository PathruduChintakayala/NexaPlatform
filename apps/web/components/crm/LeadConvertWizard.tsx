"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { convertLead, getErrorToastMessage, listContacts, searchCRM } from "../../lib/api";
import { queryKeys } from "../../lib/queryKeys";
import type { LeadConvertRequest, LeadRead, SearchResult } from "../../lib/types";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Modal } from "../ui/modal";
import { Select } from "../ui/select";
import { Spinner } from "../ui/spinner";
import { Toast, toastText, type ToastMessageValue } from "../ui/toast";

interface LeadConvertWizardProps {
  open: boolean;
  lead: LeadRead;
  onClose: () => void;
}

export function LeadConvertWizard({ open, lead, onClose }: LeadConvertWizardProps) {
  const queryClient = useQueryClient();
  const [step, setStep] = useState(1);
  const [idempotencyKey, setIdempotencyKey] = useState<string>("");
  const [message, setMessage] = useState<ToastMessageValue>(null);

  const [accountMode, setAccountMode] = useState<"existing" | "new">("existing");
  const [accountQuery, setAccountQuery] = useState(lead.company_name ?? "");
  const [selectedAccountId, setSelectedAccountId] = useState<string>(lead.converted_account_id ?? "");
  const [newAccountName, setNewAccountName] = useState(lead.company_name ?? "");
  const [newAccountRegion, setNewAccountRegion] = useState(lead.region_code ?? "");
  const [newAccountOwner, setNewAccountOwner] = useState(lead.owner_user_id ?? "");
  const [newAccountLegalEntities, setNewAccountLegalEntities] = useState(lead.selling_legal_entity_id ?? "");

  const [contactMode, setContactMode] = useState<"existing" | "new">("new");
  const [selectedContactId, setSelectedContactId] = useState(lead.converted_contact_id ?? "");
  const [newContactFirstName, setNewContactFirstName] = useState(lead.contact_first_name ?? "");
  const [newContactLastName, setNewContactLastName] = useState(lead.contact_last_name ?? "");
  const [newContactEmail, setNewContactEmail] = useState(lead.email ?? "");
  const [newContactPhone, setNewContactPhone] = useState(lead.phone ?? "");
  const [newContactOwner, setNewContactOwner] = useState(lead.owner_user_id ?? "");
  const [newContactPrimary, setNewContactPrimary] = useState(true);

  useEffect(() => {
    if (open) {
      setIdempotencyKey(crypto.randomUUID());
      setStep(1);
      setMessage(null);
    }
  }, [open]);

  const accountSearchQuery = useQuery({
    queryKey: queryKeys.crmSearch(accountQuery, "account", 10),
    queryFn: () => searchCRM(accountQuery, "account", 10),
    enabled: open && accountMode === "existing" && accountQuery.trim().length >= 2
  });

  const contactsQuery = useQuery({
    queryKey: queryKeys.contacts(selectedAccountId, {}),
    queryFn: () => listContacts(selectedAccountId, {}),
    enabled: open && contactMode === "existing" && Boolean(selectedAccountId)
  });

  const selectedAccountResult = useMemo(
    () => (accountSearchQuery.data ?? []).find((item) => item.entity_id === selectedAccountId),
    [accountSearchQuery.data, selectedAccountId]
  );

  const convertMutation = useMutation({
    mutationFn: async () => {
      const body: LeadConvertRequest = {
        row_version: lead.row_version,
        account:
          accountMode === "existing"
            ? {
                mode: "existing" as const,
                account_id: selectedAccountId
              }
            : {
                mode: "new" as const,
                name: newAccountName,
                primary_region_code: newAccountRegion || null,
                owner_user_id: newAccountOwner || null,
                legal_entity_ids: newAccountLegalEntities
                  ? newAccountLegalEntities
                      .split(",")
                      .map((item) => item.trim())
                      .filter(Boolean)
                  : []
              },
        contact:
          contactMode === "existing"
            ? {
                mode: "existing" as const,
                contact_id: selectedContactId
              }
            : {
                mode: "new" as const,
                first_name: newContactFirstName,
                last_name: newContactLastName,
                email: newContactEmail || null,
                phone: newContactPhone || null,
                owner_user_id: newContactOwner || null,
                is_primary: newContactPrimary
              },
        create_opportunity: false
      };

      return convertLead(lead.id, body, idempotencyKey);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.lead(lead.id) }),
        queryClient.invalidateQueries({ queryKey: ["leads"] }),
        queryClient.invalidateQueries({ queryKey: ["accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["contacts"] })
      ]);
      setMessage("Lead converted successfully.");
    },
    onError: async (error) => {
      const errorToast = getErrorToastMessage(error);
      const text = errorToast.message;
      setMessage(errorToast);
      if (text.toLowerCase().includes("row_version")) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.lead(lead.id) });
      }
    }
  });

  function validateStep1() {
    if (accountMode === "existing" && !selectedAccountId) {
      setMessage("Select an existing account.");
      return false;
    }
    if (accountMode === "new" && !newAccountName.trim()) {
      setMessage("Account name is required.");
      return false;
    }
    return true;
  }

  function validateStep2() {
    if (contactMode === "existing" && !selectedContactId) {
      setMessage("Select an existing contact.");
      return false;
    }
    if (contactMode === "new") {
      if (!newContactFirstName.trim() || !newContactLastName.trim()) {
        setMessage("First and last name are required for new contact.");
        return false;
      }
    }
    return true;
  }

  const converted = convertMutation.data;
  const searchResults: SearchResult[] = accountSearchQuery.data ?? [];

  return (
    <Modal open={open} title="Convert Lead" onClose={onClose}>
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <span className={step === 1 ? "font-semibold text-slate-900" : ""}>1. Account</span>
          <span>→</span>
          <span className={step === 2 ? "font-semibold text-slate-900" : ""}>2. Contact</span>
          <span>→</span>
          <span className={step === 3 ? "font-semibold text-slate-900" : ""}>3. Review</span>
        </div>

        <Toast message={message} tone={toastText(message).toLowerCase().includes("success") ? "success" : "error"} />

        {step === 1 ? (
          <div className="space-y-3">
            <div className="flex gap-2">
              <Button variant={accountMode === "existing" ? "primary" : "secondary"} onClick={() => setAccountMode("existing")}>
                Existing
              </Button>
              <Button variant={accountMode === "new" ? "primary" : "secondary"} onClick={() => setAccountMode("new")}>
                New
              </Button>
            </div>

            {accountMode === "existing" ? (
              <div className="space-y-2">
                <Input value={accountQuery} onChange={(event) => setAccountQuery(event.target.value)} placeholder="Search account" />
                {accountSearchQuery.isLoading ? <Spinner /> : null}
                <div className="space-y-1">
                  {searchResults.map((result) => (
                    <button
                      key={result.entity_id}
                      type="button"
                      onClick={() => setSelectedAccountId(result.entity_id)}
                      className={`w-full rounded-md border px-3 py-2 text-left text-sm ${selectedAccountId === result.entity_id ? "border-slate-900 bg-slate-100" : "border-slate-200"}`}
                    >
                      <p className="font-medium">{result.title}</p>
                      <p className="text-xs text-slate-500">{result.subtitle ?? ""}</p>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <Input value={newAccountName} onChange={(event) => setNewAccountName(event.target.value)} placeholder="Account name" />
                <Input value={newAccountRegion} onChange={(event) => setNewAccountRegion(event.target.value)} placeholder="Primary region code (optional)" />
                <Input value={newAccountOwner} onChange={(event) => setNewAccountOwner(event.target.value)} placeholder="Owner user ID (optional)" />
                <Input
                  value={newAccountLegalEntities}
                  onChange={(event) => setNewAccountLegalEntities(event.target.value)}
                  placeholder="Legal entity IDs (comma-separated)"
                />
              </div>
            )}

            <div className="flex justify-end">
              <Button
                onClick={() => {
                  if (validateStep1()) {
                    setStep(2);
                  }
                }}
              >
                Next
              </Button>
            </div>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="space-y-3">
            <div className="flex gap-2">
              <Button
                variant={contactMode === "existing" ? "primary" : "secondary"}
                onClick={() => setContactMode("existing")}
                disabled={accountMode !== "existing" || !selectedAccountId}
                title={accountMode !== "existing" ? "Select existing account to use existing contact" : undefined}
              >
                Existing
              </Button>
              <Button variant={contactMode === "new" ? "primary" : "secondary"} onClick={() => setContactMode("new")}>
                New
              </Button>
            </div>

            {contactMode === "existing" ? (
              <div className="space-y-2">
                {contactsQuery.isLoading ? <Spinner /> : null}
                <Select value={selectedContactId} onChange={(event) => setSelectedContactId(event.target.value)}>
                  <option value="">Select contact</option>
                  {(contactsQuery.data ?? []).map((contact) => (
                    <option key={contact.id} value={contact.id}>
                      {contact.first_name} {contact.last_name} {contact.email ? `(${contact.email})` : ""}
                    </option>
                  ))}
                </Select>
              </div>
            ) : (
              <div className="space-y-2">
                <Input value={newContactFirstName} onChange={(event) => setNewContactFirstName(event.target.value)} placeholder="First name" />
                <Input value={newContactLastName} onChange={(event) => setNewContactLastName(event.target.value)} placeholder="Last name" />
                <Input value={newContactEmail} onChange={(event) => setNewContactEmail(event.target.value)} placeholder="Email (optional)" />
                <Input value={newContactPhone} onChange={(event) => setNewContactPhone(event.target.value)} placeholder="Phone (optional)" />
                <Input value={newContactOwner} onChange={(event) => setNewContactOwner(event.target.value)} placeholder="Owner user ID (optional)" />
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={newContactPrimary} onChange={(event) => setNewContactPrimary(event.target.checked)} />
                  Set as primary
                </label>
              </div>
            )}

            <div className="flex justify-between">
              <Button variant="secondary" onClick={() => setStep(1)}>
                Back
              </Button>
              <Button
                onClick={() => {
                  if (validateStep2()) {
                    setStep(3);
                  }
                }}
              >
                Next
              </Button>
            </div>
          </div>
        ) : null}

        {step === 3 ? (
          <div className="space-y-3">
            <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm">
              <p>
                <span className="font-medium">Lead ID:</span> {lead.id}
              </p>
              <p>
                <span className="font-medium">Current status:</span> {lead.status}
              </p>
              <p>
                <span className="font-medium">Account:</span>{" "}
                {accountMode === "existing" ? selectedAccountResult?.title || selectedAccountId : newAccountName}
              </p>
              <p>
                <span className="font-medium">Contact:</span>{" "}
                {contactMode === "existing"
                  ? (contactsQuery.data ?? []).find((item) => item.id === selectedContactId)
                      ? `${(contactsQuery.data ?? []).find((item) => item.id === selectedContactId)?.first_name} ${(contactsQuery.data ?? []).find((item) => item.id === selectedContactId)?.last_name}`
                      : selectedContactId
                  : `${newContactFirstName} ${newContactLastName}`}
              </p>
              <p>
                <span className="font-medium">Idempotency-Key:</span> {idempotencyKey}
              </p>
            </div>

            {converted ? (
              <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
                <p className="font-medium">Lead converted successfully.</p>
                {converted.converted_account_id ? (
                  <p>
                    Account: <Link className="underline" href={`/crm/accounts/${converted.converted_account_id}`}>{converted.converted_account_id}</Link>
                  </p>
                ) : null}
                {converted.converted_contact_id ? <p>Contact: {converted.converted_contact_id}</p> : null}
                {converted.converted_opportunity_id ? <p>Opportunity: {converted.converted_opportunity_id}</p> : null}
              </div>
            ) : null}

            <div className="flex justify-between">
              <Button variant="secondary" onClick={() => setStep(2)}>
                Back
              </Button>
              <Button disabled={convertMutation.isPending || Boolean(converted)} onClick={() => convertMutation.mutate()}>
                {convertMutation.isPending ? "Converting..." : converted ? "Converted" : "Convert"}
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
