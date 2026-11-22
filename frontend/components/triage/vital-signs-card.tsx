import { cx } from "@/utils/cx";

/**
 * TriageAssist UI Kit — VitalSignsCard (Figma frame 3:467)
 *
 * Rebuilt on BoardUI vocabulary and the real app's vital-signs presentation
 * (QueueBoard.tsx `Vital`): labels ride the shared section-label treatment
 * (`text-caption-1-medium text-text-secondary`), values are instrument
 * figures (`font-mono tabular-nums`), and a value that needs attention is
 * rose (`text-status-rose-text`) — the same colour the queue marks an
 * abnormal reading with.
 *
 * Incomplete state: the card border takes the app's flagged-vitals treatment
 * (`border-status-rose-text/30`) and missing values render "Not recorded" in
 * rose, so the eye lands on exactly the measurements the recommendation
 * could not use.
 */
export interface TriageVitalRow {
  /** e.g. "Heart rate". */
  label: string;
  /** e.g. "88 bpm" — pass null when the measurement is missing. */
  value: string | null;
}

export interface TriageVitalSignsCardProps {
  title?: string;
  rows: TriageVitalRow[];
  /** e.g. "Recorded 09:42 · A. Chen"; omit when incomplete. */
  recorded?: string;
  className?: string;
}

const INCOMPLETE_FOOTER =
  "Incomplete information · Record missing measurements.";

export function TriageVitalSignsCard({
  title = "Vital signs",
  rows,
  recorded,
  className,
}: TriageVitalSignsCardProps) {
  const incomplete = rows.some((row) => row.value === null);

  return (
    <section
      className={cx(
        "flex flex-col gap-3 rounded-3xl border bg-background-primary-default p-6",
        incomplete
          ? "border-status-rose-text/30"
          : "border-border-button-default",
        className,
      )}
    >
      <h3 className="text-title-3-medium text-text-primary">{title}</h3>
      <dl className="flex flex-col gap-2">
        {rows.map((row) => (
          <div
            key={row.label}
            className="flex items-baseline justify-between gap-3"
          >
            <dt className="text-caption-1-medium text-text-secondary">
              {row.label}
            </dt>
            <dd
              className={cx(
                "font-mono tabular-nums text-body-medium",
                row.value === null
                  ? "text-status-rose-text"
                  : "text-text-primary",
              )}
            >
              {row.value === null ? "Not recorded" : row.value}
            </dd>
          </div>
        ))}
      </dl>
      <p
        className={cx(
          "text-caption-1-regular",
          incomplete ? "text-status-rose-text" : "text-text-secondary",
        )}
      >
        {incomplete ? INCOMPLETE_FOOTER : recorded}
      </p>
    </section>
  );
}