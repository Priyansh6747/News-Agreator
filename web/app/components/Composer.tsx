"use client";

import { useEffect, useRef } from "react";
import type { FormEvent, KeyboardEvent } from "react";

interface ComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  streaming: boolean;
  hasError?: boolean;
  placeholder?: string;
  id?: string;
  compact?: boolean;
  submitLabel?: string;
  stopLabel?: string;
  maxLength?: number;
  minLength?: number;
  autoFocus?: boolean;
}

export function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  streaming,
  hasError = false,
  placeholder = "Ask about a story, market, or event...",
  id = "brief-query",
  compact = false,
  submitLabel = "Generate brief",
  stopLabel = "Stop the brief",
  maxLength = 300,
  minLength = 2,
  autoFocus = false,
}: ComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const hintId = `${id}-hint`;

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, compact ? 120 : 160)}px`;
  }, [value, compact]);

  useEffect(() => {
    if (autoFocus) textareaRef.current?.focus();
  }, [autoFocus]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!streaming) onSubmit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      if (streaming) return;
      if (value.trim().length >= minLength) {
        onSubmit();
      } else {
        textareaRef.current?.reportValidity();
      }
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className={`group rounded-composer border bg-surface transition-colors duration-150 focus-within:border-[var(--border-focus)] focus-within:shadow-[var(--focus-ring)] ${
        compact ? "px-4 py-3" : "px-5 py-5 sm:px-6"
      } ${hasError && !streaming ? "border-error" : "border-line"}`}
    >
      <label className="sr-only" htmlFor={id}>
        Query
      </label>
      <textarea
        ref={textareaRef}
        id={id}
        name="query"
        required
        minLength={minLength}
        maxLength={maxLength}
        rows={1}
        value={value}
        readOnly={streaming}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        aria-describedby={hintId}
        className={`w-full resize-none overflow-y-auto bg-transparent leading-6 text-ink outline-none placeholder:text-placeholder ${
          compact
            ? "min-h-[44px] max-h-[120px] text-[15px]"
            : "min-h-[64px] max-h-[160px] text-[17px]"
        }`}
      />

      <div
        className={`flex items-end justify-between gap-4 ${compact ? "mt-3" : "mt-6"}`}
      >
        {compact ? (
          <span id={hintId} className="sr-only">
            Enter to send. Shift + Enter for a new line.
          </span>
        ) : (
          <p id={hintId} className="text-[11px] leading-4 text-ink-muted">
            Enter to generate
            <span className="hidden sm:inline">
              {" "}
              · Shift + Enter for a new line
            </span>
          </p>
        )}

        {streaming ? (
          <button
            type="button"
            onClick={onStop}
            aria-label={stopLabel}
            className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-line-strong bg-surface-raised text-ink transition-colors duration-150 hover:bg-surface-hover active:scale-[0.97]"
          >
            <StopIcon />
          </button>
        ) : (
          <button
            type="submit"
            aria-label={submitLabel}
            className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-line-strong bg-surface-raised text-ink transition-colors duration-150 hover:bg-surface-hover active:scale-[0.97]"
          >
            <ArrowUpIcon />
          </button>
        )}
      </div>
    </form>
  );
}

function ArrowUpIcon() {
  return (
    <svg
      aria-hidden="true"
      width="18"
      height="18"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M10 15V5" />
      <path d="m5.5 9.5 4.5-4.5 4.5 4.5" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg aria-hidden="true" width="18" height="18" viewBox="0 0 20 20">
      <rect x="6.5" y="6.5" width="7" height="7" rx="1.2" fill="currentColor" />
    </svg>
  );
}
