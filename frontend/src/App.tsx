import { useCallback, useEffect, useState } from "react";

import { api, ApiError, SESSION_LOCKED_EVENT } from "./api";
import type { CurrentUser } from "./api";
import AdministratorDashboard from "./AdministratorDashboard";
import ClinicalWorkspace from "./ClinicalWorkspace";
import LockScreen from "./LockScreen";
import LoginScreen from "./LoginScreen";
import Shell from "./Shell";
import { homePathForRole, usePathname } from "./routing";

export default function App() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [locked, setLocked] = useState(false);
  const [checking, setChecking] = useState(true);
  const [pathname, replacePath] = usePathname();

  useEffect(() => {
    api
      .me()
      .then((current) => {
        setUser(current);
        setLocked(false);
      })
      .catch((caught) => {
        /* A 423 means the session survives behind the lock, so show the lock
         * rather than the sign-in screen. Every other failure is signed out. */
        setLocked(caught instanceof ApiError && caught.status === 423);
        setUser(null);
      })
      .finally(() => setChecking(false));
  }, []);

  /*
   * Any request can be refused with 423 once the inactivity window lapses,
   * including the background polls the workspaces run. Listening for the
   * announcement covers an unattended tablet even while nobody is clicking.
   */
  useEffect(() => {
    const onLocked = () => setLocked(true);
    window.addEventListener(SESSION_LOCKED_EVENT, onLocked);
    return () => window.removeEventListener(SESSION_LOCKED_EVENT, onLocked);
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
      setLocked(false);
    }
  }, []);

  const handleLock = useCallback(async () => {
    try {
      await api.lock();
    } finally {
      setLocked(true);
    }
  }, []);

  const handleUnlock = useCallback((current: CurrentUser) => {
    setUser(current);
    setLocked(false);
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

  if (locked) {
    return <LockScreen onUnlock={handleUnlock} onSwitchUser={handleLogout} />;
  }

  if (!user) {
    return <LoginScreen onLogin={setUser} />;
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
    <Shell user={user} onLogout={handleLogout} onLock={handleLock}>
      {user.role === "clinical" ? (
        <ClinicalWorkspace />
      ) : (
        <AdministratorDashboard />
      )}
    </Shell>
  );
}
