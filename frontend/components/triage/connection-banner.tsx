import { cx } from "@/utils/cx";
import { Button } from "@/components/base/buttons/button";

/**
 * TriageAssist UI Kit — ConnectionBanner (Figma frame 3:591)
 *
 * Rebuilt on the real app's actual network presentation. The product screens
 * (QueueBoard.tsx, AdministratorDashboard.tsx, IntakeScreen.tsx) do NOT show a
 * persistent "connection banner" with offline-capability claims. They:
 *   - Poll every 5 seconds and on window focus (usePolling hook)
 *   - Show inline errors via `noticeClass.error` when a load fails
 *   - Have a "Refresh now" button (secondary) for manual retries
 *
 * The Figma sheet invented states like "Offline · Working from the local
 * cache" and "Pending · 3 records saved locally will upload when the
 * connection returns" — none of that exists in the app. This component now
 * presents only honest states:
 *   - `synced` (the default, no banner needed)
 *   - `syncing` (a background load is in flight — spinner + "Syncing…")
 *   - `error` (the last load failed — inline error text + "Retry" button)
 *
 * The caller decides when to mount this; it is not a permanent header fixture.
 * When the load succeeds, the banner unmounts.
 */
export type TriageConnectionState = "synced" | "syncing" | "error";

const TITLES: Record<TriageConnectionState, string> = {
  synced: "Synced",
  syncing: "Syncing…",
  error: "Couldn't load data",
};

const TONE = {
  synced: "bg-status-lime-background text-status-lime-text",
  syncing: "bg-status-blue-background text-status-blue-text",
  error: "bg-status-rose-background text-status-rose-text",
} as const;

export interface TriageConnectionBannerProps {
  state: TriageConnectionState;
  /** The error message when state === "error". Ignored otherwise. */
  message?: string;
  /** Called when the user presses Retry (only shown in error state). */
  onRetry?: () => void;
  className?: string;
}

export function TriageConnectionBanner({
  state,
  message,
  onRetry,
  className,
}: TriageConnectionBannerProps) {
  if (state === "synced") {
    return null;
  }

  return (
    <section
      aria-live="polite"
      className={cx(
        "flex flex-col gap-2 rounded-3xl border border-border-button-default p-4",
        TONE[state],
        className,
      )}
      role="status"
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-body-medium font-semibold">{TITLES[state]}</p>
        {state === "syncing" ? (
          <span
            className="flex h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
            aria-hidden="true"
          />
        ) : null}
      </div>

      {state === "error" && message ? (
        <p className="text-body-medium">{message}</p>
      ) : state === "syncing" ? (
        <p className="text-body-medium">Checking for updates…</p>
      ) : null}

      {state === "error" && onRetry ? (
        <Button variant="secondary" className="min-h-11" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </section>
  );
}