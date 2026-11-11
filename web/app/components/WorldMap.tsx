"use client";

import { useState } from "react";
import { geoNaturalEarth1, geoPath } from "d3-geo";
import type { FeatureCollection, Geometry } from "geojson";
import { feature } from "topojson-client";
import type { Topology } from "topojson-specification";
import worldAtlas from "world-atlas/countries-110m.json";

import type { MapData, Story } from "@/app/types";

const WIDTH = 960;
const HEIGHT = 480;

const topology = worldAtlas as unknown as Topology;
const countries = feature(
  topology,
  topology.objects.countries,
) as unknown as FeatureCollection<Geometry>;
const projection = geoNaturalEarth1().fitExtent(
  [
    [8, 8],
    [WIDTH - 8, HEIGHT - 8],
  ],
  { type: "Sphere" },
);
const path = geoPath(projection);
const countryPaths = countries.features.map((country, index) => ({
  key: index,
  d: path(country) ?? "",
}));

function storyCount(count: number): string {
  return `${count} ${count === 1 ? "story" : "stories"}`;
}

export function WorldMap({
  data,
  stories,
  layout = "default",
}: {
  data: MapData;
  stories: Story[];
  layout?: "default" | "pane";
}) {
  const [selected, setSelected] = useState<string | null>(
    data.points[0]?.country_code ?? null,
  );
  const selectedPoint =
    data.points.find((point) => point.country_code === selected) ?? null;
  const selectedStories = selectedPoint
    ? stories.filter((story) => selectedPoint.story_ids.includes(story.id))
    : [];

  return (
    <section className={layout === "pane" ? "px-5 py-5" : "px-6 py-6 sm:px-8 sm:py-7"}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
          Where the coverage points
        </h2>
        <p className="font-mono text-[11px] text-ink-muted">
          Approximate countries named in the coverage, not event coordinates
        </p>
      </div>

      <div
        className={`mt-5 grid gap-4 ${
          layout === "pane"
            ? "grid-cols-1 xl:grid-cols-[1.6fr_1fr]"
            : "lg:grid-cols-[1.6fr_1fr]"
        }`}
      >
        <div className="min-w-0 overflow-hidden rounded-lg border border-line bg-canvas-soft p-2">
          <svg
            aria-hidden="true"
            className="block h-auto w-full"
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          >
            <rect
              fill="var(--canvas-soft)"
              height={HEIGHT}
              rx={8}
              width={WIDTH}
            />
            {countryPaths.map((country) => (
              <path
                key={country.key}
                d={country.d}
                fill="var(--surface-raised)"
                stroke="var(--border)"
                strokeWidth={0.6}
              />
            ))}
            {data.points.map((point) => {
              const coordinates = projection([point.lon, point.lat]);
              if (!coordinates) return null;
              const [x, y] = coordinates;
              const radius = 4 + Math.min(point.story_ids.length, 4);
              const isSelected = point.country_code === selected;
              return (
                <g
                  key={point.country_code}
                  className="cursor-pointer"
                  onClick={() => setSelected(point.country_code)}
                >
                  <circle
                    cx={x}
                    cy={y}
                    fill="var(--accent-soft)"
                    r={radius + 5}
                  />
                  <circle
                    cx={x}
                    cy={y}
                    fill="var(--accent)"
                    r={radius}
                    stroke="var(--canvas)"
                    strokeWidth={1.5}
                  />
                  {isSelected ? (
                    <circle
                      cx={x}
                      cy={y}
                      fill="none"
                      r={radius + 3}
                      stroke="var(--text)"
                      strokeWidth={1.2}
                    />
                  ) : null}
                  <title>
                    {point.label}: {storyCount(point.story_ids.length)}
                  </title>
                </g>
              );
            })}
          </svg>
        </div>

        <div className="min-w-0">
          <ul className="space-y-2">
            {data.points.map((point) => {
              const isSelected = point.country_code === selected;
              return (
                <li key={point.country_code}>
                  <button
                    type="button"
                    onClick={() => setSelected(point.country_code)}
                    className={`w-full rounded-lg border px-3 py-2.5 text-left transition-colors duration-150 ${
                      isSelected
                        ? "border-line-strong bg-surface-raised"
                        : "border-line bg-surface hover:bg-surface-raised"
                    }`}
                  >
                    <span className="flex items-baseline justify-between gap-3">
                      <span className="truncate text-[13px] font-medium text-ink">
                        {point.label}
                      </span>
                      <span className="shrink-0 font-mono text-[10.5px] text-ink-muted">
                        {storyCount(point.story_ids.length)}
                      </span>
                    </span>
                    {point.summary ? (
                      <span className="mt-1 block text-[11px] leading-4 text-ink-muted">
                        {point.summary}
                      </span>
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>

          {selectedPoint ? (
            <div className="mt-4 border-t border-line pt-3">
              <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-muted">
                {selectedPoint.country}
              </p>
              {selectedStories.length > 0 ? (
                <ul className="mt-2 space-y-3">
                  {selectedStories.map((story) => {
                    const member = story.members[0];
                    return (
                      <li key={story.id}>
                        <p className="text-[13px] leading-5 text-ink">
                          {story.headline}
                        </p>
                        <p className="mt-0.5 font-mono text-[10.5px] text-ink-muted">
                          {member?.candidate.publisher ?? "unknown"} ·{" "}
                          <a
                            href={member?.canonical_url}
                            target="_blank"
                            rel="noreferrer"
                            className="underline decoration-line-strong underline-offset-[3px] transition-colors hover:text-ink"
                          >
                            source
                          </a>
                        </p>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="mt-2 text-[12px] text-ink-muted">
                  No linked stories.
                </p>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
