"use client";

import { useSyncExternalStore, useState } from "react";

import { useApiStatus } from "@/lib/useApiStatus";
import { useChatStream } from "@/lib/useChatStream";
import { ChatShell } from "./components/ChatShell";
import { StartScreen } from "./components/StartScreen";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8012";
const CHAT_ENDPOINT = `${API_BASE}/api/v1/chat/stream`;
const CONVERSATIONS_ENDPOINT = `${API_BASE}/api/v1/conversations`;
const HEALTH_ENDPOINT = `${API_BASE}/health`;

export default function Home() {
  const [input, setInput] = useState("");
  const mounted = useMounted();
  const apiStatus = useApiStatus(HEALTH_ENDPOINT);
  const { state, stages, elapsedMs, send, stop, reset, selectBrief } =
    useChatStream({
      endpoint: CHAT_ENDPOINT,
      conversationsEndpoint: CONVERSATIONS_ENDPOINT,
    });

  const streaming = state.phase === "executing";
  const greeting = mounted ? timeGreeting() : "Good evening.";

  function submit(explicit?: string) {
    const message = (explicit ?? input).trim();
    if (!message || streaming) return;
    setInput("");
    void send(message);
  }

  if (state.phase === "idle") {
    return (
      <StartScreen
        apiStatus={apiStatus}
        greeting={greeting}
        input={input}
        onInput={setInput}
        onSubmit={submit}
        onStop={stop}
        streaming={streaming}
      />
    );
  }

  return (
    <ChatShell
      state={state}
      apiStatus={apiStatus}
      input={input}
      onInput={setInput}
      onSend={() => submit()}
      onStop={stop}
      onReset={reset}
      onSelectBrief={selectBrief}
      stages={stages}
      elapsedMs={elapsedMs}
      streaming={streaming}
    />
  );
}

function timeGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning.";
  if (hour < 18) return "Good afternoon.";
  return "Good evening.";
}

const subscribeToMount = () => () => {};

function useMounted(): boolean {
  return useSyncExternalStore(
    subscribeToMount,
    () => true,
    () => false,
  );
}
