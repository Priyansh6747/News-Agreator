"use client";

import type { Brief } from "@/app/types";
import {
  CoverageDetails,
  Disagreements,
  KeyFacts,
  Stories,
  ThinSourcing,
  Timeline,
} from "./BriefSections";
import { ChevronDownIcon } from "./Icons";

export function BriefDetails({ brief }: { brief: Brief }) {
  return (
    <details className="group mt-4 rounded-card border border-line bg-surface">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3 [&::-webkit-details-marker]:hidden">
        <span className="min-w-0">
          <span className="block font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
            Brief details
          </span>
          <span className="mt-1 block text-[12px] leading-5 text-ink-muted">
            {brief.key_facts.length} facts · {brief.timeline.length} timeline ·{" "}
            {brief.stories.length} stories · coverage {brief.coverage.status}
          </span>
        </span>
        <ChevronDownIcon className="shrink-0 text-ink-muted transition-transform duration-200 group-open:rotate-180" />
      </summary>
      <div className="divide-y divide-line border-t border-line">
        <KeyFacts facts={brief.key_facts} />
        <Timeline entries={brief.timeline} />
        {brief.disagreements.length > 0 ? (
          <Disagreements items={brief.disagreements} />
        ) : null}
        {brief.thin_sourcing.length > 0 ? (
          <ThinSourcing notes={brief.thin_sourcing} />
        ) : null}
        <Stories stories={brief.stories} />
        <CoverageDetails coverage={brief.coverage} />
      </div>
    </details>
  );
}
