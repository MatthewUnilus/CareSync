# 16: Mobile client

**What to build:** The same client codebase shipped as a mobile app through a native shell, so intake genuinely happens at the bedside rather than in a phone-width browser tab. The mobile client talks to the same backend API as the dashboard.

**Blocked by:** 03.

**Status:** ready-for-agent

- [ ] The client codebase is packaged through a native shell and runs as an installed app on a mobile device or emulator.
- [ ] The installed app logs in and performs the full intake-to-Queue path against the backend API.
- [ ] The app and the web dashboard remain one codebase; no feature exists in only one of them.
- [ ] The bedside intake surface is the app's primary screen, reachable without navigating through the administrator surface.
- [ ] Session expiry is honoured in the app the same way it is in the browser.
