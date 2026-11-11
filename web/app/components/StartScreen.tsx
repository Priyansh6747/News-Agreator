"use client";

import type { ApiStatus } from "@/lib/useApiStatus";
import { Composer } from "./Composer";
import { Orb } from "./Orb";
import { SuggestionCards } from "./SuggestionCards";
import { TopBar } from "./TopBar";

interface StartScreenProps {
  apiStatus: ApiStatus;
  greeting: string;
  input: string;
  onInput: (value: string) => void;
  onSubmit: (query?: string) => void;
  onStop: () => void;
  streaming: boolean;
}

export function StartScreen({
  apiStatus,
  greeting,
  input,
  onInput,
  onSubmit,
  onStop,
  streaming,
}: StartScreenProps) {
  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-[960px] flex-col px-4 pb-12 sm:px-8 lg:px-10">
      <TopBar apiStatus={apiStatus} />

      <div className="flex flex-1 flex-col items-center pt-[clamp(64px,12vh,128px)]">
        <div className="enter">
          <Orb size="lg" />
        </div>

        <h1
          className="enter mt-6 text-center text-[26px] leading-[1.22] tracking-[-0.02em] text-ink-strong sm:text-[34px] sm:leading-[1.18] sm:tracking-[-0.025em]"
          style={{ animationDelay: "60ms" }}
        >
          {greeting}
          <br />
          What should I brief you on?
        </h1>

        <div
          className="enter mt-10 w-full"
          style={{ animationDelay: "120ms" }}
        >
          <Composer
            value={input}
            onChange={onInput}
            onSubmit={() => onSubmit()}
            onStop={onStop}
            streaming={streaming}
            autoFocus
          />
        </div>

        <div
          className="enter mt-7 w-full"
          style={{ animationDelay: "180ms" }}
        >
          <SuggestionCards onPick={onSubmit} />
        </div>
      </div>

      <p className="mt-auto pt-10 text-center text-[11px] leading-4 text-ink-muted">
        Free-source news briefs. Coverage is reported, not hidden.
      </p>
    </main>
  );
}
