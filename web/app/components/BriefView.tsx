import type { Brief, Story } from "../types";

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function coverageClass(status: string): string {
  if (status === "complete") return "bg-green-100 text-green-800";
  if (status === "partial") return "bg-amber-100 text-amber-800";
  return "bg-red-100 text-red-800";
}

function textStatusClass(status: string): string {
  if (status === "ok") return "bg-green-100 text-green-800";
  if (status === "blocked" || status === "timeout") return "bg-red-100 text-red-800";
  return "bg-zinc-100 text-zinc-700";
}

function Link({ url }: { url: string }) {
  return (
    <a
      className="break-all underline"
      href={url}
      target="_blank"
      rel="noreferrer"
    >
      source
    </a>
  );
}

function StoryCard({ story }: { story: Story }) {
  return (
    <article className="rounded border border-zinc-300 bg-white p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-semibold">{story.headline}</h3>
        <span className="font-mono text-xs text-zinc-500">
          importance {story.importance.score.toFixed(1)} / credibility{" "}
          {story.credibility.score.toFixed(1)}
        </span>
      </div>
      <p className="mt-1 text-xs text-zinc-500">
        families: {story.families.join(", ") || "-"} | first seen{" "}
        {formatDate(story.first_seen)}
      </p>

      <ul className="mt-2 space-y-1 text-sm">
        {story.members.map((member, index) => (
          <li key={`${member.canonical_url}-${index}`}>
            <span
              className={`rounded px-1 py-0.5 font-mono text-xs ${textStatusClass(
                member.text_status,
              )}`}
            >
              {member.text_status}
            </span>{" "}
            <span className="font-medium">
              {member.candidate.publisher ?? "unknown"}
            </span>{" "}
            <span className="text-xs text-zinc-500">
              ({member.candidate.tier} | {member.candidate.backend} | relevance{" "}
              {member.candidate.relevance?.toFixed(2) ?? "-"})
            </span>{" "}
            <Link url={member.canonical_url} />
            {member.word_count !== null ? (
              <span className="text-xs text-zinc-500">
                {" "}
                - {member.word_count} words
              </span>
            ) : null}
          </li>
        ))}
      </ul>

      {story.facts.length > 0 ? (
        <ul className="mt-2 space-y-1 border-t border-zinc-200 pt-2 text-sm">
          {story.facts.map((fact, index) => (
            <li key={`${fact.source_url}-${index}`}>
              <span className="font-medium">{fact.value ?? "fact"}:</span>{" "}
              {fact.claim}{" "}
              <Link url={fact.source_url} />
              {fact.quote ? (
                <q className="text-zinc-600"> {fact.quote}</q>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

export function BriefView({ brief }: { brief: Brief }) {
  return (
    <article className="space-y-5">
      <header className="rounded border border-zinc-300 bg-white p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h1 className="text-xl font-semibold">{brief.query}</h1>
          <span
            className={`rounded px-2 py-0.5 font-mono text-xs ${coverageClass(
              brief.coverage.status,
            )}`}
          >
            coverage: {brief.coverage.status}
          </span>
        </div>
        <p className="mt-1 font-mono text-xs text-zinc-500">
          class: {brief.query_class} | generated: {formatDate(brief.generated_at)}
        </p>
      </header>

      <section className="rounded border border-zinc-300 bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold">Answer</h2>
        <p className="text-sm leading-6">{brief.answer}</p>
      </section>

      <section className="rounded border border-zinc-300 bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold">
          Key facts ({brief.key_facts.length})
        </h2>
        {brief.key_facts.length === 0 ? (
          <p className="text-sm text-zinc-500">No structured facts.</p>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-zinc-300 text-left">
                <th className="py-1 pr-3">Value</th>
                <th className="py-1 pr-3">Meaning</th>
                <th className="py-1 pr-3">Published</th>
                <th className="py-1">Source</th>
              </tr>
            </thead>
            <tbody>
              {brief.key_facts.map((fact, index) => (
                <tr key={`${fact.source_url}-${index}`} className="border-b border-zinc-100">
                  <td className="py-1 pr-3 font-mono">{fact.value}</td>
                  <td className="py-1 pr-3">{fact.meaning}</td>
                  <td className="py-1 pr-3 text-xs text-zinc-500">
                    {formatDate(fact.published_at)}
                  </td>
                  <td className="py-1">
                    <Link url={fact.source_url} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="rounded border border-zinc-300 bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold">
          Timeline ({brief.timeline.length})
        </h2>
        {brief.timeline.length === 0 ? (
          <p className="text-sm text-zinc-500">No timeline entries.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {brief.timeline.map((entry, index) => (
              <li key={`${entry.source_url}-${index}`}>
                <span className="font-mono text-xs text-zinc-500">
                  {formatDate(entry.at)}
                </span>{" "}
                {entry.what} <Link url={entry.source_url} />
              </li>
            ))}
          </ul>
        )}
      </section>

      {brief.disagreements.length > 0 ? (
        <section className="rounded border border-zinc-300 bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold">Disagreements</h2>
          {brief.disagreements.map((item, index) => (
            <div key={`${item.topic}-${index}`} className="mb-3 last:mb-0">
              <p className="font-medium">{item.topic}</p>
              <ul className="ml-4 list-disc text-sm">
                {item.positions.map((position, positionIndex) => (
                  <li key={`${position.source_url}-${positionIndex}`}>
                    {position.claim} <Link url={position.source_url} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      ) : null}

      {brief.thin_sourcing.length > 0 ? (
        <section className="rounded border border-amber-300 bg-amber-50 p-4">
          <h2 className="mb-2 text-sm font-semibold">Thin sourcing</h2>
          <ul className="ml-4 list-disc text-sm">
            {brief.thin_sourcing.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-sm font-semibold">Stories ({brief.stories.length})</h2>
        {brief.stories.map((story) => (
          <StoryCard key={story.id} story={story} />
        ))}
      </section>

      <section className="rounded border border-zinc-300 bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold">Coverage</h2>
        <p className="font-mono text-xs">
          status: {brief.coverage.status}
        </p>

        <h3 className="mt-3 text-xs font-semibold">Backends</h3>
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-zinc-300 text-left">
              <th className="py-1 pr-3">Backend</th>
              <th className="py-1 pr-3">Attempts</th>
              <th className="py-1 pr-3">Returned</th>
              <th className="py-1">Kept</th>
            </tr>
          </thead>
          <tbody>
            {brief.coverage.backends.map((backend, index) => (
              <tr key={`${backend.backend}-${index}`} className="border-b border-zinc-100">
                <td className="py-1 pr-3 font-mono">{backend.backend}</td>
                <td className="py-1 pr-3">{backend.attempted}</td>
                <td className="py-1 pr-3">{backend.returned}</td>
                <td className="py-1">{backend.kept}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h3 className="mt-3 text-xs font-semibold">Attempts</h3>
        <ul className="space-y-1 font-mono text-xs">
          {brief.coverage.attempts.map((attempt, index) => (
            <li key={`${attempt.backend}-${index}`}>
              {attempt.backend}: {attempt.attempt}, returned {attempt.returned},{" "}
              {attempt.elapsed_ms} ms
              {attempt.detail ? ` - ${attempt.detail}` : ""}
            </li>
          ))}
        </ul>

        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div>
            <h3 className="text-xs font-semibold">Drops</h3>
            <p className="font-mono text-xs">
              {Object.entries(brief.coverage.drops)
                .map(([key, value]) => `${key}=${value}`)
                .join(", ") || "-"}
            </p>
          </div>
          <div>
            <h3 className="text-xs font-semibold">Text status</h3>
            <p className="font-mono text-xs">
              {Object.entries(brief.coverage.text_status)
                .map(([key, value]) => `${key}=${value}`)
                .join(", ") || "-"}
            </p>
          </div>
        </div>

        <div className="mt-3">
          <h3 className="text-xs font-semibold">Timings</h3>
          <p className="font-mono text-xs">
            {Object.entries(brief.coverage.timings_ms)
              .map(([key, value]) => `${key}=${value}ms`)
              .join(", ") || "-"}
          </p>
        </div>

        {brief.coverage.notes.length > 0 ? (
          <div className="mt-3">
            <h3 className="text-xs font-semibold">Notes</h3>
            <ul className="ml-4 list-disc text-xs">
              {brief.coverage.notes.map((note, index) => (
                <li key={index}>{note}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
    </article>
  );
}
