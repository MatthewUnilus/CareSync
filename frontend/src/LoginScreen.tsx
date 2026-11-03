import { useState } from "react";
import type { FormEvent } from "react";

import { api, ApiError } from "./api";
import type { CurrentUser } from "./api";

interface LoginScreenProps {
  onLogin: (user: CurrentUser) => void;
}

export default function LoginScreen({ onLogin }: LoginScreenProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

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
      </section>
    </main>
  );
}
