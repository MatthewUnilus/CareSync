/**
 * The flat brand mark: three triage bands, High over Medium over Low — the
 * tag a triage nurse pins to the chart. No tile, no gradient; this is the
 * one place urgency colour appears in the chrome.
 */
export function LogoMark() {
  return (
    <span aria-hidden="true" className="flex flex-col gap-0.5">
      <span className="h-1 w-5 rounded-full bg-status-rose-text" />
      <span className="h-1 w-5 rounded-full bg-status-yellow-text" />
      <span className="h-1 w-5 rounded-full bg-status-lime-text" />
    </span>
  );
}
