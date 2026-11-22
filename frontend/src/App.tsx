import { useCallback, useEffect, useState } from "react";

import { api } from "./api";
import type { CurrentUser } from "./api";
import AdministratorDashboard from "./AdministratorDashboard";
import ClinicalWorkspace from "./ClinicalWorkspace";
import LoginScreen from "./LoginScreen";
import Shell from "./Shell";
import TriageKitGallery from "./TriageKitGallery";
import { homePathForRole, usePathname } from "./routing";

export default function App() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [checking, setChecking] = useState(true);
  const [pathname, replacePath] = usePathname();

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setChecking(false));
  }, []);

  useEffect(() => {
    if (!user) {
      return;
    }
    const home = homePathForRole(user.role);
    if (pathname !== home) {
      replacePath(home);
    }
  }, [user, pathname, replacePath]);

  const handleLogout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  }, []);

  if (checking) {
    return (
      <main className="grid min-h-dvh place-items-center bg-background-full p-6">
        <p className="text-body-regular text-text-secondary">
          Checking session…
        </p>
      </main>
    );
  }

  if (!user) {
    return <LoginScreen onLogin={setUser} />;
  }

  /*
   * The triage-kit gallery shows synthetic example data by design. It sits
   * behind the session check so a signed-out visitor sees the login screen,
   * not a screen that reads as if the product were running.
   */
  if (pathname === "/triage-kit") {
    return (
      <div className="min-h-dvh bg-background-full">
        <div className="mx-auto max-w-6xl px-4 py-6">
          <p className="text-caption-1-medium text-text-secondary">
            Synthetic examples — not live data
          </p>
          <TriageKitGallery />
        </div>
      </div>
    );
  }

  if (pathname !== homePathForRole(user.role)) {
    return (
      <main className="grid min-h-dvh place-items-center bg-background-full p-6">
        <p className="text-body-regular text-text-secondary">
          Opening your workspace…
        </p>
      </main>
    );
  }

  return (
    <Shell user={user} onLogout={handleLogout}>
      {user.role === "clinical" ? (
        <ClinicalWorkspace />
      ) : (
        <AdministratorDashboard />
      )}
    </Shell>
  );
}
