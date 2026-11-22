export type ClientPlatform = "web" | "android" | "ios";

/**
 * Map Capacitor's platform string onto the three targets this client knows
 * about. Anything that is not a native platform is treated as the web build,
 * which keeps `npm run dev` and `npm run build:web` on relative URLs.
 */
export function readPlatform(capacitorPlatform: string): ClientPlatform {
  return capacitorPlatform === "android" || capacitorPlatform === "ios"
    ? capacitorPlatform
    : "web";
}

export function isNativePlatform(platform: ClientPlatform): boolean {
  return platform !== "web";
}

/**
 * The view the clinical workspace opens on. Intake is the entry point on every
 * surface: registration is the first thing a nurse does whether they hold the
 * bedside tablet or a browser, and history is one tap away on the view switch.
 * The parameter is kept so callers still pass the detected platform, but it no
 * longer selects the view.
 */
export type ClinicalView = "intake";

export function defaultClinicalView(_platform: ClientPlatform): ClinicalView {
  return "intake";
}
