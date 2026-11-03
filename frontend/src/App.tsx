import { useCallback, useEffect, useState } from "react";

import { api } from "./api";
import type { CurrentUser } from "./api";
import LoginScreen from "./LoginScreen";
import Shell from "./Shell";

export default function App() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setChecking(false));
  }, []);

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

  return <Shell user={user} onLogout={handleLogout} />;
}
