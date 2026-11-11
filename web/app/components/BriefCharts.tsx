"use client";

import { Component, type ReactNode } from "react";
import { useReducedMotion } from "motion/react";

import type { ChartSpec } from "@/app/types";
import { Bar } from "@/components/charts/bar";
import { BarChart } from "@/components/charts/bar-chart";
import { BarXAxis } from "@/components/charts/bar-x-axis";
import { Grid } from "@/components/charts/grid";
import { Line } from "@/components/charts/line";
import { LineChart } from "@/components/charts/line-chart";
import { PieChart } from "@/components/charts/pie-chart";
import { PieSlice } from "@/components/charts/pie-slice";
import { ChartTooltip } from "@/components/charts/tooltip";
import { XAxis } from "@/components/charts/x-axis";
import { formatDuration } from "@/lib/stream-state";

const PALETTE = [
  "var(--accent)",
  "var(--iris-cyan)",
  "var(--iris-lilac)",
  "var(--iris-pink)",
  "var(--iris-peach)",
];

function formatValue(value: number, spec: ChartSpec): string {
  if (spec.value_format === "duration") {
    return formatDuration(value);
  }
  if (spec.value_format === "percent") {
    return `${Math.round(value * 100)}%`;
  }
  const formatted = value.toLocaleString();
  return spec.value_suffix ? `${formatted} ${spec.value_suffix}` : formatted;
}

export function BriefCharts({
  charts,
  layout = "default",
}: {
  charts: ChartSpec[];
  layout?: "default" | "pane";
}) {
  const reduceMotion = useReducedMotion() ?? false;
  const animate = !reduceMotion;

  if (charts.length === 0) {
    return null;
  }

  return (
    <section className={layout === "pane" ? "px-5 py-5" : "px-6 py-6 sm:px-8 sm:py-7"}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-muted">
          Charts
        </h2>
        <p className="font-mono text-[11px] text-ink-muted">
          Selected for this brief · scored by Laya
        </p>
      </div>

      <div
        className={`mt-5 grid gap-4 ${
          layout === "pane" ? "grid-cols-1 xl:grid-cols-2" : "md:grid-cols-2"
        }`}
      >
        {charts.map((chart, index) => (
          <ChartErrorBoundary key={`${chart.kind}-${chart.title}-${index}`}>
            <ChartPanel spec={chart} animate={animate} />
          </ChartErrorBoundary>
        ))}
      </div>
    </section>
  );
}

function ChartPanel({ spec, animate }: { spec: ChartSpec; animate: boolean }) {
  const summary = spec.series
    .flatMap((series) =>
      series.points.map(
        (point) => `${point.label} ${formatValue(point.value, spec)}`,
      ),
    )
    .join(", ");

  return (
    <figure className="min-w-0 rounded-lg border border-line bg-surface-raised p-4">
      <figcaption>
        <h3 className="text-[13px] font-medium text-ink-secondary">
          {spec.title}
        </h3>
        {spec.subtitle ? (
          <p className="mt-1 text-[11px] leading-4 text-ink-muted">
            {spec.subtitle}
          </p>
        ) : null}
        {spec.takeaway ? (
          <p className="mt-2 text-[12px] leading-4 text-ink-secondary">
            {spec.takeaway}
          </p>
        ) : null}
      </figcaption>

      <div className="mt-3 min-w-0">
        <ChartRenderer spec={spec} animate={animate} />
      </div>

      <p className="sr-only">
        {spec.title}. {summary}
      </p>
    </figure>
  );
}

function ChartRenderer({ spec, animate }: { spec: ChartSpec; animate: boolean }) {
  if (spec.kind === "pie") {
    return <PieView spec={spec} animate={animate} />;
  }
  if (spec.kind === "line") {
    return <LineView spec={spec} animate={animate} />;
  }
  return <BarView spec={spec} animate={animate} />;
}

