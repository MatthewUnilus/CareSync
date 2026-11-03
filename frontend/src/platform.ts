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
 * The native shell is the bedside client, so it lands on intake. The web
 * dashboard keeps its Queue-first default. Both surfaces remain available in
 * both forms through the existing view switch.
 */
export type ClinicalView = "queue" | "intake";

export function defaultClinicalView(platform: ClientPlatform): ClinicalView {
  return isNativePlatform(platform) ? "intake" : "queue";
}
