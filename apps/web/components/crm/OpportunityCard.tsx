"use client";

import type { OpportunityRead, PipelineStageRead } from "../../lib/types";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";

interface OpportunityCardProps {
  opportunity: OpportunityRead;
  stageName: string;
  accountLabel?: string;
  availableStages: PipelineStageRead[];
  onOpenDetail: () => void;
  onMoveRequest: (targetStage: PipelineStageRead) => void;
}

export function OpportunityCard({
  opportunity,
  stageName,
  accountLabel,
  availableStages,
  onOpenDetail,
  onMoveRequest
}: OpportunityCardProps) {
  const isClosed = Boolean(opportunity.closed_won_at || opportunity.closed_lost_at);

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <div>
        <button className="text-left text-sm font-semibold text-slate-900 hover:underline" onClick={onOpenDetail}>
          {opportunity.name}
        </button>
        <p className="text-xs text-slate-500">{accountLabel ? accountLabel : `Account ${opportunity.account_id}`}</p>
        {opportunity.revenue_quote_id || opportunity.revenue_order_id ? (
          <div className="mt-1">
            <Badge tone="warning">Revenue linked</Badge>
          </div>
        ) : null}
      </div>
      <div className="space-y-1 text-xs text-slate-600">
        <p>
          <span className="font-medium">Stage:</span> {stageName}
        </p>
        <p>
          <span className="font-medium">Amount:</span> {opportunity.amount} {opportunity.currency_code}
        </p>
        <p>
          <span className="font-medium">Expected close:</span> {opportunity.expected_close_date ?? "-"}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <select
          className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-xs"
          disabled={isClosed}
          defaultValue=""
          onChange={(event) => {
            const target = availableStages.find((item) => item.id === event.target.value);
            if (target) {
              onMoveRequest(target);
            }
            event.currentTarget.value = "";
          }}
        >
          <option value="">Move to...</option>
          {availableStages
            .filter((stage) => stage.id !== opportunity.stage_id)
            .map((stage) => (
              <option key={stage.id} value={stage.id}>
                {stage.name}
              </option>
            ))}
        </select>
        <Button variant="secondary" onClick={onOpenDetail}>
          Open
        </Button>
      </div>
    </div>
  );
}
