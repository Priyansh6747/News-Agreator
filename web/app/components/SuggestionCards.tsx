interface Suggestion {
  title: string;
  body: string;
  query: string;
}

const SUGGESTIONS: Suggestion[] = [
  {
    title: "Markets",
    body: "Gold, oil, and the indices moving today.",
    query: "gold prices",
  },
  {
    title: "Conflict",
    body: "Front lines, diplomacy, and what changed this week.",
    query: "ukraine war",
  },
  {
    title: "Chips",
    body: "Nvidia, AMD, and the AI hardware race.",
    query: "nvidia vs amd",
  },
];

export function SuggestionCards({
  onPick,
  suggestions = SUGGESTIONS,
}: {
  onPick: (query: string) => void;
  suggestions?: Suggestion[];
}) {
  return (
    <div className="grid gap-4 min-[720px]:grid-cols-3">
      {suggestions.map((suggestion) => (
        <button
          key={suggestion.query}
          type="button"
          onClick={() => onPick(suggestion.query)}
          className="group flex min-h-[96px] flex-col justify-between gap-5 rounded-card border border-line bg-surface p-5 text-left transition-colors duration-200 hover:border-line-strong hover:bg-surface-raised"
        >
          <span>
            <span className="block text-[17px] font-semibold tracking-[-0.01em] text-ink">
              {suggestion.title}
            </span>
            <span className="mt-2 block text-[13px] leading-5 text-ink-muted">
              {suggestion.body}
            </span>
          </span>
          <span className="flex items-center justify-between gap-3 font-mono text-[11px] text-ink-muted">
            {suggestion.query}
            <ArrowRightIcon />
          </span>
        </button>
      ))}
    </div>
  );
}

function ArrowRightIcon() {
  return (
    <svg
      aria-hidden="true"
      width="16"
      height="16"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="opacity-0 transition-opacity duration-200 group-hover:opacity-100 group-focus-visible:opacity-100"
    >
      <path d="M4 10h12" />
      <path d="m11 5 5 5-5 5" />
    </svg>
  );
}
