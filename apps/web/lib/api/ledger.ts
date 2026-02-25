import type { OpsJournalEntryRead } from "../types";
import { apiRequest, toQuery } from "./core";

export function listJournalEntries(params: {
  tenant_id: string;
  company_code?: string;
  start_date?: string;
  end_date?: string;
}) {
  return apiRequest<OpsJournalEntryRead[]>(`/ledger/journal-entries${toQuery(params)}`);
}

export function getJournalEntry(entryId: string) {
  return apiRequest<OpsJournalEntryRead>(`/ledger/journal-entries/${entryId}`);
}

export function reverseJournalEntry(entryId: string, body: { reason: string; created_by: string }) {
  return apiRequest<OpsJournalEntryRead>(`/ledger/journal-entries/${entryId}/reverse`, {
    method: "POST",
    body: JSON.stringify(body)
  });
}
