import type { Brief } from "@/app/types";
import { BriefCharts } from "./BriefCharts";
import {
  CoverageDetails,
  Disagreements,
  KeyFacts,
  Section,
  SectionLabel,
  Stories,
  ThinSourcing,
  Timeline,
  formatDate,
} from "./BriefSections";
import { WorldMap } from "./WorldMap";

export function BriefView({ brief }: { brief: Brief }) {
  const charts = brief.charts ?? [];
  const map = brief.map;

  return (
    <article className="rounded-card border border-line bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-6 py-4 sm:px-8">
        <span className="font-mono text-[11px] text-ink-muted">
          Generated {formatDate(brief.generated_at)}
        </span>
        <span className="font-mono text-[11px] text-ink-muted">
          {brief.query_class} query
        </span>
      </div>

      <div className="divide-y divide-line">
        <Section>
          <SectionLabel>Answer</SectionLabel>
          {brief.answer ? (
            <p className="mt-3 max-w-[68ch] whitespace-pre-wrap text-[17px] leading-[1.65] text-ink">
              {brief.answer}
            </p>
          ) : (
            <p className="mt-3 text-[13px] leading-5 text-ink-muted">
              No answer was generated.
            </p>
          )}
        </Section>

        {charts.length > 0 ? <BriefCharts charts={charts} /> : null}
        {map && map.points.length > 0 ? (
          <WorldMap key={brief.query} data={map} stories={brief.stories} />
        ) : null}
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
    </article>
  );
}