function BarView({ spec, animate }: { spec: ChartSpec; animate: boolean }) {
  const series = spec.series;
  const labels = series[0]?.points.map((point) => point.label) ?? [];
  const rows = labels.map((label, index) => {
    const row: Record<string, unknown> = { label };
    series.forEach((entry, seriesIndex) => {
      row[`s${seriesIndex}`] = entry.points[index]?.value ?? 0;
    });
    return row;
  });

  if (rows.length === 0) {
    return <EmptyChart />;
  }

  return (
    <BarChart
      data={rows}
      xDataKey="label"
      animationDuration={animate ? 800 : 0}
      aspectRatio="2.2 / 1"
      margin={{ top: 16, right: 12, bottom: 30, left: 12 }}
      barGap={0.35}
    >
      <Grid />
      {series.map((entry, index) => (
        <Bar
          key={`${entry.label}-${index}`}
          dataKey={`s${index}`}
          fill={PALETTE[index % PALETTE.length]}
          lineCap={3}
        />
      ))}
      <BarXAxis maxLabels={{ base: 3, sm: 4, md: 6 }} />
      <ChartTooltip
        showCrosshair={false}
        rows={(point) =>
          series.map((entry, index) => ({
            color: PALETTE[index % PALETTE.length],
            label: entry.label,
            value: formatValue(Number(point[`s${index}`]) || 0, spec),
          }))
        }
      />
    </BarChart>
  );
}

function LineView({ spec, animate }: { spec: ChartSpec; animate: boolean }) {
  const series = spec.series[0];
  const points = series?.points ?? [];
  const rows = points.flatMap((point) => {
    if (!point.at) return [];
    const date = new Date(point.at);
    if (Number.isNaN(date.getTime())) return [];
    return [{ date, value: point.value }];
  });

  if (!series || rows.length < 2) {
    return <EmptyChart />;
  }

  return (
    <LineChart
      data={rows}
      xDataKey="date"
      animationDuration={animate ? 900 : 0}
      aspectRatio="2.2 / 1"
      margin={{ top: 16, right: 16, bottom: 30, left: 16 }}
      yScaleDomainMax={spec.value_format === "percent" ? 1 : undefined}
    >
      <Grid horizontal />
      <Line
        dataKey="value"
        stroke="var(--accent)"
        strokeWidth={2.5}
        glow={{ blur: 4, opacity: 0.25 }}
      />
      <XAxis numTicks={4} />
      <ChartTooltip
        rows={(point) => [
          {
            color: "var(--accent)",
            label: series.label,
            value: formatValue(Number(point.value) || 0, spec),
          },
        ]}
      />
    </LineChart>
  );
}

function PieView({ spec, animate }: { spec: ChartSpec; animate: boolean }) {
  const points = spec.series[0]?.points ?? [];
  const data = points.map((point, index) => ({
    label: point.label,
    value: point.value,
    color: PALETTE[index % PALETTE.length],
  }));

  if (data.length === 0) {
    return <EmptyChart />;
  }

  return (
    <div>
      <div className="mx-auto aspect-square w-full max-w-[220px]">
        <PieChart
          data={data}
          innerRadius={54}
          padAngle={0.02}
          cornerRadius={3}
        >
          {data.map((point, index) => (
            <PieSlice
              key={point.label}
              index={index}
              color={point.color}
              animate={animate}
            />
          ))}
        </PieChart>
      </div>

      <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1">
        {data.map((point) => (
          <li
            key={point.label}
            className="flex items-center justify-between gap-2 text-[12px]"
          >
            <span className="flex min-w-0 items-center gap-2">
              <span
                aria-hidden="true"
                className="h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: point.color }}
              />
              <span className="truncate text-ink-muted">{point.label}</span>
            </span>
            <span className="shrink-0 font-mono text-ink-secondary">
              {formatValue(point.value, spec)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function EmptyChart() {
  return <p className="py-6 text-center text-[12px] text-ink-muted">Not enough data.</p>;
}

class ChartErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return (
        <div
          role="alert"
          className="rounded-lg border border-error/30 bg-error-soft p-4 text-[12px] text-error"
        >
          This chart could not be rendered.
        </div>
      );
    }
    return this.props.children;
  }
}
