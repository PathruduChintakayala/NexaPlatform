"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { getErrorToastMessage, reopenOpportunity } from "../../lib/api";
import { queryKeys } from "../../lib/queryKeys";
import type { OpportunityRead, PipelineStageRead } from "../../lib/types";
import { Button } from "../ui/button";
import { Modal } from "../ui/modal";
import { Select } from "../ui/select";
import { Toast, toastText, type ToastMessageValue } from "../ui/toast";

const schema = z.object({
  new_stage_id: z.string().optional().or(z.literal(""))
});

type FormValues = z.infer<typeof schema>;

export function OpportunityReopenModal({
  open,
  opportunity,
  openStages,
  onClose
}: {
  open: boolean;
  opportunity: OpportunityRead;
  openStages: PipelineStageRead[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<ToastMessageValue>(null);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      new_stage_id: ""
    }
  });

  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      reopenOpportunity(opportunity.id, {
        row_version: opportunity.row_version,
        new_stage_id: values.new_stage_id || null
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.opportunity(opportunity.id) }),
        queryClient.invalidateQueries({ queryKey: ["opportunities"] })
      ]);
      setMessage("Opportunity reopened.");
      onClose();
    },
    onError: (error) => setMessage(getErrorToastMessage(error))
  });

  return (
    <Modal open={open} title="Reopen Opportunity" onClose={onClose}>
      <div className="space-y-3">
        <Toast message={message} tone={toastText(message).toLowerCase().includes("reopened") ? "success" : "error"} />
        <form className="space-y-3" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">New open stage (optional)</label>
            <Select {...form.register("new_stage_id")}>
              <option value="">Use default open stage</option>
              {openStages.map((stage) => (
                <option key={stage.id} value={stage.id}>
                  {stage.name}
                </option>
              ))}
            </Select>
          </div>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Reopening..." : "Reopen"}
          </Button>
        </form>
      </div>
    </Modal>
  );
}
