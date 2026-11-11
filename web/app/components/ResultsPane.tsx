"use client";

import type { Brief } from "@/app/types";
import { BriefCharts } from "./BriefCharts";
import { CoveragePill } from "./CoveragePill";
import { WorldMap } from "./WorldMap";

export function ResultsPane({ brief }: { brief: Brief }) {
  const charts = brief.charts ?? [];
  const map = brief.map;
  const hasMap = Boolean(map && map.points.length > 0);

  return (
    <div>
      <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
        <div className="min-w-0">
          <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
            Results
          </p>
          <p className="mt-1 truncate text-[13px] font-medium text-ink-secondary">
            {brief.query}
          </p>
        </div>
        <CoveragePill status={brief.coverage.status} />
      </div>

      <div className="divide-y divide-line">
        {charts.length > 0 ? (
          <BriefCharts charts={charts} layout="pane" />
        ) : null}
        {hasMap && map ? (
          <WorldMap data={map} stories={brief.stories} layout="pane" />
        ) : null}
        {charts.length === 0 && !hasMap ? (
          <div className="px-5 py-6">
            <p className="text-[13px] leading-5 text-ink-secondary">
              No charts or map were generated for this brief.
            </p>
            <p className="mt-1 text-[12px] leading-5 text-ink-muted">
              The facts, timeline, and sources are in the brief details on the
              left.
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
