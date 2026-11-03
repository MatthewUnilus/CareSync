import { useState } from "react";
import type { FormEvent } from "react";

import { api, ApiError } from "./api";
import type { CurrentUser, Role } from "./api";
import IntakeScreen from "./IntakeScreen";

interface ShellProps {
  user: CurrentUser;
  onLogout: () => Promise<void>;
}

interface Notice {
  kind: "success" | "error";
  text: string;
}

function roleLabel(role: Role): string {
  return role === "clinical" ? "Clinical" : "Administrator";
}

export default function Shell({ user, onLogout }: ShellProps) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordNotice, setPasswordNotice] = useState<Notice | null>(null);
  const [changingPassword, setChangingPassword] = useState(false);
  const [accessNotice, setAccessNotice] = useState<Notice | null>(null);

  async function handleChangePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordNotice(null);
    setChangingPassword(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setPasswordNotice({
        kind: "success",
        text: "Password changed. Use the new password next time you sign in.",
      });
    } catch (caught) {
      setPasswordNotice({
        kind: "error",
        text:
          caught instanceof ApiError
            ? caught.message
            : "Unable to reach the server.",
      });
    } finally {
      setChangingPassword(false);
    }
  }

  async function checkAccess(scope: Role) {
    setAccessNotice(null);
    try {
      const result = await api.access(scope);
      setAccessNotice({ kind: "success", text: result.message });
    } catch (caught) {
      setAccessNotice({
        kind: "error",
        text:
          caught instanceof ApiError
            ? `Refused (${caught.status}): ${caught.message}`
            : "Unable to reach the server.",
      });
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <span className="brand-mark" aria-hidden="true">
            TA
          </span>
          <div>
            <strong>TriageAssist</strong>
            <p className="muted">Clinical decision support</p>
          </div>
        </div>

        <div className="identity">
          <span className={`role-badge role-${user.role}`}>
            {roleLabel(user.role)}
          </span>
          <span className="identity-name">{user.display_name}</span>
          <button type="button" className="link-button" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </header>

      <main className="shell-main">
        {user.role === "clinical" ? (
          <IntakeScreen />
        ) : (
          <>
            <section className="card">
              <h2>Signed in</h2>
              <p className="lead">
                You hold the <strong>{roleLabel(user.role)}</strong> role.
              </p>
              <dl className="facts">
                <div>
                  <dt>Email</dt>
                  <dd>{user.email}</dd>
                </div>
                <div>
                  <dt>Role</dt>
                  <dd>{roleLabel(user.role)}</dd>
                </div>
              </dl>
              <p className="muted">Reports arrive with later tickets.</p>
            </section>

            <section className="card">
              <h2>Role enforcement</h2>
              <p className="muted">
                The API decides access, not this screen. Both buttons are
                available to both roles; one of them will be refused.
              </p>
              <div className="row">
                <button
                  type="button"
                  className="secondary"
                  onClick={() => checkAccess("clinical")}
                >
                  Call Clinical endpoint
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => checkAccess("administrator")}
                >
                  Call Administrator endpoint
                </button>
              </div>
              {accessNotice ? (
                <p
                  className={`notice notice-${accessNotice.kind}`}
                  role="status"
                >
                  {accessNotice.text}
                </p>
              ) : null}
            </section>
          </>
        )}

        <section className="card">
          <h2>Change password</h2>
          <form onSubmit={handleChangePassword} className="stack">
            <label>
              Current password
              <input
                type="password"
                autoComplete="current-password"
                required
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
              />
            </label>
            <label>
              New password
              <input
                type="password"
                autoComplete="new-password"
                minLength={8}
                required
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
              />
            </label>
            <button type="submit" disabled={changingPassword}>
              {changingPassword ? "Changing…" : "Change password"}
            </button>
          </form>
          {passwordNotice ? (
            <p
              className={`notice notice-${passwordNotice.kind}`}
              role="status"
            >
              {passwordNotice.text}
            </p>
          ) : null}
        </section>
      </main>
    </div>
  );
}
