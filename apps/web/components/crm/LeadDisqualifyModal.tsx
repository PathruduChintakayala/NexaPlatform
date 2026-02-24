"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { disqualifyLead, getErrorToastMessage } from "../../lib/api";
import { queryKeys } from "../../lib/queryKeys";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Modal } from "../ui/modal";
import { Toast, toastText, type ToastMessageValue } from "../ui/toast";
import { useState } from "react";

const schema = z.object({
  reason_code: z.string().min(1, "Reason code is required"),
  notes: z.string().optional()
});

type FormValues = z.infer<typeof schema>;

interface LeadDisqualifyModalProps {
  open: boolean;
  leadId: string;
  rowVersion: number;
  onClose: () => void;
}

export function LeadDisqualifyModal({ open, leadId, rowVersion, onClose }: LeadDisqualifyModalProps) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<ToastMessageValue>(null);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { reason_code: "", notes: "" }
  });

  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      disqualifyLead(leadId, {
        reason_code: values.reason_code,
        notes: values.notes || null,
        row_version: rowVersion
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.lead(leadId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.leads({}) })
      ]);
      setMessage("Lead disqualified.");
      form.reset();
      onClose();
    },
    onError: (error) => setMessage(getErrorToastMessage(error))
  });

  return (
    <Modal open={open} title="Disqualify Lead" onClose={onClose}>
      <div className="space-y-3">
        <Toast message={message} tone={toastText(message).toLowerCase().includes("disqualified") ? "success" : "error"} />
        <form className="space-y-3" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Reason code</label>
            <Input placeholder="NO_BUDGET" {...form.register("reason_code")} />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Notes</label>
            <textarea className="min-h-20 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" {...form.register("notes")} />
          </div>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Saving..." : "Disqualify"}
          </Button>
        </form>
      </div>
    </Modal>
  );
}
