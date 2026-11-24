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
 * The clinical workspace starts with the ward's current work. Registration and
 * record lookup remain one clear choice away, but neither should displace the
 * patients a nurse is already caring for when the shared device is opened.
 */
export type ClinicalView = "board";

export function defaultClinicalView(_platform: ClientPlatform): ClinicalView {
  return "board";
}
