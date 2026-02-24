"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { CustomFieldsReadOnly } from "./CustomFieldsReadOnly";
import { closeLost, getErrorToastMessage } from "../../lib/api";
import { queryKeys } from "../../lib/queryKeys";
import type { CustomFieldDefinitionRead, OpportunityRead } from "../../lib/types";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Modal } from "../ui/modal";
import { Toast, toastText, type ToastMessageValue } from "../ui/toast";

const schema = z.object({
  close_reason: z.string().min(1, "Close reason is required")
});

type FormValues = z.infer<typeof schema>;

export function OpportunityCloseLostModal({
  open,
  opportunity,
  customFieldDefinitions,
  onClose
}: {
  open: boolean;
  opportunity: OpportunityRead;
  customFieldDefinitions: CustomFieldDefinitionRead[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<ToastMessageValue>(null);
  const idemKey = useMemo(() => {
    void open;
    return crypto.randomUUID();
  }, [open]);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      close_reason: ""
    }
  });

  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      closeLost(
        opportunity.id,
        {
          row_version: opportunity.row_version,
          close_reason: values.close_reason
        },
        idemKey
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.opportunity(opportunity.id) }),
        queryClient.invalidateQueries({ queryKey: ["opportunities"] })
      ]);
      setMessage("Opportunity closed lost.");
      onClose();
    },
    onError: (error) => setMessage(getErrorToastMessage(error))
  });

  return (
    <Modal open={open} title="Close Lost" onClose={onClose}>
      <div className="space-y-3">
        <Toast message={message} tone={toastText(message).toLowerCase().includes("lost") ? "success" : "error"} />
        <form className="space-y-3" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
          <div>
            <p className="mb-1 text-xs font-medium text-slate-600">Current custom fields</p>
            <CustomFieldsReadOnly
              definitions={customFieldDefinitions}
              values={opportunity.custom_fields}
              emptyText="No custom fields set"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Close reason</label>
            <Input {...form.register("close_reason")} placeholder="NO_BUDGET" />
          </div>
          <p className="text-xs text-slate-500">Idempotency-Key: {idemKey}</p>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Closing..." : "Close Lost"}
          </Button>
        </form>
      </div>
    </Modal>
  );
}
