"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { CustomFieldsReadOnly } from "./CustomFieldsReadOnly";
import { closeWon, getErrorToastMessage } from "../../lib/api";
import { queryKeys } from "../../lib/queryKeys";
import type { CustomFieldDefinitionRead, OpportunityRead } from "../../lib/types";
import { Button } from "../ui/button";
import { Modal } from "../ui/modal";
import { Select } from "../ui/select";
import { Toast, toastText, type ToastMessageValue } from "../ui/toast";

const schema = z.object({
  revenue_handoff_mode: z.enum(["NONE", "CREATE_DRAFT_QUOTE", "CREATE_DRAFT_ORDER"]),
  revenue_handoff_requested: z.boolean()
});

type FormValues = z.infer<typeof schema>;

export function OpportunityCloseWonModal({
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
      revenue_handoff_mode: "NONE",
      revenue_handoff_requested: false
    }
  });

  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      closeWon(
        opportunity.id,
        {
          row_version: opportunity.row_version,
          revenue_handoff_mode: values.revenue_handoff_mode === "NONE" ? null : values.revenue_handoff_mode,
          revenue_handoff_requested: values.revenue_handoff_requested
        },
        idemKey
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.opportunity(opportunity.id) }),
        queryClient.invalidateQueries({ queryKey: ["opportunities"] })
      ]);
      setMessage("Opportunity closed won.");
      onClose();
    },
    onError: (error) => setMessage(getErrorToastMessage(error))
  });

  return (
    <Modal open={open} title="Close Won" onClose={onClose}>
      <div className="space-y-3">
        <Toast message={message} tone={toastText(message).toLowerCase().includes("won") ? "success" : "error"} />
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
            <label className="mb-1 block text-xs font-medium text-slate-600">Revenue handoff mode</label>
            <Select {...form.register("revenue_handoff_mode")}>
              <option value="NONE">None</option>
              <option value="CREATE_DRAFT_QUOTE">Create Draft Quote</option>
              <option value="CREATE_DRAFT_ORDER">Create Draft Order</option>
            </Select>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" {...form.register("revenue_handoff_requested")} />
            Request handoff
          </label>
          <p className="text-xs text-slate-500">Idempotency-Key: {idemKey}</p>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Closing..." : "Close Won"}
          </Button>
        </form>
      </div>
    </Modal>
  );
}
