import type { CapacitorConfig } from "@capacitor/cli";

/*
 * The native shell wraps the same Vite build that `npm run build:web` produces.
 * It does not contain a second UI: `webDir` points at the existing client's
 * output, so every screen, request and behaviour is shared with the dashboard.
 *
 * Dev API access: the app is served from the local WebView origin, which is a
 * different origin from the API. `androidScheme: "http"` keeps that origin as
 * `http://localhost`, i.e. the same site as an API reached at
 * `http://localhost:8000` through `adb reverse`. A scheme mismatch (https app
 * calling an http API) would make the session cookie cross-site, and a browser
 * will not send a `SameSite=Lax` cookie on a cross-site fetch. See README
 * "Mobile client".
 */
const config: CapacitorConfig = {
  appId: "com.caresync.app",
  appName: "CareSync",
  webDir: "frontend/dist",
  server: {
    // Capacitor 8 no longer applies `server.cleartext` on Android, so the
    // platform projects carry the local-network allowances themselves:
    // android/app/src/main/AndroidManifest.xml (usesCleartextTraffic) and
    // ios/App/App/Info.plist (NSAllowsLocalNetworking).
    androidScheme: "http",
  },
};

export default config;
