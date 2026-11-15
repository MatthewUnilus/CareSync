/**
 * Shared BoardUI class vocabulary for this client.
 *
 * Every class here is a semantic token or composite type utility from the
 * BoardUI theme (styles/theme.css, styles/typography.css) — no raw palette
 * classes, no hex, no `dark:` overrides. Centralising them keeps the screens
 * consistent and gives the token audit one place to check.
 */

/**
 * The standard panel: a rounded-3xl card on the page background.
 * `min-w-0` lets the card shrink inside the shell grid so wide children
 * (the report tables) scroll in their own overflow wrapper instead of
 * widening the page on phones.
 */
export const cardClass =
  "flex min-w-0 flex-col gap-5 rounded-3xl border border-border-button-default bg-background-primary-default p-6";

/**
 * Small section label (legend, detail heading, table column head).
 *
 * `text-text-secondary` rather than `-tertiary`: the tertiary step is
 * neutral-400, which measures ~2.6:1 on the white card surface and fails WCAG AA
 * for text this size. Secondary is neutral-500 at ~4.7:1, which passes. The
 * labels are load-bearing here — they are how a reader tells "systolic" from
 * "diastolic" — so they must not be decorative.
 */
export const sectionLabelClass = "text-caption-1-medium text-text-secondary";

/** Muted supporting copy. */
export const mutedTextClass = "text-body-regular text-text-secondary";

/**
 * Instrument figures — waiting times, vital signs, report percentages.
 * Mono, tabular, quiet: the numbers read like a monitor readout.
 */
export const figureClass = "font-mono tabular-nums";

/**
 * Inline status paragraph (kept as plain text with `role="status"` in the
 * callers — the BoardUI Notification card is built for toast stacks, not
 * inline notices). Warning keeps the Unclassified flag's purple family so
 * "needs review" reads as one colour everywhere.
 */
export const noticeClass = {
  success: "text-status-lime-text",
  error: "text-text-error-primary",
  warning: "text-status-purple-text",
} as const;

/** Data tables. Styled primitives, not the React Aria `Table` — see
 * boardui-usage.md: these tables are read-only server figures with
 * `scope="row"` headers and captions, and none of them select, sort or page. */
export const tableWrapClass = "overflow-x-auto";
export const tableClass =
  "w-full border-collapse text-body-regular text-text-primary";
export const tableCaptionClass =
  "pb-2 text-left text-caption-1-regular text-text-secondary";
export const tableHeadCellClass = `border-b border-separator-border px-3 py-2 text-left whitespace-nowrap ${sectionLabelClass}`;
export const tableRowClass =
  "border-b border-separator-border last:border-b-0 hover:bg-background-secondary-default";
export const tableCellClass = "px-3 py-2 align-middle text-body-regular";
