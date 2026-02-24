"use client";

import type { OpportunityRead, PipelineStageRead } from "../../lib/types";
import { OpportunityCard } from "./OpportunityCard";

interface OpportunityPipelineBoardProps {
  stages: PipelineStageRead[];
  opportunities: OpportunityRead[];
  onOpenOpportunity: (opportunityId: string) => void;
  onMoveRequest: (payload: { opportunity: OpportunityRead; targetStage: PipelineStageRead }) => void;
}

function sumAmount(items: OpportunityRead[]) {
  return items.reduce((acc, row) => acc + row.amount, 0);
}

export function OpportunityPipelineBoard({
  stages,
  opportunities,
  onOpenOpportunity,
  onMoveRequest
}: OpportunityPipelineBoardProps) {
  const orderedStages = [...stages].sort((left, right) => left.position - right.position);
  const grouped = new Map<string, OpportunityRead[]>();
  orderedStages.forEach((stage) => grouped.set(stage.id, []));
  const otherRows: OpportunityRead[] = [];

  opportunities.forEach((opportunity) => {
    if (!grouped.has(opportunity.stage_id)) {
      otherRows.push(opportunity);
      return;
    }
    grouped.get(opportunity.stage_id)?.push(opportunity);
  });

  const columns = Array.from(grouped.entries()).map(([stageId, rows]) => {
    const stage = orderedStages.find((item) => item.id === stageId);
    if (!stage) {
      return null;
    }
    return { stage, rows };
  }).filter((value): value is { stage: PipelineStageRead; rows: OpportunityRead[] } => value !== null);

  return (
    <div className="grid gap-4 xl:grid-cols-4 lg:grid-cols-3 md:grid-cols-2">
      {columns.map(({ stage, rows }) => (
        <section key={stage.id} className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">{stage.name}</h3>
            <p className="text-xs text-slate-500">
              {rows.length} item(s) · Sum {sumAmount(rows).toFixed(2)}
            </p>
          </div>
          <div className="space-y-2">
            {rows.map((opportunity) => (
              <OpportunityCard
                key={opportunity.id}
                opportunity={opportunity}
                stageName={stage.name}
                availableStages={stages}
                onOpenDetail={() => onOpenOpportunity(opportunity.id)}
                onMoveRequest={(targetStage) => onMoveRequest({ opportunity, targetStage })}
              />
            ))}
            {rows.length === 0 ? <p className="text-xs text-slate-500">No opportunities.</p> : null}
          </div>
        </section>
      ))}
      {otherRows.length > 0 ? (
        <section className="space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">Other / Inactive</h3>
            <p className="text-xs text-slate-500">
              {otherRows.length} item(s) · Sum {sumAmount(otherRows).toFixed(2)}
            </p>
          </div>
          <div className="space-y-2">
            {otherRows.map((opportunity) => (
              <OpportunityCard
                key={opportunity.id}
                opportunity={opportunity}
                stageName="Other / Inactive"
                availableStages={orderedStages}
                onOpenDetail={() => onOpenOpportunity(opportunity.id)}
                onMoveRequest={(targetStage) => onMoveRequest({ opportunity, targetStage })}
              />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
