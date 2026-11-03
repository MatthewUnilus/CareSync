import { useCallback, useEffect, useState } from "react";

import { api } from "./api";
import type { CurrentUser } from "./api";
import AdministratorDashboard from "./AdministratorDashboard";
import ClinicalWorkspace from "./ClinicalWorkspace";
import LoginScreen from "./LoginScreen";
import Shell from "./Shell";
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
      <main className="centered">
        <p className="muted">Checking session…</p>
      </main>
    );
  }

  if (!user) {
    return <LoginScreen onLogin={setUser} />;
  }

  if (pathname !== homePathForRole(user.role)) {
    return (
      <main className="centered">
        <p className="muted">Opening your workspace…</p>
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
