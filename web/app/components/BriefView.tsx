import type { ReactNode } from "react";

import type {
  BackendCoverage,
  Brief,
  Coverage,
  Disagreement,
  FactRow,
  Story,
  TimelineEntry,
} from "@/app/types";
import { BriefCharts } from "./BriefCharts";
import { ChevronDownIcon, WarningIcon } from "./Icons";
import { WorldMap } from "./WorldMap";

function formatDate(value: string | null | undefined): string {
  if (!value) return "unknown date";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <h2 className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
      {children}
    </h2>
  );
}

function SourceLink({ url }: { url: string }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      className="text-ink-muted underline decoration-line-strong underline-offset-[3px] transition-colors hover:text-ink focus-visible:text-ink"
    >
      source
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}

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
            <Empty>No answer was generated.</Empty>
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

function Section({ children }: { children: ReactNode }) {
  return <section className="px-6 py-6 sm:px-8 sm:py-7">{children}</section>;
}

function Empty({ children }: { children: ReactNode }) {
  return <p className="mt-3 text-[13px] leading-5 text-ink-muted">{children}</p>;
}

function KeyFacts({ facts }: { facts: FactRow[] }) {
  return (
    <Section>
      <div className="flex items-baseline justify-between gap-4">
        <SectionLabel>Key facts</SectionLabel>
        <span className="font-mono text-[11px] text-ink-muted">
          {facts.length}
        </span>
      </div>

      {facts.length === 0 ? (
        <Empty>No structured facts were extracted.</Empty>
      ) : (
        <dl className="mt-5 divide-y divide-line">
          {facts.map((fact, index) => (
            <div
              key={`${fact.source_url}-${index}`}
              className="grid gap-2 py-4 first:pt-0 last:pb-0 sm:grid-cols-[minmax(150px,0.4fr)_1fr] sm:gap-6"
            >
              <dt className="break-words font-mono text-[13px] leading-6 text-accent-strong">
                {fact.value || "fact"}
              </dt>
              <dd>
                <p className="text-[14px] leading-6 text-ink">{fact.meaning}</p>
                <p className="mt-1 font-mono text-[11px] text-ink-muted">
                  {formatDate(fact.published_at)} ·{" "}
                  <SourceLink url={fact.source_url} />
                </p>
              </dd>
            </div>
          ))}
        </dl>
      )}
    </Section>
  );
}

function Timeline({ entries }: { entries: TimelineEntry[] }) {
  return (
    <Section>
      <div className="flex items-baseline justify-between gap-4">
        <SectionLabel>Timeline</SectionLabel>
        <span className="font-mono text-[11px] text-ink-muted">
          {entries.length}
        </span>
      </div>

      {entries.length === 0 ? (
        <Empty>No timeline entries.</Empty>
      ) : (
        <ol className="mt-5 space-y-5 border-l border-line pl-5">
          {entries.map((entry, index) => (
            <li
              key={`${entry.source_url}-${index}`}
              className="relative min-w-0"
            >
              <span
                aria-hidden="true"
                className="absolute -left-[23px] top-2 h-1.5 w-1.5 rounded-full bg-accent"
              />
              <p className="font-mono text-[11px] text-ink-muted">
                {formatDate(entry.at)}
              </p>
              <p className="mt-1 text-[14px] leading-6 text-ink">
                {entry.what} <SourceLink url={entry.source_url} />
              </p>
            </li>
          ))}
        </ol>
      )}
    </Section>
  );
}

