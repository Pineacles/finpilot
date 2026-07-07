"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Runs `callback` immediately and then every `ms`, but only while the tab is
 * visible (document.visibilityState). Pauses cleanly when the tab is hidden
 * — no wasted requests, and no misleadingly-fresh "last updated" timestamps
 * for a tab nobody is looking at — and resumes with an immediate refresh
 * when it regains focus.
 *
 * Returns `live`: true while polling is active, false while paused.
 */
export function useVisibleInterval(callback: () => void | Promise<void>, ms: number): boolean {
  const [live, setLive] = useState(true);
  const savedCallback = useRef(callback);
  savedCallback.current = callback;

  useEffect(() => {
    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const tick = () => {
      if (!cancelled) void savedCallback.current();
    };

    const start = () => {
      if (intervalId) return;
      tick();
      intervalId = setInterval(tick, ms);
    };
    const stop = () => {
      if (intervalId) {
        clearInterval(intervalId);
        intervalId = null;
      }
    };

    const onVisibility = () => {
      const visible = document.visibilityState === "visible";
      setLive(visible);
      if (visible) start();
      else stop();
    };

    if (typeof document !== "undefined" && document.visibilityState === "visible") {
      start();
    } else {
      setLive(false);
    }

    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelled = true;
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms]);

  return live;
}
