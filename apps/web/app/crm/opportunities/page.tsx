"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { getDefaultPipeline, getErrorMessage, listOpportunities } from "../../../lib/api";
import { queryKeys } from "../../../lib/queryKeys";
import type { OpportunityRead, PipelineStageRead } from "../../../lib/types";
import { OpportunityChangeStageModal } from "../../../components/crm/OpportunityChangeStageModal";
import { OpportunityPipelineBoard } from "../../../components/crm/OpportunityPipelineBoard";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Select } from "../../../components/ui/select";
import { Spinner } from "../../../components/ui/spinner";
import { Table, Td, Th } from "../../../components/ui/table";

export default function OpportunitiesPage() {
  const router = useRouter();
  const [view, setView] = useState<"pipeline" | "list">("pipeline");
  const [stageFilter, setStageFilter] = useState("");
  const [ownerFilter, setOwnerFilter] = useState("");
  const [forecastFilter, setForecastFilter] = useState("");
  const [expectedFrom, setExpectedFrom] = useState("");
  const [expectedTo, setExpectedTo] = useState("");

  const [selectedMoveOpportunity, setSelectedMoveOpportunity] = useState<OpportunityRead | null>(null);
  const [selectedTargetStage, setSelectedTargetStage] = useState<PipelineStageRead | null>(null);

  const filters = useMemo(
    () => ({
      stage_id: stageFilter || undefined,
      owner_user_id: ownerFilter || undefined,
      forecast_category: forecastFilter || undefined,
      expected_close_from: expectedFrom || undefined,
      expected_close_to: expectedTo || undefined,
      limit: 200
    }),
    [stageFilter, ownerFilter, forecastFilter, expectedFrom, expectedTo]
  );

  const opportunitiesQuery = useQuery({
    queryKey: queryKeys.opportunities(filters),
    queryFn: () => listOpportunities(filters)
  });

  const defaultPipelineQuery = useQuery({
    queryKey: queryKeys.pipelineDefault(),
    queryFn: () => getDefaultPipeline()
  });

  const opportunities = opportunitiesQuery.data ?? [];
  const stages = useMemo(
    () => [...(defaultPipelineQuery.data?.stages ?? [])].sort((left, right) => left.position - right.position),
    [defaultPipelineQuery.data?.stages]
  );
  const stageNameById = useMemo(() => {
    const mapping = new Map<string, string>();
    stages.forEach((stage) => {
      mapping.set(stage.id, stage.name);
    });
    return mapping;
  }, [stages]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Opportunities</h1>
          <p className="text-sm text-slate-500">Pipeline and lifecycle management.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant={view === "pipeline" ? "primary" : "secondary"} onClick={() => setView("pipeline")}>
            Pipeline
          </Button>
          <Button variant={view === "list" ? "primary" : "secondary"} onClick={() => setView("list")}>
            List
          </Button>
        </div>
      </div>

      <div className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 md:grid-cols-5">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Stage ID</label>
          <Input value={stageFilter} onChange={(event) => setStageFilter(event.target.value)} placeholder="UUID" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Owner</label>
          <Input value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value)} placeholder="UUID" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Forecast</label>
          <Select value={forecastFilter} onChange={(event) => setForecastFilter(event.target.value)}>
            <option value="">Any</option>
            <option value="Pipeline">Pipeline</option>
            <option value="Commit">Commit</option>
            <option value="Closed">Closed</option>
          </Select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Expected close from</label>
          <Input type="date" value={expectedFrom} onChange={(event) => setExpectedFrom(event.target.value)} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">Expected close to</label>
          <Input type="date" value={expectedTo} onChange={(event) => setExpectedTo(event.target.value)} />
        </div>
      </div>

      {opportunitiesQuery.isLoading || defaultPipelineQuery.isLoading ? (
        <Spinner />
      ) : opportunitiesQuery.isError || defaultPipelineQuery.isError ? (
        <p className="text-sm text-red-600">{getErrorMessage(opportunitiesQuery.error ?? defaultPipelineQuery.error)}</p>
      ) : view === "pipeline" ? (
        <OpportunityPipelineBoard
          stages={stages}
          opportunities={opportunities}
          onOpenOpportunity={(opportunityId) => router.push(`/crm/opportunities/${opportunityId}`)}
          onMoveRequest={({ opportunity, targetStage }) => {
            setSelectedMoveOpportunity(opportunity);
            setSelectedTargetStage(targetStage);
          }}
        />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Name</Th>
              <Th>Stage</Th>
              <Th>Amount</Th>
              <Th>Expected close</Th>
              <Th>Status</Th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {opportunities.map((row) => {
              const status = row.closed_won_at ? "ClosedWon" : row.closed_lost_at ? "ClosedLost" : "Open";
              return (
                <tr key={row.id}>
                  <Td>
                    <button className="font-medium hover:underline" onClick={() => router.push(`/crm/opportunities/${row.id}`)}>
                      {row.name}
                    </button>
                  </Td>
                  <Td>{stageNameById.get(row.stage_id) ?? "Other / Inactive"}</Td>
                  <Td>{`${row.amount} ${row.currency_code}`}</Td>
                  <Td>{row.expected_close_date ?? "-"}</Td>
                  <Td>
                    <Badge tone={status === "ClosedWon" ? "success" : status === "ClosedLost" ? "danger" : "default"}>
                      {status}
                    </Badge>
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      )}

      {selectedMoveOpportunity && selectedTargetStage ? (
        <OpportunityChangeStageModal
          open={Boolean(selectedMoveOpportunity)}
          opportunity={selectedMoveOpportunity}
          stages={stages}
          defaultStageId={selectedTargetStage.id}
          onClose={() => {
            setSelectedMoveOpportunity(null);
            setSelectedTargetStage(null);
          }}
        />
      ) : null}
    </div>
  );
}
