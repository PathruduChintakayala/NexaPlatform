"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { changeOpportunityStage, getErrorToastMessage, patchOpportunity } from "../../lib/api";
import { queryKeys } from "../../lib/queryKeys";
import type { OpportunityRead, PipelineStageRead } from "../../lib/types";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Modal } from "../ui/modal";
import { Select } from "../ui/select";
import { Toast, toastText, type ToastMessageValue } from "../ui/toast";

const schema = z.object({
  stage_id: z.string().uuid("Select a valid stage"),
  amount: z.string().optional(),
  expected_close_date: z.string().optional()
});

type FormValues = z.infer<typeof schema>;

interface OpportunityChangeStageModalProps {
  open: boolean;
  opportunity: OpportunityRead;
  stages: PipelineStageRead[];
  defaultStageId?: string;
  onClose: () => void;
}

export function OpportunityChangeStageModal({
  open,
  opportunity,
  stages,
  defaultStageId,
  onClose
}: OpportunityChangeStageModalProps) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<ToastMessageValue>(null);
  const idemKey = useMemo(() => {
    void open;
    return crypto.randomUUID();
  }, [open]);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { stage_id: defaultStageId ?? "", amount: "", expected_close_date: "" }
  });

  useEffect(() => {
    if (!open) {
      return;
    }
    form.reset({ stage_id: defaultStageId ?? "", amount: "", expected_close_date: "" });
  }, [defaultStageId, form, open]);

  const selectedStageId = form.watch("stage_id");
  const selectedStage = stages.find((stage) => stage.id === selectedStageId);
  const needsAmount = Boolean(selectedStage?.requires_amount && opportunity.amount <= 0);
  const needsExpectedCloseDate = Boolean(selectedStage?.requires_expected_close_date && !opportunity.expected_close_date);

  const mutation = useMutation({
    mutationFn: async (values: FormValues) => {
      const selected = stages.find((stage) => stage.id === values.stage_id);
      if (!selected) {
        throw new Error("Stage not found");
      }

      let currentOpportunity = opportunity;
      const patchPayload: Record<string, unknown> = { row_version: currentOpportunity.row_version };

      if (selected.requires_amount && currentOpportunity.amount <= 0) {
        const amountValue = Number(values.amount ?? "");
        if (!Number.isFinite(amountValue) || amountValue <= 0) {
          throw new Error("This stage requires amount > 0. Set amount first.");
        }
        patchPayload.amount = amountValue;
      }

      if (selected.requires_expected_close_date && !currentOpportunity.expected_close_date) {
        if (!values.expected_close_date) {
          throw new Error("This stage requires expected close date. Set expected close date first.");
        }
        patchPayload.expected_close_date = values.expected_close_date;
      }

      if ("amount" in patchPayload || "expected_close_date" in patchPayload) {
        currentOpportunity = await patchOpportunity(opportunity.id, patchPayload);
      }

      return changeOpportunityStage(
        currentOpportunity.id,
        {
          stage_id: values.stage_id,
          row_version: currentOpportunity.row_version
        },
        idemKey
      );
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.opportunity(opportunity.id) }),
        queryClient.invalidateQueries({ queryKey: ["opportunities"] })
      ]);
      setMessage("Stage updated.");
      onClose();
    },
    onError: (error) => setMessage(getErrorToastMessage(error))
  });

  return (
    <Modal open={open} title="Change Stage" onClose={onClose}>
      <div className="space-y-3">
        <Toast message={message} tone={toastText(message).toLowerCase().includes("updated") ? "success" : "error"} />
        <form className="space-y-3" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Target stage</label>
            <Select {...form.register("stage_id")}>
              <option value="">Select stage</option>
              {stages.map((stage) => (
                <option key={stage.id} value={stage.id}>
                  {stage.name}
                </option>
              ))}
            </Select>
          </div>

          {needsAmount ? (
            <div className="space-y-1">
              <p className="text-xs text-amber-700">Selected stage requires amount. Set amount to continue.</p>
              <label className="mb-1 block text-xs font-medium text-slate-600">Set amount</label>
              <Input type="number" min={0} step="0.01" placeholder="0.00" {...form.register("amount")} />
            </div>
          ) : null}

          {needsExpectedCloseDate ? (
            <div className="space-y-1">
              <p className="text-xs text-amber-700">Selected stage requires expected close date. Set date to continue.</p>
              <label className="mb-1 block text-xs font-medium text-slate-600">Set expected close date</label>
              <Input type="date" {...form.register("expected_close_date")} />
            </div>
          ) : null}

          <p className="text-xs text-slate-500">Idempotency-Key: {idemKey}</p>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Updating..." : "Update stage"}
          </Button>
        </form>
      </div>
    </Modal>
  );
}
