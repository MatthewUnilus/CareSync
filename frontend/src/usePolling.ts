import { useEffect } from "react";

/**
 * Re-read a resource immediately, every `intervalMs`, and when the window
 * regains focus. This is the single polling mechanism behind the app's live
 * views, so a change in the record appears without a manual refresh.
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
