import type { StageEvent } from "../types";

function stateClass(state: string): string {
  if (state === "failed") return "text-red-700";
  if (state === "finished") return "text-green-700";
  return "text-zinc-500";
}

export function StageLog({
  events,
  loading,
}: {
  events: StageEvent[];
  loading: boolean;
}) {
  return (
    <section className="rounded border border-zinc-300 bg-white p-4">
      <h2 className="mb-2 text-sm font-semibold">Pipeline</h2>
      {events.length === 0 ? (
        <p className="text-sm text-zinc-500">
          {loading ? "Starting..." : "No stages yet."}
        </p>
      ) : (
        <ul className="space-y-1 font-mono text-xs">
          {events.map((event, index) => (
            <li key={`${event.stage}-${event.state}-${index}`}>
              <span className={stateClass(event.state)}>
                {event.stage}/{event.state}
              </span>
              {Object.keys(event.counts).length > 0
                ? ` ${JSON.stringify(event.counts)}`
                : ""}
              {event.message ? ` - ${event.message}` : ""}
              {event.elapsed_ms !== null ? ` (${event.elapsed_ms} ms)` : ""}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
