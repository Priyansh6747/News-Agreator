"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import { BriefView } from "./components/BriefView";
import { StageLog } from "./components/StageLog";
import type { Brief, StageEvent } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8012";

const EXAMPLES = ["gold prices", "ukraine war", "nvidia vs amd"];

export default function Home() {
  const [query, setQuery] = useState("gold prices");
  const [brief, setBrief] = useState<Brief | null>(null);
  const [events, setEvents] = useState<StageEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState<number | null>(null);

  function handleEventChunk(chunk: string) {
    let eventName = "message";
    const dataLines: string[] = [];

    for (const line of chunk.split(/\r?\n/)) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    }

    if (dataLines.length === 0) return;
    const payload = JSON.parse(dataLines.join("\n")) as unknown;

    if (eventName === "stage") {
      setEvents((previous) => [...previous, payload as StageEvent]);
    } else if (eventName === "brief") {
      setBrief(payload as Brief);
    } else if (eventName === "error") {
      const errorPayload = payload as { message?: string };
      setError(errorPayload.message ?? "Pipeline failed.");
    }
  }

  async function readStream(response: Response) {
    if (!response.body) throw new Error("No response body");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split(/\r?\n\r?\n/);
      buffer = chunks.pop() ?? "";
      for (const chunk of chunks) handleEventChunk(chunk);
    }

    if (buffer.trim()) handleEventChunk(buffer);
  }

  async function fetchBrief(cleaned: string): Promise<Brief> {
    const response = await fetch(`${API_BASE}/api/v1/brief`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query: cleaned }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return (await response.json()) as Brief;
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleaned = query.trim();
    if (cleaned.length < 2) {
      setError("Enter a query.");
      return;
    }

    setLoading(true);
    setError(null);
    setBrief(null);
    setEvents([]);
    setElapsed(null);
    const started = Date.now();

    try {
      const response = await fetch(`${API_BASE}/api/v1/brief/stream`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ query: cleaned }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await readStream(response);
    } catch {
      try {
        setBrief(await fetchBrief(cleaned));
      } catch (fallbackError) {
        const message =
          fallbackError instanceof Error ? fallbackError.message : "unknown error";
        setError(
          `Could not reach the API at ${API_BASE} (${message}). Is the FastAPI server running?`,
        );
      }
    } finally {
      setElapsed(Date.now() - started);
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-5xl space-y-5 p-4 sm:p-6">
      <header>
        <h1 className="text-2xl font-semibold">NewsAgreator</h1>
        <p className="text-sm text-zinc-600">
          Structured news briefs from free sources, with coverage.
        </p>
      </header>

      <form
        className="space-y-2 rounded border border-zinc-300 bg-white p-4"
        onSubmit={submit}
      >
        <label className="text-sm font-medium" htmlFor="query">
          Query
        </label>
        <div className="flex gap-2">
          <input
            id="query"
            className="w-full rounded border border-zinc-300 px-3 py-2 text-sm"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            disabled={loading}
            placeholder="e.g. gold prices"
          />
          <button
            className="rounded bg-zinc-900 px-4 py-2 text-sm text-white disabled:opacity-50"
            type="submit"
            disabled={loading}
          >
            {loading ? "Running..." : "Run"}
          </button>
        </div>
        <div className="flex flex-wrap gap-2 text-xs">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              className="rounded border border-zinc-300 px-2 py-1 hover:bg-zinc-100 disabled:opacity-50"
              onClick={() => setQuery(example)}
              disabled={loading}
            >
              {example}
            </button>
          ))}
        </div>
      </form>

      <p className="font-mono text-xs text-zinc-500">
        API: {API_BASE} - queries can take 30-90 seconds.
      </p>

      {error ? (
        <p className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      ) : null}

      {loading || events.length > 0 ? (
        <StageLog events={events} loading={loading} />
      ) : null}

      {elapsed !== null ? (
        <p className="font-mono text-xs text-zinc-500">
          Finished in {(elapsed / 1000).toFixed(1)}s.
        </p>
      ) : null}

      {brief ? <BriefView brief={brief} /> : null}
    </main>
  );
}
