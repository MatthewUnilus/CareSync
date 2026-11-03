import { useEffect } from "react";

/**
 * Re-read a resource immediately, every `intervalMs`, and when the window
 * regains focus. This is the single polling mechanism used by both the
 * Clinical Queue board and the Administrator dashboard, so neither needs a
 * manual refresh to show a changed Final Decision or a Departure.
 */
export function usePolling(
  load: () => void | Promise<void>,
  intervalMs: number,
): void {
  useEffect(() => {
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, intervalMs);
    const onFocus = () => {
      void load();
    };
    window.addEventListener("focus", onFocus);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, [load, intervalMs]);
}
