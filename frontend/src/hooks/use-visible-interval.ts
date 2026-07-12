"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";

// document.visibilityState is an external, mutable source outside React,
// tracked via useSyncExternalStore (subscribing to the `visibilitychange`
// event) rather than useState + an effect that calls setState synchronously
// (react-hooks/set-state-in-effect). This also means `live` is correct on
// the very first client render, with no hydration-mismatch risk: SSR/first
// paint assumes visible (matching this hook's old default), and the real
// value is swapped in as soon as the browser can report it.
function subscribeVisibility(callback: () => void) {
  document.addEventListener("visibilitychange", callback);
  return () => document.removeEventListener("visibilitychange", callback);
}
function getVisibilitySnapshot() {
  return document.visibilityState === "visible";
}
function getVisibilityServerSnapshot() {
  return true;
}

/**
 * Runs `callback` immediately and then every `ms`, but only while the tab is
 * visible (document.visibilityState). Pauses cleanly when the tab is hidden,
 * with no wasted requests and no misleadingly-fresh "last updated" timestamps
 * for a tab nobody is looking at, and resumes with an immediate refresh
 * when it regains focus.
 *
 * Returns `live`: true while polling is active, false while paused.
 */
export function useVisibleInterval(callback: () => void | Promise<void>, ms: number): boolean {
  const live = useSyncExternalStore(subscribeVisibility, getVisibilitySnapshot, getVisibilityServerSnapshot);
  const savedCallback = useRef(callback);

  // Keep the ref pointing at the latest callback. Refs must not be written
  // during render (react-hooks/refs), so this sync happens in its own
  // effect (no deps array, runs after every render) rather than inline.
  useEffect(() => {
    savedCallback.current = callback;
  });

  useEffect(() => {
    if (!live) return;
    let cancelled = false;
    const tick = () => {
      if (!cancelled) void savedCallback.current();
    };
    tick();
    const intervalId = setInterval(tick, ms);
    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [live, ms]);

  return live;
}