function Disagreements({ items }: { items: Disagreement[] }) {
  return (
    <Section>
      <SectionLabel>Disagreements</SectionLabel>
      <div className="mt-5 space-y-6">
        {items.map((item, index) => (
          <div key={`${item.topic}-${index}`}>
            <h3 className="text-[15px] font-semibold text-ink">{item.topic}</h3>
            <ul className="mt-2 space-y-2">
              {item.positions.map((position, positionIndex) => (
                <li
                  key={`${position.source_url}-${positionIndex}`}
                  className="flex gap-2 text-[14px] leading-6 text-ink-secondary"
                >
                  <span
                    aria-hidden="true"
                    className="mt-[11px] h-1 w-1 shrink-0 rounded-full bg-ink-faint"
                  />
                  <span>
                    {position.claim}{" "}
                    <SourceLink url={position.source_url} />
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </Section>
  );
}

function ThinSourcing({ notes }: { notes: string[] }) {
  return (
    <Section>
      <div className="rounded-lg border border-warning/25 bg-warning-soft p-4">
        <div className="flex items-center gap-2 text-[12px] font-semibold text-warning">
          <WarningIcon />
          Thin sourcing
        </div>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-[13px] leading-5 text-warning">
          {notes.map((note, index) => (
            <li key={index}>{note}</li>
          ))}
        </ul>
      </div>
    </Section>
  );
}

function Stories({ stories }: { stories: Story[] }) {
  return (
    <Section>
      <div className="flex items-baseline justify-between gap-4">
        <SectionLabel>Stories</SectionLabel>
        <span className="font-mono text-[11px] text-ink-muted">
          {stories.length}
        </span>
      </div>

      {stories.length === 0 ? (
        <Empty>No stories were selected.</Empty>
      ) : (
        <div className="mt-3 divide-y divide-line">
          {stories.map((story) => (
            <StoryRow key={story.id} story={story} />
          ))}
        </div>
      )}
    </Section>
  );
}

function StoryRow({ story }: { story: Story }) {
  return (
    <details className="group">
      <summary className="flex cursor-pointer list-none items-start justify-between gap-4 py-4 [&::-webkit-details-marker]:hidden">
        <span className="min-w-0">
          <span className="block text-[15px] font-semibold leading-6 text-ink">
            {story.headline}
          </span>
          <span className="mt-1 block font-mono text-[11px] text-ink-muted">
            {story.members.length}{" "}
            {story.members.length === 1 ? "source" : "sources"} · importance{" "}
            {story.importance.score.toFixed(1)} · credibility{" "}
            {story.credibility.score.toFixed(1)}
            {story.facts.length > 0 ? ` · ${story.facts.length} facts` : ""}
          </span>
        </span>
        <ChevronDownIcon className="mt-1 shrink-0 text-ink-muted transition-transform duration-200 group-open:rotate-180" />
      </summary>

      <div className="pb-5">
        <ul className="space-y-2.5">
          {story.members.map((member, index) => (
            <li
              key={`${member.canonical_url}-${index}`}
              className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-[13px] leading-5"
            >
              <span className="font-medium text-ink-secondary">
                {member.candidate.publisher ?? "unknown"}
              </span>
              <span
                className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
                  member.text_status === "ok"
                    ? "bg-success-soft text-success"
                    : member.text_status === "blocked" ||
                        member.text_status === "timeout"
                      ? "bg-error-soft text-error"
                      : "bg-surface-raised text-ink-muted"
                }`}
              >
                {member.text_status}
              </span>
              <span className="font-mono text-[10.5px] text-ink-muted">
                {member.candidate.tier} · {member.candidate.backend} ·
                relevance {member.candidate.relevance?.toFixed(2) ?? "-"}
                {member.word_count !== null
                  ? ` · ${member.word_count} words`
                  : ""}
              </span>
              <SourceLink url={member.canonical_url} />
            </li>
          ))}
        </ul>

        {story.facts.length > 0 ? (
          <ul className="mt-4 space-y-2">
            {story.facts.map((fact, index) => (
              <li
                key={`${fact.source_url}-${index}`}
                className="text-[13px] leading-5 text-ink-secondary"
              >
                <span className="font-mono text-[11px] text-accent-strong">
                  {fact.value ?? "fact"}
                </span>{" "}
                {fact.claim} <SourceLink url={fact.source_url} />
                {fact.quote ? (
                  <q className="text-ink-muted"> {fact.quote}</q>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}

        <p className="mt-3 font-mono text-[10.5px] text-ink-muted">
          Families: {story.families.join(", ") || "-"}
        </p>
      </div>
    </details>
  );
}

function CoverageDetails({ coverage }: { coverage: Coverage }) {
  return (
    <details className="group">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-6 py-6 sm:px-8 sm:py-7 [&::-webkit-details-marker]:hidden">
        <span className="min-w-0">
          <span className="block font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
            Coverage
          </span>
          <span className="mt-1 block text-[12px] leading-5 text-ink-muted">
            {coverage.backends.length} backends · {coverage.attempts.length}{" "}
            attempts · status {coverage.status}
          </span>
        </span>
        <ChevronDownIcon className="shrink-0 text-ink-muted transition-transform duration-200 group-open:rotate-180" />
      </summary>

      <div className="space-y-6 px-6 pb-7 sm:px-8">
        <CoverageTable backends={coverage.backends} />

        <div className="grid gap-6 sm:grid-cols-2">
          <div>
            <h3 className="font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
              Attempts
            </h3>
            {coverage.attempts.length === 0 ? (
              <p className="mt-2 text-[12px] text-ink-muted">
                No backend attempts recorded.
              </p>
            ) : (
              <ul className="mt-2 space-y-1.5 font-mono text-[11px] leading-5 text-ink-muted">
                {coverage.attempts.map((attempt, index) => (
                  <li key={`${attempt.backend}-${index}`}>
                    {attempt.backend}: {attempt.attempt} · {attempt.returned}{" "}
                    returned · {attempt.elapsed_ms}ms
                    {attempt.detail ? ` · ${attempt.detail}` : ""}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <h3 className="font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
              Drops
            </h3>
            <p className="mt-2 font-mono text-[11px] leading-5 text-ink-muted">
              {formatNumberMap(coverage.drops)}
            </p>

            <h3 className="mt-5 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
              Text status
            </h3>
            <p className="mt-2 font-mono text-[11px] leading-5 text-ink-muted">
              {formatNumberMap(coverage.text_status)}
            </p>
          </div>
        </div>

        <div>
          <h3 className="font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
            Timings
          </h3>
          <p className="mt-2 font-mono text-[11px] leading-5 text-ink-muted">
            {formatTimings(coverage.timings_ms)}
          </p>
        </div>

        {coverage.notes.length > 0 ? (
          <div>
            <h3 className="font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
              Notes
            </h3>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-[12px] leading-5 text-ink-muted">
              {coverage.notes.map((note, index) => (
                <li key={index}>{note}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </details>
  );
}

function CoverageTable({ backends }: { backends: BackendCoverage[] }) {
  if (backends.length === 0) {
    return (
      <p className="text-[12px] text-ink-muted">
        No backend coverage was recorded.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] border-collapse text-left">
        <thead>
          <tr className="border-b border-line">
            <th
              scope="col"
              className="pb-2 pr-4 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted"
            >
              Backend
            </th>
            <th
              scope="col"
              className="pb-2 pr-4 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted"
            >
              Attempts
            </th>
            <th
              scope="col"
              className="pb-2 pr-4 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted"
            >
              Returned
            </th>
            <th
              scope="col"
              className="pb-2 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-muted"
            >
              Kept
            </th>
          </tr>
        </thead>
        <tbody>
          {backends.map((backend, index) => (
            <tr
              key={`${backend.backend}-${index}`}
              className="border-b border-line last:border-0"
            >
              <td className="py-2 pr-4 font-mono text-[12px] text-ink-secondary">
                {backend.backend}
              </td>
              <td className="py-2 pr-4 font-mono text-[12px] text-ink-muted">
                {backend.attempted}
              </td>
              <td className="py-2 pr-4 font-mono text-[12px] text-ink-muted">
                {backend.returned}
              </td>
              <td className="py-2 font-mono text-[12px] text-ink-muted">
                {backend.kept}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatNumberMap(values: Record<string, number>): string {
  const entries = Object.entries(values);
  if (entries.length === 0) return "-";
  return entries.map(([key, value]) => `${key} ${value}`).join(" · ");
}

function formatTimings(values: Record<string, number>): string {
  const entries = Object.entries(values);
  if (entries.length === 0) return "-";
  return entries.map(([key, value]) => `${key} ${value}ms`).join(" · ");
}
