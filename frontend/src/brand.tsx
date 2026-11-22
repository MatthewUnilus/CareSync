/**
 * The flat brand mark: a quiet, neutral glyph — a solid graphite tile with a
 * knocked-out centre.
 *
 * It is deliberately not the urgency palette. Rose, yellow and lime are data
 * colour (what a level *is*), so they belong in the record and never in the
 * chrome; the mark stays graphite on purpose. Everything rides BoardUI
 * semantic tokens, so it follows light and dark mode without a `dark:`
 * override.
 */
export function LogoMark() {
  return (
    <span
      aria-hidden="true"
      className="grid size-6 shrink-0 place-items-center rounded-lg bg-foreground-icon-primary"
    >
      <span className="size-2 rounded-full bg-foreground-full" />
    </span>
  );
}
