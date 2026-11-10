"use client";

import { useEffect, useState } from "react";

export type ApiStatus = "checking" | "online" | "offline";

export function useApiStatus(healthUrl: string): ApiStatus {
  const [status, setStatus] = useState<ApiStatus>("checking");

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 3000);
    let active = true;

    async function probe() {
      try {
        const response = await fetch(healthUrl, {
          cache: "no-store",
          signal: controller.signal,
        });
        if (active) {
          setStatus(response.ok ? "online" : "offline");
        }
      } catch {
        if (active) {
          setStatus("offline");
        }
      } finally {
        clearTimeout(timer);
      }
    }

    void probe();

    return () => {
      active = false;
      clearTimeout(timer);
      controller.abort();
    };
  }, [healthUrl]);

  return status;
}
