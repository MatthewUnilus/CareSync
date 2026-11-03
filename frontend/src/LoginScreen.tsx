import { useState } from "react";
import type { FormEvent } from "react";

import { api, ApiError } from "./api";
import type { CurrentUser } from "./api";
import { isNativePlatform } from "./platform";
import { detectPlatform } from "./runtime";
import {
  defaultApiBaseUrl,
  normaliseApiBaseUrl,
  readApiBaseUrlOverride,
  saveApiBaseUrlOverride,
  clearApiBaseUrlOverride,
} from "./runtimeConfig";

interface LoginScreenProps {
  onLogin: (user: CurrentUser) => void;
}

export default function LoginScreen({ onLogin }: LoginScreenProps) {
  const platform = detectPlatform();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [serverUrl, setServerUrl] = useState(
    () => readApiBaseUrlOverride() ?? "",
  );
  const [serverNotice, setServerNotice] = useState<string | null>(null);

  function handleSaveServer(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!serverUrl.trim()) {
      clearApiBaseUrlOverride();
      setServerNotice(`Cleared. Using ${defaultApiBaseUrl(platform)}.`);
      return;
    }
    if (!normaliseApiBaseUrl(serverUrl)) {
      setServerNotice("Enter an http(s) address, e.g. http://localhost:8000.");
      return;
    }
    saveApiBaseUrlOverride(serverUrl);
    setServerNotice("Saved. The next request uses this address.");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      const user = await api.login(email.trim(), password);
      onLogin(user);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Unable to reach the server.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="centered">
      <section className="login-card">
        <div className="brand-block">
          <span className="brand-mark" aria-hidden="true">
            TA
          </span>
          <div>
            <h1>TriageAssist</h1>
            <p className="muted">Clinical decision support</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="stack">
          <label>
            Email
            <input
              type="email"
              name="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>

          <label>
            Password
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>

          {error ? (
            <p className="notice notice-error" role="alert">
              {error}
            </p>
          ) : null}

          <button type="submit" disabled={pending}>
            {pending ? "Signing in…" : "Sign in"}
          </button>
        </form>

        {isNativePlatform(platform) ? (
          <details className="server-settings">
            <summary>Server</summary>
            <form onSubmit={handleSaveServer} className="stack">
              <label>
                API base URL
                <input
                  type="url"
                  inputMode="url"
                  autoComplete="off"
                  placeholder={defaultApiBaseUrl(platform)}
                  value={serverUrl}
                  onChange={(event) => setServerUrl(event.target.value)}
                />
              </label>
              <p className="muted">
                The installed app calls the API cross-origin. Leave this empty
                for {defaultApiBaseUrl(platform)}, or enter the address the
                device or emulator can reach.
              </p>
              <button type="submit" className="secondary">
                Save server
              </button>
              {serverNotice ? (
                <p className="notice notice-success" role="status">
                  {serverNotice}
                </p>
              ) : null}
            </form>
          </details>
        ) : null}
      </section>
    </main>
  );
}
